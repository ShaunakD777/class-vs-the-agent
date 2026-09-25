"""The game engine: stages, timer, scoring, reveal and leaderboard, plus the
live agent moments (commentary, difficulty check) hooked in at the right
points. Everything else here is plain server code, no AI.
"""

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

from app import agent
from app.connections import manager
from app.db import get_connection
from app.quiz_data import load_safe_mode_quiz

QUESTION_SECONDS = 20
TOTAL_QUESTIONS = 5

# In-memory per-game runtime state. Not persisted: it only tracks the
# currently running timer, who has answered the current question, the
# pending approval decision the presenter hasn't made yet, and how much
# time was left on a question when it was paused.
_timers: dict[str, asyncio.Task] = {}
_answered: dict[str, set[str]] = {}
_approval_events: dict[str, asyncio.Event] = {}
_approval_decisions: dict[str, str] = {}
_paused_remaining: dict[str, tuple[str, int, float]] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


async def handle_start(game_id: str) -> None:
    """Presenter clicked Start. Uses questions 1-3 from a prior research run
    if there are any; otherwise falls back to the hard-coded quiz so the
    game is still playable without the agent (e.g. for testing)."""
    conn = get_connection()
    try:
        researched = conn.execute(
            "SELECT COUNT(*) AS n FROM question WHERE game_id = ? AND slot <= 3", (game_id,)
        ).fetchone()["n"]
        conn.execute(
            "DELETE FROM answer WHERE question_id IN (SELECT id FROM question WHERE game_id = ?)",
            (game_id,),
        )
        conn.execute(
            "DELETE FROM revision_note WHERE question_id IN (SELECT id FROM question WHERE game_id = ?)",
            (game_id,),
        )
        conn.execute("UPDATE player SET score = 0, streak = 0 WHERE game_id = ?", (game_id,))

        if researched < 3:
            conn.execute("DELETE FROM question WHERE game_id = ?", (game_id,))
            for slot, q in enumerate(load_safe_mode_quiz(), start=1):
                conn.execute(
                    """INSERT INTO question
                       (id, game_id, text, options, correct_index, difficulty, explanation, source_url, slot)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        f"{game_id}-{slot}",
                        game_id,
                        q["text"],
                        json.dumps(q["options"]),
                        q["correct_index"],
                        q["difficulty"],
                        q["explanation"],
                        q["source_url"],
                        slot,
                    ),
                )
        else:
            # Keep the researched questions 1-3; drop any leftover 4/5 from a previous game.
            conn.execute("DELETE FROM question WHERE game_id = ? AND slot > 3", (game_id,))
        conn.commit()
    finally:
        conn.close()

    await _start_question(game_id, slot=1)


async def handle_next(game_id: str) -> None:
    """Presenter clicked Next. From the reveal screen this just shows the
    leaderboard; from the leaderboard it moves on (running the difficulty
    check after question 3, or the wrap-up after question 5)."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT stage, current_question FROM game WHERE id = ?", (game_id,)
        ).fetchone()
    finally:
        conn.close()

    stage = row["stage"]
    current = row["current_question"] or 0

    if stage == "reveal":
        conn = get_connection()
        try:
            players = conn.execute(
                "SELECT id, nickname, score FROM player WHERE game_id = ? AND removed = 0 ORDER BY score DESC",
                (game_id,),
            ).fetchall()
        finally:
            conn.close()
        await _show_leaderboard(game_id, players)
    elif current == 3:
        await _run_difficulty_check_and_continue(game_id)
    elif current >= TOTAL_QUESTIONS:
        await _run_wrap_up(game_id)
    else:
        await _start_question(game_id, slot=current + 1)


async def handle_safe_mode(game_id: str) -> None:
    """Presenter clicked Safe Mode: switch every not-yet-played question to
    the safe-mode quiz (no internet or AI needed), without disturbing
    whatever question is currently live."""
    conn = get_connection()
    try:
        game_row = conn.execute(
            "SELECT stage, current_question FROM game WHERE id = ?", (game_id,)
        ).fetchone()
        current = game_row["current_question"] or 0
        safe_quiz = load_safe_mode_quiz()
        for slot in range(1, TOTAL_QUESTIONS + 1):
            if slot <= current:
                continue
            q = safe_quiz[(slot - 1) % len(safe_quiz)]
            conn.execute(
                """INSERT OR REPLACE INTO question
                   (id, game_id, text, options, correct_index, difficulty, explanation, source_url, slot)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    f"{game_id}-{slot}",
                    game_id,
                    q["text"],
                    json.dumps(q["options"]),
                    q["correct_index"],
                    q["difficulty"],
                    q["explanation"],
                    q["source_url"],
                    slot,
                ),
            )
        conn.execute("UPDATE game SET safe_mode = 1 WHERE id = ?", (game_id,))
        if game_row["stage"] == "lobby":
            conn.execute("UPDATE game SET stage = 'ready' WHERE id = ?", (game_id,))
        conn.commit()
    finally:
        conn.close()

    await manager.broadcast_to_host({"type": "safe_mode_on"})


async def handle_pause(game_id: str) -> None:
    """Presenter clicked Pause during a live question: freeze the clock."""
    if game_id in _paused_remaining:
        return  # already paused

    conn = get_connection()
    try:
        game_row = conn.execute(
            "SELECT stage, current_question FROM game WHERE id = ?", (game_id,)
        ).fetchone()
        if game_row["stage"] != "question":
            return
        slot = game_row["current_question"]
        q = conn.execute(
            "SELECT id, ends_at FROM question WHERE game_id = ? AND slot = ?", (game_id, slot)
        ).fetchone()
    finally:
        conn.close()

    task = _timers.get(game_id)
    if task and not task.done():
        task.cancel()

    remaining = max(0.0, (datetime.fromisoformat(q["ends_at"]) - _now()).total_seconds())
    _paused_remaining[game_id] = (q["id"], slot, remaining)
    await manager.broadcast_to_host({"type": "paused"})
    await manager.broadcast_to_players({"type": "paused"})


async def handle_resume(game_id: str) -> None:
    """Presenter clicked Resume: restart the clock with the same time left."""
    pending = _paused_remaining.pop(game_id, None)
    if pending is None:
        return
    question_id, slot, remaining = pending

    ends_at = _now() + timedelta(seconds=remaining)
    conn = get_connection()
    try:
        conn.execute("UPDATE question SET ends_at = ? WHERE id = ?", (_iso(ends_at), question_id))
        conn.commit()
    finally:
        conn.close()

    payload = {"type": "resumed", "ends_at": _iso(ends_at)}
    await manager.broadcast_to_host(payload)
    await manager.broadcast_to_players(payload)

    task = asyncio.create_task(_question_timer(game_id, question_id, slot, remaining))
    _timers[game_id] = task


async def handle_skip(game_id: str) -> None:
    """Presenter clicked Skip question: end it now, same as a timeout."""
    conn = get_connection()
    try:
        game_row = conn.execute(
            "SELECT stage, current_question FROM game WHERE id = ?", (game_id,)
        ).fetchone()
        if game_row["stage"] != "question":
            return
        slot = game_row["current_question"]
        q = conn.execute(
            "SELECT id FROM question WHERE game_id = ? AND slot = ?", (game_id, slot)
        ).fetchone()
    finally:
        conn.close()

    _paused_remaining.pop(game_id, None)
    task = _timers.get(game_id)
    if task and not task.done():
        task.cancel()
    await _end_question(game_id, q["id"], slot)


async def handle_remove_player(game_id: str, player_id: str) -> None:
    """Presenter removed a player from the lobby list with one click."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE player SET removed = 1 WHERE id = ? AND game_id = ?", (player_id, game_id)
        )
        conn.commit()
        player_count = conn.execute(
            "SELECT COUNT(*) AS n FROM player WHERE game_id = ? AND removed = 0", (game_id,)
        ).fetchone()["n"]
    finally:
        conn.close()

    await manager.kick_player(player_id)
    await manager.broadcast_to_host(
        {"type": "player_removed", "player_id": player_id, "player_count": player_count}
    )


async def handle_approval_decision(game_id: str, decision: str) -> None:
    """Presenter clicked Approve or Skip on the drafted winners announcement."""
    if decision not in ("approve", "skip"):
        return
    _approval_decisions[game_id] = decision
    event = _approval_events.get(game_id)
    if event:
        event.set()


async def _run_difficulty_check_and_continue(game_id: str) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE game SET stage = 'difficulty_check' WHERE id = ?", (game_id,))
        conn.commit()
    finally:
        conn.close()

    difficulty, reason = await agent.run_difficulty_check(game_id)

    await manager.broadcast_to_host(
        {"type": "difficulty_banner", "difficulty": difficulty, "reason": reason}
    )
    await asyncio.sleep(4)
    await _start_question(game_id, slot=4)


async def handle_submit_answer(game_id: str, player_id: str, question_id, chosen_index) -> None:
    if question_id is None or chosen_index is None:
        return
    if player_id in _answered.get(game_id, set()):
        return

    conn = get_connection()
    try:
        game_row = conn.execute("SELECT stage FROM game WHERE id = ?", (game_id,)).fetchone()
        q = conn.execute("SELECT * FROM question WHERE id = ?", (question_id,)).fetchone()
        player_row = conn.execute(
            "SELECT removed FROM player WHERE id = ?", (player_id,)
        ).fetchone()
        if q is None or game_row["stage"] != "question":
            return
        if player_row is None or player_row["removed"]:
            return

        ends_at = datetime.fromisoformat(q["ends_at"])
        received_at = _now()
        time_left = max(0.0, (ends_at - received_at).total_seconds())
        is_correct = int(chosen_index) == q["correct_index"]
        points = 500 + round(500 * time_left / QUESTION_SECONDS) if is_correct else 0

        conn.execute(
            """INSERT INTO answer (player_id, question_id, chosen_index, is_correct, received_at, points)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(player_id, question_id) DO NOTHING""",
            (player_id, question_id, int(chosen_index), int(is_correct), _iso(received_at), points),
        )
        if is_correct:
            conn.execute(
                "UPDATE player SET score = score + ?, streak = streak + 1 WHERE id = ?",
                (points, player_id),
            )
        else:
            conn.execute("UPDATE player SET streak = 0 WHERE id = ?", (player_id,))
        conn.commit()

        answered_count = conn.execute(
            "SELECT COUNT(*) AS n FROM answer WHERE question_id = ?", (question_id,)
        ).fetchone()["n"]
        player_count = conn.execute(
            "SELECT COUNT(*) AS n FROM player WHERE game_id = ? AND removed = 0", (game_id,)
        ).fetchone()["n"]
    finally:
        conn.close()

    _answered.setdefault(game_id, set()).add(player_id)

    await manager.broadcast_to_host(
        {"type": "answer_count", "answered": answered_count, "total": player_count}
    )

    if player_count > 0 and answered_count >= player_count:
        task = _timers.get(game_id)
        if task and not task.done():
            task.cancel()
        await _end_question(game_id, question_id, slot=q["slot"])


async def _start_question(game_id: str, slot: int) -> None:
    conn = get_connection()
    try:
        q = conn.execute(
            "SELECT * FROM question WHERE game_id = ? AND slot = ?", (game_id, slot)
        ).fetchone()
        ends_at = _now() + timedelta(seconds=QUESTION_SECONDS)
        conn.execute(
            "UPDATE question SET starts_at = ?, ends_at = ? WHERE id = ?",
            (_iso(_now()), _iso(ends_at), q["id"]),
        )
        conn.execute(
            "UPDATE game SET stage = 'question', current_question = ? WHERE id = ?",
            (slot, game_id),
        )
        conn.commit()
        player_count = conn.execute(
            "SELECT COUNT(*) AS n FROM player WHERE game_id = ? AND removed = 0", (game_id,)
        ).fetchone()["n"]
    finally:
        conn.close()

    _answered[game_id] = set()

    payload = {
        "type": "question_live",
        "question_id": q["id"],
        "slot": slot,
        "total_questions": TOTAL_QUESTIONS,
        "text": q["text"],
        "options": json.loads(q["options"]),
        "ends_at": _iso(ends_at),
        "seconds": QUESTION_SECONDS,
        "player_count": player_count,
    }
    await manager.broadcast_to_host(payload)
    await manager.broadcast_to_players(payload)

    task = asyncio.create_task(_question_timer(game_id, q["id"], slot, QUESTION_SECONDS))
    _timers[game_id] = task


async def _question_timer(game_id: str, question_id: str, slot: int, seconds: int) -> None:
    await asyncio.sleep(seconds)
    await _end_question(game_id, question_id, slot)


async def _end_question(game_id: str, question_id: str, slot: int) -> None:
    conn = get_connection()
    try:
        game_row = conn.execute(
            "SELECT stage, current_question FROM game WHERE id = ?", (game_id,)
        ).fetchone()
        # Guard against a stale timer firing after the question already ended
        # (e.g. everyone answered early and a later question has since started).
        if game_row["stage"] != "question" or game_row["current_question"] != slot:
            return

        q = conn.execute("SELECT * FROM question WHERE id = ?", (question_id,)).fetchone()
        conn.execute("UPDATE game SET stage = 'reveal' WHERE id = ?", (game_id,))
        conn.commit()

        options = json.loads(q["options"])
        counts = [0] * len(options)
        for row in conn.execute(
            "SELECT chosen_index FROM answer WHERE question_id = ?", (question_id,)
        ):
            if row["chosen_index"] is not None and 0 <= row["chosen_index"] < len(counts):
                counts[row["chosen_index"]] += 1

        players = conn.execute(
            "SELECT id, nickname, score, streak FROM player WHERE game_id = ? AND removed = 0 ORDER BY score DESC",
            (game_id,),
        ).fetchall()
        answers_by_player = {
            row["player_id"]: row
            for row in conn.execute(
                "SELECT * FROM answer WHERE question_id = ?", (question_id,)
            )
        }
    finally:
        conn.close()

    stats = {
        "correct_answer": options[q["correct_index"]],
        "correct_count": sum(1 for a in answers_by_player.values() if a["is_correct"]),
        "total_players": len(players),
        "top_scorers_this_round": [
            {
                "nickname": p["nickname"],
                "points": answers_by_player[p["id"]]["points"] if p["id"] in answers_by_player else 0,
                "streak": p["streak"],
            }
            for p in sorted(
                players,
                key=lambda p: answers_by_player[p["id"]]["points"] if p["id"] in answers_by_player else 0,
                reverse=True,
            )[:5]
        ],
        "missed_by": [
            p["nickname"]
            for p in players
            if p["id"] not in answers_by_player or not answers_by_player[p["id"]]["is_correct"]
        ][:5],
    }
    # Reveal and round results go out immediately (no AI call on this path,
    # so this stays well under a second even at load); commentary is
    # generated concurrently and streamed in as its own message once ready,
    # instead of holding up the reveal students are waiting to see.
    await manager.broadcast_to_host(
        {
            "type": "reveal",
            "question_id": question_id,
            "correct_index": q["correct_index"],
            "option_counts": counts,
            "explanation": q["explanation"],
            "source_url": q["source_url"],
        }
    )

    for rank, player in enumerate(players, start=1):
        answer = answers_by_player.get(player["id"])
        await manager.send_to_player_id(
            player["id"],
            {
                "type": "round_result",
                "correct": bool(answer["is_correct"]) if answer else False,
                "points": answer["points"] if answer else 0,
                "score": player["score"],
                "rank": rank,
            },
        )

    async def _send_commentary() -> None:
        commentary = await agent.write_commentary(game_id, slot, stats)
        await manager.broadcast_to_host({"type": "commentary", "commentary": commentary})

    # Fire-and-forget: commentary streams in whenever it's ready, but the
    # presenter controls when to leave the reveal screen (handle_next),
    # not a fixed timer.
    asyncio.create_task(_send_commentary())


async def _show_leaderboard(game_id: str, players: list) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE game SET stage = 'leaderboard' WHERE id = ?", (game_id,))
        conn.commit()
    finally:
        conn.close()

    top10 = [{"nickname": p["nickname"], "score": p["score"]} for p in players[:10]]
    await manager.broadcast_to_host({"type": "leaderboard", "top": top10})


async def _run_wrap_up(game_id: str) -> None:
    """Moment 4: write revision notes, draft the winners announcement, wait
    for the presenter's real Approve/Skip decision, then send each player
    their final rank and the notes for the questions they missed."""
    conn = get_connection()
    try:
        conn.execute("UPDATE game SET stage = 'final' WHERE id = ?", (game_id,))
        conn.commit()
        players = conn.execute(
            "SELECT id, nickname, score FROM player WHERE game_id = ? AND removed = 0 ORDER BY score DESC",
            (game_id,),
        ).fetchall()
    finally:
        conn.close()

    notes, draft = await agent.write_wrap_up(game_id, players)

    conn = get_connection()
    try:
        for slot, note in enumerate(notes, start=1):
            conn.execute(
                "INSERT OR REPLACE INTO revision_note (question_id, note) VALUES (?, ?)",
                (f"{game_id}-{slot}", note),
            )
        approval_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO approval (id, game_id, action, draft, status)
               VALUES (?, ?, 'show_announcement', ?, 'waiting')""",
            (approval_id, game_id, draft),
        )
        conn.execute("UPDATE game SET stage = 'approval' WHERE id = ?", (game_id,))
        conn.commit()
    finally:
        conn.close()

    event = asyncio.Event()
    _approval_events[game_id] = event
    await manager.broadcast_to_host({"type": "approval_request", "draft": draft})

    await event.wait()
    decision = _approval_decisions.pop(game_id, "skip")
    del _approval_events[game_id]

    conn = get_connection()
    try:
        conn.execute(
            "UPDATE approval SET status = ?, decided_at = ? WHERE game_id = ? AND status = 'waiting'",
            (decision, _iso(_now()), game_id),
        )
        conn.execute("UPDATE game SET stage = 'notes' WHERE id = ?", (game_id,))
        conn.commit()
    finally:
        conn.close()

    top10 = [{"nickname": p["nickname"], "score": p["score"]} for p in players[:10]]
    await manager.broadcast_to_host(
        {
            "type": "final",
            "top": top10,
            "announcement": draft if decision == "approve" else None,
        }
    )

    await _send_final_to_players(game_id, players)


async def _send_final_to_players(game_id: str, players: list) -> None:
    conn = get_connection()
    try:
        notes_by_slot = {
            row["slot"]: row["note"]
            for row in conn.execute(
                """SELECT q.slot, r.note FROM revision_note r
                   JOIN question q ON q.id = r.question_id
                   WHERE q.game_id = ?""",
                (game_id,),
            )
        }
        correct_slots_by_player: dict[str, set[int]] = {}
        for row in conn.execute(
            """SELECT q.slot, a.player_id FROM question q
               JOIN answer a ON a.question_id = q.id
               WHERE q.game_id = ? AND a.is_correct = 1""",
            (game_id,),
        ):
            correct_slots_by_player.setdefault(row["player_id"], set()).add(row["slot"])
    finally:
        conn.close()

    all_slots = sorted(notes_by_slot.keys())

    for rank, player in enumerate(players, start=1):
        correct = correct_slots_by_player.get(player["id"], set())
        missed_notes = [notes_by_slot[slot] for slot in all_slots if slot not in correct]
        await manager.send_to_player_id(
            player["id"],
            {
                "type": "final",
                "rank": rank,
                "score": player["score"],
                "notes": missed_notes,
            },
        )
