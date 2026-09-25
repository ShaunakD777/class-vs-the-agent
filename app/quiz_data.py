"""Loads the safe-mode quiz: a ready-made set of questions that runs with
no internet or AI, for emergencies. Kept as a JSON file outside the code
(see spec.md's "Settings kept outside the code") so it can be edited or
swapped without touching Python.
"""

import json
from pathlib import Path

SAFE_MODE_QUIZ_PATH = Path(__file__).resolve().parent.parent / "safe_mode_quiz.json"


def load_safe_mode_quiz() -> list[dict]:
    with open(SAFE_MODE_QUIZ_PATH, encoding="utf-8") as f:
        return json.load(f)
