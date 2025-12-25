# Telegram Channel Forwarder

A **Telethon-based** automation system for forwarding/copying messages from Telegram source channels to a destination channel. Uses the Telegram User API (not Bot API) for full access to channels.

## ✅ Setup Checklist

### 1. Get Telegram API Credentials

1. Go to [my.telegram.org](https://my.telegram.org)
2. Log in with your phone number
3. Click on **"API development tools"**
4. Create a new application:
   - **App title**: Any name (e.g., "Channel Forwarder")
   - **Short name**: Any short name
   - **Platform**: Can be "Desktop" or "Other"
5. Copy your **API ID** and **API Hash**

### 2. Install Dependencies

```bash
# Create and activate a virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
# Copy the example environment file
cp .env.example .env

# Edit with your values
nano .env  # or use any text editor
```

**Required settings:**
- `TELEGRAM_API_ID` - Your API ID from my.telegram.org
- `TELEGRAM_API_HASH` - Your API Hash from my.telegram.org
- `TELEGRAM_PHONE_NUMBER` - Your phone number with country code (e.g., +1234567890)
- `SOURCE_CHANNELS` - Comma-separated list of source channels
- `DESTINATION_CHANNEL` - The channel to forward messages to

### 4. Join Required Channels

Make sure your Telegram account:
- Is a **member** of all source channels (for private channels)
- Has **posting permissions** in the destination channel (admin or member with post rights)

### 5. First Run (Authentication)

```bash
python -m telegram_forwarder.main
```

On first run, you'll be prompted to:
1. Enter the verification code sent to your Telegram app
2. Enter your 2FA password (if enabled)

A session file (`telegram_forwarder.session`) will be created to persist your login.

---

## 🚀 Usage

### Run the Forwarder

```bash
# Standard run
python -m telegram_forwarder.main

# Or with custom session name
TELEGRAM_SESSION_NAME=my_bot python -m telegram_forwarder.main
```

### Run in Background (Production)

```bash
# Using nohup
nohup python -m telegram_forwarder.main > forwarder.log 2>&1 &

# Using screen
screen -S forwarder
python -m telegram_forwarder.main
# Detach with Ctrl+A, D

# Using tmux
tmux new -s forwarder
python -m telegram_forwarder.main
# Detach with Ctrl+B, D
```

### Using systemd (Recommended for VPS)

Create `/etc/systemd/system/telegram-forwarder.service`:

```ini
[Unit]
Description=Telegram Channel Forwarder
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/tg_bot
Environment=PATH=/path/to/tg_bot/venv/bin
ExecStart=/path/to/tg_bot/venv/bin/python -m telegram_forwarder.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable telegram-forwarder
sudo systemctl start telegram-forwarder
sudo systemctl status telegram-forwarder
```

---

## 📁 Project Structure

```
tg_bot/
├── telegram_forwarder/
│   ├── __init__.py          # Package initialization
│   ├── config.py             # Configuration management
│   ├── handlers.py           # Message handling and forwarding
│   └── main.py               # Application entry point
├── requirements.txt          # Python dependencies
├── .env.example              # Environment template
├── .env                      # Your configuration (not in git)
├── telegram_forwarder.session  # Session file (not in git)
└── README.md                 # This file
```

---

## ⚙️ Configuration Reference

### Channel Identifiers

You can specify channels in multiple formats:

| Format | Example | Notes |
|--------|---------|-------|
| Username | `@channelname` | Public channels only |
| Channel ID | `-100xxxxxxxxx` | Works for all channels |
| Link | `https://t.me/channelname` | Public channels |

**Finding Channel IDs:**
1. Forward a message from the channel to [@userinfobot](https://t.me/userinfobot)
2. Or use Telethon to get the ID programmatically

### Forward vs Copy Mode

| Mode | `FORWARD_MODE` | Behavior |
|------|----------------|----------|
| Copy | `false` (default) | Posts as your account, no "Forwarded from" label |
| Forward | `true` | Shows "Forwarded from [source]" label |

### Message Filters

| Setting | Description | Example |
|---------|-------------|---------|
| `INCLUDE_KEYWORDS` | Only forward if contains keyword | `crypto,bitcoin,eth` |
| `EXCLUDE_KEYWORDS` | Never forward if contains keyword | `spam,ad,promotion` |
| `INCLUDE_MEDIA_ONLY` | Forward media without text | `true` |
| `MIN_MESSAGE_LENGTH` | Skip short messages | `10` |

---

## ⚠️ Safety & Rate Limits

### Avoid Account Bans

1. **Use Conservative Rate Limits**
   - Default: 1 second delay between messages
   - Maximum: 20 messages per minute
   - Increase delays if you get FloodWaitErrors

2. **Use a Secondary Account**
   - Create a dedicated Telegram account for automation
   - Don't use your primary account
   - New accounts have stricter limits - let them age first

3. **Don't Abuse the System**
   - Respect Telegram's Terms of Service
   - Don't spam or scrape aggressively
   - This tool is for legitimate cross-posting needs

### FloodWaitError Handling

The system automatically handles FloodWaitErrors by:
1. Waiting the required time (with a safety multiplier)
2. Retrying the operation
3. Logging the incident

If you see frequent FloodWaitErrors, increase your delays:

```bash
MESSAGE_DELAY=2.0
MAX_MESSAGES_PER_MINUTE=10
```

### Session Security

- **Protect your session file** (`*.session`) - it contains your login credentials
- Add to `.gitignore`: `*.session`
- On VPS, set proper permissions: `chmod 600 *.session`

---

## 🔧 Future Extensions

The architecture supports easy extension for:

### 1. Caption Rewriting

Add to `handlers.py`:

```python
def rewrite_caption(self, text: str) -> str:
    """Modify message text before forwarding."""
    # Add your channel watermark
    return f"{text}\n\n📢 via @YourChannel"
```

### 2. Scheduling

Implement a queue with scheduled delivery:

```python
from asyncio import Queue
from datetime import datetime, timedelta

class ScheduledQueue:
    def __init__(self):
        self.queue = Queue()
    
    async def schedule(self, message, delay_seconds: int):
        deliver_at = datetime.now() + timedelta(seconds=delay_seconds)
        await self.queue.put((deliver_at, message))
```

### 3. Multi-Channel Configs

Extend `config.py` to support JSON configuration:

```json
{
  "routes": [
    {
      "sources": ["@channel1", "@channel2"],
      "destination": "@dest1",
      "filters": {"include": ["crypto"]}
    },
    {
      "sources": ["@channel3"],
      "destination": "@dest2"
    }
  ]
}
```

### 4. Database Logging

Store forwarded messages for tracking:

```python
import sqlite3

def log_message(message_id, source, dest, timestamp):
    conn = sqlite3.connect('forwarder.db')
    conn.execute('''INSERT INTO messages 
                    VALUES (?, ?, ?, ?)''', 
                 (message_id, source, dest, timestamp))
    conn.commit()
```

---

## 🐛 Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| `ValueError: Missing required environment variables` | Check your `.env` file has all required values |
| `Cannot resolve channel` | Make sure you're a member of the channel |
| `ChatWriteForbiddenError` | You don't have posting rights in the destination |
| `FloodWaitError` | Increase MESSAGE_DELAY and reduce MAX_MESSAGES_PER_MINUTE |
| `SessionPasswordNeededError` | Enter your 2FA password when prompted |

### Debug Mode

Enable debug logging:

```bash
LOG_LEVEL=DEBUG python -m telegram_forwarder.main
```

### Test Connection

```python
# test_connection.py
import asyncio
from telethon import TelegramClient

async def test():
    client = TelegramClient('test', API_ID, API_HASH)
    await client.start(phone=PHONE)
    me = await client.get_me()
    print(f"Connected as: {me.first_name}")
    await client.disconnect()

asyncio.run(test())
```

---

## 📄 License

This project is for educational purposes. Use responsibly and in accordance with Telegram's Terms of Service.
