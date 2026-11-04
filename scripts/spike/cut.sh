#!/usr/bin/env bash
# Cut an excerpt as 16 kHz mono WAV: cut.sh <input> <output.wav> [start] [duration]
# Keep the output under work/, it is real audio.
set -euo pipefail

input=$1
output=$2
start=${3:-0}
duration=${4:-}

args=(-hide_banner -loglevel error -n -ss "$start" -i "$input")
if [[ -n "$duration" ]]; then
  args+=(-t "$duration")
fi
ffmpeg "${args[@]}" -map 0:a:0 -ac 1 -ar 16000 -c:a pcm_s16le "$output"
