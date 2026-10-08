#!/bin/sh
# Start boson-video web in a container: fetch the speech models into the volume once (SenseVoice
# for Chinese, Parakeet for English, Silero for finding speech; about 650 MB), then serve.
set -e
M="${BOSON_MODELS:-/data/models}"
URL=https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models
mkdir -p "$M"

fetch() {
  [ -d "$M/$1" ] && return 0
  echo "downloading $1 (once, into the volume)"
  rm -rf "$M/.part" && mkdir -p "$M/.part"
  curl -fsSL "$URL/$1.tar.bz2" | tar -xj -C "$M/.part"
  mv "$M/.part/$1" "$M/$1" && rm -rf "$M/.part"
}
fetch sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2025-09-09
fetch sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8
[ -f "$M/silero_vad.onnx" ] || curl -fsSL -o "$M/silero_vad.onnx" "$URL/silero_vad.onnx"

# Behind Coolify's proxy, which brings HTTPS and the domain; the first start prints your invite code.
exec boson-video web --hosted --host 0.0.0.0 --port "${PORT:-8770}"
