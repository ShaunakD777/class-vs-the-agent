"""Loads the two ready-made question files, both kept as JSON outside the
code (see spec.md's "Settings kept outside the code") so they can be
edited or swapped without touching Python:

- the safe-mode quiz: runs with no internet or AI, for emergencies.
- the wrap-up quiz bank: the end-of-lecture questions, tagged easy, medium
  or hard, that the wrap-up quiz draws from.
"""

import json
from pathlib import Path

SAFE_MODE_QUIZ_PATH = Path(__file__).resolve().parent.parent / "data" / "safe_mode_quiz.json"
WRAP_UP_QUIZ_PATH = Path(__file__).resolve().parent.parent / "data" / "wrap_up_quiz.json"


def load_safe_mode_quiz() -> list[dict]:
    with open(SAFE_MODE_QUIZ_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_wrap_up_quiz() -> list[dict]:
    with open(WRAP_UP_QUIZ_PATH, encoding="utf-8") as f:
        return json.load(f)
