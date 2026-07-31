@echo off
chcp 65001 >nul
echo ========================================
echo   IT资产管理系统 - 前端服务
echo ========================================
echo.
cd /d "%~dp0frontend"
echo 启动前端开发服务器...
echo 前端地址: http://localhost:5173
echo.
npm run dev
pause
