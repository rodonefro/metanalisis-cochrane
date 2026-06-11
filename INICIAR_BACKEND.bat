@echo off
title Backend - MetaAnalysis API
cd /d "%~dp0backend"
echo Iniciando servidor backend en http://localhost:8000 ...
call venv\Scripts\activate.bat
python run.py
pause
