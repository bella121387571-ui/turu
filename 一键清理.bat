@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在清理已删除的旧功能……
echo.
set "VBS=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\turu_daily.vbs"
if exist "%VBS%" (del /q "%VBS%" & echo   [已删] 开机自动导入项) else (echo   [跳过] 开机自动导入项 未安装)
if exist "turu\webview.py" (del /q "turu\webview.py" & echo   [已删] turu\webview.py) else (echo   [跳过] turu\webview.py)
if exist "tests\test_web.py" (del /q "tests\test_web.py" & echo   [已删] tests\test_web.py) else (echo   [跳过] tests\test_web.py)
if exist "examples" (rd /s /q "examples" & echo   [已删] examples 文件夹) else (echo   [跳过] examples 文件夹)
if exist "手机查看.bat" (del /q "手机查看.bat" & echo   [已删] 手机查看.bat) else (echo   [跳过] 手机查看.bat)
if exist "演示.bat" (del /q "演示.bat" & echo   [已删] 演示.bat) else (echo   [跳过] 演示.bat)
if exist "安装每日自动导入.bat" (del /q "安装每日自动导入.bat" & echo   [已删] 安装每日自动导入.bat) else (echo   [跳过] 安装每日自动导入.bat)
echo.
if exist "data\turu.db" (echo   [保留] data\turu.db 它的记忆完好无损) else (echo   [注意] 没找到 data\turu.db)
echo.
echo 清理完成。接下来双击 远程连接.bat 就能用了。
echo.
pause
