"""A thin wrapper around Tavily so the agent can search the web."""

import asyncio
import os

from tavily import TavilyClient

_client: TavilyClient | None = None


def _get_client() -> TavilyClient:
    global _client
    if _client is None:
        _client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    return _client


async def web_search(query: str, max_results: int = 5) -> list[dict]:
    def _search():
        result = _get_client().search(query, max_results=max_results)
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", ""),
            }
            for r in result.get("results", [])
        ]

    return await asyncio.wait_for(asyncio.to_thread(_search), timeout=5)
