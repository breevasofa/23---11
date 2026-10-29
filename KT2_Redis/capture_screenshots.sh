#!/usr/bin/env bash
set -euo pipefail

mkdir -p KT2_Redis/screenshots
export DISPLAY=:99
Xvfb :99 -screen 0 1600x900x24 -nolisten tcp >/tmp/kt2-xvfb.log 2>&1 &
xvfb_pid=$!
trap 'kill "$xvfb_pid" 2>/dev/null || true' EXIT
sleep 1

cat >/tmp/kt2-code-filter.sh <<'SH'
set -e
printf '$ nl -ba KT2_Redis/solution.py | sed -n "10,35p"\n\n'
nl -ba KT2_Redis/solution.py | sed -n '10,35p'
touch "$1"
sleep 30
SH

cat >/tmp/kt2-code-hset.sh <<'SH'
set -e
printf '$ nl -ba KT2_Redis/solution.py | sed -n "37,66p"\n\n'
nl -ba KT2_Redis/solution.py | sed -n '37,66p'
touch "$1"
sleep 30
SH

cat >/tmp/kt2-python.sh <<'SH'
set -e
printf '$ python KT2_Redis/solution.py\n\n'
python KT2_Redis/solution.py
touch "$1"
sleep 30
SH

cat >/tmp/kt2-redis-cli.sh <<'SH'
set -e
key="$(cat KT2_Redis/sample_key.txt)"
printf '$ redis-cli --raw DBSIZE\n'
redis-cli --raw DBSIZE
printf '\n$ redis-cli --raw TYPE "%s"\n' "$key"
redis-cli --raw TYPE "$key"
printf '\n$ redis-cli --raw HLEN "%s"\n' "$key"
redis-cli --raw HLEN "$key"
printf '\n$ redis-cli --raw HGETALL "%s"\n' "$key"
redis-cli --raw HGETALL "$key"
touch "$1"
sleep 30
SH

capture() {
    local title="$1" script="$2" output="$3" geometry="$4"
    local marker="/tmp/${title}.done"
    xterm -u8 -fa 'DejaVu Sans Mono' -fs 14 -geometry "$geometry" \
        -bg '#101827' -fg '#f9fafb' -title "$title" \
        -e bash "$script" "$marker" &
    local terminal_pid=$!
    for _ in $(seq 1 120); do
        if [ -f "$marker" ]; then break; fi
        sleep 0.25
    done
    test -f "$marker"
    xwd -name "$title" -out /tmp/kt2-evidence.xwd
    convert /tmp/kt2-evidence.xwd "$output"
    kill "$terminal_pid" 2>/dev/null || true
    wait "$terminal_pid" 2>/dev/null || true
}

capture code_filter /tmp/kt2-code-filter.sh KT2_Redis/screenshots/01_filter.png '135x35+20+20'
capture code_hset /tmp/kt2-code-hset.sh KT2_Redis/screenshots/02_hset.png '135x39+20+20'
capture python_run /tmp/kt2-python.sh KT2_Redis/screenshots/03_python.png '135x16+20+20'
capture redis_cli /tmp/kt2-redis-cli.sh KT2_Redis/screenshots/04_redis_cli.png '135x24+20+20'

file KT2_Redis/screenshots/*.png
