# TuneBox Converter — python worker.
#
# Proof-of-Origin tokens: yt-dlp ships NO built-in PO-token minter
# (its debug output says "PO Token Providers: none" even with a JS
# runtime installed), so Deno alone cannot fix the web players.
# The tokens come from the bgutil provider: the
# bgutil-ytdlp-pot-provider plugin (in requirements.txt) asks a
# separate provider server — the brainicism/bgutil-ytdlp-pot-provider
# image, run as its own Railway service — to mint them. The bot
# points at it with POT_PROVIDER_URL (see bot.py). No JS runtime is
# needed in this image.
#
# Railway builds this automatically when a Dockerfile sits in the
# service's root directory (tunebox-converter/). The Procfile is kept
# as a fallback start command.
FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py .

CMD ["python", "bot.py"]
