@echo off
REM Activa LIVE Ciel — crea LIVE_MGC.txt solo con confirmacion tipada SI.
REM El asistente NUNCA crea este archivo. Abortar = borrar LIVE_MGC.txt.
cd /d "%~dp0"
echo.
echo  === ACTIVAR CIEL LIVE (ordenes REALES en Lucid) ===
echo  Perfil tipico demo: CIEL_LUCID_PROFILE=25k  CIEL_MARKETS=MGC
echo  Eval 150k:          CIEL_LUCID_PROFILE=150k CIEL_MARKETS=MGC,ZW
echo.
echo  Escribe SI (mayusculas) para crear LIVE_MGC.txt:
set /p CONFIRM=
if /I not "%CONFIRM%"=="SI" (
  echo Cancelado. Sigue en DRY-RUN.
  pause
  exit /b 1
)
echo. > LIVE_MGC.txt
echo OK — LIVE_MGC.txt creado. El ejecutor pondra ordenes reales.
echo Para abortar: borra LIVE_MGC.txt
pause
