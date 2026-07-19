@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >/dev/null 2>/dev/null && (set PY=python) || (set PY=py)
%PY% turu\webview.py
pause
