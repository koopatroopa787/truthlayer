import json
import os
import re
from openai import OpenAI
from tavily import TavilyClient


def _parse_json(text: str) -> dict | None:
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    raw = m.group(1) if m else text
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None

_tavily = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
_openai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def run(requirements: str) -> str:
    """Takes a claim (plain text or JSON with 'claim' key), returns fact-check JSON."""
    try:
        req = json.loads(requirements)
        claim = req.get("claim", requirements)
    except (json.JSONDecodeError, TypeError):
        claim = requirements

    results = _tavily.search(claim, search_depth="basic", max_results=5, include_raw_content=False)

    sources = [
        {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
        for r in results.get("results", [])
    ]
    sources_text = "\n".join(f"[{i+1}] {s['title']}\nURL: {s['url']}\n{s['snippet']}" for i, s in enumerate(sources))

    msg = _openai.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=800,
        messages=[{
            "role": "user",
            "content": (
                f"Claim to fact-check: {claim}\n\n"
                f"Evidence sources:\n{sources_text}\n\n"
                "Assess this claim based on the sources. Return ONLY valid JSON:\n"
                '{"claim": "...", "verdict": "supported|refuted|uncertain|unverifiable", '
                '"confidence": 0.0-1.0, '
                '"reasoning": "one sentence", '
                '"supporting_source_indices": [1, 2], '
                '"contradicting_source_indices": [3]}'
            )
        }]
    )

    result = _parse_json(msg.choices[0].message.content) or {"claim": claim, "verdict": "uncertain", "confidence": 0.0, "reasoning": msg.choices[0].message.content, "supporting_source_indices": [], "contradicting_source_indices": []}

    result["sources"] = sources
    return json.dumps(result)
