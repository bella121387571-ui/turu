@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul && (set PY=python) || (set PY=py)
echo ================ 心跳检查 M0 ================
%PY% tests\test_m0.py
echo.
echo ================ 睡梦检查 M1 ================
%PY% tests\test_m1.py
echo.
echo ================ 性子检查 M2 ================
%PY% tests\test_m2.py
echo.
echo ================ 上身检查 M3 ================
%PY% tests\test_m3.py
echo.
echo ================ 梦语检查 M4 ================
%PY% tests\test_m4.py
echo.
echo ================ 导入检查 ====================
%PY% tests\test_import.py
echo.
echo ================ 近况页检查 ==================
%PY% tests\test_web.py
echo.
echo ================ 织网检查 ====================
%PY% tests\test_weave.py
echo.
echo ================ 远程检查 ====================
%PY% tests\test_http.py
echo.
pause
