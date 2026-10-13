"""
« Voulez-vous la suite ? » : quand plusieurs passages d'un document répondent à la
question, on en affiche une première partie et on mémorise le reste pour la prochaine
réponse « oui » de l'utilisateur (table `chatbot_pending`, une ligne par utilisateur).

Si la table n'existe pas encore (migration non appliquée), le chatbot continue de
fonctionner normalement : simplement sans la fonction « suite ».
"""
import json
import logging
import re
import unicodedata
from typing import Optional

log = logging.getLogger(__name__)

TTL_MINUTES = 15

FOLLOWUP = {
    "fr": "Il y a d'autres informations à ce sujet dans le document. "
          "Voulez-vous que je vous affiche la suite ? (répondez « oui » ou « non »)",
    "en": "There is more information on this topic in the document. "
          "Would you like me to show the rest? (reply “yes” or “no”)",
}
NO_MORE = {
    "fr": "Il n'y a pas d'autres informations dans les documents à ce sujet.",
    "en": "There is no further information on this topic in the documents.",
}
DECLINED = {
    "fr": "D'accord ! N'hésitez pas si vous avez une autre question.",
    "en": "Alright! Feel free to ask if you have another question.",
}


def _norm(text: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", t)).strip()


_AFFIRM = re.compile(
    r"^(oui|ouais|yes|yep|yeah|ok|okay|d accord|volontiers|bien sur|sure|continue|continuez|"
    r"la suite|suite|affiche|affichez|montre|montrez|vas y|allez y|go on|more|show|please|svp|s il vous plait)\b"
)
_NEG = re.compile(
    r"^(non|no|nope|nah|pas besoin|ca ira|c est bon|ca suffit|merci|thanks|thank you|stop)\b"
)
_STRONG_YES = re.compile(r"\b(oui|yes|suite|more|continue)\b")


def is_affirmative(text: str) -> bool:
    """Réponse courte et sans question qui veut dire « oui, affichez la suite »."""
    if "?" in text:
        return False
    n = _norm(text)
    if not n or len(n.split()) > 5:
        return False
    if _NEG.match(n) and not _STRONG_YES.search(n):
        return False
    return bool(_AFFIRM.match(n) or re.search(r"\b(la suite|le reste|the rest)\b", n))


def is_negative(text: str) -> bool:
    """Refus court. Un message plus long est traité comme une nouvelle question."""
    n = _norm(text)
    if not n or len(n.split()) > 4 or is_affirmative(text):
        return False
    return bool(_NEG.match(n))


# --- Stockage ---------------------------------------------------------------

def save_pending(conn, role: str, user_id: int, question: str, chunk_ids: list[int], last_answer: str) -> None:
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO chatbot_pending (role, user_id, question, chunk_ids, last_answer, created_at)
                   VALUES (%s, %s, %s, %s, %s, NOW())
                   ON DUPLICATE KEY UPDATE question = VALUES(question), chunk_ids = VALUES(chunk_ids),
                                           last_answer = VALUES(last_answer), created_at = NOW()""",
                (role, user_id, question, json.dumps([int(i) for i in chunk_ids]), (last_answer or "")[-1500:]),
            )
    except Exception as exc:  # table absente, etc. : fonction facultative
        log.warning("save_pending ignoré : %s", exc)


def get_pending(conn, role: str, user_id: int) -> Optional[dict]:
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT question, chunk_ids, last_answer FROM chatbot_pending
                   WHERE role = %s AND user_id = %s AND created_at >= (NOW() - INTERVAL %s MINUTE)""",
                (role, user_id, TTL_MINUTES),
            )
            row = cur.fetchone()
        if not row:
            return None
        return {"question": row["question"], "chunk_ids": json.loads(row["chunk_ids"] or "[]"),
                "last_answer": row["last_answer"] or ""}
    except Exception as exc:
        log.warning("get_pending ignoré : %s", exc)
        return None


def clear_pending(conn, role: str, user_id: int) -> None:
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chatbot_pending WHERE role = %s AND user_id = %s", (role, user_id))
    except Exception as exc:
        log.warning("clear_pending ignoré : %s", exc)