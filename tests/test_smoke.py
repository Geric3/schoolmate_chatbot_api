"""
Tests "de fumée" : rapides, sans base de données ni clé API réelle.
Ils vérifient que l'application démarre et que la sécurité de base est en place.
"""
from fastapi.testclient import TestClient

from main import app  # ⚠️ adaptez "main" si votre fichier d'entrée a un autre nom

client = TestClient(app)


def test_app_starts_and_docs_are_served():
    assert client.get("/docs").status_code == 200


def test_chat_requires_authentication():
    r = client.post("/chat", json={"message": "bonjour"})
    # Sans jeton : 401 ou 403 attendu. (422 ou 500 = bug.)
    assert r.status_code in (401, 403)


def test_admin_routes_require_authentication():
    # Ce test aurait détecté le bug "Depends manquant" de _admin_only :
    # l'API répondait 422 au lieu de 401/403.
    for path in ("/admin/faqs", "/admin/documents", "/admin/announcements", "/admin/unanswered"):
        r = client.get(path)
        assert r.status_code in (401, 403), f"{path} a répondu {r.status_code}"