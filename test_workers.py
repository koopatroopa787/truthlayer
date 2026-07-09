"""Quick smoke-test for research and verify workers. Requires real API keys in .env."""
import json
import os
from dotenv import load_dotenv
load_dotenv() or load_dotenv(".env.example")

def test_research():
    from workers import research
    result = research.run(json.dumps({"query": "What is Bitcoin?", "depth": "basic"}))
    data = json.loads(result)
    assert "summary" in data, f"missing summary: {data}"
    assert "sources" in data, f"missing sources: {data}"
    assert len(data["sources"]) > 0, "no sources returned"
    print(f"research OK — {len(data['sources'])} sources, title={data.get('title','?')!r}")

def test_verify():
    from workers import verify
    result = verify.run("Bitcoin was created in 2009")
    data = json.loads(result)
    assert "verdict" in data, f"missing verdict: {data}"
    assert data["verdict"] in ("supported", "refuted", "uncertain", "unverifiable"), f"bad verdict: {data['verdict']}"
    assert 0.0 <= data.get("confidence", -1) <= 1.0, f"bad confidence: {data}"
    print(f"verify OK — verdict={data['verdict']} confidence={data.get('confidence')}")

if __name__ == "__main__":
    missing = [k for k in ("OPENAI_API_KEY", "TAVILY_API_KEY") if not os.environ.get(k)]
    if missing:
        print(f"SKIP: missing env vars {missing}")
    else:
        test_research()
        test_verify()
        print("all checks passed")
