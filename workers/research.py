import json
import os
import re
from openai import OpenAI
from tavily import TavilyClient


def _parse_json(text: str) -> dict | None:
    # strip markdown code fences if present
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    raw = m.group(1) if m else text
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None

_tavily = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
_openai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def run(requirements: str) -> str:
    """Takes requirements JSON or plain text query, returns structured research report JSON."""
    try:
        req = json.loads(requirements)
        query = req.get("query", requirements)
        depth = req.get("depth", "basic")
    except (json.JSONDecodeError, TypeError):
        query = requirements
        depth = "basic"

    search_depth = "advanced" if depth == "deep" else "basic"
    results = _tavily.search(query, search_depth=search_depth, max_results=6, include_raw_content=False)

    sources = [
        {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
        for r in results.get("results", [])
    ]
    sources_text = "\n".join(f"[{i+1}] {s['title']}\nURL: {s['url']}\n{s['snippet']}" for i, s in enumerate(sources))

    msg = _openai.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=1500,
        messages=[{
            "role": "user",
            "content": (
                f"Research query: {query}\n\n"
                f"Sources:\n{sources_text}\n\n"
                "Write a concise research report. Return ONLY valid JSON:\n"
                '{"title": "...", "summary": "2-3 paragraph synthesis", '
                '"key_findings": ["finding1", "finding2", ...], '
                '"citations": [{"claim": "...", "source_index": 1}, ...]}'
            )
        }]
    )

    report = _parse_json(msg.choices[0].message.content) or {"title": query, "summary": msg.choices[0].message.content, "key_findings": [], "citations": []}

    report["sources"] = sources
    return json.dumps(report)
