# Adjugo — Démo Hackathon : Pipeline Multi-Agents

Système **3 agents IA** orchestrés qui transforme un appel d'offres public en
dossier de réponse complet, avec composition automatique d'un groupement de co-traitants.

```
Agent 1 SOURCEUR     →  Agent 2 STRATÈGE       →  Agent 3 RÉDACTEUR
veille BOAMP            détecte les lots non       mémoire technique
scoring multi-critères  couverts par l'entreprise  CERFA DC1/DC2/ATTRI1
Go/No-Go IA argumenté   matche les co-traitants    (en groupement)
                        compose le groupement      dossier ZIP
```

## Lancer la démo (zéro dépendance — SQLite, pas de Docker)

```bash
cd adjugo-backend
venv/bin/python seed_demo.py            # crée le scénario de démo
venv/bin/uvicorn app.main:app --port 8000
```

Puis ouvrir **http://localhost:8000/demo** et cliquer **« ▶ Lancer le pipeline »**.
Le tableau de bord montre les 3 agents travailler en temps réel (SSE).
Durée d'un run complet : ~90 s (3 appels Claude enchaînés).

## Le scénario

- **Entreprise candidate** : *BTP Armor Construction* — maçonnerie / gros œuvre, Quimper (29),
  Qualibat 2111, CA 1,25 M€, 12 salariés.
- **Appel d'offres** : réhabilitation d'un groupe scolaire à Quimper, **alloti en 4 lots**
  (gros œuvre, électricité, CVC, menuiseries), 740 k€ HT.
- **Réseau de co-traitants** : 5 entreprises (3 pertinentes + 2 distracteurs).

L'entreprise ne couvre **que le Lot 1** seule. L'Agent Stratège détecte les 3 lots
manquants et compose un **groupement solidaire** : BTP Armor (mandataire) + l'électricien
+ le chauffagiste + le menuisier, chacun sur son lot, avec score d'adéquation et
justification (CPV, qualification, ratio CA/montant, proximité).

## Points forts à montrer

1. **Scoring intelligent** des leads : le lead « voirie/VRD » est rétrogradé car *voirie*
   est un mot-clé exclu des critères du client.
2. **Go/No-Go piloté par les seuils** configurés par le client (GO si score ≥ 60).
3. **Le différenciateur** : le carnet d'adresses co-traitants devient un **moteur de
   recommandation contextualisé** par l'IA (Agent 2).
4. **Documents réels** : DC1 (groupement), DC2 (un par membre), ATTRI1, mémoire technique,
   le tout dans un ZIP téléchargeable.

## API

| Méthode | Route | Description |
|---|---|---|
| POST | `/api/pipeline/demo/run` | Pipeline complet (SSE), mode démo sans auth |
| POST | `/api/pipeline/run` | Pipeline complet (SSE), authentifié (Bearer) |
| POST | `/api/cotraitants/suggest` | Agent Stratège seul (suggestion sur un projet) |
| GET | `/demo` | Tableau de bord temps réel |

## Architecture du code (nouveaux fichiers)

```
app/services/llm.py                 # couche LLM centralisée (modèles, JSON robuste)
app/services/orchestrator.py        # enchaîne les 3 agents, émet le flux SSE
app/services/agents/
  ├── sourcing.py                   # Agent 1 — veille + scoring + Go/No-Go
  ├── groupement.py                 # Agent 2 — couverture des lots + matching co-traitants
  ├── redaction.py                  # Agent 3 — mémoire + CERFA groupement + ZIP
  └── sample_dce.py                 # DCE de démo (repli bulletproof)
app/routers/pipeline.py             # routes pipeline + /demo
app/static/demo.html                # tableau de bord temps réel (autonome)
seed_demo.py                        # scénario de démonstration
```

Modèles Claude : `claude-sonnet-4-6` (analyse, stratégie), `claude-haiku-4-5` (rédaction).
