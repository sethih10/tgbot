"""
Configuration module for Telegram Forwarder.
Load settings from environment variables or .env file.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TelegramConfig:
    """Telegram API configuration."""
    api_id: int
    api_hash: str
    phone_number: str
    session_name: str = "telegram_forwarder"
    
    @classmethod
    def from_env(cls) -> "TelegramConfig":
        """Load configuration from environment variables."""
        api_id = os.getenv("TELEGRAM_API_ID")
        api_hash = os.getenv("TELEGRAM_API_HASH")
        phone_number = os.getenv("TELEGRAM_PHONE_NUMBER")
        session_name = os.getenv("TELEGRAM_SESSION_NAME", "telegram_forwarder")
        
        if not api_id or not api_hash or not phone_number:
            raise ValueError(
                "Missing required environment variables: "
                "TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE_NUMBER"
            )
        
        return cls(
            api_id=int(api_id),
            api_hash=api_hash,
            phone_number=phone_number,
            session_name=session_name,
        )


@dataclass
class ChannelConfig:
    """Channel forwarding configuration."""
    # Source channels: can be usernames (@channel), IDs (-100xxxxx), or links
    source_channels: List[str] = field(default_factory=list)
    
    # Destination channel: username, ID, or link
    destination_channel: Optional[str] = None
    
    # Whether to forward (preserves original sender) or copy (sends as your account)
    forward_mode: bool = False  # False = copy, True = forward
    
    @classmethod
    def from_env(cls) -> "ChannelConfig":
        """Load channel configuration from environment variables."""
        source_channels_str = os.getenv("SOURCE_CHANNELS", "")
        destination_channel = os.getenv("DESTINATION_CHANNEL")
        forward_mode = os.getenv("FORWARD_MODE", "false").lower() == "true"
        
        # Parse comma-separated source channels
        source_channels = [
            ch.strip() for ch in source_channels_str.split(",") 
            if ch.strip()
        ]
        
        if not source_channels:
            raise ValueError("At least one SOURCE_CHANNELS must be specified")
        
        if not destination_channel:
            raise ValueError("DESTINATION_CHANNEL must be specified")
        
        return cls(
            source_channels=source_channels,
            destination_channel=destination_channel,
            forward_mode=forward_mode,
        )


@dataclass
class RateLimitConfig:
    """Rate limiting configuration to avoid flood bans."""
    # Delay between message forwards (seconds)
    message_delay: float = 1.0
    
    # Delay after receiving a flood wait error (multiplier of server wait time)
    flood_wait_multiplier: float = 1.5
    
    # Maximum messages to forward per minute
    max_messages_per_minute: int = 20
    
    @classmethod
    def from_env(cls) -> "RateLimitConfig":
        """Load rate limit configuration from environment variables."""
        return cls(
            message_delay=float(os.getenv("MESSAGE_DELAY", "1.0")),
            flood_wait_multiplier=float(os.getenv("FLOOD_WAIT_MULTIPLIER", "1.5")),
            max_messages_per_minute=int(os.getenv("MAX_MESSAGES_PER_MINUTE", "20")),
        )


@dataclass
class FilterConfig:
    """Message filtering configuration (for future extensions)."""
    # Keywords to include (message must contain at least one)
    include_keywords: List[str] = field(default_factory=list)
    
    # Keywords to exclude (message must not contain any)
    exclude_keywords: List[str] = field(default_factory=list)
    
    # Whether to include messages without text (media only)
    include_media_only: bool = True
    
    # Minimum message length (0 = no limit)
    min_message_length: int = 0
    
    @classmethod
    def from_env(cls) -> "FilterConfig":
        """Load filter configuration from environment variables."""
        include_str = os.getenv("INCLUDE_KEYWORDS", "")
        exclude_str = os.getenv("EXCLUDE_KEYWORDS", "")
        
        return cls(
            include_keywords=[k.strip() for k in include_str.split(",") if k.strip()],
            exclude_keywords=[k.strip() for k in exclude_str.split(",") if k.strip()],
            include_media_only=os.getenv("INCLUDE_MEDIA_ONLY", "true").lower() == "true",
            min_message_length=int(os.getenv("MIN_MESSAGE_LENGTH", "0")),
        )


@dataclass
class AppConfig:
    """Complete application configuration."""
    telegram: TelegramConfig
    channels: ChannelConfig
    rate_limit: RateLimitConfig
    filters: FilterConfig
    
    # Logging level
    log_level: str = "INFO"
    
    @classmethod
    def from_env(cls) -> "AppConfig":
        """Load complete configuration from environment variables."""
        return cls(
            telegram=TelegramConfig.from_env(),
            channels=ChannelConfig.from_env(),
            rate_limit=RateLimitConfig.from_env(),
            filters=FilterConfig.from_env(),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )


def load_dotenv_if_available() -> None:
    """Load .env file if python-dotenv is available."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # python-dotenv not installed, use system env vars


def get_config() -> AppConfig:
    """Get the application configuration."""
    load_dotenv_if_available()
    return AppConfig.from_env()
