"""Unit tests for rag.chunk_text — pure Python, no database or model needed."""

import pytest

from app.rag import chunk_text


def test_heading_and_its_paragraph_stay_together():
    chunks = chunk_text("## Refunds\nRefunds take 3-5 days.")
    assert chunks == ["## Refunds\nRefunds take 3-5 days."]


def test_every_chunk_in_a_section_carries_the_heading():
    body = "\n\n".join(["p" * 500] * 3)  # 3 paragraphs, won't fit in one chunk
    chunks = chunk_text(f"## Long section\n{body}", chunk_size=800)
    assert len(chunks) > 1
    assert all(c.startswith("## Long section\n") for c in chunks)


def test_sections_become_separate_chunks():
    chunks = chunk_text("## A\nalpha\n\n## B\nbeta")
    assert chunks == ["## A\nalpha", "## B\nbeta"]


def test_short_paragraphs_pack_up_to_chunk_size():
    paras = ["x" * 300, "y" * 300, "z" * 300]
    chunks = chunk_text("\n\n".join(paras), chunk_size=800)
    # first two fit together (300 + 2 + 300 = 602); adding the third (904) would not
    assert chunks == [f"{paras[0]}\n\n{paras[1]}", paras[2]]


def test_long_paragraph_splits_with_overlap_and_covers_all_text():
    text = "".join(chr(97 + i % 26) for i in range(2000))
    chunks = chunk_text(text, chunk_size=800, overlap=150)
    assert [len(c) for c in chunks] == [800, 800, 700]
    assert chunks[1].startswith(text[650:660])  # second window starts 150 chars back
    assert chunks[-1].endswith(text[-10:])      # nothing dropped at the end


def test_hash_line_inside_code_fence_is_not_a_heading():
    md = "## Runbook\nStep one.\n\n```bash\n# restart the service\ndocker compose restart\n```"
    chunks = chunk_text(md)
    assert len(chunks) == 1
    assert "# restart the service" in chunks[0]


def test_plain_text_without_headings():
    assert chunk_text("first\n\nsecond") == ["first\n\nsecond"]


@pytest.mark.parametrize("text", ["", "   ", "\n\n\t\n"])
def test_empty_or_whitespace_document_yields_no_chunks(text):
    assert chunk_text(text) == []


@pytest.mark.parametrize("chunk_size,overlap", [(0, 0), (-1, 0), (800, 800), (800, 900), (800, -1)])
def test_invalid_settings_raise(chunk_size, overlap):
    with pytest.raises(ValueError):
        chunk_text("anything", chunk_size=chunk_size, overlap=overlap)
