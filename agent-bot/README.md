# Personal Agent Bot

Arkar's private AI agent on Telegram — chats, runs code, works with files, fetches the web,
remembers things, schedules reminders, and can reach his **Vultr server** (SSH) and his
**Windows laptop** (companion worker).

**Owner-only.** Only `ADMIN_CHAT_ID` (8028025915) can talk to it. No invite codes — an agent
with shell access must never be shared.

## Deploy (Railway)

Service: `agent-bot` (worker — no public domain needed, but the HTTP port must be
exposed for the laptop worker polling; Railway gives every service a domain).
Volume: `agent-data` mounted at `/data`.

Root Directory: `agent-bot` (relative to the myanmar-bots repo root).

Env vars:
- `BOT_TOKEN` — Telegram bot token from @BotFather
- `ANTHROPIC_API_KEY` — Claude API key
- `MODEL` — default `claude-sonnet-5-5`
- `ADMIN_CHAT_ID` — `8028025915`
- `DATA_DIR` — `/data`
- `VULTR_HOST` — `149.28.150.78`
- `VULTR_USER` — `root`
- `VULTR_PASSWORD` — Vultr root password (enables the `vultr` tool)
- `WORKER_SECRET` — optional; auto-generated and persisted if unset

## Laptop companion

`laptop-worker/laptop_worker.py` — stdlib-only Python script for the Windows laptop.
The owner edits `AGENT_URL` + `WORKER_SECRET` at the top, then double-clicks it.
While running, the agent's `laptop` tool (shell/read/write/list) works.

## Tools (agent loop, up to 12 steps per message)

run_python, run_shell, read/write/list/delete_file (agent workspace on volume),
fetch_url, vultr (SSH), laptop (queue), remember (long-term memory), schedule.
