#!/usr/bin/env python3
"""Test script to verify we can send to the destination channel."""

import asyncio
from telethon import TelegramClient
from telegram_forwarder.config import get_config

async def test():
    config = get_config()
    
    client = TelegramClient(
        config.telegram.session_name,
        config.telegram.api_id,
        config.telegram.api_hash
    )
    
    await client.start(phone=config.telegram.phone_number)
    
    # Check who we're logged in as
    me = await client.get_me()
    print(f"✓ Logged in as: {me.first_name} ({me.phone})")
    
    # Try to resolve destination channel
    dest_channel = config.channels.destination_channel
    print(f"\nDestination channel: '{dest_channel}'")
    
    try:
        dest = await client.get_entity(dest_channel)
        print(f"✓ Resolved to: {dest.title} (ID: {dest.id})")
    except Exception as e:
        print(f"✗ Failed to resolve channel: {e}")
        await client.disconnect()
        return
    
    # Try to send a test text message
    print("\nTrying to send a test message...")
    try:
        await client.send_message(dest, "Test message from bot - please ignore")
        print("✓ Text message sent successfully!")
    except Exception as e:
        print(f"✗ Failed to send text: {type(e).__name__}: {e}")
    
    # Try to send a test photo (a simple placeholder)
    print("\nTrying to send a test photo...")
    try:
        # Send a simple 1x1 pixel image
        import io
        # Create a minimal valid PNG
        png_data = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
            0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
            0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,
            0x54, 0x08, 0xD7, 0x63, 0xF8, 0xFF, 0xFF, 0x3F,
            0x00, 0x05, 0xFE, 0x02, 0xFE, 0xDC, 0xCC, 0x59,
            0xE7, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E,
            0x44, 0xAE, 0x42, 0x60, 0x82
        ])
        await client.send_file(dest, io.BytesIO(png_data), caption="Test image")
        print("✓ Photo sent successfully!")
    except Exception as e:
        print(f"✗ Failed to send photo: {type(e).__name__}: {e}")
    
    await client.disconnect()
    print("\n✓ Test complete!")

if __name__ == "__main__":
    asyncio.run(test())
