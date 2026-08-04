@echo off
chcp 65001 >nul
cd /d "%~dp0"
title turu - 它的记忆（这个窗口别关）
where python >/dev/null 2>/dev/null && (set PY=python) || (set PY=py)
%PY% turu\mcp_http.py
pause
