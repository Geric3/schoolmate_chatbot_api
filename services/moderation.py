"""
Guardrails that run BEFORE we touch the database or an LLM.

Rules enforced here:
1. Nobody — student, teacher, admin, not even the LLM step — is ever given
   a password. We refuse outright rather than let the model "explain" it.
2. A student can only ever ask about their own record. Any attempt to name
   another student (by student number or by asking to compare/see someone
   else's grades/payments) is refused before it reaches the DB layer.
3. Teachers/admins get a bit more room (they may legitimately look up a
   named student), but that lookup is still done through parameterised,
   scoped queries in context_builder.py — never free-text SQL — and is
   restricted to their own tenant database via the JWT.
"""
import re

PASSWORD_PATTERNS = re.compile(
    r"mot\s*de\s*passe|password|mdp\b|admin_password|stripe_secret", re.IGNORECASE
)

# Matches things like "STU2024001", "22B123", etc. — the kind of token a
# student would use to refer to a *different* student's record.
STUDENT_NUMBER_LIKE = re.compile(r"\b[A-Za-z]{0,4}\d{3,}[A-Za-z0-9]*\b")

OTHER_STUDENT_INTENT = re.compile(
    r"(note|résultat|resultat|moyenne|paiement|solde)\s+(de|d')\s+[A-Za-zÀ-ÿ]+",
    re.IGNORECASE,
)

REFUSAL_PASSWORD_FR = (
    "Je ne peux pas communiquer ou deviner de mots de passe, même le vôtre. "
    "Utilisez l'option « mot de passe oublié » sur la page de connexion."
)
REFUSAL_PASSWORD_EN = (
    "I can't share or guess any password, including your own. "
    "Please use the \"forgot password\" option on the login page."
)

REFUSAL_OTHER_STUDENT_FR = (
    "Je ne peux partager les informations (notes, paiements, coordonnées) "
    "que d'un seul compte : le vôtre. Je ne peux pas afficher les données "
    "d'un autre étudiant."
)
REFUSAL_OTHER_STUDENT_EN = (
    "I can only share information (grades, payments, contact details) for "
    "your own account. I can't show another student's data."
)


def check_password_request(message: str, lang: str) -> str | None:
    if PASSWORD_PATTERNS.search(message):
        return REFUSAL_PASSWORD_FR if lang == "fr" else REFUSAL_PASSWORD_EN
    return None


def check_cross_student_request(message: str, role: str, own_student_number: str | None, lang: str) -> str | None:
    if role != "student":
        return None  # teachers/admins are allowed to look up named students

    if OTHER_STUDENT_INTENT.search(message):
        return REFUSAL_OTHER_STUDENT_FR if lang == "fr" else REFUSAL_OTHER_STUDENT_EN

    for match in STUDENT_NUMBER_LIKE.findall(message):
        if own_student_number and match.upper() != own_student_number.upper():
            return REFUSAL_OTHER_STUDENT_FR if lang == "fr" else REFUSAL_OTHER_STUDENT_EN

    return None


def strip_sensitive_columns(row: dict) -> dict:
    """Extra safety net: even if a query upstream ever accidentally selected
    a sensitive column, never let it leave this service."""
    sensitive_keys = {
        "password", "admin_password", "stripe_secret_key",
        "reset_token", "reset_token_expiry",
    }
    return {k: v for k, v in row.items() if k.lower() not in sensitive_keys}
