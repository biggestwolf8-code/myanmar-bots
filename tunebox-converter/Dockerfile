# TuneBox Converter — python worker + Deno (JS runtime).
#
# Why Deno is here: yt-dlp can only mint YouTube Proof-of-Origin (PO)
# tokens when a JavaScript runtime is installed. Without one, the web
# players answer a signed-in request with "Requested format is not
# available" (the formats are withheld until a PO token is presented),
# which is exactly what the Railway logs showed on every cookie pass.
# Deno is the runtime yt-dlp enables by default for this. No code
# change is needed — yt-dlp fetches the token automatically once the
# runtime is on PATH.
#
# Railway builds this automatically when a Dockerfile sits in the
# service's root directory (tunebox-converter/). The Procfile is kept
# as a fallback start command.
FROM python:3.13-slim

# Tools for the Deno install script (curl + unzip) and TLS roots.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Deno (JS runtime) for yt-dlp's PO-token minting.
ENV DENO_INSTALL=/root/.deno
RUN curl -fsSL https://deno.land/install.sh | sh
ENV PATH=/root/.deno/bin:$PATH

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py .

CMD ["python", "bot.py"]
