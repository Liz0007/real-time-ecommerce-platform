"""
RAG layer: chunk documents, embed them locally with sentence-transformers,
store in Postgres+pgvector, and retrieve the most relevant chunks for a query.

Usage:
    # ingest (or re-sync) a folder of .md/.txt files:
    python -m app.rag ingest ./docs

    # then the agent can call search_knowledge_base(query) as a tool.
"""

import hashlib
import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import psycopg
from langchain_core.tools import tool

if TYPE_CHECKING:  # import only for type checkers, never at runtime
    from sentence_transformers import SentenceTransformer

AGENT_DB_URL = os.getenv(
    "AGENT_DB_URL",
    "postgresql://agent:agent@agent-db:5432/agent_knowledge",
)

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"  # runs locally, no API key needed
# Must match the model's output size. Changing the model to one with a
# different dimension also requires recreating document_chunks, since the
# column type is fixed at vector(EMBEDDING_DIM).
EMBEDDING_DIM = 384

CHUNK_SIZE = 800     # target body characters; the section heading is added afterward,
                     # so stored chunk content can intentionally exceed this
# Only used when a single paragraph is longer than CHUNK_SIZE and has to be
# split mid-paragraph; normal chunks break on paragraph boundaries instead.
CHUNK_OVERLAP = 150

# Bump when chunk_text()'s logic changes, so re-ingestion re-embeds every
# file instead of skipping them as "unchanged". If you add a new setting
# that affects chunk boundaries or content, either include it in
# _fingerprint() or bump this — otherwise unchanged files keep chunks
# built with the old setting.
CHUNKER_VERSION = 1

TOP_K = 3

# Cosine distance cutoff (0 = identical, 2 = opposite). Chunks farther than
# this are treated as "not actually relevant" rather than returned as a
# weak match.
#
# Measured, not guessed: evals/rag_probe.py over the current corpus put
# relevant questions at 0.246-0.643 and irrelevant ones at 0.887-0.994.
# 0.75 sits in the middle of that gap, with margin on both sides. (An
# earlier guess of 0.5 would have rejected five correct retrievals,
# including every bare-identifier query like "insufficient_funds".)
# Re-run the probe after adding documents; the gap can move.
RELEVANCE_THRESHOLD = 0.75

_HEADING_RE = re.compile(r"^#{1,6}\s+\S")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")

_model = None  # lazy-loaded so importing this module doesn't load the model


def get_model() -> "SentenceTransformer":
    """Loads the embedding model on first use.

    sentence-transformers (and torch behind it) is imported here rather
    than at module level so that importing app.rag costs nothing until
    the model is actually needed: the service starts faster when the RAG
    tool goes unused, and the pure-Python parts (chunk_text and friends)
    can be imported and tested without torch installed.
    """
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        dim = model.get_sentence_embedding_dimension()
        if dim != EMBEDDING_DIM:
            raise RuntimeError(
                f"{EMBEDDING_MODEL_NAME} produces {dim}-dim embeddings, but "
                f"EMBEDDING_DIM is {EMBEDDING_DIM}; update it and recreate document_chunks."
            )
        _model = model
    return _model


def init_vector_store() -> None:
    """Creates the pgvector extension and both tables if they don't exist.

    No ivfflat/HNSW index: at this project's scale (a handful of docs, a
    few dozen to low-hundreds of chunks) a sequential scan is fast enough.
    If the corpus grows enough to need one, benchmark HNSW against the
    sequential scan first. IVFFlat in particular must not be built on an
    empty/tiny table, since its clustering comes from the data present at
    build time.
    """
    with psycopg.connect(AGENT_DB_URL) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS document_chunks (
                id SERIAL PRIMARY KEY,
                source TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                embedding vector({EMBEDDING_DIM}) NOT NULL,
                UNIQUE (source, chunk_index)
            );
        """)
        # One row per ingested file: a fingerprint of its content plus the
        # settings that shaped its chunks/embeddings, so re-ingestion can
        # skip files that genuinely haven't changed.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ingested_files (
                source TEXT PRIMARY KEY,
                content_hash TEXT NOT NULL,
                ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
        """)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def _split_sections(text: str) -> list[tuple[str | None, str]]:
    """Splits Markdown into (heading, body) sections. Lines inside fenced
    code blocks are never treated as headings, so a `# comment` in a bash
    snippet doesn't start a new section. Plain text with no headings comes
    back as a single (None, text) section.
    """
    sections: list[tuple[str | None, str]] = []
    heading: str | None = None
    body: list[str] = []
    in_fence = False

    def flush() -> None:
        content = "\n".join(body).strip()
        if content:
            sections.append((heading, content))

    for line in text.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            body.append(line)
        elif not in_fence and _HEADING_RE.match(line):
            flush()
            heading = line.strip()
            body = []
        else:
            body.append(line)
    flush()
    return sections


def _pack_paragraphs(body: str, chunk_size: int, overlap: int) -> list[str]:
    """Packs blank-line-separated paragraphs into ~chunk_size pieces. A
    single paragraph longer than chunk_size is split with a fixed-size
    window (the only place overlap applies)."""
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    pieces: list[str] = []
    current = ""
    for para in paragraphs:
        if len(para) > chunk_size:
            if current:
                pieces.append(current)
                current = ""
            start = 0
            while True:
                pieces.append(para[start:start + chunk_size].strip())
                if start + chunk_size >= len(para):
                    break  # window reached the end; another step would only repeat overlap
                start += chunk_size - overlap
            continue
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) > chunk_size:
            pieces.append(current)
            current = para
        else:
            current = candidate
    if current:
        pieces.append(current)
    return [p for p in pieces if p]


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Section-aware chunking: splits on Markdown headings first, packs each
    section's paragraphs into ~chunk_size pieces, and prefixes every piece
    with its section heading. Without the prefix, a chunk from the middle
    of "## Failed payments" wouldn't say what topic it's about, which
    hurts both retrieval matching and the agent's ability to cite it.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        # overlap >= chunk_size would stop the long-paragraph window from
        # advancing, looping forever.
        raise ValueError("overlap must be >= 0 and < chunk_size")

    chunks: list[str] = []
    for heading, body in _split_sections(text):
        for piece in _pack_paragraphs(body, chunk_size, overlap):
            chunks.append(f"{heading}\n{piece}" if heading else piece)
    return chunks


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

def _fingerprint(text: str) -> str:
    """Hash of the file content AND the settings that shaped its chunks and
    embeddings. Changing the model, chunk size/overlap, or chunker logic
    changes every fingerprint, so re-ingestion re-embeds everything rather
    than keeping chunks built with the old settings."""
    settings = f"{EMBEDDING_MODEL_NAME}|{CHUNK_SIZE}|{CHUNK_OVERLAP}|v{CHUNKER_VERSION}"
    return hashlib.sha256(f"{settings}\n{text}".encode("utf-8")).hexdigest()


def _warn_if_truncated(source: str, chunks: list[str]) -> int:
    """Chunks are sized in characters, but the model reads tokens and
    silently truncates anything past its max sequence length. That limit is
    read from the model at runtime (get_max_seq_length()), not assumed;
    for all-MiniLM-L6-v2 it's currently observed to be 256. Prose at
    CHUNK_SIZE stays well under it, but token-dense text (code, config,
    long identifiers) can exceed it. This measures every chunk and warns
    rather than guessing. Returns the number of chunks that would be
    truncated."""
    model = get_model()
    max_len = model.get_max_seq_length()
    if not max_len:
        return 0
    truncated = 0
    for i, chunk in enumerate(chunks):
        n_tokens = len(model.tokenizer(chunk, add_special_tokens=True)["input_ids"])
        if n_tokens > max_len:
            truncated += 1
            print(f"WARNING {source} chunk {i}: {n_tokens} tokens > model max "
                  f"{max_len}; only the first {max_len} are embedded.")
    return truncated


def ingest_file(path: Path) -> tuple[str, int]:
    """Chunks, embeds, and stores one file. Returns (status, chunk_count),
    where status is "unchanged", "empty", or "ingested".

    Embedding happens before the write transaction opens, so the DB
    connection isn't held idle-in-transaction while the model loads or
    encodes. Existing chunks for the source are replaced, not duplicated.
    """
    text = path.read_text(encoding="utf-8")
    source = path.name
    fingerprint = _fingerprint(text)

    with psycopg.connect(AGENT_DB_URL) as conn:
        row = conn.execute(
            "SELECT content_hash FROM ingested_files WHERE source = %s", (source,)
        ).fetchone()
    if row is not None and row[0] == fingerprint:
        return "unchanged", 0

    chunks = chunk_text(text)
    if chunks:
        _warn_if_truncated(source, chunks)
    embeddings = get_model().encode(chunks).tolist() if chunks else []

    with psycopg.connect(AGENT_DB_URL) as conn:  # commits on clean exit
        conn.execute("DELETE FROM document_chunks WHERE source = %s", (source,))
        if chunks:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO document_chunks (source, chunk_index, content, embedding)
                    VALUES (%s, %s, %s, %s::vector)
                    """,
                    [(source, i, c, e) for i, (c, e) in enumerate(zip(chunks, embeddings))],
                )
        conn.execute(
            """
            INSERT INTO ingested_files (source, content_hash, ingested_at)
            VALUES (%s, %s, now())
            ON CONFLICT (source) DO UPDATE
            SET content_hash = EXCLUDED.content_hash, ingested_at = now()
            """,
            (source, fingerprint),
        )

    return ("ingested", len(chunks)) if chunks else ("empty", 0)


def ingest_directory(dir_path: str) -> int:
    """Syncs the knowledge base with dir_path: ingests new/changed .md/.txt
    files and removes sources that no longer exist on disk. Cleanup runs
    even when the folder is now empty — otherwise deleting every doc would
    leave all of their chunks searchable.

    Returns the number of files that failed to ingest (0 = full success).

    Assumes ONE corpus: sources are stored by filename only, and "stale"
    means "in the database but not in this directory". Ingesting a second,
    different directory would treat the first one's files as deleted and
    remove them. If multiple corpora are ever needed, scope rows by a
    corpus/root key (or store relative paths) before doing that.
    """
    folder = Path(dir_path)
    if not folder.is_dir():
        print(f"Not a directory: {dir_path}")
        sys.exit(1)

    init_vector_store()
    files = sorted(folder.glob("*.md")) + sorted(folder.glob("*.txt"))
    current_sources = {f.name for f in files}

    with psycopg.connect(AGENT_DB_URL) as conn:
        stored = {r[0] for r in conn.execute("SELECT source FROM ingested_files").fetchall()}
        stale = sorted(stored - current_sources)
        for source in stale:
            conn.execute("DELETE FROM document_chunks WHERE source = %s", (source,))
            conn.execute("DELETE FROM ingested_files WHERE source = %s", (source,))
    if stale:
        print(f"Removed {len(stale)} deleted source(s): {', '.join(stale)}")

    if not files:
        print(f"No .md or .txt files found in {dir_path}")
        return 0

    total = 0
    failed: list[str] = []
    for f in files:
        # One unreadable file (e.g. not valid UTF-8) shouldn't abort the
        # whole sync. It's reported and skipped; any chunks it had from a
        # previous successful ingestion are left in place.
        try:
            status, n = ingest_file(f)
        except (UnicodeDecodeError, OSError) as e:
            print(f"FAILED {f.name}: {e.__class__.__name__}: {e}")
            failed.append(f.name)
            continue
        if status == "ingested":
            print(f"Ingested {f.name}: {n} chunks")
        elif status == "empty":
            print(f"Skipped {f.name}: file is empty")
        else:
            print(f"Skipped {f.name}: unchanged")
        total += n
    print(f"Done. {total} chunks (re-)embedded across {len(files)} files"
          + (f", {len(failed)} failed." if failed else "."))
    return len(failed)


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def retrieve(query: str, k: int = TOP_K) -> list[dict]:
    query_embedding = get_model().encode([query])[0].tolist()
    with psycopg.connect(AGENT_DB_URL) as conn:
        rows = conn.execute(
            """
            SELECT source, chunk_index, content, embedding <=> %s::vector AS distance
            FROM document_chunks
            ORDER BY distance
            LIMIT %s
            """,
            (query_embedding, k),
        ).fetchall()
    return [
        {"source": r[0], "chunk_index": r[1], "content": r[2], "distance": round(float(r[3]), 3)}
        for r in rows
    ]


@tool
def search_knowledge_base(query: str) -> list[dict]:
    """Search internal docs/runbooks for information not available via the
    order/payment/inventory tools (e.g. policies, troubleshooting guides,
    how something works). Returns the most relevant text passages found."""
    # Database failures (missing table, unreachable agent-db) become
    # structured tool results rather than exceptions, matching the other
    # tools' _safe_get convention. Model/configuration errors from
    # get_model() intentionally still propagate, so deployment problems
    # aren't hidden behind a "knowledge base unavailable" message.
    try:
        results = retrieve(query)
    except psycopg.errors.UndefinedTable:
        return [{"error": "Knowledge base has not been ingested yet.", "source": None}]
    except psycopg.Error as e:
        return [{"error": f"Knowledge base unavailable ({e.__class__.__name__}).", "source": None}]

    relevant = [r for r in results if r["distance"] < RELEVANCE_THRESHOLD]
    if not relevant:
        return [{"content": "No relevant documents found.", "source": None}]
    return relevant


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "ingest":
        print("Usage: python -m app.rag ingest <directory>")
        sys.exit(1)
    sys.exit(1 if ingest_directory(sys.argv[2]) else 0)