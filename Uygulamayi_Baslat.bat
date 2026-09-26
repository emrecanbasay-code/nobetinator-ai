@echo off
setlocal
title Nobet Uygulamasi
cd /d "%~dp0"
if errorlevel 1 goto hata

if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" -m streamlit run "%~dp0app.py" --server.headless=false
) else (
    python -m streamlit run "%~dp0app.py" --server.headless=false
)
if errorlevel 1 goto hata
exit /b 0

:hata
echo.
echo Uygulama baslatilamadi. Yukaridaki hata mesajini kontrol edin.
pause
exit /b 1
