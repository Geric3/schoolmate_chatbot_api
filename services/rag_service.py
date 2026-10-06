"""
Retrieval-augmented answers over admin-uploaded institute documents
(reglement interieur, procedures, guides, etc.).

Storage: `chatbot_documents` (one row per uploaded document) +
`chatbot_document_chunks` (its text split into ~700-char overlapping
chunks).

Deliberately dependency-light: no embeddings/vector DB, just a TF-style
word-overlap score over chunks. This is enough for a few dozen documents of
a few pages each and keeps the app deployable on a free Render/
PythonAnywhere instance with no extra native libraries. It can be swapped
for a real vector store later without touching the rest of the app - only
`search_documents` would need to change.
"""
import re
from collections import Counter
from typing import Optional

_WORD_RE = re.compile(r"[a-zA-ZÀ-ÿ0-9]+")
CHUNK_SIZE = 700  # characters
CHUNK_OVERLAP = 100


def _tokenize(text: str) -> Counter:
    return Counter(w.lower() for w in _WORD_RE.findall(text) if len(w) > 2)


def chunk_text(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - CHUNK_OVERLAP
    return chunks or [text]


def create_document(conn, title: str, content: str, uploaded_by: Optional[int] = None) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO chatbot_documents (title, uploaded_by, created_at) VALUES (%s, %s, NOW())",
            (title, uploaded_by),
        )
        document_id = cur.lastrowid
        chunks = chunk_text(content)
        cur.executemany(
            "INSERT INTO chatbot_document_chunks (document_id, chunk_index, chunk_text) VALUES (%s, %s, %s)",
            [(document_id, i, c) for i, c in enumerate(chunks)],
        )
    return document_id


def list_documents(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT d.id, d.title, d.created_at, COUNT(c.id) AS chunk_count
               FROM chatbot_documents d
               LEFT JOIN chatbot_document_chunks c ON c.document_id = d.id
               GROUP BY d.id, d.title, d.created_at
               ORDER BY d.created_at DESC"""
        )
        return cur.fetchall()


def delete_document(conn, document_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM chatbot_documents WHERE id = %s", (document_id,))
        # chatbot_document_chunks rows are removed via ON DELETE CASCADE, see migration


def search_documents(conn, query: str, top_k: int = 3, min_score: float = 0.15) -> list[dict]:
    q_tokens = _tokenize(query)
    if not q_tokens:
        return []

    with conn.cursor() as cur:
        cur.execute(
            """SELECT d.title, c.chunk_text FROM chatbot_document_chunks c
               JOIN chatbot_documents d ON d.id = c.document_id"""
        )
        rows = cur.fetchall()

    scored = []
    for row in rows:
        chunk_tokens = _tokenize(row["chunk_text"])
        if not chunk_tokens:
            continue
        overlap = sum((q_tokens & chunk_tokens).values())
        score = overlap / max(len(q_tokens), 1)
        if score >= min_score:
            scored.append({"title": row["title"], "text": row["chunk_text"], "score": round(score, 2)})

    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:top_k]


def get_document_by_title_fragment(conn, fragment: str) -> Optional[list[dict]]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT d.title, c.chunk_text FROM chatbot_document_chunks c
               JOIN chatbot_documents d ON d.id = c.document_id
               WHERE d.title LIKE %s ORDER BY c.chunk_index LIMIT 6""",
            (f"%{fragment}%",),
        )
        rows = cur.fetchall()
    return rows or None
