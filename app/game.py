"""The game engine: stages, timer, scoring, reveal and leaderboard, plus the
live agent moments (commentary, difficulty check) hooked in at the right
points. Everything else here is plain server code, no AI.

The same engine also runs the wrap-up quiz (game.mode = 'wrap_up'): 15
questions drawn from wrap_up_quiz.json, with the agent choosing the
difficulty after question 7 and again whenever accuracy drops. Its own
functions are grouped at the bottom of this file.
"""

import asyncio
import json
import random
import uuid
from datetime import datetime, timedelta, timezone

from app import agent
from app.connections import manager
from app.db import get_connection
from app.quiz_data import load_safe_mode_quiz, load_wrap_up_quiz

QUESTION_SECONDS = 20
TOTAL_QUESTIONS = 5

WRAP_UP_TOTAL_QUESTIONS = 15
WRAP_UP_OPENING = [("easy", 3), ("medium", 4)]  # questions 1-7, before the agent looks
WRAP_UP_FIRST_CHECK = 7                          # the agent's first difficulty decision
RETHINK_DROP_POINTS = 15                         # rethink if a question lands this far under average

# The presenter can only switch modes between games, never mid-question.
SWITCHABLE_STAGES = ("lobby", "ready", "notes")

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


def get_mode(game_id: str) -> str:
    conn = get_connection()
    try:
        return conn.execute("SELECT mode FROM game WHERE id = ?", (game_id,)).fetchone()["mode"]
    finally:
        conn.close()


def _total_questions(mode: str) -> int:
    return WRAP_UP_TOTAL_QUESTIONS if mode == "wrap_up" else TOTAL_QUESTIONS


async def handle_start(game_id: str) -> None:
    """Presenter clicked Start. Uses questions 1-3 from a prior research run
    if there are any; otherwise falls back to the hard-coded quiz so the
    game is still playable without the agent (e.g. for testing)."""
    if get_mode(game_id) == "wrap_up":
        await _start_wrap_up_quiz(game_id)
        return

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
    elif get_mode(game_id) == "wrap_up":
        await _next_wrap_up_step(game_id, current)
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
    if get_mode(game_id) == "wrap_up":
        return  # the wrap-up quiz already runs from a ready-made file

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


async def handle_switch_mode(game_id: str) -> None:
    """Presenter clicked the mode button in the header: flip between the main
    game and the wrap-up quiz. Only between games. Joined players stay in;
    everything from the previous game (questions, answers, scores, topic)
    is cleared so the new mode starts fresh from the lobby."""
    conn = get_connection()
    try:
        game_row = conn.execute("SELECT stage, mode FROM game WHERE id = ?", (game_id,)).fetchone()
        if game_row["stage"] not in SWITCHABLE_STAGES:
            return
        new_mode = "main" if game_row["mode"] == "wrap_up" else "wrap_up"

        conn.execute(
            "DELETE FROM answer WHERE question_id IN (SELECT id FROM question WHERE game_id = ?)",
            (game_id,),
        )
        conn.execute(
            "DELETE FROM revision_note WHERE question_id IN (SELECT id FROM question WHERE game_id = ?)",
            (game_id,),
        )
        conn.execute("DELETE FROM question WHERE game_id = ?", (game_id,))
        conn.execute("UPDATE player SET score = 0, streak = 0 WHERE game_id = ?", (game_id,))
        conn.execute(
            """UPDATE game SET mode = ?, stage = 'lobby', current_question = NULL, topic = NULL,
                   research_notes = NULL, difficulty = NULL, difficulty_reason = NULL, safe_mode = 0
               WHERE id = ?""",
            (new_mode, game_id),
        )
        conn.commit()
    finally:
        conn.close()

    payload = {"type": "mode_changed", "mode": new_mode}
    await manager.broadcast_to_host(payload)
    await manager.broadcast_to_players(payload)


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
        mode = conn.execute("SELECT mode FROM game WHERE id = ?", (game_id,)).fetchone()["mode"]
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
        "total_questions": _total_questions(mode),
        "mode": mode,
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
            "SELECT stage, current_question, mode FROM game WHERE id = ?", (game_id,)
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

    # The wrap-up quiz has no commentary: its only agent moment is choosing
    # the difficulty.
    if game_row["mode"] == "wrap_up":
        return

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


# ---------------------------------------------------------------------------
# Wrap-up quiz. All plain server code except for one agent call,
# agent.choose_wrap_up_difficulty, made after question 7 and again whenever
# a question lands well under the class average.

# If the chosen level has run out of questions, take the nearest one that hasn't.
FALLBACK_ORDER = {
    "easy": ["easy", "medium", "hard"],
    "medium": ["medium", "easy", "hard"],
    "hard": ["hard", "medium", "easy"],
}


def _insert_question(conn, game_id: str, slot: int, q: dict) -> None:
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


async def _start_wrap_up_quiz(game_id: str) -> None:
    """Start in wrap-up mode: clear the last game, then draw questions 1-7
    at random from the bank (3 easy, then 4 medium)."""
    bank = load_wrap_up_quiz()
    opening = []
    for level, count in WRAP_UP_OPENING:
        opening += random.sample([q for q in bank if q["difficulty"] == level], count)

    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM answer WHERE question_id IN (SELECT id FROM question WHERE game_id = ?)",
            (game_id,),
        )
        conn.execute(
            "DELETE FROM revision_note WHERE question_id IN (SELECT id FROM question WHERE game_id = ?)",
            (game_id,),
        )
        conn.execute("DELETE FROM question WHERE game_id = ?", (game_id,))
        conn.execute("UPDATE player SET score = 0, streak = 0 WHERE game_id = ?", (game_id,))
        for slot, q in enumerate(opening, start=1):
            _insert_question(conn, game_id, slot, q)
        conn.execute(
            "UPDATE game SET difficulty = 'medium', difficulty_reason = NULL WHERE id = ?",
            (game_id,),
        )
        conn.commit()
    finally:
        conn.close()

    await _start_question(game_id, slot=1)


def _wrap_up_results(game_id: str) -> list[dict]:
    """How many answered, and how many got it right, on each question played so far."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT q.slot, q.difficulty, COUNT(a.player_id) AS answered,
                      COALESCE(SUM(a.is_correct), 0) AS correct
               FROM question q LEFT JOIN answer a ON a.question_id = q.id
               WHERE q.game_id = ? AND q.starts_at IS NOT NULL
               GROUP BY q.slot ORDER BY q.slot""",
            (game_id,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def _pct(correct: int, answered: int) -> int:
    return round(100 * correct / answered) if answered else 0


async def _next_wrap_up_step(game_id: str, current: int) -> None:
    """Next on the leaderboard in wrap-up mode. Decides, in plain code,
    whether the agent needs to wake up before the next question."""
    if current >= WRAP_UP_TOTAL_QUESTIONS:
        await _finish_wrap_up_quiz(game_id)
        return
    if current < WRAP_UP_FIRST_CHECK:
        await _start_question(game_id, slot=current + 1)  # already drawn at Start
        return

    results = _wrap_up_results(game_id)

    if current == WRAP_UP_FIRST_CHECK:
        accuracy = _pct(sum(r["correct"] for r in results), sum(r["answered"] for r in results))
        await _choose_wrap_up_difficulty(
            game_id,
            trigger=f"Reading how the class did on questions 1-{current}.",
            results=results,
            accuracy=accuracy,
            evidence=f"of answers were right on questions 1–{current}.",
        )
    else:
        last, earlier = results[-1], results[:-1]
        earlier_answered = sum(r["answered"] for r in earlier)
        if last["answered"] and earlier_answered:
            last_pct = _pct(last["correct"], last["answered"])
            average = _pct(sum(r["correct"] for r in earlier), earlier_answered)
            if average - last_pct >= RETHINK_DROP_POINTS:
                await _choose_wrap_up_difficulty(
                    game_id,
                    trigger=(
                        f"Q{current} came in at {last_pct}%, well under the {average}% "
                        "average. Rethinking the difficulty."
                    ),
                    results=results,
                    accuracy=last_pct,
                    evidence=f"got question {current} right, against a {average}% average before it.",
                )

    await _start_wrap_up_question(game_id, slot=current + 1)


def _unused_questions(game_id: str) -> list[dict]:
    conn = get_connection()
    try:
        used = {row["text"] for row in conn.execute("SELECT text FROM question WHERE game_id = ?", (game_id,))}
    finally:
        conn.close()
    return [q for q in load_wrap_up_quiz() if q["text"] not in used]


async def _choose_wrap_up_difficulty(
    game_id: str, trigger: str, results: list[dict], accuracy: int, evidence: str
) -> None:
    """Wake the agent to choose the level, then show its decision on the dial."""
    conn = get_connection()
    try:
        previous = conn.execute("SELECT difficulty FROM game WHERE id = ?", (game_id,)).fetchone()["difficulty"]
        conn.execute("UPDATE game SET stage = 'difficulty_check' WHERE id = ?", (game_id,))
        conn.commit()
    finally:
        conn.close()
    previous = previous or "medium"

    questions_left = {level: 0 for level in FALLBACK_ORDER}
    for q in _unused_questions(game_id):
        questions_left[q["difficulty"]] += 1

    difficulty, reason = await agent.choose_wrap_up_difficulty(
        game_id, trigger, results, accuracy, previous, questions_left
    )

    conn = get_connection()
    try:
        conn.execute(
            "UPDATE game SET difficulty = ?, difficulty_reason = ? WHERE id = ?",
            (difficulty, reason, game_id),
        )
        conn.commit()
    finally:
        conn.close()

    await manager.broadcast_to_host(
        {
            "type": "difficulty_banner",
            "difficulty": difficulty,
            "reason": reason,
            "previous": previous,
            "accuracy": accuracy,
            "evidence": evidence,
        }
    )
    await asyncio.sleep(4)


async def _start_wrap_up_question(game_id: str, slot: int) -> None:
    """Draw a random unused question at the current difficulty and start it."""
    conn = get_connection()
    try:
        level = conn.execute("SELECT difficulty FROM game WHERE id = ?", (game_id,)).fetchone()["difficulty"]
    finally:
        conn.close()
    level = level or "medium"

    unused = _unused_questions(game_id)
    for candidate in FALLBACK_ORDER[level]:
        pool = [q for q in unused if q["difficulty"] == candidate]
        if pool:
            break
    if candidate != level:
        await agent.log_event(
            game_id, "difficulty", "thought", None,
            f"No {agent.LEVEL_NAMES[level]} questions left, using {agent.LEVEL_NAMES[candidate]} instead.",
        )

    conn = get_connection()
    try:
        _insert_question(conn, game_id, slot, random.choice(pool))
        conn.commit()
    finally:
        conn.close()

    await _start_question(game_id, slot)


async def _finish_wrap_up_quiz(game_id: str) -> None:
    """End of the wrap-up quiz. No agent call and no approval step: the
    revision notes are built straight from each question's answer and
    explanation, then the final screen and phones update right away."""
    conn = get_connection()
    try:
        players = conn.execute(
            "SELECT id, nickname, score FROM player WHERE game_id = ? AND removed = 0 ORDER BY score DESC",
            (game_id,),
        ).fetchall()
        for q in conn.execute("SELECT * FROM question WHERE game_id = ?", (game_id,)).fetchall():
            answer = json.loads(q["options"])[q["correct_index"]]
            note = f"{q['text']} Answer: {answer}. {q['explanation']}".strip()
            conn.execute(
                "INSERT OR REPLACE INTO revision_note (question_id, note) VALUES (?, ?)",
                (q["id"], note),
            )
        conn.execute("UPDATE game SET stage = 'notes' WHERE id = ?", (game_id,))
        conn.commit()
    finally:
        conn.close()

    top10 = [{"nickname": p["nickname"], "score": p["score"]} for p in players[:10]]
    await manager.broadcast_to_host({"type": "final", "top": top10, "announcement": None})
    await _send_final_to_players(game_id, players)
