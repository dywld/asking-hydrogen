@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -u kgs_watch.py watch --hours 24 --apply %*
pause
