"""
FAQs stockées dans `chatbot_faqs` (question_key, answer, lang).

Correspondance : mots-clés normalisés (sans accents, sans pluriel, sans mots vides)
puis score de Dice. Une FAQ saisie sous forme de question complète
(« Quels sont les horaires d'ouverture de l'institut ? ») est maintenant retrouvée
même si l'utilisateur écrit seulement « horaires ».
"""
import re
import unicodedata
from collections import Counter
from typing import Optional

_WORD_RE = re.compile(r"[a-zA-ZÀ-ÿ0-9]+")


def _norm(text: str) -> str:
    """minuscules + suppression des accents : « Règlement » == « reglement »."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


_RAW_STOPWORDS = {
    # français
    "le", "la", "les", "de", "des", "du", "un", "une", "et", "est", "sont", "suis", "etes",
    "je", "tu", "il", "elle", "on", "nous", "vous", "ils", "que", "qui", "quoi", "quel",
    "quels", "quelle", "quelles", "comment", "pour", "avec", "dans", "sur", "mon", "ma",
    "mes", "ce", "cette", "ces", "à", "au", "aux", "se", "sa", "son", "ses", "par", "pas",
    "voudrais", "veux", "peux", "puis", "svp", "bonjour", "bonsoir", "salut",
    # anglais
    "the", "an", "of", "and", "is", "are", "you", "he", "she", "we", "they", "what",
    "how", "for", "with", "my", "this", "that", "does", "can", "please", "hello",
}
_STOPWORDS = {_norm(w) for w in _RAW_STOPWORDS}


def _stem(word: str) -> str:
    """Pluriels simples : horaires -> horaire, examens -> examen."""
    if len(word) > 4 and word.endswith(("s", "x")):
        return word[:-1]
    return word


def _tokenize(text: str, lang: str = "fr") -> Counter:
    words = (_norm(w) for w in _WORD_RE.findall(text))
    return Counter(_stem(w) for w in words if len(w) > 2 and w not in _STOPWORDS)


def _score(msg: set, key: set) -> tuple[float, int]:
    overlap = len(msg & key)
    if overlap == 0:
        return 0.0, 0
    dice = 2 * overlap / (len(msg) + len(key))
    # La question de l'admin est entièrement contenue dans le message de l'utilisateur
    # (message long mais qui contient tous ses mots-clés) -> bonne correspondance.
    if overlap == len(key):
        dice = max(dice, 0.85 if len(key) >= 2 else 0.55)
    return dice, overlap


def find_best_faq(conn, message: str, lang: str, min_score: float = 0.5) -> dict | None:
    with conn.cursor() as cur:
        # Toutes les langues : la langue de session ne doit plus faire disparaître une FAQ.
        cur.execute("SELECT id, question_key, answer, lang FROM chatbot_faqs")
        faqs = cur.fetchall()

    if not faqs:
        return None

    msg_tokens = set(_tokenize(message, lang))
    if not msg_tokens:
        return None

    best, best_key = None, (0.0, 0)
    for faq in faqs:
        key_tokens = set(_tokenize((faq["question_key"] or "").replace("_", " "), lang))
        if not key_tokens:
            continue
        score, overlap = _score(msg_tokens, key_tokens)
        if faq.get("lang") and faq["lang"] != lang:
            score *= 0.9
        if (score, overlap) > best_key:
            best, best_key = faq, (score, overlap)

    if best and best_key[0] >= min_score:
        return {"id": best["id"], "answer": best["answer"], "score": round(best_key[0], 2)}
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
    """Alimente la file « questions sans réponse » (chatbot_learning)."""
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