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
| `/show` | Specimens of the weekly video and the monthly board + video, sent to your DM |

**Scheduling:** in the bot's chat, type a command, long-press send, *Schedule message*, set *Repeat* (daily / weekly / monthly).

**How messages reach GitHub (instant, free):** Telegram sends each message to a Cloudflare Worker
(`worker/telegram-webhook.js`), which drops anything that is not an admin command and otherwise starts the
"Bot commands" workflow through `repository_dispatch`. No polling and no cron site.

## One-time Worker setup

1. Create a fine-grained GitHub token for this repo only with **Contents: Read and write**.
2. Cloudflare dashboard > Workers & Pages > Create > Hello World > Deploy, then *Edit code*, paste `worker/telegram-webhook.js`, Deploy.
3. Worker > Settings > Variables and Secrets:
   secrets `BOT_TOKEN`, `GH_TOKEN` (the token from step 1), `WEBHOOK_SECRET` (any long random string);
   variables `REPO` = `sajee05/project50leaderboard`, `ADMIN_IDS` = `7574436736`.
4. Point Telegram at the Worker (open this URL once in a browser, filled in):
   `https://api.telegram.org/bot<BOT_TOKEN>/setWebhook?url=<WORKER_URL>&secret_token=<WEBHOOK_SECRET>&allowed_updates=["message","callback_query"]`
5. Send `/show` to the bot. You should get "On it" within a second.

Remove the webhook with `.../deleteWebhook` if you ever want to go back to polling (manual runs of the workflow use `getUpdates`).

**Failures:** you get a DM with a **Rerun** button. The button remembers the exact day, so a rerun after midnight still reposts the
right date. Automatic and rerun boards use the previous day when they run before 06:00 IST (`ROLLOVER_HOUR`).

## Data

`data/weeks/*.json` holds every finished week (daily minutes per person). They are committed to the repo and kept forever.
The monthly board is computed from them.

## Setup

Secrets: `BOT_TOKEN`, `SHEET_CSV_URL` and/or `GOOGLE_SA_JSON`, optional `ALERT_CHAT_ID` (defaults to the admin ID).
Message the bot once (`/start`) so it can DM you.


## Scheduling without Telegram Premium

Telegram's repeating scheduled messages need Premium, so the Worker has its own free cron triggers.
In Cloudflare: Worker > Settings > Triggers > Cron Triggers > Add, one per line (UTC):

| Cron | Runs | IST |
|---|---|---|
| `59 17 * * *` | `/daily` | every night 23:29 |

The monthly board and video post by themselves right after every 4th saved week (the weekly run triggers them), so there is no monthly cron. `/monthly` still works by hand any time.

The weekly video posts by itself after the daily board of the cycle's last (7th) day, and the monthly after every 4th saved week, so the only cron you need is `/daily`. `/weekly` and `/monthly` still work by hand.
