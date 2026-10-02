@echo off
chcp 65001 >nul
title 市场管理中心物料仓库进销存系统
cd /d "%~dp0"
echo ============================================
echo   物料仓库进销存系统 启动中...
echo ============================================
echo.
echo 请勿关闭此窗口，关闭即停止服务。
echo.
start "" http://127.0.0.1:5000
venv\Scripts\python.exe app.py
pause
