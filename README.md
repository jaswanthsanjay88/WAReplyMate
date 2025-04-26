# WhatsApp Automated Auto-Reply Bot

## ⚠️ Important Notice

**Using unofficial WhatsApp automation tools (including this bot and `whatsapp_bridge`) may violate WhatsApp's Terms of Service. Your WhatsApp account could be temporarily or permanently banned as a result.**

- Use at your own risk.
- Prefer using a secondary or test account for automation.
- The author is not responsible for any bans or account restrictions.

This project is a Python-based WhatsApp auto-reply bot that uses the `whatsapp_bridge` library to automate replies to incoming WhatsApp messages. It supports per-chat configuration, owner commands, rate limiting, and graceful shutdown.

## Features

- **Auto-reply** to incoming messages after a configurable delay.
- **Per-chat configuration** for enabling/disabling, delay, message, and rate limit.
- **Owner commands** for runtime configuration via WhatsApp.
- **Graceful shutdown** and persistent config.
- **Excludes system/broadcast chats** (e.g., `status@broadcast`).

## Requirements

- Python 3.8+
- `whatsapp_bridge` Python package (and its dependencies)
- WhatsApp Bridge backend running and accessible (usually at `http://localhost:8080`)

## Setup

1. **Clone or copy this repository.**

2. **Install dependencies:**
   ```sh
   pip install whatsapp_bridge
   ```

3. **Create a `config.json` file** in the project directory. Example:
   ```json
   {
     "bot_owner_jid": "1234567890@s.whatsapp.net",
     "defaults": {
       "enabled": true,
       "delay_seconds": 300,
       "message": "I am currently away. I will get back to you soon.",
       "rate_limit_minutes": 15
     },
     "chats": {}
   }
   ```
   - Replace `"bot_owner_jid"` with your WhatsApp JID (number@s.whatsapp.net).

4. **Start the WhatsApp Bridge backend** (see [whatsapp_bridge documentation](https://github.com/joeg/whatsapp-bridge) for setup).

5. **Run the bot:**
   ```sh
   python code.py
   ```

## Usage

### Owner Commands

Send these commands **from your owner account** to the bot in any chat:

- `/autoreply on` — Enable auto-reply for the current chat.
- `/autoreply off` — Disable auto-reply for the current chat.
- `/autoreply delay <seconds>` — Set delay before auto-reply (minimum 10 seconds).
- `/autoreply message <text>` — Set the auto-reply message for the current chat.
- `/autoreply status` — Show current auto-reply settings for the chat.
- `/autoreply help` — Show command help.

### Notes

- The bot will **not send auto-replies to system/broadcast chats** (e.g., `status@broadcast`).
- You can hardcode additional excluded chats in the `EXCLUDE_CHATS` list in `code.py`.
- All configuration changes are saved to `config.json`.

## Version Control (Git)

You can use Git to track changes to your code and configuration.

### Step-by-step: Add this project to GitHub

1. **Initialize a Git repository (if not already done):**
   ```sh
   git init
   ```

2. **Add your files:**
   ```sh
   git add code.py README.md config.json
   ```

3. **Commit your changes:**
   ```sh
   git commit -m "Initial commit: WhatsApp auto-reply bot"
   ```

4. **Add the remote repository:**
   ```sh
   git remote add origin https://github.com/jaswanthsanjay88/What-a-bot-.git
   ```

5. **Rename your branch to main (if needed):**
   ```sh
   git branch -M main
   ```

6. **Push your code to GitHub:**
   ```sh
   git push -u origin main
   ```

> **Tip:** Add `config.json` to `.gitignore` if it contains sensitive information.

### Example `.gitignore`

```
config.json
__pycache__/
*.pyc
.env
```

## Troubleshooting

- **500 Server Error:** Make sure the WhatsApp Bridge backend is running and accessible.
- **No auto-replies:** Check that the bot is running, the chat is enabled, and the delay/rate limit are set as expected.
- **Owner commands not working:** Ensure your JID is set correctly as `bot_owner_jid` in `config.json`.

## License

MIT License (or as applicable).

