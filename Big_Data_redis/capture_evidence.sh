#!/usr/bin/env bash
set -euo pipefail

mkdir -p Big_Data_redis/screenshots
export DISPLAY=:99
Xvfb :99 -screen 0 1600x900x24 -nolisten tcp >/tmp/redis-evidence-xvfb.log 2>&1 &
xvfb_pid=$!
trap 'kill "$xvfb_pid" 2>/dev/null || true' EXIT
sleep 1

cat >/tmp/redis-code-filter.sh <<'SH'
set -e
printf 'GitHub Actions  |  breevasofa/23---11  |  load_to_redis.py\n\n'
printf '$ nl -ba Big_Data_redis/load_to_redis.py | sed -n "25,57p"\n\n'
nl -ba Big_Data_redis/load_to_redis.py | sed -n '25,57p'
touch "$1"
sleep 30
SH

cat >/tmp/redis-code-write.sh <<'SH'
set -e
printf 'GitHub Actions  |  breevasofa/23---11  |  load_to_redis.py\n\n'
printf '$ nl -ba Big_Data_redis/load_to_redis.py | sed -n "62,90p"\n\n'
nl -ba Big_Data_redis/load_to_redis.py | sed -n '62,90p'
touch "$1"
sleep 30
SH

cat >/tmp/redis-python-run.sh <<'SH'
set -e
printf 'GitHub Actions  |  Python 3.12  |  Redis localhost:6379\n\n'
printf '$ python Big_Data_redis/load_to_redis.py\n\n'
python Big_Data_redis/load_to_redis.py
touch "$1"
sleep 30
SH

cat >/tmp/redis-cli-run.sh <<'SH'
set -e
printf 'GitHub Actions  |  redis-cli  |  Redis localhost:6379\n\n'
printf '$ redis-cli --raw PING\n'
redis-cli --raw PING
printf '\n$ redis-cli --scan --pattern "uk:org:*" | wc -l\n'
redis-cli --scan --pattern 'uk:org:*' | wc -l
sample_key=$(redis-cli --scan --pattern 'uk:org:*' | sort | sed -n '1p')
printf '\n$ redis-cli --raw HGETALL %s\n' "$sample_key"
redis-cli --raw HGETALL "$sample_key"
touch "$1"
sleep 30
SH

capture() {
    local title="$1" script="$2" output="$3" geometry="$4"
    local marker="/tmp/${title// /_}.done"
    rm -f "$marker"
    xterm -u8 -fa 'DejaVu Sans Mono' -fs 14 -geometry "$geometry" \
        -bg '#101827' -fg '#f9fafb' -title "$title" \
        -e bash "$script" "$marker" &
    local terminal_pid=$!
    for _ in $(seq 1 120); do
        if [ -f "$marker" ]; then break; fi
        sleep 0.25
    done
    test -f "$marker"
    xwd -name "$title" -out /tmp/redis-evidence.xwd
    convert /tmp/redis-evidence.xwd "$output"
    kill "$terminal_pid" 2>/dev/null || true
    wait "$terminal_pid" 2>/dev/null || true
}

capture 'Code filter' /tmp/redis-code-filter.sh Big_Data_redis/screenshots/01_code_filter.png '125x40+30+30'
capture 'Code Redis' /tmp/redis-code-write.sh Big_Data_redis/screenshots/02_code_redis.png '125x36+30+30'
capture 'Python output' /tmp/redis-python-run.sh Big_Data_redis/screenshots/03_python_output.png '125x12+30+30'
capture 'Redis CLI output' /tmp/redis-cli-run.sh Big_Data_redis/screenshots/04_redis_cli_output.png '125x22+30+30'

file Big_Data_redis/screenshots/*.png
