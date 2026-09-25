"""Simulates a full game with many phones joining and answering, per
spec.md's Testing table ("Load: Script opens 50 player connections and
answers randomly. Pass mark: All answers counted, reveal within 1 s").

Usage:
    python load_test.py                          # 50 players against localhost:8000
    python load_test.py --players 15
    python load_test.py --url wss://your-app.up.railway.app --pin 1234
"""

import argparse
import asyncio
import json
import random
import sys
import time

import websockets

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


async def player_flow(player_url: str, i: int, stats: dict):
    try:
        async with websockets.connect(player_url) as ws:
            await ws.send(json.dumps({"type": "join", "nickname": f"P{i}"}))
            joined = json.loads(await ws.recv())
            if joined["type"] != "joined":
                stats["join_errors"].append((i, joined))
                return

            for _ in range(5):
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
                if msg["type"] != "question_live":
                    stats["unexpected"].append((i, msg))
                    return
                qid = msg["question_id"]
                # Small random delay to simulate real answering speed.
                await asyncio.sleep(random.uniform(0, 2))
                await ws.send(
                    json.dumps(
                        {"type": "submit_answer", "question_id": qid, "chosen_index": random.randint(0, 3)}
                    )
                )
                stats["answers_sent"] += 1
                result = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
                if result["type"] == "round_result":
                    stats["results_received"] += 1

            final = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
            if final["type"] == "final":
                stats["finals_received"] += 1
    except Exception as exc:
        stats["errors"].append((i, repr(exc)))


async def host_flow(host_url: str, num_players: int, stats: dict):
    async with websockets.connect(host_url) as ws:

        async def recv_type(*types, timeout=60):
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
                if msg["type"] in types:
                    return msg, time.time()

        # Wait for all phones to actually finish joining before starting,
        # same as a real presenter would watch the lobby fill up first.
        joined_count = 0
        while joined_count < num_players:
            msg, _ = await recv_type("player_joined", timeout=30)
            joined_count = msg["player_count"]
        print(f"All {joined_count} players joined, starting game.")

        await ws.send(json.dumps({"type": "host_control", "action": "start"}))

        for slot in range(1, 6):
            await recv_type("question_live")
            last_answer_count_time = None
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
                if msg["type"] == "answer_count":
                    if msg["answered"] >= msg["total"]:
                        last_answer_count_time = time.time()
                elif msg["type"] == "reveal":
                    reveal_time = time.time()
                    if last_answer_count_time is not None:
                        latency = reveal_time - last_answer_count_time
                        stats["reveal_latencies"].append(latency)
                        print(f"slot {slot}: reveal {latency:.2f}s after last answer counted")
                    break

            if slot == 3:
                await ws.send(json.dumps({"type": "host_control", "action": "next"}))
                await recv_type("difficulty_banner", timeout=20)
            else:
                await recv_type("leaderboard")
                await ws.send(json.dumps({"type": "host_control", "action": "next"}))

        await recv_type("approval_request", timeout=25)
        await ws.send(json.dumps({"type": "host_control", "action": "approval_decision", "decision": "skip"}))
        await recv_type("final", timeout=15)


async def main(host_url: str, player_url: str, num_players: int):
    stats = {
        "join_errors": [],
        "unexpected": [],
        "errors": [],
        "answers_sent": 0,
        "results_received": 0,
        "finals_received": 0,
        "reveal_latencies": [],
    }

    start = time.time()
    host_task = asyncio.create_task(host_flow(host_url, num_players, stats))
    player_tasks = [asyncio.create_task(player_flow(player_url, i, stats)) for i in range(num_players)]

    await asyncio.wait_for(asyncio.gather(host_task, *player_tasks, return_exceptions=False), timeout=300)

    elapsed = time.time() - start
    print(f"\n--- RESULTS ({elapsed:.1f}s total) ---")
    print("join_errors:", stats["join_errors"])
    print("unexpected:", stats["unexpected"])
    print("errors:", stats["errors"])
    print("answers_sent:", stats["answers_sent"], "/ expected", num_players * 5)
    print("results_received:", stats["results_received"], "/ expected", num_players * 5)
    print("finals_received:", stats["finals_received"], "/ expected", num_players)
    print("reveal_latencies:", [f"{x:.2f}" for x in stats["reveal_latencies"]])

    assert not stats["join_errors"], "some players failed to join"
    assert not stats["errors"], "some players errored"
    assert stats["answers_sent"] == num_players * 5
    assert stats["results_received"] == num_players * 5
    assert stats["finals_received"] == num_players
    print("\nPASS: all answers counted, all players finished")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="ws://127.0.0.1:8000", help="Base ws:// or wss:// URL of the server")
    parser.add_argument("--players", type=int, default=50, help="Number of simulated phones")
    parser.add_argument("--pin", default="", help="Presenter PIN, if PRESENTER_PIN is set on the server")
    args = parser.parse_args()

    host_url = f"{args.url}/ws/host"
    if args.pin:
        host_url += f"?pin={args.pin}"
    player_url = f"{args.url}/ws/player"

    asyncio.run(main(host_url, player_url, args.players))
