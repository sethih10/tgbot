#!/usr/bin/env python3
"""
Telegram Channel Forwarder - Main Application

A Telethon-based automation system for forwarding messages 
from source Telegram channels to a destination channel.

Usage:
    python -m telegram_forwarder.main
    
Or run directly:
    python main.py
"""

import asyncio
import logging
import signal
import sys
from typing import Optional

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from .config import get_config, AppConfig
from .handlers import MessageHandler


def setup_logging(level: str = "INFO") -> logging.Logger:
    """
    Configure logging for the application.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        
    Returns:
        The root logger
    """
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    # Reduce noise from telethon
    logging.getLogger("telethon").setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)


class TelegramForwarder:
    """Main application class for the Telegram forwarder."""
    
    def __init__(self, config: Optional[AppConfig] = None):
        """
        Initialize the forwarder.
        
        Args:
            config: Application configuration. If None, loads from environment.
        """
        self.config = config or get_config()
        self.logger = setup_logging(self.config.log_level)
        self.client: Optional[TelegramClient] = None
        self.handler: Optional[MessageHandler] = None
        self._running = False
    
    async def authenticate(self) -> TelegramClient:
        """
        Authenticate with Telegram and return a connected client.
        
        The first time this runs, it will prompt for:
        1. Phone number verification code (sent to your Telegram app)
        2. Two-factor authentication password (if enabled)
        
        Subsequent runs will use the saved session file.
        
        Returns:
            An authenticated TelegramClient
        """
        tg_config = self.config.telegram
        
        self.logger.info(f"Connecting to Telegram (session: {tg_config.session_name})...")
        
        client = TelegramClient(
            tg_config.session_name,
            tg_config.api_id,
            tg_config.api_hash,
        )
        
        await client.connect()
        
        # Check if we're already authorized
        if not await client.is_user_authorized():
            self.logger.info("Authentication required...")
            
            # Send code request
            await client.send_code_request(tg_config.phone_number)
            
            # Prompt for code
            print("\n" + "=" * 50)
            print("TELEGRAM AUTHENTICATION")
            print("=" * 50)
            print(f"A verification code has been sent to {tg_config.phone_number}")
            print("Check your Telegram app for the code.\n")
            
            code = input("Enter the verification code: ").strip()
            
            try:
                await client.sign_in(tg_config.phone_number, code)
            except SessionPasswordNeededError:
                # Two-factor authentication is enabled
                print("\nTwo-factor authentication is enabled.")
                password = input("Enter your 2FA password: ").strip()
                await client.sign_in(password=password)
            
            self.logger.info("Authentication successful!")
        else:
            self.logger.info("Already authenticated (using saved session)")
        
        # Get information about the logged-in user
        me = await client.get_me()
        self.logger.info(f"Logged in as: {me.first_name} (@{me.username or 'no username'})")
        
        return client
    
    async def start(self) -> None:
        """Start the forwarder and run until interrupted."""
        self.logger.info("Starting Telegram Forwarder...")
        
        try:
            # Authenticate
            self.client = await self.authenticate()
            
            # Set up message handler
            self.handler = MessageHandler(self.client, self.config)
            await self.handler.setup_handlers()
            
            self._running = True
            
            # Print startup info
            print("\n" + "=" * 50)
            print("TELEGRAM FORWARDER RUNNING")
            print("=" * 50)
            print(f"Monitoring {len(self.config.channels.source_channels)} source channel(s)")
            print(f"Forwarding to: {self.config.channels.destination_channel}")
            print(f"Mode: {'Forward' if self.config.channels.forward_mode else 'Copy'}")
            print("\nPress Ctrl+C to stop.")
            print("=" * 50 + "\n")
            
            # Run until disconnected
            await self.client.run_until_disconnected()
            
        except Exception as e:
            self.logger.error(f"Error: {e}")
            raise
        finally:
            await self.stop()
    
    async def stop(self) -> None:
        """Stop the forwarder and clean up."""
        self._running = False
        
        if self.handler:
            stats = self.handler.get_stats()
            self.logger.info(
                f"Session stats - Received: {stats['messages_received']}, "
                f"Forwarded: {stats['messages_forwarded']}, "
                f"Filtered: {stats['messages_filtered']}, "
                f"Errors: {stats['errors']}"
            )
        
        if self.client:
            await self.client.disconnect()
            self.logger.info("Disconnected from Telegram")


def handle_interrupt(signum, frame):
    """Handle interrupt signals gracefully."""
    print("\n\nReceived interrupt signal, shutting down...")
    sys.exit(0)


async def main():
    """Main entry point."""
    # Set up signal handlers
    signal.signal(signal.SIGINT, handle_interrupt)
    signal.signal(signal.SIGTERM, handle_interrupt)
    
    # Create and run the forwarder
    forwarder = TelegramForwarder()
    await forwarder.start()


def run():
    """Run the application."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
