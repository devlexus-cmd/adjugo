# Adjugo — Backend API

API FastAPI pour la gestion des marchés publics et l'analyse IA des appels d'offres.

## Architecture

```
adjugo-backend/
├── app/
│   ├── main.py              # Point d'entrée FastAPI
│   ├── core/
│   │   ├── config.py         # Configuration (env vars)
│   │   ├── database.py       # SQLAlchemy + session
│   │   └── security.py       # JWT + hachage mots de passe
│   ├── models/
│   │   └── __init__.py       # Tous les modèles SQLAlchemy
│   ├── schemas/
│   │   └── __init__.py       # Schémas Pydantic (validation)
│   ├── routers/
│   │   ├── auth.py           # Inscription, connexion, profil
│   │   ├── projects.py       # CRUD appels d'offres
│   │   ├── analysis.py       # Analyse IA (Claude API)
│   │   ├── documents.py      # Coffre-fort documentaire
│   │   ├── invoices.py       # Devis et facturation
│   │   ├── contacts.py       # CRM contacts
│   │   └── company.py        # Profil entreprise + critères
│   └── services/
│       └── analysis.py       # Moteur d'analyse Claude
├── docker-compose.yml        # PostgreSQL + API
├── Dockerfile
├── requirements.txt
└── .env.example
```

## Installation rapide

### 1. Prérequis
- Python 3.12+
- Docker (pour PostgreSQL)

### 2. Lancer la base de données
```bash
docker-compose up -d db
```

### 3. Configurer l'environnement
```bash
cp .env.example .env
# Éditer .env avec vos clés API
```

### 4. Installer les dépendances
```bash
pip install -r requirements.txt
```

### 5. Lancer l'API
```bash
uvicorn app.main:app --reload --port 8000
```

### 6. Documentation
Ouvrir http://localhost:8000/docs pour la documentation interactive Swagger.

## Endpoints principaux

| Méthode | Route | Description |
|---------|-------|-------------|
| POST | `/api/auth/register` | Créer un compte |
| POST | `/api/auth/login` | Se connecter (JWT) |
| GET | `/api/auth/me` | Profil utilisateur |
| GET/POST | `/api/projects/` | Lister / créer un AO |
| POST | `/api/analysis/{id}` | Analyser un DCE (Claude IA) |
| GET/PUT | `/api/company/` | Profil entreprise |
| GET/PUT | `/api/criteria/` | Critères Go/No-Go |
| GET/POST | `/api/documents/` | Coffre-fort documentaire |
| GET/POST | `/api/invoices/` | Devis et factures |
| GET/POST | `/api/contacts/` | CRM contacts |

## Stack technique

- **FastAPI** — Framework API async Python
- **SQLAlchemy** — ORM pour PostgreSQL
- **JWT (python-jose)** — Authentification stateless
- **Anthropic Claude** — Analyse IA des DCE
- **pypdf** — Extraction de texte PDF
- **Stripe** — Paiements (à venir)
- **S3** — Stockage fichiers (à venir)
