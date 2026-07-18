@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >/dev/null 2>/dev/null && (set PY=python) || (set PY=py)
echo ============ 演示一：记、联想、忘、疼 ============
%PY% examples\demo.py
echo.
echo ============ 演示二：睡几晚，看它做梦 ============
%PY% examples\demo_sleep.py
echo.
echo ============ 演示三：三个月，看它长性格 ============
%PY% examples\demo_person.py
echo.
pause
