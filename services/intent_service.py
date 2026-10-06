import re
from dataclasses import dataclass, field
from typing import Optional

INTENT_PATTERNS = {
    "grades": re.compile(r"\b(notes?|résultats?|resultats?|moyenne|grades?|results?|scores?)\b", re.I),
    "semester_validation": re.compile(r"valid(é|e)r?|passed|réussi|reussi|semestre|semester", re.I),
    "payment": re.compile(r"pay(er|é|ment)|solde|reste.*payer|combien.*(payer|dois)|balance|tuition|frais|scolarité", re.I),
    "courses": re.compile(r"\bcours\b|matières?|matieres?|subjects?|emploi du temps|schedule|planning", re.I),
    "teacher_lookup": re.compile(r"(enseignant|professeur|prof|teacher).*(de|of|en|for)?\s*(.+)", re.I),
    "announcements": re.compile(r"annonce|announcement|règlement|reglement|interieur|intérieur|rules?|policy|note de service", re.I),
    "notifications": re.compile(r"notifications?", re.I),
    "teacher_hours": re.compile(r"(mes|my)?\s*heures|hours\s*worked|combien d.?heures", re.I),
    "teacher_subjects": re.compile(r"mes (cours|matières|matieres)|my (subjects|courses)", re.I),
    "institution_stats": re.compile(r"combien d.?(étudiants|etudiants|students|enseignants|teachers)", re.I),
}


@dataclass
class Intent:
    name: str
    entities: dict = field(default_factory=dict)


def classify(message: str) -> Optional[Intent]:
    msg = message.strip()

    # Order matters: more specific patterns first.
    if INTENT_PATTERNS["semester_validation"].search(msg):
        sem_match = re.search(r"semestre\s*(1|2)|semester\s*(1|2)", msg, re.I)
        semester = None
        if sem_match:
            semester = sem_match.group(1) or sem_match.group(2)
        return Intent("semester_validation", {"semester": semester})

    if INTENT_PATTERNS["payment"].search(msg):
        return Intent("payment")

    if INTENT_PATTERNS["teacher_lookup"].search(msg) and re.search(r"qui\s+(est|enseigne)|who\s+(is|teaches)", msg, re.I):
        m = INTENT_PATTERNS["teacher_lookup"].search(msg)
        subject_fragment = m.group(3).strip(" ?.!") if m else ""
        return Intent("teacher_lookup", {"subject_fragment": subject_fragment})

    if INTENT_PATTERNS["grades"].search(msg):
        return Intent("grades")

    if INTENT_PATTERNS["teacher_hours"].search(msg):
        return Intent("teacher_hours")

    if INTENT_PATTERNS["teacher_subjects"].search(msg):
        return Intent("teacher_subjects")

    if INTENT_PATTERNS["courses"].search(msg):
        return Intent("courses")

    if INTENT_PATTERNS["announcements"].search(msg):
        return Intent("announcements")

    if INTENT_PATTERNS["notifications"].search(msg):
        return Intent("notifications")

    if INTENT_PATTERNS["institution_stats"].search(msg):
        return Intent("institution_stats")

    return None
