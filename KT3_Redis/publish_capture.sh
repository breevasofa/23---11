#!/usr/bin/env bash
set -euo pipefail

image="$1"
stem="$(basename "$image" .png)"
convert "$image" -resize 1400x788 -quality 35 "/tmp/$stem.jpg"
encoded="$(base64 -w 0 "/tmp/$stem.jpg")"
length=${#encoded}
total=$(((length + 11999) / 12000))
if ((total > 10)); then
  echo "Capture $stem needs $total annotations; max is 10" >&2
  exit 1
fi
for ((index = 0; index < total; index++)); do
  chunk="${encoded:index*12000:12000}"
  printf '::notice title=CAPTURE_%s_%03d_%03d::%s\n' "$stem" "$((index + 1))" "$total" "$chunk"
done
