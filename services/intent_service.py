import re
from dataclasses import dataclass, field
from typing import Optional

_SEMESTER_RE = re.compile(r"\b(?:semestre|semester|sem\.?|s)\s*[-:]?\s*([12])\b", re.I)
_ACADEMIC_YEAR_RE = re.compile(r"\b(20\d{2})\s*[-/]\s*(20\d{2})\b")

INTENT_PATTERNS = {
    "grades": re.compile(r"\b(notes?|résultats?|resultats?|grades?|results?|scores?)\b", re.I),
    "average": re.compile(r"\b(moyenne|average|gpa)\b", re.I),
    "validation": re.compile(
        r"\b(valid(?:er|e|é|ée|és|ées)?|réussi(?:e|es|s)?|reussi(?:e|es|s)?|passed|pass(?:ed)?)\b",
        re.I,
    ),
    "failed_courses": re.compile(
        r"\b(rattrap(?:age|er|e|ées|és)?|non\s+valid(?:ée|e|ées|es)?|"
        r"échoué(?:e|es|s)?|echoue(?:e|es|s)?|failed|retake|resit)\b",
        re.I,
    ),
    "payment": re.compile(
        r"pay(er|é|ment)|solde|reste.*payer|combien.*(payer|dois)|balance|tuition|frais|scolarité",
        re.I,
    ),
    "courses": re.compile(
        r"\bcours\b|matières?|matieres?|subjects?|emploi du temps|schedule|planning",
        re.I,
    ),
    "teacher_terms": re.compile(r"\b(enseignants?|professeurs?|profs?|teachers?)\b", re.I),
    "teacher_lookup": re.compile(
        r"\b(?:qui\s+(?:est|enseigne|donne|assure)|quel(?:le)?\s+(?:est\s+)?"
        r"(?:le\s+)?(?:nom|professeur|enseignant)|(?:enseignant|professeur|prof|teacher)"
        r"(?:e)?\s+(?:de|pour|of|for))\b",
        re.I,
    ),
    "announcements": re.compile(
        r"annonce|announcement|règlement|reglement|interieur|intérieur|rules?|policy|note de service",
        re.I,
    ),
    "notifications": re.compile(r"notifications?", re.I),
    "teacher_hours": re.compile(r"(?:mes|my)?\s*heures|hours\s*worked|combien d.?heures", re.I),
    "teacher_subjects": re.compile(
        r"(?:cours|matières?|matieres?)\s+(?:que\s+j['’]enseigne|que\s+je\s+donne)|"
        r"(?:subjects|courses)\s+i\s+teach",
        re.I,
    ),
    "institution_stats": re.compile(r"combien d.?(?:étudiants|etudiants|students|enseignants|teachers)", re.I),
}


@dataclass
class Intent:
    name: str
    entities: dict = field(default_factory=dict)


def _entities(message: str) -> dict:
    semester_match = _SEMESTER_RE.search(message)
    year_match = _ACADEMIC_YEAR_RE.search(message)
    entities = {}
    if semester_match:
        entities["semester"] = semester_match.group(1)
    if year_match:
        entities["academic_year"] = f"{year_match.group(1)}-{year_match.group(2)}"
    return entities


def _teacher_fragment(message: str) -> str:
    patterns = (
        r"\bqui\s+(?:est\s+)?(?:le|la|l['’])?\s*(?:enseignant|professeur|prof|teacher)(?:e)?"
        r"\s+(?:de|pour|of|for)\s+(.+)",
        r"\bqui\s+(?:enseigne|donne|assure)\s+(?:le\s+cours\s+de\s+)?(.+)",
        r"\bquel(?:le)?\s+(?:est\s+)?(?:le\s+)?(?:nom\s+de\s+)?"
        r"(?:l['’]enseignant|l['’]enseignante|du\s+professeur|du\s+prof|"
        r"de\s+l['’]enseignant|de\s+la\s+professeure)\s+(?:de|pour)\s+(.+)",
        r"\bquel(?:le)?\s+(?:est\s+)?(?:le\s+)?(?:professeur|prof|enseignant|teacher)"
        r"(?:e)?\s+(?:de|pour|of|for)\s+(.+)",
        r"\b(?:quels?|quelles?)\s+(?:cours|matières?|matieres?|subjects?)\s+"
        r"(?:enseigne|donne|teach(?:es)?)\s+(?:(?:le|la)\s+)?"
        r"(?:professeur|prof|enseignant|teacher)\s+(.+)",
        r"\b(?:cours|matières?|matieres?|subjects?)\s+(?:de|du|d['’]|for)\s+"
        r"(?:(?:le|la)\s+)?(?:professeur|prof|enseignant|teacher)\s+(.+)",
        r"\b(?:enseignant|professeur|prof|teacher)(?:e)?\s+(?:de|pour|of|for)\s+(.+)",
        r"\b(?:matières?|matieres?|cours|subjects?)\s+(?:de|du|d['’]|for)\s+(.+)",
    )
    for pattern in patterns:
        match = re.search(pattern, message, re.I)
        if match:
            fragment = match.group(1).strip(" ?.!,:;")
            fragment = re.sub(
                r"^(?:la\s+)?(?:matière|matiere|cours)\s+(?:de\s+)?", "", fragment, flags=re.I,
            )
            fragment = re.sub(
                r"^(?:(?:le|la)\s+)?(?:professeur|prof|enseignant|teacher)\s+", "",
                fragment, flags=re.I,
            )
            if fragment.lower() not in {"mon enseignant", "mon professeur", "mes enseignants",
                                        "mes professeurs", "mes profs"}:
                return fragment
    return ""


def classify(message: str) -> Optional[Intent]:
    msg = message.strip()
    entities = _entities(msg)

    if INTENT_PATTERNS["payment"].search(msg):
        return Intent("payment", entities)

    if INTENT_PATTERNS["teacher_lookup"].search(msg):
        entities["teacher_fragment"] = _teacher_fragment(msg)
        return Intent("teacher_lookup", entities)

    if INTENT_PATTERNS["failed_courses"].search(msg):
        return Intent("failed_courses", entities)

    if INTENT_PATTERNS["average"].search(msg):
        return Intent("semester_average", entities)

    if INTENT_PATTERNS["validation"].search(msg):
        return Intent("semester_validation", entities)

    if INTENT_PATTERNS["grades"].search(msg):
        return Intent("grades", entities)

    if INTENT_PATTERNS["teacher_hours"].search(msg):
        return Intent("teacher_hours", entities)

    if INTENT_PATTERNS["teacher_subjects"].search(msg):
        return Intent("teacher_subjects", entities)

    if INTENT_PATTERNS["institution_stats"].search(msg):
        return Intent("institution_stats", entities)

    if INTENT_PATTERNS["teacher_terms"].search(msg):
        entities["teacher_fragment"] = _teacher_fragment(msg)
        return Intent("teacher_lookup", entities)

    if INTENT_PATTERNS["courses"].search(msg):
        return Intent("courses", entities)

    if INTENT_PATTERNS["announcements"].search(msg):
        return Intent("announcements", entities)

    if INTENT_PATTERNS["notifications"].search(msg):
        return Intent("notifications", entities)

    return None
