@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >/dev/null 2>/dev/null && (set PY=python) || (set PY=py)
if exist cloudflared.exe (
  echo 同时启动 记忆服务器 + 隧道。看下面输出里 trycloudflare.com 的网址，
  echo 连接器地址 = 那个网址 + /令牌/mcp（令牌见下方本机地址一行）
  echo.
  start "turu-remote" %PY% turu\mcp_http.py
  cloudflared.exe tunnel --url http://127.0.0.1:7778
) else (
  echo 未找到 cloudflared.exe（放到本文件夹可一键开隧道），先只启动本机服务器：
  echo.
  %PY% turu\mcp_http.py
)
pause
