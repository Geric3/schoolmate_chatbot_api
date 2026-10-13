"""Tests unitaires de fonctions pures (aucune dépendance externe)."""
from services.rag_service import chunk_text
from services.faq_service import _tokenize


def test_chunk_text_short_text_is_one_chunk():
    assert chunk_text("bonjour tout le monde") == ["bonjour tout le monde"]


def test_chunk_text_long_text_is_split_with_limit():
    chunks = chunk_text("a" * 2000)
    assert len(chunks) > 1
    assert all(len(c) <= 700 for c in chunks)


def test_faq_tokenizer_drops_stopwords():
    tokens = _tokenize("Comment payer la scolarité", "fr")
    assert "payer" in tokens
    assert "comment" not in tokens