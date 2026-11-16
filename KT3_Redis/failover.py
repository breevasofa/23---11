"""КТ3_1, задание 2: автоматический failover кластера Redis 3+6."""

from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import time
import traceback
from pathlib import Path


PORTS = range(5500, 5509)
MASTER_PORT = 5500
OTHER_MASTER_PORT = 5501
KEY = "f"  # Redis Cluster slot 3168; у первого мастера диапазон 0–5460.
VALUE = "888"


def cli(port: int, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["redis-cli", "--raw", "-p", str(port), *args],
        text=True,
        capture_output=True,
        timeout=15,
    )
    if check and result.returncode:
        raise RuntimeError(f"redis-cli -p {port} {' '.join(args)}: {result.stderr or result.stdout}")
    return result.stdout.strip()


def wait_for(predicate, label: str, seconds: int = 45):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        value = predicate()
        if value:
            return value
        time.sleep(0.5)
    raise TimeoutError(f"Время ожидания истекло: {label}")


def nodes(port: int) -> dict[str, dict]:
    result = {}
    for line in cli(port, "CLUSTER", "NODES").splitlines():
        parts = line.split()
        address = parts[1].split("@", 1)[0]
        result[parts[0]] = {
            "port": int(address.rsplit(":", 1)[1]),
            "flags": set(parts[2].split(",")),
            "master_id": parts[3],
            "slots": parts[8:],
            "line": line,
        }
    return result


def node_at(view: dict[str, dict], port: int):
    return next(((node_id, item) for node_id, item in view.items() if item["port"] == port), None)


def cluster_ok(port: int) -> bool:
    return "cluster_state:ok" in cli(port, "CLUSTER", "INFO")


def main() -> None:
    processes: dict[int, subprocess.Popen] = {}
    stopped = False
    with tempfile.TemporaryDirectory(prefix="kt3_redis_") as tmp:
        root = Path(tmp)
        try:
            for port in PORTS:
                directory = root / str(port)
                directory.mkdir()
                log = (directory / "redis.log").open("w", encoding="utf-8")
                process = subprocess.Popen(
                    [
                        "redis-server",
                        "--port", str(port),
                        "--bind", "127.0.0.1",
                        "--cluster-enabled", "yes",
                        "--cluster-config-file", "nodes.conf",
                        "--cluster-node-timeout", "2000",
                        "--appendonly", "yes",
                        "--dir", str(directory),
                        "--protected-mode", "no",
                    ],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                log.close()
                processes[port] = process
            wait_for(lambda: all(cli(port, "PING", check=False) == "PONG" for port in PORTS), "запуск 9 узлов")

            command = ["redis-cli", "--cluster", "create"]
            command += [f"127.0.0.1:{port}" for port in PORTS]
            command += ["--cluster-replicas", "2", "--cluster-yes"]
            created = subprocess.run(command, text=True, capture_output=True, timeout=90)
            if created.returncode:
                raise RuntimeError(created.stdout + "\n" + created.stderr)
            wait_for(lambda: cluster_ok(OTHER_MASTER_PORT), "готовность кластера")
            before = nodes(OTHER_MASTER_PORT)
            original = node_at(before, MASTER_PORT)
            assert original and "master" in original[1]["flags"]
            original_id = original[0]
            replicas = {node_id for node_id, item in before.items() if item["master_id"] == original_id}
            assert len(before) == 9 and len(replicas) == 2
            assert sum("master" in x["flags"] for x in before.values()) == 3
            assert sum("slave" in x["flags"] for x in before.values()) == 6
            print("=== ДО СБОЯ: 9 узлов, 3 мастера, 6 реплик; у 5500 две реплики ===", flush=True)
            print("\n".join(x["line"] for x in sorted(before.values(), key=lambda x: x["port"])), flush=True)

            # Одна TCP-сессия обеспечивает WAIT именно для сделанной записи.
            with __import__("socket").create_connection(("127.0.0.1", MASTER_PORT), timeout=10) as sock:
                payload = (
                    f"*3\r\n$3\r\nSET\r\n${len(KEY)}\r\n{KEY}\r\n${len(VALUE)}\r\n{VALUE}\r\n"
                    "*3\r\n$4\r\nWAIT\r\n$1\r\n2\r\n$4\r\n5000\r\n"
                )
                sock.sendall(payload.encode())
                reply = sock.recv(4096).decode(errors="replace")
                assert "+OK" in reply, reply
                if ":2" not in reply:
                    reply += sock.recv(4096).decode(errors="replace")
                assert ":2" in reply, f"Запись не подтвердилась обеими репликами: {reply!r}"
            print("SET f 888; WAIT 2 5000 -> обе реплики подтвердили запись", flush=True)

            os.kill(processes[MASTER_PORT].pid, signal.SIGSTOP)
            stopped = True
            print(f"=== СБОЙ: SIGSTOP redis-server :{MASTER_PORT}, PID {processes[MASTER_PORT].pid} ===", flush=True)

            def promoted():
                view = nodes(OTHER_MASTER_PORT)
                candidates = [(node_id, item) for node_id, item in view.items()
                              if node_id in replicas and "master" in item["flags"] and "0-5460" in item["slots"]]
                return (view, candidates[0]) if candidates and cluster_ok(OTHER_MASTER_PORT) else None

            after, (new_id, new_master) = wait_for(promoted, "автоматическое повышение реплики", 60)
            assert cli(OTHER_MASTER_PORT, "CLUSTER", "KEYSLOT", KEY) == "3168"
            result = subprocess.run(
                ["redis-cli", "-c", "--raw", "-p", str(OTHER_MASTER_PORT), "GET", KEY],
                text=True, capture_output=True, timeout=15, check=True,
            ).stdout.strip()
            assert result == VALUE, f"После failover прочитано {result!r} вместо {VALUE!r}"
            print(f"=== ПОСЛЕ СБОЯ: реплика :{new_master['port']} стала мастером слотов 0-5460 ===", flush=True)
            print("\n".join(x["line"] for x in sorted(after.values(), key=lambda x: x["port"])), flush=True)
            print(f"cluster_state:ok; GET {KEY} -> {result}", flush=True)

            os.kill(processes[MASTER_PORT].pid, signal.SIGCONT)
            stopped = False
            def rejoined():
                old = node_at(nodes(OTHER_MASTER_PORT), MASTER_PORT)
                return old and "slave" in old[1]["flags"] and old[1]["master_id"] == new_id
            wait_for(rejoined, "возврат прежнего мастера как реплики", 45)
            print(f"=== ВОССТАНОВЛЕНИЕ: :{MASTER_PORT} вернулся как реплика :{new_master['port']} ===", flush=True)
            print(f"cluster_state:ok; GET {KEY} -> {cli(new_master['port'], 'GET', KEY)}", flush=True)
        finally:
            if stopped:
                os.kill(processes[MASTER_PORT].pid, signal.SIGCONT)
            for process in processes.values():
                process.terminate()
            for process in processes.values():
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Публичная аннотация CI сообщает причину сбоя без доступа к закрытому логу.
        frame = traceback.extract_tb(exc.__traceback__)[-1]
        print(f"::error title=KT3 Redis failover::{type(exc).__name__} at line {frame.lineno}: {exc}", flush=True)
        raise
