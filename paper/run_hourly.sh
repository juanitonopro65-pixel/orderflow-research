#!/usr/bin/env bash
# Fase 1 — un ciclo de paper Ciel (trigo + oro). Correr cada hora en sesión NY.
cd "$(dirname "$0")/.." || exit 1
python paper/ciel_paper.py >> paper/ciel_paper.log 2>&1
