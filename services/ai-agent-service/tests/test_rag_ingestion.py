"""Integration tests for incremental ingestion and search failure behavior.

Runs against a real Postgres+pgvector, but in a separate database
(agent_knowledge_test) so it never touches the real knowledge base. Uses a
fake embedding model, so these tests check the ingestion/sync logic, not
retrieval quality (that's what evals/rag_probe.py is for).

Requires agent-db to be running and reachable, e.g. from the host:
    RAG_TEST_ADMIN_URL=postgresql://agent:<password>@localhost:5433/agent_knowledge pytest tests/
Skipped automatically if the database can't be reached.
"""

import hashlib
import os

import numpy as np
import psycopg
import pytest

from app import rag

ADMIN_URL = os.getenv(
    "RAG_TEST_ADMIN_URL",
    "postgresql://agent:agent@localhost:5433/agent_knowledge",
)
TEST_DB = "agent_knowledge_test"


class FakeModel:
    """Deterministic stand-in for SentenceTransformer: each distinct text
    maps to its own one-hot vector, so identical text has distance 0 and
    different text has distance 1."""

    def get_sentence_embedding_dimension(self):
        return rag.EMBEDDING_DIM

    # Crude tokenizer (one token per whitespace-separated word) so the
    # truncation check can be exercised without the real model.
    def get_max_seq_length(self):
        return 256

    def tokenizer(self, text, add_special_tokens=True):
        return {"input_ids": text.split()}

    def encode(self, texts):
        vectors = np.zeros((len(texts), rag.EMBEDDING_DIM), dtype="float32")
        for row, text in enumerate(texts):
            slot = int(hashlib.sha256(text.encode()).hexdigest(), 16) % rag.EMBEDDING_DIM
            vectors[row, slot] = 1.0
        return vectors


@pytest.fixture(scope="session")
def test_db_url():
    try:
        with psycopg.connect(ADMIN_URL, autocommit=True, connect_timeout=3) as conn:
            exists = conn.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)
            ).fetchone()
            if not exists:
                conn.execute(f'CREATE DATABASE "{TEST_DB}"')
    except psycopg.OperationalError as e:
        pytest.skip(f"agent-db not reachable at {ADMIN_URL}: {e}")
    return ADMIN_URL.rsplit("/", 1)[0] + f"/{TEST_DB}"


@pytest.fixture
def docs(test_db_url, monkeypatch, tmp_path):
    """Fresh, empty test database + fake model + empty docs folder per test."""
    monkeypatch.setattr(rag, "AGENT_DB_URL", test_db_url)
    monkeypatch.setattr(rag, "_model", FakeModel())
    with psycopg.connect(test_db_url) as conn:
        conn.execute("DROP TABLE IF EXISTS document_chunks, ingested_files")
    return tmp_path


def chunk_counts() -> dict[str, int]:
    with psycopg.connect(rag.AGENT_DB_URL) as conn:
        rows = conn.execute(
            "SELECT source, count(*) FROM document_chunks GROUP BY source"
        ).fetchall()
    return dict(rows)


TWO_SECTIONS = "## A\nalpha\n\n## B\nbeta"


# --- incremental ingestion --------------------------------------------------

def test_new_file_is_ingested(docs):
    f = docs / "faq.md"
    f.write_text(TWO_SECTIONS)
    rag.init_vector_store()
    assert rag.ingest_file(f) == ("ingested", 2)
    assert chunk_counts() == {"faq.md": 2}


def test_unchanged_file_is_skipped(docs):
    f = docs / "faq.md"
    f.write_text(TWO_SECTIONS)
    rag.init_vector_store()
    rag.ingest_file(f)
    assert rag.ingest_file(f) == ("unchanged", 0)
    assert chunk_counts() == {"faq.md": 2}


def test_modified_file_replaces_old_chunks(docs):
    f = docs / "faq.md"
    f.write_text(TWO_SECTIONS)
    rag.init_vector_store()
    rag.ingest_file(f)
    f.write_text("## A\nonly one section now")
    assert rag.ingest_file(f) == ("ingested", 1)
    assert chunk_counts() == {"faq.md": 1}  # replaced, not 3


def test_file_emptied_out_removes_its_chunks(docs):
    f = docs / "faq.md"
    f.write_text(TWO_SECTIONS)
    rag.init_vector_store()
    rag.ingest_file(f)
    f.write_text("   \n")
    assert rag.ingest_file(f) == ("empty", 0)
    assert chunk_counts() == {}


def test_deleted_file_is_removed_on_sync(docs):
    (docs / "keep.md").write_text(TWO_SECTIONS)
    (docs / "gone.md").write_text("## X\nsoon deleted")
    assert rag.ingest_directory(str(docs)) == 0
    (docs / "gone.md").unlink()
    rag.ingest_directory(str(docs))
    assert chunk_counts() == {"keep.md": 2}


def test_deleting_every_file_empties_the_knowledge_base(docs):
    (docs / "faq.md").write_text(TWO_SECTIONS)
    rag.ingest_directory(str(docs))
    (docs / "faq.md").unlink()
    rag.ingest_directory(str(docs))
    assert chunk_counts() == {}
    with psycopg.connect(rag.AGENT_DB_URL) as conn:
        assert conn.execute("SELECT count(*) FROM ingested_files").fetchone()[0] == 0


def test_chunker_version_bump_forces_reingestion(docs, monkeypatch):
    f = docs / "faq.md"
    f.write_text(TWO_SECTIONS)
    rag.init_vector_store()
    rag.ingest_file(f)
    monkeypatch.setattr(rag, "CHUNKER_VERSION", rag.CHUNKER_VERSION + 1)
    assert rag.ingest_file(f) == ("ingested", 2)


def test_unreadable_file_does_not_abort_the_sync(docs):
    (docs / "bad.md").write_bytes(b"\xff\xfe\x00 not utf-8 \x80")
    (docs / "good.md").write_text(TWO_SECTIONS)
    assert rag.ingest_directory(str(docs)) == 1  # one failure reported
    assert chunk_counts() == {"good.md": 2}      # the rest still ingested


def test_token_dense_chunk_is_flagged(docs, capsys):
    max_len = FakeModel().get_max_seq_length()
    f = docs / "dense.md"
    # Few characters (fits one chunk) but more "tokens" than the model limit.
    f.write_text("## Dense\n" + "a " * (max_len + 50))
    rag.init_vector_store()
    assert rag.ingest_file(f) == ("ingested", 1)
    assert f"only the first {max_len} are embedded" in capsys.readouterr().out


# --- search failure behavior -------------------------------------------------

def _search(query: str) -> list[dict]:
    return rag.search_knowledge_base.invoke({"query": query})


def test_search_before_any_ingestion_reports_missing_table(docs):
    result = _search("anything")
    assert result[0]["source"] is None
    assert "not been ingested" in result[0]["error"]


def test_search_with_database_unreachable_returns_error(docs, monkeypatch):
    monkeypatch.setattr(rag, "AGENT_DB_URL", "postgresql://agent:agent@localhost:1/nope")
    result = _search("anything")
    assert "unavailable" in result[0]["error"]


def test_search_on_empty_knowledge_base(docs):
    rag.init_vector_store()
    assert _search("anything") == [{"content": "No relevant documents found.", "source": None}]


def test_search_returns_matching_chunk(docs):
    (docs / "faq.md").write_text(TWO_SECTIONS)
    rag.ingest_directory(str(docs))
    # With the fake model, an identical string has distance 0.
    result = _search("## B\nbeta")
    assert result[0]["source"] == "faq.md"
    assert result[0]["content"] == "## B\nbeta"
    assert result[0]["chunk_index"] == 1
    assert result[0]["distance"] == 0.0
