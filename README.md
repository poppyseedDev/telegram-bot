# Telegram Broadcast Forwarder

This bot forwards Thena (TNA) campaign broadcasts to Telegram groups. When a broadcast is created in Thena and sent to the `#test-bot-tg-slack-forwarder` Slack channel, the bot picks it up and delivers it to every Telegram group listed in the config.

```
Thena Broadcast → #test-bot-tg-slack-forwarder (Slack) → bot → Telegram Groups
```

## How it works

1. Thena sends a campaign broadcast to the `#test-bot-tg-slack-forwarder` channel in Slack
2. The bot is connected to Slack via Socket Mode and watches that channel for new messages
3. It only forwards messages tagged as Thena campaigns (`MARKETING_CAMPAIGN` metadata) — regular messages, joins, and topic changes are ignored
4. The bot converts Slack formatting (Block Kit rich text, bold, italic, links, lists, etc.) into Telegram-compatible HTML
5. The formatted message is sent to every Telegram group specified in `TELEGRAM_GROUP_IDS`
6. If a message is too long for Telegram (4096 char limit), it gets split at paragraph boundaries
7. If one group fails, the bot continues sending to the rest

## Configuration

All config lives in environment variables (set in Railway for production, or in a `.env` file for local dev):

| Variable | What it is |
|---|---|
| `SLACK_APP_TOKEN` | Slack app-level token (`xapp-...`) for Socket Mode |
| `SLACK_BOT_TOKEN` | Slack bot OAuth token (`xoxb-...`) |
| `SLACK_CHANNEL_ID` | The ID of `#test-bot-tg-slack-forwarder` |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from @BotFather |
| `TELEGRAM_GROUP_IDS` | Comma-separated list of Telegram group chat IDs to forward to |

### Adding a new Telegram group

1. Add the bot to the Telegram group
2. Run `python get_chat_ids.py` locally — it starts a polling loop
3. Send a message in that group — the script prints the chat ID (a negative number like `-1001234567890`)
4. Add that ID to the `TELEGRAM_GROUP_IDS` list in Railway and redeploy

### Removing a Telegram group

Remove its chat ID from `TELEGRAM_GROUP_IDS` in Railway and redeploy.

## Files

| File | What it does |
|---|---|
| `bot.py` | Main app — listens to Slack, sends to Telegram |
| `formatting.py` | Converts Slack formatting to Telegram HTML |
| `get_chat_ids.py` | Helper script to discover Telegram group chat IDs |
| `Dockerfile` | Container image for Railway |

## Deployment

The bot is deployed on [Railway](https://railway.app). Environment variables are configured in the Railway dashboard. Pushing to `main` triggers an automatic redeploy.
