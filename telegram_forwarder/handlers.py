"""
Message handler module for processing and forwarding messages.
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from telethon import TelegramClient, events
from telethon.tl.types import Message, Channel, Chat
from telethon.errors import FloodWaitError, ChatWriteForbiddenError

from .config import AppConfig

logger = logging.getLogger(__name__)


class MessageFilter:
    """Filter messages based on configured criteria."""
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.filters = config.filters
    
    def should_forward(self, message: Message) -> bool:
        """
        Determine if a message should be forwarded based on filter rules.
        
        Args:
            message: The Telegram message to evaluate
            
        Returns:
            True if the message passes all filters, False otherwise
        """
        text = message.text or message.caption or ""
        
        # Check if it's a media-only message
        if not text and message.media:
            return self.filters.include_media_only
        
        # Check minimum length
        if len(text) < self.filters.min_message_length:
            logger.debug(f"Message too short: {len(text)} < {self.filters.min_message_length}")
            return False
        
        # Check include keywords (if specified, at least one must match)
        if self.filters.include_keywords:
            text_lower = text.lower()
            if not any(kw.lower() in text_lower for kw in self.filters.include_keywords):
                logger.debug("Message doesn't contain required keywords")
                return False
        
        # Check exclude keywords (none should match)
        if self.filters.exclude_keywords:
            text_lower = text.lower()
            if any(kw.lower() in text_lower for kw in self.filters.exclude_keywords):
                logger.debug("Message contains excluded keywords")
                return False
        
        return True


class RateLimiter:
    """Rate limiter to avoid flood bans."""
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.rate_config = config.rate_limit
        self.message_times: list = []
        self._lock = asyncio.Lock()
    
    async def wait_if_needed(self) -> None:
        """Wait if we're exceeding the rate limit."""
        async with self._lock:
            now = datetime.now()
            
            # Remove messages older than 1 minute
            cutoff = now - timedelta(minutes=1)
            self.message_times = [t for t in self.message_times if t > cutoff]
            
            # Check if we've hit the limit
            if len(self.message_times) >= self.rate_config.max_messages_per_minute:
                # Wait until the oldest message falls out of the window
                wait_time = (self.message_times[0] - cutoff).total_seconds()
                if wait_time > 0:
                    logger.info(f"Rate limit reached, waiting {wait_time:.1f}s")
                    await asyncio.sleep(wait_time)
            
            # Apply standard delay
            await asyncio.sleep(self.rate_config.message_delay)
            
            # Record this message
            self.message_times.append(datetime.now())
    
    async def handle_flood_wait(self, error: FloodWaitError) -> None:
        """Handle a FloodWaitError from Telegram."""
        wait_time = error.seconds * self.rate_config.flood_wait_multiplier
        logger.warning(f"Flood wait error! Waiting {wait_time:.0f}s (server requested {error.seconds}s)")
        await asyncio.sleep(wait_time)


class MessageHandler:
    """
    Handles message forwarding from source channels to destination.
    """
    
    def __init__(self, client: TelegramClient, config: AppConfig):
        self.client = client
        self.config = config
        self.message_filter = MessageFilter(config)
        self.rate_limiter = RateLimiter(config)
        
        # Cache for resolved channel entities
        self._channel_cache: Dict[str, Any] = {}
        
        # Statistics
        self.stats = {
            "messages_received": 0,
            "messages_forwarded": 0,
            "messages_filtered": 0,
            "errors": 0,
        }
    
    async def resolve_channel(self, channel_id: str) -> Any:
        """
        Resolve a channel identifier to a Telegram entity.
        
        Args:
            channel_id: Channel username, ID, or link
            
        Returns:
            The resolved Telegram entity
        """
        if channel_id in self._channel_cache:
            return self._channel_cache[channel_id]
        
        try:
            # Handle different input formats
            if channel_id.startswith("https://t.me/"):
                # Extract username from link
                channel_id = channel_id.replace("https://t.me/", "")
                if channel_id.startswith("+"):
                    # Private invite link, join first if needed
                    channel_id = channel_id  # Keep as-is for now
            
            entity = await self.client.get_entity(channel_id)
            self._channel_cache[channel_id] = entity
            logger.info(f"Resolved channel: {channel_id} -> {getattr(entity, 'title', entity)}")
            return entity
        except Exception as e:
            logger.error(f"Failed to resolve channel {channel_id}: {e}")
            raise
    
    async def forward_message(self, message: Message) -> bool:
        """
        Forward or copy a message to the destination channel.
        
        Args:
            message: The message to forward
            
        Returns:
            True if successful, False otherwise
        """
        try:
            dest = await self.resolve_channel(self.config.channels.destination_channel)
            
            if self.config.channels.forward_mode:
                # Forward mode: preserves original sender
                await self.client.forward_messages(dest, message)
                logger.info(f"Forwarded message {message.id} to {dest.title}")
            else:
                # Copy mode: sends as your account
                if message.media:
                    await self.client.send_file(
                        dest,
                        message.media,
                        caption=message.text or message.caption,
                    )
                else:
                    await self.client.send_message(dest, message.text)
                logger.info(f"Copied message {message.id} to {dest.title}")
            
            return True
            
        except FloodWaitError as e:
            await self.rate_limiter.handle_flood_wait(e)
            # Retry after waiting
            return await self.forward_message(message)
        
        except ChatWriteForbiddenError:
            logger.error(f"Cannot write to destination channel - check permissions!")
            self.stats["errors"] += 1
            return False
        
        except Exception as e:
            logger.error(f"Error forwarding message {message.id}: {e}")
            self.stats["errors"] += 1
            return False
    
    async def handle_new_message(self, event: events.NewMessage.Event) -> None:
        """
        Event handler for new messages in source channels.
        
        Args:
            event: The new message event
        """
        message = event.message
        self.stats["messages_received"] += 1
        
        # Log the source
        chat = await event.get_chat()
        chat_title = getattr(chat, 'title', str(chat.id))
        logger.debug(f"New message from {chat_title}: {message.id}")
        
        # Apply filters
        if not self.message_filter.should_forward(message):
            self.stats["messages_filtered"] += 1
            logger.debug(f"Message {message.id} filtered out")
            return
        
        # Rate limiting
        await self.rate_limiter.wait_if_needed()
        
        # Forward the message
        if await self.forward_message(message):
            self.stats["messages_forwarded"] += 1
    
    async def setup_handlers(self) -> None:
        """Set up event handlers for all source channels."""
        source_entities = []
        
        for channel_id in self.config.channels.source_channels:
            try:
                entity = await self.resolve_channel(channel_id)
                source_entities.append(entity)
            except Exception as e:
                logger.error(f"Failed to set up handler for {channel_id}: {e}")
        
        if not source_entities:
            raise ValueError("No valid source channels found!")
        
        # Register the event handler
        @self.client.on(events.NewMessage(chats=source_entities))
        async def handler(event):
            await self.handle_new_message(event)
        
        logger.info(f"Set up handlers for {len(source_entities)} source channel(s)")
        
        # Also resolve destination to verify access
        dest = await self.resolve_channel(self.config.channels.destination_channel)
        logger.info(f"Destination channel verified: {dest.title}")
    
    def get_stats(self) -> Dict[str, int]:
        """Get current statistics."""
        return self.stats.copy()
