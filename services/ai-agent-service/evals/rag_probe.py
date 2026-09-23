"""Records real retrieval distances for representative questions, so
RELEVANCE_THRESHOLD can be set from measurements instead of guessed.

Uses the real embedding model and the real ingested knowledge base, and
applies NO threshold, so you can see where relevant and irrelevant
questions actually land. Run from services/ai-agent-service after
ingesting docs/:

    AGENT_DB_URL=postgresql://agent:<password>@localhost:5433/agent_knowledge \
        python -m evals.rag_probe

Add a probe whenever you add a doc or see the agent retrieve badly.
"""

from app.rag import RELEVANCE_THRESHOLD, retrieve

# (question, heading the top result should come from — or None if nothing
# in the knowledge base should match)
PROBES = [
    ("What are the possible order statuses?", "## Order statuses"),
    ("When does an order become confirmed?", "## Order statuses"),
    ("Does inventory get checked before payment?", "## Payment and inventory checks run in parallel"),
    ("Why might a payment fail?", "## Failed payments"),
    ("Is there a retry window after a failed payment?", "## Failed payments"),
    ("How long is stock held for an order?", "## Inventory reservations"),
    ("Are expired reservations released automatically?", "## Inventory reservations"),
    # Exact-term lookups: semantic embeddings can miss literal identifiers.
    # If these come back MISS, that's the evidence for adding Postgres
    # full-text search alongside pgvector (hybrid retrieval).
    ("What does card_declined mean?", "## Failed payments"),
    ("insufficient_funds", "## Failed payments"),
    ("provider_timeout", "## Failed payments"),
    ("Can a customer cancel their order?", "## Cancellations and refunds"),
    ("How do I get a refund?", "## Cancellations and refunds"),
    ("What's the capital of Peru?", None),
    ("How do I reset my password?", None),
    ("Write me a poem about the ocean.", None),
]


def _heading(content: str) -> str:
    first = content.splitlines()[0] if content else ""
    return first if first.startswith("#") else "(no heading)"


def main() -> None:
    relevant_top, irrelevant_top = [], []
    print(f"{'dist':>6}  {'ok':<4}  question  ->  top section")
    print("-" * 90)
    for question, expected in PROBES:
        hits = retrieve(question, k=1)
        if not hits:
            print(f"{'-':>6}  {'??':<4}  {question}  ->  (knowledge base is empty)")
            continue
        top = hits[0]
        got = _heading(top["content"])
        if expected is None:
            irrelevant_top.append(top["distance"])
            mark = "-"
        else:
            relevant_top.append(top["distance"])
            mark = "OK" if got == expected else "MISS"
        print(f"{top['distance']:>6.3f}  {mark:<4}  {question}  ->  {got}")

    print("-" * 90)
    if relevant_top and irrelevant_top:
        worst_relevant = max(relevant_top)
        best_irrelevant = min(irrelevant_top)
        print(f"Relevant questions:   top-hit distance {min(relevant_top):.3f} – {worst_relevant:.3f}")
        print(f"Irrelevant questions: top-hit distance {best_irrelevant:.3f} – {max(irrelevant_top):.3f}")
        print(f"Current RELEVANCE_THRESHOLD = {RELEVANCE_THRESHOLD}")
        if worst_relevant < best_irrelevant:
            print(f"Separable: any threshold between {worst_relevant:.3f} and "
                  f"{best_irrelevant:.3f} keeps every relevant hit and rejects every irrelevant one.")
        else:
            print("Not cleanly separable: some irrelevant question scores closer than a relevant one. "
                  "Look at those cases before picking a threshold.")


if __name__ == "__main__":
    main()
