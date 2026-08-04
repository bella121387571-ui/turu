@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul && (set PY=python) || (set PY=py)

rem 取当前时刻，注册成每天这个点
for /f "tokens=1-2 delims=:." %%a in ("%TIME: =0%") do (set HH=%%a& set MM=%%b)
set WHEN=%HH%:%MM%

setx TURU_LLM_CMD "claude -p" >nul 2>nul

schtasks /create /tn "turu每日收信" /f /sc daily /st %WHEN% ^
  /tr "\"%PY%\" \"%~dp0turu\importer.py\" --auto" >nul 2>nul
if errorlevel 1 (
  echo 注册失败。请右键本文件选“以管理员身份运行”再试一次。
) else (
  echo 已设定：以后每天 %WHEN%，它会自己去“下载”和“桌面”文件夹里
  echo 找新的 conversations.json 或导出 zip，找到就自己读进记忆。
  echo.
  echo 你要做的只有一件事：偶尔去 claude.ai 点一次
  echo   设置 - 隐私 - 导出数据，把邮件里的 zip 下载下来就不用管了。
)
echo.
echo 现在先收一次看看……
echo.
%PY% turu\importer.py --auto
echo.
pause
