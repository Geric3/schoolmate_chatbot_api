"""
FAQs live in `chatbot_faqs` (question_key, answer, lang) — the same table
the old PHP chatbot used, so nothing already entered is lost. Matching is a
simple, dependency-free word-overlap score: good enough for a few dozen to a
few hundred FAQ entries and easy to reason about/debug from the admin UI.
"""
import re
from collections import Counter
from typing import Optional

_WORD_RE = re.compile(r"[a-zA-ZÀ-ÿ0-9]+")

_STOPWORDS = {
    "fr": {"le", "la", "les", "de", "des", "du", "un", "une", "et", "est",
           "je", "tu", "il", "elle", "on", "nous", "vous", "ils", "que",
           "qui", "quoi", "comment", "pour", "avec", "dans", "sur", "mon",
           "ma", "mes", "ce", "cette", "à", "au", "aux", "se", "sa", "son"},
    "en": {"the", "a", "an", "of", "and", "is", "i", "you", "he", "she",
           "we", "they", "what", "how", "for", "with", "in", "on", "my",
           "this", "that", "to", "do", "does", "are"},
}


def _tokenize(text: str, lang: str) -> Counter:
    words = [w.lower() for w in _WORD_RE.findall(text)]
    stop = _STOPWORDS.get(lang, _STOPWORDS["fr"])
    return Counter(w for w in words if w not in stop and len(w) > 2)


def find_best_faq(conn, message: str, lang: str, min_score: float = 0.35) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, question_key, answer, lang FROM chatbot_faqs WHERE lang = %s OR lang IS NULL",
            (lang,),
        )
        faqs = cur.fetchall()

    if not faqs:
        return None

    msg_tokens = _tokenize(message, lang)
    if not msg_tokens:
        return None

    best, best_score = None, 0.0
    for faq in faqs:
        key_tokens = _tokenize(faq["question_key"].replace("_", " "), lang)
        if not key_tokens:
            continue
        overlap = sum((msg_tokens & key_tokens).values())
        score = overlap / max(len(key_tokens), 1)
        if score > best_score:
            best, best_score = faq, score

    if best and best_score >= min_score:
        return {"id": best["id"], "answer": best["answer"], "score": round(best_score, 2)}
    return None


def list_faqs(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("SELECT id, question_key, answer, lang FROM chatbot_faqs ORDER BY id DESC")
        return cur.fetchall()


def create_faq(conn, question_key: str, answer: str, lang: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO chatbot_faqs (question_key, answer, lang) VALUES (%s, %s, %s)",
            (question_key, answer, lang),
        )
        return cur.lastrowid


def update_faq(conn, faq_id: int, question_key: str, answer: str, lang: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE chatbot_faqs SET question_key=%s, answer=%s, lang=%s WHERE id=%s",
            (question_key, answer, lang, faq_id),
        )


def delete_faq(conn, faq_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM chatbot_faqs WHERE id=%s", (faq_id,))


def log_unanswered(conn, question: str, answer: str) -> None:
    """Feeds the admin's 'unanswered questions' review queue (chatbot_learning)."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO chatbot_learning (question, answer) VALUES (%s, %s)",
            (question, answer),
        )


def list_unanswered(conn, limit: int = 50) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, question, answer, timestamp FROM chatbot_learning ORDER BY id DESC LIMIT %s",
            (limit,),
        )
        return cur.fetchall()


def delete_unanswered(conn, entry_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM chatbot_learning WHERE id=%s", (entry_id,))


def log_interaction(conn, user_id: Optional[int], question: str, response: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO chatbot_logs (user_id, question, response, timestamp) VALUES (%s, %s, %s, NOW())",
            (user_id, question, response),
        )

