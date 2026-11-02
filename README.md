# Dahiya Auto Forwarder Bot

Telegram automation for chats you own or are explicitly authorized to access. Python 3.11+, python-telegram-bot 22.x, Telethon 1.42, SQLite, aiohttp health endpoint.

## Features in this build
- Bot control panel: `/admin`, `/routes`, `/addroute SOURCE DEST`, `/routeon ID`, `/routeoff ID`, `/delroute ID`.
- Telethon user-session live forwarding for enabled routes, media and captions, with caption branding rules.
- Historical sync: `/sync SOURCE DEST [LIMIT]`, persisted per-job checkpoints, `/pausesync JOB_ID`, `/jobs`; rerunning the same source/destination resumes the paused job.
- Delivery idempotency and destination message ID tracking.
- Branding rules: `/branding OLD_TEXT | NEW_TEXT`, `/brandlist`, `/branddel ID`, `/bulkbrand [LIMIT]` to edit already delivered messages recorded in this database.
- Owner and additional admin controls: `/addadmin USER_ID`, `/deladmin USER_ID`, `/admins`. Owners are configured by `OWNER_IDS`.
- Join-request auto-approval toggle in `/admin`; bot must be admin with approve/invite permissions in the relevant chat.
- HTTP `/health` endpoint for Render.
- SQLite WAL database on configurable persistent disk.

## Setup
1. Python 3.11+; `python -m venv .venv`; activate it; `pip install -r requirements.txt`.
2. Copy `.env.example` to `.env`; set `BOT_TOKEN`, `API_ID`, `API_HASH`, `OWNER_IDS`.
3. Generate a Telethon StringSession on your own trusted computer: `python session_gen.py`. Put it only in `TELETHON_SESSION` environment variable. Never send it in chat or commit it.
4. Run `python main.py`.
5. Add Telethon account to each source and destination chat; ensure it has permission to read and post. Add the bot as administrator to chats where it must approve join requests.

## Commands
- `/addroute SOURCE DEST`; `/routes`; `/routeon ID`; `/routeoff ID`; `/delroute ID`
- `/sync SOURCE DEST [LIMIT]`; `/pausesync JOB_ID`; `/jobs`
- `/branding OLD | NEW`; `/brandlist`; `/branddel ID`; `/bulkbrand [LIMIT]`
- `/addadmin USER_ID`; `/deladmin USER_ID`; `/admins`

## Render
Use a paid always-on web service and persistent disk for dependable operation. Configure `DB_PATH=/var/data/bot.sqlite3`, `PORT` (Render supplies it), and all secrets in Environment. Free instances may sleep and do not provide always-on guarantees. Keep a single instance; polling and a local SQLite database are not safe to scale horizontally.

## Important limitations
- Telegram Bot API cannot read all historical messages; Telethon user session must be a member with access. Do not use this to copy content without permission.
- Bulk branding edits only messages successfully delivered and tracked in this bot's database; it cannot edit messages posted manually or before tracking began.
- Sync pause takes effect after the current message finishes. Telegram FloodWait/errors pause the job with its checkpoint retained. Resume by running `/sync` again for the same source and destination.
- Albums may be forwarded as individual messages; Telegram rate limits apply. No unlimited throughput or guaranteed uptime.
- Auto-approval is global ON/OFF in this build; group-specific toggles and per-group analytics are not implemented.
- Retry of failed historical deliveries should be done by rerunning `/sync`; deduplication skips successful deliveries and retries failed ones.

## Tests
`python -m unittest discover -s tests -v`
These are local database/unit tests. Live Telegram tests require valid credentials, a real session, and authorized test chats.

## Security
Never upload `.env`, Bot Token, API Hash, or Telethon StringSession to GitHub. If a token/session was exposed, revoke it and generate a new one.
