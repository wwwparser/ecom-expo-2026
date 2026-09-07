@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Запускаю отчёт с открытием постов в Telegram Desktop...
python serve_report.py
pause
