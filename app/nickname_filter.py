"""A small built-in blocklist for nicknames, checked case-insensitively as
a substring match. Swap BLOCKED_WORDS for a custom list any time."""

BLOCKED_WORDS = [
    "fuck",
    "shit",
    "bitch",
    "asshole",
    "bastard",
    "cunt",
    "dick",
    "piss",
    "slut",
    "whore",
    "nigger",
    "nigga",
    "faggot",
    "retard",
    "rape",
    "nazi",
    "hitler",
]


def contains_blocked_word(nickname: str) -> bool:
    lowered = nickname.lower()
    return any(word in lowered for word in BLOCKED_WORDS)
