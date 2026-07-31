@echo off
chcp 65001 >nul
echo ========================================
echo   IT资产管理系统 - 后端服务
echo ========================================
echo.

:: 1. 修正路径：直接切换到当前脚本所在的绝对目录
cd /d "%~dp0"

echo 启动后端服务器
echo 后端地址:http://0.0.0.0:8000
echo API文档:/docs
echo.

:: 2.使用虚拟环境里的 python.exe 绝对路径启动，并去掉 --reload
:: 注意：请确认你的虚拟环境文件夹名字是 .venv 还是 venv, 如果是 venv 请把下面改一下
"%~dp0venv\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000

pause
