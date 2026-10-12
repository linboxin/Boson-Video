#!/bin/sh
# Start boson-video web in a container: fetch the speech models into the volume once (SenseVoice
# for Chinese, Parakeet for English, Silero for finding speech; about 650 MB), then serve.
set -e
umask 077
# Use the engine's atomic downloader: an interrupted download must not look complete.
boson-video models all

# Behind Coolify's proxy, which brings HTTPS and the domain; the first start prints your invite code.
exec boson-video web --hosted --host 0.0.0.0 --port "${PORT:-8770}"
