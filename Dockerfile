FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Dépendances système minimales (psycopg2 binaire n'en a pas besoin, mais utiles aux libs PDF)
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Utilisateur non-root
RUN adduser --disabled-password --gecos "" appuser \
    && chmod +x entrypoint.sh \
    && mkdir -p uploads && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["./entrypoint.sh"]
