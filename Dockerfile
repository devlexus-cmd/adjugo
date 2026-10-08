FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Dépendances système : tesseract (OCR des DCE scannés, langue FR) + poppler (pdf2image).
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-fra poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Installation VERROUILLÉE : requirements.lock fige TOUTES les dépendances (y compris
# indirectes) à la version exacte, avec le hachage SHA-256 de chaque paquet. Un paquet
# altéré, ou une dépendance absente du lock, fait échouer le build au lieu de passer.
# Le lock est généré depuis requirements.txt pour linux x86_64 / Python 3.12 :
# procédure de mise à jour et d'audit dans docs/DEPENDANCES.md.
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock

COPY . .

# Utilisateur non-root
RUN adduser --disabled-password --gecos "" appuser \
    && chmod +x entrypoint.sh \
    && mkdir -p uploads && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["./entrypoint.sh"]
