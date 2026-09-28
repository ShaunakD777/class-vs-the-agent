"""SQLite schema and connection helper.

Only `game` and `player` are used in Phase 1. The rest of the tables from
spec.md's Backend schema are created now so later phases don't need a
migration step, but nothing writes to them yet.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "game.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS game (
    id TEXT PRIMARY KEY,
    topic TEXT,
    stage TEXT NOT NULL DEFAULT 'lobby',
    current_question INTEGER,
    difficulty TEXT,
    difficulty_reason TEXT,
    safe_mode INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    research_notes TEXT,
    mode TEXT NOT NULL DEFAULT 'main'
);

CREATE TABLE IF NOT EXISTS player (
    id TEXT PRIMARY KEY,
    game_id TEXT NOT NULL REFERENCES game(id),
    nickname TEXT NOT NULL,
    device_token TEXT NOT NULL,
    score INTEGER NOT NULL DEFAULT 0,
    streak INTEGER NOT NULL DEFAULT 0,
    removed INTEGER NOT NULL DEFAULT 0,
    joined_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(game_id, nickname)
);

CREATE TABLE IF NOT EXISTS question (
    id TEXT PRIMARY KEY,
    game_id TEXT NOT NULL REFERENCES game(id),
    text TEXT NOT NULL,
    options TEXT NOT NULL,
    correct_index INTEGER NOT NULL,
    difficulty TEXT,
    explanation TEXT,
    source_url TEXT,
    slot INTEGER NOT NULL,
    starts_at TEXT,
    ends_at TEXT
);

CREATE TABLE IF NOT EXISTS answer (
    player_id TEXT NOT NULL REFERENCES player(id),
    question_id TEXT NOT NULL REFERENCES question(id),
    chosen_index INTEGER,
    is_correct INTEGER,
    received_at TEXT,
    points INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (player_id, question_id)
);

CREATE TABLE IF NOT EXISTS revision_note (
    question_id TEXT PRIMARY KEY REFERENCES question(id),
    note TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id TEXT NOT NULL REFERENCES game(id),
    moment TEXT NOT NULL,
    kind TEXT NOT NULL,
    tool TEXT,
    summary TEXT NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS approval (
    id TEXT PRIMARY KEY,
    game_id TEXT NOT NULL REFERENCES game(id),
    action TEXT NOT NULL,
    draft TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'waiting',
    decided_at TEXT
);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        # `mode` ('main' or 'wrap_up') was added after the first version of
        # this table, so a game.db created before then needs it added here;
        # CREATE TABLE IF NOT EXISTS leaves an existing table untouched.
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(game)")]
        if "mode" not in columns:
            conn.execute("ALTER TABLE game ADD COLUMN mode TEXT NOT NULL DEFAULT 'main'")
        conn.commit()
    finally:
        conn.close()
