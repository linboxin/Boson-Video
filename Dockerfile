# boson-video web on a server (Coolify, or any Docker host). It runs with --hosted: uploads only,
# because YouTube downloads stay on the user's side (docs/DIRECTION.md). Mount a persistent
# volume at /data: videos, invite codes and the speech models (about 650 MB, fetched on the
# first start by deploy/start.sh) live there. Keys come from the environment, never the image.
FROM python:3.12-slim

# ffmpeg reads the uploads; libgl1 and libglib2.0-0 are what OpenCV (under the screen reader) needs
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg ca-certificates curl bzip2 libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev
COPY deploy/start.sh ./start.sh

ENV BOSON_VIDEO_HOME=/data \
    BOSON_MODELS=/data/models \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
EXPOSE 8770
CMD ["sh", "/app/start.sh"]
