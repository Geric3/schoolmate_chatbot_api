import requests
from config import settings

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"

BASE_SYSTEM_PROMPT = {
    "fr": (
        "Tu es SchoolmateBot, l'assistant virtuel de l'institut. Tu réponds de façon "
        "chaleureuse, encourageante et concise aux étudiants, enseignants et à "
        "l'administration. Règles strictes, sans exception : "
        "1) Tu ne révèles, ne devines et ne discutes jamais de mots de passe, clés API "
        "ou identifiants. "
        "2) Tu ne partages jamais les informations personnelles, notes, paiements ou "
        "coordonnées d'une personne avec une autre. "
        "3) Si un contexte de données t'est fourni, tu t'appuies UNIQUEMENT sur ces "
        "données pour les faits (notes, paiements, cours) : n'invente jamais de chiffre. "
        "4) Si aucun contexte pertinent n'est fourni et que la question ne concerne pas "
        "l'institut, tu peux répondre avec tes connaissances générales, en restant bref "
        "et utile."
    ),
    "en": (
        "You are SchoolmateBot, the institute's virtual assistant. You answer students, "
        "teachers and staff warmly, encouragingly and concisely. Strict rules, no "
        "exceptions: "
        "1) Never reveal, guess, or discuss passwords, API keys or credentials. "
        "2) Never share one person's personal information, grades, payments or contact "
        "details with someone else. "
        "3) If data context is provided, rely ONLY on that data for facts (grades, "
        "payments, courses): never invent a number. "
        "4) If no relevant context is provided and the question isn't about the "
        "institute, you may answer from general knowledge, briefly and helpfully."
    ),
}


def _call(url: str, api_key: str, model: str, messages: list[dict], max_tokens: int = 500) -> str:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.6,
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except requests.RequestException:
        return None
    except (KeyError, IndexError, ValueError):
        return None


def _dispatch(messages: list[dict]) -> str | None:
    if settings.LLM_PROVIDER == "openai" and settings.OPENAI_API_KEY:
        result = _call(OPENAI_URL, settings.OPENAI_API_KEY, settings.OPENAI_MODEL, messages)
        if result:
            return result
    if settings.GROQ_API_KEY:
        result = _call(GROQ_URL, settings.GROQ_API_KEY, settings.GROQ_MODEL, messages)
        if result:
            return result
    # last resort fallback if the primary provider is unset/unreachable
    if settings.OPENAI_API_KEY:
        return _call(OPENAI_URL, settings.OPENAI_API_KEY, settings.OPENAI_MODEL, messages)
    return None


def polish_structured_answer(lang: str, user_question: str, facts: dict) -> str:
    """Turn a dict of DB facts into an encouraging, natural-language answer.
    The model is explicitly told not to invent any number beyond what's given."""
    system = BASE_SYSTEM_PROMPT.get(lang, BASE_SYSTEM_PROMPT["fr"])
    user_msg = (
        f"Question de l'utilisateur : {user_question}\n\n"
        f"Données factuelles (source unique de vérité, ne rien inventer d'autre) :\n{facts}\n\n"
        "Réponds dans un ton encourageant et bienveillant, en 2 à 5 phrases, dans la même "
        "langue que la question." if lang == "fr" else
        f"User question: {user_question}\n\n"
        f"Factual data (single source of truth, don't invent anything else):\n{facts}\n\n"
        "Reply in an encouraging, supportive tone, in 2-5 sentences, in the same language "
        "as the question."
    )
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user_msg}]
    result = _dispatch(messages)
    return result or _fallback_render(lang, facts)


def answer_with_documents(lang: str, user_question: str, chunks: list[dict]) -> str | None:
    system = BASE_SYSTEM_PROMPT.get(lang, BASE_SYSTEM_PROMPT["fr"])
    context = "\n---\n".join(f"[{c['title']}] {c['text']}" for c in chunks)
    instruction = (
        "Réponds à la question UNIQUEMENT à partir des extraits de documents "
        "ci-dessous. Si les extraits ne permettent pas de répondre, dis-le "
        "clairement plutôt que d'inventer."
        if lang == "fr" else
        "Answer the question using ONLY the document excerpts below. If they "
        "don't contain the answer, say so clearly rather than guessing."
    )
    user_msg = f"{instruction}\n\nExtraits:\n{context}\n\nQuestion: {user_question}"
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user_msg}]
    return _dispatch(messages)


def answer_general(lang: str, user_question: str) -> str:
    system = BASE_SYSTEM_PROMPT.get(lang, BASE_SYSTEM_PROMPT["fr"])
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user_question}]
    result = _dispatch(messages)
    if result:
        return result
    return (
        "Désolé, le service de réponse générale est momentanément indisponible."
        if lang == "fr" else
        "Sorry, the general-answer service is temporarily unavailable."
    )


def _fallback_render(lang: str, facts: dict) -> str:
    """Used only if both LLM providers are unreachable — still returns the real data."""
    return (str(facts))
