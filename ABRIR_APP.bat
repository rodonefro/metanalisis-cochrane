@echo off
title MetaAnalisis Cochrane
echo ============================================
echo   INICIANDO MetaAnalisis Cochrane Platform
echo ============================================
echo.

:: Arrancar Backend en ventana separada
start "Backend API" cmd /k "cd /d %~dp0backend && call venv\Scripts\activate.bat && python run.py"

:: Esperar 3 segundos a que el backend arranque
timeout /t 3 /nobreak > nul

:: Arrancar Frontend en ventana separada
start "Frontend Web" cmd /k "cd /d %~dp0frontend && npm run dev"

:: Esperar 4 segundos a que el frontend arranque
timeout /t 4 /nobreak > nul

:: Abrir el navegador
echo Abriendo navegador...
start http://localhost:5173

echo.
echo ============================================
echo  La app se abre en: http://localhost:5173
echo  Deja abiertas las dos ventanas negras.
echo  Para cerrar la app, cierra las ventanas.
echo ============================================
pause
