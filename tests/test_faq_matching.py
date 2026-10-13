"""La FAQ saisie par l'admin doit être retrouvée même si l'utilisateur écrit autrement."""
from services.faq_service import find_best_faq


class _Cur:
    def __init__(self, rows): self.rows = rows
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, *a, **k): pass
    def fetchall(self): return self.rows


class _Conn:
    def __init__(self, rows): self.rows = rows
    def cursor(self): return _Cur(self.rows)


FAQS = [
    {"id": 1, "question_key": "Quels sont les horaires d'ouverture de l'institut ?", "answer": "8h-17h", "lang": "fr"},
    {"id": 2, "question_key": "frais inscription", "answer": "30 000 F", "lang": "fr"},
]


def test_full_question_matches_itself():
    hit = find_best_faq(_Conn(FAQS), "Quels sont les horaires d'ouverture de l'institut ?", "fr")
    assert hit and hit["id"] == 1


def test_short_keyword_finds_long_faq():
    hit = find_best_faq(_Conn(FAQS), "horaires", "fr")
    assert hit and hit["id"] == 1


def test_accents_and_plurals_are_ignored():
    hit = find_best_faq(_Conn(FAQS), "horaire d ouverture", "fr")
    assert hit and hit["id"] == 1


def test_long_message_containing_keywords_matches():
    hit = find_best_faq(_Conn(FAQS), "Bonjour, je voudrais connaitre les frais d'inscription svp", "fr")
    assert hit and hit["id"] == 2


def test_other_language_session_still_finds_faq():
    hit = find_best_faq(_Conn(FAQS), "frais inscription", "en")
    assert hit and hit["id"] == 2


def test_unrelated_question_returns_nothing():
    assert find_best_faq(_Conn(FAQS), "donne moi une recette de cuisine", "fr") is None