"""
Réponses augmentées par les documents de l'institut (règlement, procédures, guides...).

Recherche sans dépendance lourde : mots normalisés (sans accents ni pluriels) et
pondération TF-IDF simplifiée -> un mot rare (« redoublement ») compte plus qu'un mot
courant (« institut »), ce qui retrouve beaucoup mieux le bon passage.
"""
import math
import re
import unicodedata
from collections import Counter
from typing import Optional

_WORD_RE = re.compile(r"[a-zA-ZÀ-ÿ0-9]+")
CHUNK_SIZE = 700
CHUNK_OVERLAP = 100

_STOP = {
    "les", "des", "une", "est", "sont", "que", "qui", "quoi", "quel", "quels", "quelle",
    "quelles", "comment", "pour", "avec", "dans", "sur", "mon", "mes", "ces", "cette", "aux",
    "par", "pas", "ont", "elle", "nous", "vous", "voudrais", "veux", "peux", "svp",
    "bonjour", "bonsoir", "salut",
    "the", "and", "for", "with", "what", "how", "does", "are", "this", "that", "can", "you",
    "your", "from", "have", "has", "was", "were", "who", "when", "please", "hello",
}


def _norm(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


_STOP = {_norm(w) for w in _STOP}


def _stem(word: str) -> str:
    if len(word) > 4 and word.endswith(("s", "x")):
        return word[:-1]
    return word


def _tokenize(text: str) -> Counter:
    words = (_norm(w) for w in _WORD_RE.findall(text))
    return Counter(_stem(w) for w in words if len(w) > 2 and w not in _STOP)


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


def rank_chunks(rows: list[dict], query: str, top_k: int = 3, min_score: float = 0.3,
                relative_min: float = 0.0) -> list[dict]:
    """Classe les passages (fonction pure, testable sans base de données)."""
    q_tokens = set(_tokenize(query))
    if not q_tokens or not rows:
        return []

    n = len(rows)
    token_sets = [set(_tokenize(r["chunk_text"])) for r in rows]
    df = Counter()
    for ts in token_sets:
        df.update(ts)

    # Poids IDF ; un mot de la question absent de tous les documents compte pour moitié
    weights = {t: math.log(1 + n / (1 + df[t])) * (1.0 if df[t] else 0.5) for t in q_tokens}
    total = sum(weights.values())
    if total <= 0:
        return []

    scored = []
    for row, ts in zip(rows, token_sets):
        score = sum(weights[t] for t in q_tokens if t in ts) / total
        if score >= min_score:
            scored.append({
                "id": row.get("id"), "doc_id": row.get("document_id"),
                "chunk_index": row.get("chunk_index", 0),
                "title": row["title"], "text": row["chunk_text"], "score": round(score, 3),
            })
    scored.sort(key=lambda r: r["score"], reverse=True)
    if scored and relative_min:
        best = scored[0]["score"]
        scored = [s for s in scored if s["score"] >= best * relative_min]
    return scored[:top_k]


def search_documents(conn, query: str, top_k: int = 3, min_score: float = 0.3,
                     relative_min: float = 0.0) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT c.id, c.document_id, c.chunk_index, d.title, c.chunk_text
               FROM chatbot_document_chunks c JOIN chatbot_documents d ON d.id = c.document_id"""
        )
        rows = cur.fetchall()
    return rank_chunks(rows, query, top_k, min_score, relative_min)


def get_chunks_by_ids(conn, ids: list[int]) -> list[dict]:
    """Relit des passages précis (suite d'une réponse), dans l'ordre demandé."""
    ids = [int(i) for i in ids]
    if not ids:
        return []
    placeholders = ",".join(["%s"] * len(ids))
    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT c.id, c.document_id, c.chunk_index, d.title, c.chunk_text
                FROM chatbot_document_chunks c JOIN chatbot_documents d ON d.id = c.document_id
                WHERE c.id IN ({placeholders})""",
            ids,
        )
        by_id = {r["id"]: r for r in cur.fetchall()}
    return [
        {"id": i, "doc_id": by_id[i]["document_id"], "chunk_index": by_id[i]["chunk_index"],
         "title": by_id[i]["title"], "text": by_id[i]["chunk_text"], "score": 1.0}
        for i in ids if i in by_id
    ]


def get_document_by_title_fragment(conn, fragment: str) -> Optional[list[dict]]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT d.title, c.chunk_text FROM chatbot_document_chunks c
               JOIN chatbot_documents d ON d.id = c.document_id
               WHERE d.title LIKE %s ORDER BY c.chunk_index LIMIT 6""",
            (f"%{fragment}%",),
        )
        rows = cur.fetchall()
    return [{"title": r["title"], "text": r["chunk_text"], "score": 1.0} for r in rows] or None