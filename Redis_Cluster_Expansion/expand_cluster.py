"""Reproduce Redis Cluster growth, replica replacement, and data resharding."""

from __future__ import annotations

import binascii
import os
import shutil
import subprocess
import tempfile
import time
import traceback
from pathlib import Path


BASE_PORTS = tuple(range(4000, 4012))
ADDED_PORTS = (4012, 4013)
SEED_PORT = 4000
MOVED_SLOTS = 64


def run(*command: str, timeout: int = 30) -> str:
    result = subprocess.run(command, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{' '.join(command)}\n{result.stdout}\n{result.stderr}")
    return result.stdout.strip()


def cli(port: int, *args: str) -> str:
    return run("redis-cli", "--raw", "-p", str(port), *args)


def cluster(*args: str, timeout: int = 120) -> str:
    return run("redis-cli", "--cluster", *args, timeout=timeout)


def wait_for(predicate, label: str, timeout: int = 60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = predicate()
            if result:
                return result
        except (AssertionError, RuntimeError, OSError):
            pass
        time.sleep(0.5)
    raise TimeoutError(label)


def node_map() -> dict[str, dict]:
    result = {}
    for line in cli(SEED_PORT, "CLUSTER", "NODES").splitlines():
        parts = line.split()
        address = parts[1].split("@", 1)[0]
        result[parts[0]] = {
            "port": int(address.rsplit(":", 1)[1]),
            "flags": set(parts[2].split(",")),
            "master_id": parts[3],
            "link": parts[7],
            "slots": parts[8:],
        }
    return result


def node_by_port(view: dict[str, dict], port: int) -> tuple[str, dict] | None:
    return next(((id_, node) for id_, node in view.items() if node["port"] == port), None)


def slots(node: dict) -> list[int]:
    result = []
    for part in node["slots"]:
        if not part[0].isdigit():
            continue
        if "-" in part:
            start, end = map(int, part.split("-", 1))
            result.extend(range(start, end + 1))
        else:
            result.append(int(part))
    return result


def key_slot(key: str) -> int:
    return binascii.crc_hqx(key.encode(), 0) % 16384


def keys_for_slots(target_slots: list[int]) -> dict[str, str]:
    wanted = set(target_slots)
    result = {}
    for candidate in range(500_000):
        key = f"kt4:item:{candidate}"
        slot = key_slot(key)
        if slot in wanted and slot not in result:
            result[slot] = key
            if len(result) == len(wanted):
                break
    assert len(result) == len(wanted), "Could not find keys for all selected slots"
    return {key: f"value-{slot}" for slot, key in sorted(result.items())}


def values_readable(data: dict[str, str]) -> bool:
    return all(cli(SEED_PORT, "-c", "GET", key) == value for key, value in data.items())


def verify(expected_nodes: int, expected_masters: int, data: dict[str, str]) -> dict[str, dict]:
    view = node_map()
    masters = [node for node in view.values() if "master" in node["flags"]]
    replicas = [node for node in view.values() if "slave" in node["flags"]]
    assert len(view) == expected_nodes, (len(view), expected_nodes)
    assert len(masters) == expected_masters, (len(masters), expected_masters)
    assert len(replicas) == expected_nodes - expected_masters
    assert all(not ({"fail", "fail?"} & node["flags"]) and node["link"] == "connected"
               for node in view.values())
    assert sum(len(slots(node)) for node in masters) == 16384
    info = dict(line.split(":", 1) for line in cli(SEED_PORT, "CLUSTER", "INFO").splitlines() if ":" in line)
    assert info["cluster_state"] == "ok", info
    assert info["cluster_slots_assigned"] == "16384", info
    check = cluster("check", f"127.0.0.1:{SEED_PORT}", timeout=60)
    assert "[OK] All 16384 slots covered" in check, check[-1000:]
    assert values_readable(data), "A seeded key could not be read"
    return view


def wait_for_cluster_convergence(view: dict[str, dict], timeout: int = 90) -> None:
    """Wait until each node, including the new empty master, sees the full cluster."""
    ports = sorted(node["port"] for node in view.values())
    deadline = time.monotonic() + timeout
    last_status = {}
    while time.monotonic() < deadline:
        last_status = {}
        for port in ports:
            try:
                info = dict(line.split(":", 1) for line in cli(port, "CLUSTER", "INFO").splitlines() if ":" in line)
                known_nodes = len(cli(port, "CLUSTER", "NODES").splitlines())
                last_status[port] = (info.get("cluster_state"), info.get("cluster_slots_assigned"), known_nodes)
            except (RuntimeError, OSError, subprocess.TimeoutExpired):
                last_status[port] = ("unreachable", None, None)
        if all(status == ("ok", "16384", len(ports)) for status in last_status.values()):
            return
        time.sleep(0.5)
    raise TimeoutError(f"Cluster did not converge on every node: {last_status}")


def show_stage(stage: str, title: str, view: dict[str, dict], data: dict[str, str], extra: str = "") -> None:
    print("\033[2J\033[H", end="", flush=True)
    print(f"=== {stage}: {title} ===", flush=True)
    port_for_id = {id_: node["port"] for id_, node in view.items()}
    for id_, node in sorted(view.items(), key=lambda pair: pair[1]["port"]):
        role = "MASTER " if "master" in node["flags"] else "REPLICA"
        parent = f":{port_for_id[node['master_id']]}" if node["master_id"] in port_for_id else "-"
        print(f":{node['port']}  {role}  upstream={parent:>5}  slots={len(slots(node)):>4}", flush=True)
    print(f"cluster_state:ok | 16384/16384 slots | {len(view)} nodes | {len(data)} keys readable", flush=True)
    if extra:
        print(extra, flush=True)
    print(f"::notice title={stage}::{title}; cluster_state:ok; 16384 slots; {len(data)} keys readable", flush=True)
    capture_dir = os.environ.get("KT4_CAPTURE_DIR")
    if capture_dir:
        location = Path(capture_dir)
        location.mkdir(parents=True, exist_ok=True)
        (location / f"{stage}.ready").touch()
        wait_for(lambda: (location / f"{stage}.continue").exists(), f"Screenshot {stage}", 90)


def main() -> None:
    processes: dict[int, subprocess.Popen] = {}
    with tempfile.TemporaryDirectory(prefix="redis_cluster_expansion_") as temp:
        root = Path(temp)

        def start_node(port: int) -> None:
            directory = root / str(port)
            directory.mkdir()
            log = (directory / "redis.log").open("w", encoding="utf-8")
            processes[port] = subprocess.Popen(
                ["redis-server", "--port", str(port), "--bind", "127.0.0.1",
                 "--cluster-enabled", "yes", "--cluster-config-file", "nodes.conf",
                 "--cluster-node-timeout", "3000", "--appendonly", "yes",
                 "--save", "", "--dir", str(directory), "--protected-mode", "no"],
                stdout=log, stderr=subprocess.STDOUT,
            )
            log.close()
            wait_for(lambda: cli(port, "PING") == "PONG", f"Start :{port}")

        try:
            for port in BASE_PORTS:
                start_node(port)
            cluster("create", *(f"127.0.0.1:{port}" for port in BASE_PORTS),
                    "--cluster-replicas", "2", "--cluster-yes", timeout=120)
            empty: dict[str, str] = {}
            initial = wait_for(lambda: verify(12, 4, empty), "Initial 4+8 cluster")
            source_id, source = min(
                ((id_, node) for id_, node in initial.items() if "master" in node["flags"]),
                key=lambda pair: pair[1]["port"],
            )
            chosen_slots = slots(source)[:MOVED_SLOTS]
            assert len(chosen_slots) == MOVED_SLOTS
            data = keys_for_slots(chosen_slots)
            for key, value in data.items():
                assert cli(SEED_PORT, "-c", "SET", key, value) == "OK"
            initial = verify(12, 4, data)
            show_stage("00_initial", "4 masters, 2 replicas each", initial, data,
                       f"Chosen master :{source['port']}; seeded {MOVED_SLOTS} slots")

            for port in ADDED_PORTS:
                start_node(port)
                cluster("add-node", f"127.0.0.1:{port}", f"127.0.0.1:{SEED_PORT}",
                        "--cluster-slave", "--cluster-master-id", source_id)

            def added_replicas():
                view = verify(14, 4, data)
                attached = {node["port"] for node in view.values() if node["master_id"] == source_id}
                return view if set(ADDED_PORTS) <= attached and len(attached) == 4 else None

            added = wait_for(added_replicas, "Two new replicas on chosen master")
            show_stage("01_two_replicas", "Added :4012 and :4013 as replicas", added, data,
                       f"Both replicate master :{source['port']}; it now has 4 replicas")

            removed_id, removed_node = node_by_port(added, 4013)
            assert "slave" in removed_node["flags"]
            cluster("del-node", f"127.0.0.1:{SEED_PORT}", removed_id)
            processes[4013].terminate()
            processes[4013].wait(timeout=10)
            del processes[4013]

            def after_removal():
                view = verify(13, 4, data)
                return view if not node_by_port(view, 4013) else None

            removed = wait_for(after_removal, "Replica :4013 removed")
            show_stage("02_removed", "Removed replica :4013", removed, data,
                       f"Replica :4012 remains on master :{source['port']}")

            shutil.rmtree(root / "4013")
            start_node(4013)
            cluster("add-node", "127.0.0.1:4013", f"127.0.0.1:{SEED_PORT}")

            def new_master_ready():
                view = verify(14, 5, data)
                match = node_by_port(view, 4013)
                return (view, match[0]) if match and "master" in match[1]["flags"] and not slots(match[1]) else None

            remastered, new_id = wait_for(new_master_ready, "New master :4013 without slots")
            assert new_id != removed_id, "Re-added node must have a fresh ID"
            show_stage("03_new_master", "Re-added :4013 as empty master", remastered, data,
                       "5 masters; new master has 0 slots before resharding")

            wait_for_cluster_convergence(remastered)

            cluster("reshard", f"127.0.0.1:{SEED_PORT}", "--cluster-from", source_id,
                    "--cluster-to", new_id, "--cluster-slots", str(MOVED_SLOTS),
                    "--cluster-yes", timeout=180)

            def reshared_ready():
                view = verify(14, 5, data)
                target = view[new_id]
                return view if len(slots(target)) == MOVED_SLOTS else None

            reshared = wait_for(reshared_ready, "64 slots on new master", 90)
            target_slots = set(slots(reshared[new_id]))
            assert set(chosen_slots) == target_slots, "Different slots were moved than those seeded"
            assert cli(4013, "DBSIZE") == str(len(data)), "Seeded data did not move to :4013"
            show_stage("04_resharded", "Moved 64 slots and 64 keys to :4013", reshared, data,
                       "New master :4013 owns 64 slots; DBSIZE=64; GET checks passed")
            print("ALL STAGES PASSED", flush=True)
        finally:
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
        frame = traceback.extract_tb(exc.__traceback__)[-1]
        print(f"::error title=Redis Cluster Expansion::{type(exc).__name__} at line {frame.lineno}: {exc}", flush=True)
        raise
