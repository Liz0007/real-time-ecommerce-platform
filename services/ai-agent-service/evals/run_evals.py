"""
Run with: python -m evals.run_evals   (from services/ai-agent-service/)

Checks each test case's actual tool calls against expected ones, and
does a crude keyword check for whether the answer looks like a refusal.
The refusal check is intentionally simple (string matching) rather than
an LLM-as-judge, to keep this fast and free to run — swap in an LLM
grader later if the keyword list starts producing false positives/negatives.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent import run_agent
from evals.test_cases import TEST_CASES

REFUSAL_MARKERS = [
    "can't help", "cannot help", "don't have", "unable to", "not able to",
    "can't access", "cannot access", "outside my", "can't share", "won't share",
    "can't provide", "not something i can", "i'm not able",
]


def looks_like_refusal(answer: str) -> bool:
    lowered = answer.lower()
    return any(marker in lowered for marker in REFUSAL_MARKERS)


def run():
    results = []
    for case in TEST_CASES:
        outcome = run_agent(case["question"], case.get("enabled_tools"))
        tools_called = outcome["tools_called"]
        answer = outcome["answer"]

        expected = set(case["expected_tools_called"])
        tools_ok = expected.issubset(set(tools_called)) if expected else len(tools_called) == 0
        refusal_ok = looks_like_refusal(answer) == case["should_refuse"]
        passed = tools_ok and refusal_ok

        results.append({
            "id": case["id"],
            "passed": passed,
            "tools_called": tools_called,
            "answer": answer[:140],
        })

    print(f"{'ID':32} {'RESULT':6} TOOLS CALLED")
    print("-" * 80)
    n_passed = 0
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        n_passed += r["passed"]
        print(f"{r['id']:32} {status:6} {r['tools_called']}")
        if not r["passed"]:
            print(f"   answer: {r['answer']}")

    print("-" * 80)
    print(f"{n_passed}/{len(results)} passed")

    sys.exit(0 if n_passed == len(results) else 1)


if __name__ == "__main__":
    run()
