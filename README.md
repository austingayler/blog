# bolgrog

A frictionless blogging system. Send voice notes, photos, and text to a Telegram bot — it transcribes, generates a draft markdown post, and commits it directly to this repo. Review later, publish when ready.

## How it works

1. Send anything to [@VoiceBlogBot](https://t.me/VoiceBlogBot) — text, voice notes, photos, or any mix
2. Send `/done` when you're finished (or wait 1 hour of inactivity)
3. The bot transcribes voice via Whisper, assembles a draft via GPT-4o, and commits to `content/posts/` with `draft: true`
4. Review the markdown, edit if needed, set `draft: false` and push
5. GitHub Actions builds the Hugo site and deploys to GitHub Pages automatically

## Architecture

```
Telegram (capture)
    ↓
python-telegram-bot (handlers.py)
    ↓ queues to SQLite
aiosqlite (storage.py) + asyncio sliding timer (session.py)
    ↓ on /done or 1hr inactivity
OpenAI Whisper API → transcripts
GPT-4o → draft markdown
    ↓
githubkit → Git Data API → atomic commit to GitHub
    ↓
GitHub Actions → Hugo build → GitHub Pages
```

## Running locally

**Requirements:** Python 3.12+, pip

```bash
git clone https://github.com/austingayler/blog
cd blog

python3 -m venv .venv
.venv/bin/pip install -r bot/requirements.txt

cp .env.example .env
# fill in .env (see below)

.venv/bin/python bot/main.py
```

The bot runs in polling mode locally — no public URL or tunnel needed.

To preview the site locally:

```bash
cd site
hugo server -D   # -D renders draft posts too
```

## Environment variables

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | From [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_ALLOWED_USER_IDS` | Comma-separated Telegram user IDs (get yours from [@userinfobot](https://t.me/userinfobot)) |
| `OPENAI_API_KEY` | OpenAI API key (used for Whisper + GPT-4o) |
| `GITHUB_TOKEN` | Personal access token with `repo` + `workflow` scopes |
| `GITHUB_REPO` | `austingayler/blog` |
| `GITHUB_BRANCH` | `main` |
| `MODE` | `polling` locally, `webhook` in production |
| `GROUPING_TIMEOUT_SECONDS` | How long to wait after last message before processing (default `3600`) |
| `DATA_DIR` | Where SQLite DB and temp files are stored (default `./data`) |

## Bot commands

| Command | Description |
|---|---|
| `/start` | Show help |
| `/status` | See what's currently queued |
| `/done` | Process the queue immediately without waiting |

## Publishing a post

Drafts are committed to `content/posts/` with `draft: true` in the frontmatter. To publish:

```bash
# edit the post
vim content/posts/2026-06-30-my-post/index.md
# change: draft: true → draft: false

git add -A && git commit -m "publish: my-post" && git push
```

GitHub Actions will rebuild and deploy within ~30 seconds.

## Deploying to Railway

1. Create a new project in [Railway](https://railway.app) from this GitHub repo
2. Add a volume mounted at `/app/data`
3. Set all env vars in the Railway dashboard
4. Set `MODE=webhook` — the bot self-registers its webhook using `RAILWAY_PUBLIC_DOMAIN`

## Cost

Roughly **$0.02 per capture session** (2-min voice note + a few photos):
- Whisper: $0.006/min
- GPT-4o: ~$0.006 per draft
