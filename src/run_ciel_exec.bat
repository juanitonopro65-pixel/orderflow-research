@echo off
REM Ejecutor Ciel — tarea programada Windows (cada 1-5 min en sesion).
REM Quantower + AgustinaBridge deben estar corriendo.
cd /d "%~dp0\.."
if not defined CIEL_LUCID_PROFILE set CIEL_LUCID_PROFILE=25k
if not defined CIEL_MARKETS set CIEL_MARKETS=MGC
python src\agus_ejecutor_ciel.py >> src\ciel_exec.log 2>&1
