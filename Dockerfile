# Image officielle Python légère (>= 3.10 requis par votre code : syntaxe "X | None")
FROM python:3.12-slim

# Logs immédiats et pas de fichiers .pyc inutiles dans le conteneur
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 1) On copie d'abord SEULEMENT les dépendances : Docker met cette étape en cache
#    et ne réinstalle les paquets que si requirements.txt change (builds bien plus rapides).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2) Puis le code de l'API
COPY . .

# Sécurité : ne pas faire tourner l'API en root
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# Render fournit le port via la variable $PORT ; 8000 en local.
# ⚠️ "main:app" = fichier main.py contenant `app = FastAPI(...)`. Adaptez si votre fichier s'appelle autrement.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]