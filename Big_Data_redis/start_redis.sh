#!/bin/sh
set -eu

if redis-cli ping 2>/dev/null | grep -qx PONG; then
    exit 0
fi

data_dir="$(pwd)/Big_Data_redis/.redis-data"
mkdir -p "$data_dir"
redis-server --bind 127.0.0.1 --protected-mode yes --port 6379 \
    --dir "$data_dir" --appendonly yes --daemonize yes
redis-cli ping
