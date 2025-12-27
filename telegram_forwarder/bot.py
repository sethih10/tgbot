"""
User Submission Bot - Allows users to submit messages for moderation.

This bot:
1. Accepts messages from users via private chat
2. Screens messages based on configured criteria
3. Forwards approved messages to the destination channel
4. Provides feedback to users about their submission status
"""

import asyncio
import logging
import re
from typing import Optional, List, Dict, Any
from datetime import datetime

from telethon import TelegramClient, events, Button
from telethon.tl.types import Message, User
from telethon.errors import FloodWaitError, ChatWriteForbiddenError

from .config import AppConfig, get_config

logger = logging.getLogger(__name__)


class SubmissionScreener:
    """Screen user submissions based on configured rules."""
    
    # Default rental/apartment related keywords
    DEFAULT_REQUIRED_KEYWORDS = [
        'apartment', 'flat', 'rent', 'renting', 'rental',
        'room', 'studio', 'bedroom', 'sublet', 'lease',
        'housing', 'accommodation', 'vuokra', 'asunto',
        '1bdrm', '2bdrm', '3bdrm', 'квартира', 'комната', 'аренда'
    ]
    
    # Spam/scam indicators
    DEFAULT_BLOCKED_PATTERNS = [
        r'bit\.ly', r'tinyurl', r'click here',
        r'earn money', r'make money fast', r'crypto',
        r'investment opportunity', r'guaranteed returns',
    ]
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.filters = config.filters
        
        # Use config keywords or defaults
        self.required_keywords = (
            self.filters.include_keywords 
            if self.filters.include_keywords 
            else self.DEFAULT_REQUIRED_KEYWORDS
        )
        
        self.blocked_keywords = self.filters.exclude_keywords or []
        self.blocked_patterns = [re.compile(p, re.IGNORECASE) for p in self.DEFAULT_BLOCKED_PATTERNS]
    
    def screen_message(self, text: str) -> Dict[str, Any]:
        """
        Screen a message and return the result.
        
        Args:
            text: The message text to screen
            
        Returns:
            Dict with 'approved', 'reason', and optional 'suggestions'
        """
        if not text or not text.strip():
            return {
                'approved': False,
                'reason': 'empty_message',
                'message': '❌ Your message is empty. Please include details about the rental/apartment.'
            }
        
        text_lower = text.lower()
        
        # Check for blocked patterns (spam/scam)
        for pattern in self.blocked_patterns:
            if pattern.search(text):
                return {
                    'approved': False,
                    'reason': 'spam_detected',
                    'message': '❌ Your message contains suspicious content and cannot be posted.'
                }
        
        # Check for blocked keywords
        for keyword in self.blocked_keywords:
            if keyword.lower() in text_lower:
                return {
                    'approved': False,
                    'reason': 'blocked_keyword',
                    'message': f'❌ Your message contains blocked content and cannot be posted.'
                }
        
        # Check minimum length
        min_length = self.filters.min_message_length or 20
        if len(text) < min_length:
            return {
                'approved': False,
                'reason': 'too_short',
                'message': f'❌ Your message is too short. Please include more details (minimum {min_length} characters).'
            }
        
        # Check for required keywords (rental/apartment related)
        has_required = any(kw.lower() in text_lower for kw in self.required_keywords)
        if not has_required:
            return {
                'approved': False,
                'reason': 'off_topic',
                'message': (
                    '❌ Your message doesn\'t appear to be about rentals/apartments.\n\n'
                    'Please include relevant information like:\n'
                    '• Type: apartment, flat, room, studio\n'
                    '• Terms: rent, lease, sublet\n'
                    '• Details: price, location, bedrooms'
                )
            }
        
        # All checks passed
        return {
            'approved': True,
            'reason': 'approved',
            'message': '✅ Your message has been approved and posted to the channel!'
        }


class UserSubmissionBot:
    """
    Bot that handles user submissions for the channel.
    
    Users send messages to this bot, which screens them and
    posts approved messages to the destination channel.
    """
    
    def __init__(self, client: TelegramClient, config: AppConfig):
        self.client = client
        self.config = config
        self.screener = SubmissionScreener(config)
        
        # Track pending submissions (for confirmation flow)
        self.pending_submissions: Dict[int, str] = {}  # user_id -> message
        
        # Statistics
        self.stats = {
            'submissions_received': 0,
            'submissions_approved': 0,
            'submissions_rejected': 0,
        }
    
    async def setup_handlers(self) -> None:
        """Set up event handlers for the bot."""
        
        @self.client.on(events.NewMessage(pattern='/start'))
        async def handle_start(event):
            """Handle /start command."""
            await event.respond(
                "👋 **Welcome to the Rental Posting Bot!**\n\n"
                "I help you post apartment/rental listings to our channel.\n\n"
                "**How to use:**\n"
                "1. Send me your listing message\n"
                "2. I'll check if it meets our guidelines\n"
                "3. If approved, it will be posted to the channel\n\n"
                "**Your message should include:**\n"
                "• Type (apartment/flat/room/studio)\n"
                "• Location/area\n"
                "• Price and terms\n"
                "• Contact information\n\n"
                "📝 Send your listing now!"
            )
        
        @self.client.on(events.NewMessage(pattern='/help'))
        async def handle_help(event):
            """Handle /help command."""
            await event.respond(
                "📖 **Posting Guidelines**\n\n"
                "✅ **DO include:**\n"
                "• Property type (apartment, flat, room, studio)\n"
                "• Location/neighborhood\n"
                "• Monthly rent/price\n"
                "• Available date\n"
                "• Contact details\n"
                "• Photos (optional but recommended)\n\n"
                "❌ **DON'T include:**\n"
                "• Spam or promotional content\n"
                "• Suspicious links\n"
                "• Off-topic messages\n\n"
                "📝 Just send me your listing message to get started!"
            )
        
        @self.client.on(events.NewMessage(pattern='/status'))
        async def handle_status(event):
            """Handle /status command."""
            await event.respond(
                f"📊 **Bot Statistics**\n\n"
                f"Total submissions: {self.stats['submissions_received']}\n"
                f"Approved: {self.stats['submissions_approved']}\n"
                f"Rejected: {self.stats['submissions_rejected']}"
            )
        
        @self.client.on(events.NewMessage(func=lambda e: e.is_private and not e.text.startswith('/')))
        async def handle_submission(event):
            """Handle user message submissions."""
            await self.process_submission(event)
        
        # Handle callback queries (button presses)
        @self.client.on(events.CallbackQuery())
        async def handle_callback(event):
            await self.handle_button_callback(event)
        
        logger.info("User submission bot handlers set up")
    
    async def process_submission(self, event: events.NewMessage.Event) -> None:
        """
        Process a user's submission.
        
        Args:
            event: The new message event
        """
        user = await event.get_sender()
        user_name = getattr(user, 'first_name', 'User')
        user_id = event.sender_id
        message_text = event.text or event.caption or ""
        
        self.stats['submissions_received'] += 1
        logger.info(f"Submission from {user_name} ({user_id}): {message_text[:50]}...")
        
        # Screen the message
        result = self.screener.screen_message(message_text)
        
        if result['approved']:
            # Store pending submission and ask for confirmation
            self.pending_submissions[user_id] = message_text
            
            # Show preview with confirm/cancel buttons
            preview = message_text[:500] + ('...' if len(message_text) > 500 else '')
            
            await event.respond(
                f"📋 **Preview of your listing:**\n\n"
                f"{preview}\n\n"
                f"Would you like to post this to the channel?",
                buttons=[
                    [Button.inline("✅ Post to Channel", b"confirm_post")],
                    [Button.inline("❌ Cancel", b"cancel_post")],
                    [Button.inline("✏️ Edit", b"edit_post")]
                ]
            )
        else:
            # Rejected - send feedback
            self.stats['submissions_rejected'] += 1
            await event.respond(result['message'])
    
    async def handle_button_callback(self, event: events.CallbackQuery.Event) -> None:
        """Handle button callback queries."""
        user_id = event.sender_id
        data = event.data.decode('utf-8')
        
        if data == "confirm_post":
            if user_id not in self.pending_submissions:
                await event.answer("No pending submission found. Please send a new message.")
                return
            
            message_text = self.pending_submissions.pop(user_id)
            
            # Post to channel
            success = await self.post_to_channel(message_text, user_id)
            
            if success:
                self.stats['submissions_approved'] += 1
                await event.edit(
                    "✅ **Your listing has been posted to the channel!**\n\n"
                    "Thank you for your submission. 🏠"
                )
            else:
                await event.edit(
                    "❌ **Failed to post to the channel.**\n\n"
                    "Please try again later or contact an admin."
                )
        
        elif data == "cancel_post":
            self.pending_submissions.pop(user_id, None)
            await event.edit("❌ Submission cancelled. Send a new message anytime!")
        
        elif data == "edit_post":
            self.pending_submissions.pop(user_id, None)
            await event.edit("✏️ Please send your edited listing message.")
        
        await event.answer()
    
    async def post_to_channel(self, message_text: str, user_id: int) -> bool:
        """
        Post an approved message to the destination channel.
        
        Args:
            message_text: The message to post
            user_id: The submitting user's ID (for attribution)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            dest_channel = self.config.channels.destination_channel
            entity = await self.client.get_entity(dest_channel)
            
            # Format the message with attribution
            formatted_message = (
                f"🏠 **New Listing**\n\n"
                f"{message_text}\n\n"
                f"━━━━━━━━━━━━━━━\n"
                f"📮 _Submitted via bot_"
            )
            
            await self.client.send_message(entity, formatted_message)
            logger.info(f"Posted submission from user {user_id} to {dest_channel}")
            return True
            
        except ChatWriteForbiddenError:
            logger.error(f"Cannot write to destination channel - check permissions!")
            return False
        except FloodWaitError as e:
            logger.warning(f"Flood wait: {e.seconds}s")
            await asyncio.sleep(e.seconds)
            return await self.post_to_channel(message_text, user_id)
        except Exception as e:
            logger.error(f"Error posting to channel: {e}")
            return False
    
    def get_stats(self) -> Dict[str, int]:
        """Get current statistics."""
        return self.stats.copy()
