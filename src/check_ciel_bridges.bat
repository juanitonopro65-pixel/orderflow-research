@echo off
REM Health check bridges Ciel en Quantower (MGC:8765 ZW:8768)
cd /d "%~dp0\.."
if not defined CIEL_MARKETS set CIEL_MARKETS=MGC,ZW
python src\agus_ejecutor_ciel.py --check --markets %CIEL_MARKETS%
pause
