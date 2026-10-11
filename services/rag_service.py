"""
RAG léger sur les documents de l'institut (règlement, procédures, guides...).
Amélioration : stopwords FR/EN + normalisation des accents, pour que
« règlement » et « reglement » se correspondent et que les mots vides
(« comment », « quelle »...) ne faussent plus le score.
"""
import re
import unicodedata
from collections import Counter
from typing import Optional

_WORD_RE = re.compile(r"[a-zA-ZÀ-ÿ0-9]+")
CHUNK_SIZE = 700
CHUNK_OVERLAP = 100

_STOP = {
    "le", "la", "les", "des", "une", "est", "que", "qui", "quoi", "quel", "quelle",
    "quels", "quelles", "comment", "pour", "avec", "dans", "sur", "mon", "mes",
    "ces", "cette", "aux", "par", "pas", "ont", "sont", "elle", "nous", "vous",
    "the", "and", "for", "with", "what", "how", "does", "are", "this", "that",
    "can", "you", "your", "from", "have", "has", "was", "were", "who", "when",
}


def _norm(text: str) -> str:
    return unicodedata.normalize("NFD", text.lower()).encode("ascii", "ignore").decode()


def _tokenize(text: str) -> Counter:
    words = (_norm(w) for w in _WORD_RE.findall(text))
    return Counter(w for w in words if len(w) > 2 and w not in _STOP)


def chunk_text(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    chunks, start = [], 0
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
        cur.executemany(
            "INSERT INTO chatbot_document_chunks (document_id, chunk_index, chunk_text) VALUES (%s, %s, %s)",
            [(document_id, i, c) for i, c in enumerate(chunk_text(content))],
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


def search_documents(conn, query: str, top_k: int = 3, min_score: float = 0.25) -> list[dict]:
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
        overlap = len((q_tokens.keys() & chunk_tokens.keys()))
        score = overlap / len(q_tokens)
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
    # même format que search_documents (clé "text") pour llm_service
    return [{"title": r["title"], "text": r["chunk_text"], "score": 1.0} for r in rows] or None