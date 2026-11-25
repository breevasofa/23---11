#!/usr/bin/env bash
set -euo pipefail

export DISPLAY=:99
export KT4_CAPTURE_DIR=/tmp/redis_cluster_expansion_capture
mkdir -p "$KT4_CAPTURE_DIR" Redis_Cluster_Expansion/screenshots

Xvfb :99 -screen 0 1600x900x24 >/tmp/redis_expansion_xvfb.log 2>&1 &
sleep 1

xterm -T 'Redis Cluster expansion - GitHub Actions terminal' \
  -geometry 135x38+20+20 -fa 'DejaVu Sans Mono' -fs 13 \
  -bg '#1e1e1e' -fg '#e8e8e8' -hold \
  -e bash -lc 'python3 -u Redis_Cluster_Expansion/expand_cluster.py 2>&1 | tee /tmp/redis_expansion_console.log; echo "${PIPESTATUS[0]}" > /tmp/redis_expansion_exit' &

for stage in 00_initial 01_two_replicas 02_removed 03_new_master 04_resharded; do
  timeout 120 bash -c 'until test -f "$1/$2.ready"; do sleep 0.2; done' _ "$KT4_CAPTURE_DIR" "$stage"
  scrot "Redis_Cluster_Expansion/screenshots/${stage}.png"
  touch "$KT4_CAPTURE_DIR/$stage.continue"
done

timeout 180 bash -c 'until test -f /tmp/redis_expansion_exit; do sleep 0.2; done'
test "$(cat /tmp/redis_expansion_exit)" = 0
test "$(find Redis_Cluster_Expansion/screenshots -name '*.png' | wc -l)" = 5
