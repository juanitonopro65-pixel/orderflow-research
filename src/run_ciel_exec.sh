#!/usr/bin/env bash
# Ejecutor Ciel — cron/sesión. En Windows preferí run_ciel_exec.bat
cd "$(dirname "$0")/.." || exit 1
export CIEL_LUCID_PROFILE="${CIEL_LUCID_PROFILE:-25k}"
export CIEL_MARKETS="${CIEL_MARKETS:-MGC}"
python src/agus_ejecutor_ciel.py >> src/ciel_exec.log 2>&1
