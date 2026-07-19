@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >/dev/null 2>/dev/null && (set PY=python) || (set PY=py)
rem 让每日提炼也能用夜间引擎（已设过也无妨）
setx TURU_LLM_CMD "claude -p" >/dev/null 2>nul
rem 生成开机自动导入脚本（无窗口）到启动文件夹
set "VBS=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\turu_daily.vbs"
>  "%VBS%" echo Set ws = CreateObject("WScript.Shell")
>> "%VBS%" echo ws.Run """%PY%"" ""%~dp0turu\importer.py"" --daily", 0, False
echo 已安装：以后每次开机，自动把前一天（和更早欠着）的对话导入它的记忆。
echo 现在先补导一次……
echo.
%PY% turu\importer.py --daily
echo.
pause
