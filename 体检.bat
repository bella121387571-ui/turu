@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >/dev/null 2>/dev/null && (set PY=python) || (set PY=py)
echo ================ 心跳检查 M0 ================
%PY% tests\test_m0.py
echo.
echo ================ 睡梦检查 M1 ================
%PY% tests\test_m1.py
echo.
pause
