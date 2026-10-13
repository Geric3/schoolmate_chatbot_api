from services.rag_service import rank_chunks
from services.continuation_service import is_affirmative, is_negative

ROWS = [
    {"id": 1, "document_id": 1, "chunk_index": 0, "title": "Règlement", "chunk_text": "Le redoublement est autorisé une seule fois par cycle pour tout étudiant."},
    {"id": 2, "document_id": 1, "chunk_index": 1, "title": "Règlement", "chunk_text": "Les horaires des cours vont de 8h à 17h du lundi au vendredi."},
    {"id": 3, "document_id": 1, "chunk_index": 2, "title": "Règlement", "chunk_text": "Les absences injustifiées au-delà de trois séances entraînent un avertissement."},
]


def test_rare_word_finds_right_passage():
    res = rank_chunks(ROWS, "Peut-on avoir un redoublement ?")
    assert res and res[0]["id"] == 1


def test_accents_and_plurals_in_documents():
    res = rank_chunks(ROWS, "horaire des cours")
    assert res and res[0]["id"] == 2


def test_unrelated_question_has_no_passage():
    assert rank_chunks(ROWS, "capitale de la France") == []


def test_affirmative_answers():
    for text in ("oui", "Oui !", "yes", "ok", "la suite", "Oui, affiche la suite", "d'accord"):
        assert is_affirmative(text), text


def test_not_affirmative_when_it_is_a_new_question():
    assert not is_affirmative("oui mais quels sont les frais d'inscription ?")
    assert not is_affirmative("non merci")
    assert not is_affirmative("merci")


def test_negative_answers():
    for text in ("non", "Non merci", "no thanks", "merci"):
        assert is_negative(text), text
    assert not is_negative("non je voulais savoir les horaires de la bibliothèque")