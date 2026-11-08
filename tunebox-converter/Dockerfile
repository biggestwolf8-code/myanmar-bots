# TuneBox Converter — python worker + Deno.
#
# Deno is here for yt-dlp's JS challenge solver (signature and "n"
# challenge solving — without a JS runtime those fail with
# "Signature solving failed" and formats go missing). Deno does NOT
# mint Proof-of-Origin tokens: yt-dlp ships no built-in token minter
# ("PO Token Providers: none" even with Deno installed). The tokens
# come from the bgutil provider: the bgutil-ytdlp-pot-provider plugin
# (in requirements.txt) asks a separate provider server — the
# brainicism/bgutil-ytdlp-pot-provider image, run as its own Railway
# service — to mint them. The bot points at it with POT_PROVIDER_URL
# (see bot.py).
#
# Railway builds this automatically when a Dockerfile sits in the
# service's root directory (tunebox-converter/). The Procfile is kept
# as a fallback start command.
FROM python:3.13-slim

# Tools for the Deno install script (curl + unzip) and TLS roots.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Deno (JS runtime) for yt-dlp's signature/challenge solving.
ENV DENO_INSTALL=/root/.deno
RUN curl -fsSL https://deno.land/install.sh | sh
ENV PATH=/root/.deno/bin:$PATH

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py .

CMD ["python", "bot.py"]
