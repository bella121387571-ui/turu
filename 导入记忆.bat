@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >/dev/null 2>/dev/null && (set PY=python) || (set PY=py)
if "%~1"=="" (
  echo 用法：把 conversations.json（claude.ai 导出的）或对话记录文件夹
  echo       直接拖到本文件图标上，它会把那些旧日子重新活一遍。
  echo.
  pause
  exit /b
)
%PY% turu\importer.py "%~1"
pause
