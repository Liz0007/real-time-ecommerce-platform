"""
Run with: python -m evals.run_evals   (from services/ai-agent-service/)

Checks each test case's actual tool calls against expected ones, and
does a crude keyword check for whether the answer looks like a refusal.
The refusal check is intentionally simple (string matching) rather than
an LLM-as-judge, to keep this fast and free to run — swap in an LLM
grader later if the keyword list starts producing false positives/negatives.

Calls the real services and the real model, so each run costs API tokens
and needs the stack up. Order IDs referenced by test_cases.py must still
exist in order-postgres; a preflight check reports any that don't rather
than letting those cases pass for the wrong reason.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent import run_agent
from app.tools import ORDER_SERVICE_URL, _safe_get
from evals.test_cases import TEST_CASES

# Phrases that mean "I won't/can't answer this kind of question" — scope
# refusals and guardrail declines.
#
# Deliberately excludes data-absence phrasing like "I don't have any
# record of that order": that's a *successful* answer reporting a lookup
# that found nothing (see the nonexistent_order case), not a refusal.
# Keeping "don't have" here would fail that case for behaving correctly.
REFUSAL_MARKERS = [
    "outside my", "outside the scope", "out of scope",
    "can only help", "i can only", "only able to help",
    "can't help", "cannot help", "can't assist", "cannot assist",
    "can't share", "won't share", "can't reveal", "cannot reveal",
    "can't access", "cannot access", "don't have a tool", "no tool",
    "not something i can", "wasn't given access", "don't have access",
]

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)

# Orders the cases deliberately expect NOT to exist.
EXPECTED_MISSING = {"00000000-0000-0000-0000-000000000000"}


def looks_like_refusal(answer: str) -> bool:
    lowered = answer.lower()
    return any(marker in lowered for marker in REFUSAL_MARKERS)


def preflight() -> None:
    """Warns about order IDs referenced by looking at all order IDs mentioned 
    in the test cases, check whether those orders actually exist in the order 
    service, and stop the tests if an expected-to-exist order is missing.
    (e.g. after wiping order-postgres). Those cases would often still
    'pass' — the tool is still called, the agent still doesn't refuse —
    while actually testing 'reports not found' instead of what they mean
    to test."""
    referenced = {
        oid
        for case in TEST_CASES
        for oid in UUID_RE.findall(case["question"])
        if oid.lower() not in EXPECTED_MISSING
    }
    missing = sorted(
        oid for oid in referenced
        if "error" in _safe_get(f"{ORDER_SERVICE_URL}/orders/{oid}", "missing")
    )
    if missing:
        print("WARNING: order IDs in test_cases.py not found in order-service:")
        for oid in missing:
            print(f" {oid}")
        print("Those cases are not testing what they were written to test. "
              "Create fresh orders and update test_cases.py.\n")
        sys.exit(1)

def run():
    preflight()

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
            "tools_ok": tools_ok,
            "refusal_ok": refusal_ok,
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
            # Say which half failed, so a wrong-tools failure isn't
            # confused with a refusal-detection failure.
            reasons = []
            if not r["tools_ok"]:
                reasons.append("tools")
            if not r["refusal_ok"]:
                reasons.append("refusal")
            print(f"   failed on: {', '.join(reasons)}")
            print(f"   answer: {r['answer']}")

    print("-" * 80)
    print(f"{n_passed}/{len(results)} passed")

    sys.exit(0 if n_passed == len(results) else 1)


if __name__ == "__main__":
    run()