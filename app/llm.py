"""Thin wrappers around the two LLM providers. Groq drives the actual
research tool-calling loop; Gemini is only used as a one-shot fallback if
Groq fails, per spec.md: "If Groq's per-minute token limit is hit, send
just that call to Gemini."
"""

import json
import os
import time

from groq import Groq
from google import genai
from google.genai.errors import ServerError

GROQ_MODEL = "openai/gpt-oss-120b"
GEMINI_MODEL = "gemini-3.8-flash"

_groq_client: Groq | None = None
_gemini_client = None


def groq_client() -> Groq:
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _groq_client


def gemini_client():
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _gemini_client


def groq_chat_with_tools(messages: list[dict], tools: list[dict]):
    """One Groq chat-completion turn. Returns the raw message object."""
    response = groq_client().chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        tools=tools,
        tool_choice="auto",
    )
    return response.choices[0].message


def groq_generate_json(prompt: str) -> dict:
    """One plain Groq completion asked to return a single JSON object, no
    tools. Used for commentary and the difficulty check, which don't need
    a search loop."""
    response = groq_client().chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


def gemini_generate_json(prompt: str) -> dict:
    """One Gemini call asked to return a single JSON object. Used only as
    the fallback path when Groq is unavailable. Retries once on a transient
    503 (Gemini reporting it's overloaded), since that clears up quickly."""
    for attempt in range(2):
        try:
            response = gemini_client().models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config={"response_mime_type": "application/json"},
            )
            return json.loads(response.text)
        except ServerError:
            if attempt == 0:
                time.sleep(2)
            else:
                raise
