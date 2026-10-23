#!/bin/sh
# Synchronise le projet vers /private/tmp/adjugo-preview, d'où tourne le serveur de
# preview. Pourquoi un miroir : le bac à sable de l'outil de preview n'a pas accès à
# ~/Downloads (dossier protégé par macOS) — il ne peut ni lire le code ni le venv ici.
# À relancer après des modifications pour que la preview les voie (ou déplacer le repo
# hors de ~/Downloads pour se passer du miroir).
set -e
SRC="$(cd "$(dirname "$0")/.." && pwd)"
rsync -a --delete \
  --exclude ".git" --exclude "__pycache__" --exclude "*.pyc" --exclude "test_adjugo.db" \
  --exclude "adjugo.db" \
  "$SRC/" /private/tmp/adjugo-preview/
echo "Miroir de preview synchronisé : /private/tmp/adjugo-preview"
