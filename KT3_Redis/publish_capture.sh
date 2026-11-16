#!/usr/bin/env bash
set -euo pipefail

image="$1"
stem="$(basename "$image" .png)"
convert "$image" -resize 1300x731 -colorspace Gray -threshold 30% -type bilevel -strip "/tmp/$stem.png"
encoded="$(base64 -w 0 "/tmp/$stem.png")"
length=${#encoded}
total=$(((length + 3499) / 3500))
if ((total > 10)); then
  echo "Capture $stem needs $total annotations; max is 10" >&2
  exit 1
fi
for ((index = 0; index < total; index++)); do
  chunk="${encoded:index*3500:3500}"
  printf '::notice title=CAPTURE_%s_%03d_%03d::%s\n' "$stem" "$((index + 1))" "$total" "$chunk"
done
