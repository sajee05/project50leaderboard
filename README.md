# project50leaderboard

Reads the study sheet, renders leaderboards (PNG) and animated podium videos, posts them to the Telegram group.
Everything runs on free GitHub Actions; no cron site or server is needed.

## Commands (admin only, in the bot's DM)

Admin IDs come from `ADMIN_IDS` (default `7574436736`). Messages from anyone else are ignored.

| Command | What it does |
|---|---|
| `/daily` (also `/today`, `/leaderboard`, `/rerun`) | Post today's leaderboard to the group |
| `/yesterday` | Post yesterday's leaderboard to the group |
| `/weekly` | Archive the finished cycle to `data/weeks/<cycle-start>.json` and post the weekly podium video (`/weekly force` to run mid-cycle) |
| `/monthly` | Post the monthly leaderboard + podium video built from the last 4 archived weeks |
| `/show` | Specimens of the weekly and monthly boards and videos, sent to your DM |

**Scheduling:** in the bot's chat, type a command, long-press send, *Schedule message*, set *Repeat* (daily / weekly / monthly).
The "Bot commands" workflow checks for new messages every 5 minutes, so posts can arrive a few minutes after the scheduled time.

**Failures:** you get a DM with a **Rerun** button. The button remembers the exact day, so a rerun after midnight still reposts the
right date. Automatic and rerun boards use the previous day when they run before 06:00 IST (`ROLLOVER_HOUR`).

## Data

`data/weeks/*.json` holds every finished week (daily minutes per person). They are committed to the repo and kept forever.
The monthly board is computed from them.

## Setup

Secrets: `BOT_TOKEN`, `SHEET_CSV_URL` and/or `GOOGLE_SA_JSON`, optional `ALERT_CHAT_ID` (defaults to the admin ID).
The bot must have no webhook set (commands are read with `getUpdates`). Message the bot once (`/start`) so it can DM you.
