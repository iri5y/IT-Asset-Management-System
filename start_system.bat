@echo off
chcp 65001 >nul
echo ========================================
echo   IT资产管理系统 - 一键启动
echo ========================================
echo.

echo 正在检查环境...

:: 检查Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python未安装，请先安装Python
    pause
    exit /b 1
)
echo ✅ Python已安装

:: 检查Node.js
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Node.js未安装，请先安装Node.js
    pause
    exit /b 1
)
echo ✅ Node.js已安装

echo.
echo 正在检查数据库...
:: 检测PostgreSQL服务
setlocal enabledelayedexpansion
set "POSTGRES_SERVICE="
for %%s in (postgresql-x64-18 postgresql-x64-17 postgresql-x64-16 postgresql-x64-15 postgresql) do (
    sc query "%%s" >nul 2>&1
    if !errorlevel! == 0 (
        set "POSTGRES_SERVICE=%%s"
        goto :service_found
    )
)

echo ❌ PostgreSQL服务未找到
echo 请确认已安装PostgreSQL并且服务名称正确
echo.
echo 💡 检查步骤：
echo 1. 确认PostgreSQL已安装
echo 2. 打开"服务"管理器查看PostgreSQL服务名称
echo 3. 确认服务已启用
pause
exit /b 1

:service_found
echo ✅ 找到PostgreSQL服务: !POSTGRES_SERVICE!

sc query "!POSTGRES_SERVICE!" | find "RUNNING" >nul
if %errorlevel% neq 0 (
    echo 🔄 PostgreSQL服务未运行，正在启动...
    net start "!POSTGRES_SERVICE!"
    if %errorlevel% neq 0 (
        echo ❌ PostgreSQL服务启动失败
        echo 请尝试以管理员权限运行此脚本
        pause
        exit /b 1
    )
    echo ✅ PostgreSQL服务启动成功
) else (
    echo ✅ PostgreSQL服务正在运行
)
endlocal

:: 保存项目根目录
set "PROJECT_ROOT=%~dp0"

echo.
echo 正在启动后端服务...
cd /d "%PROJECT_ROOT%backend"

:: 检查并安装后端依赖
python -c "import uvicorn" >nul 2>&1
if %errorlevel% neq 0 (
    echo 正在安装后端依赖...
    pip install -r requirements.txt
)

:: 检查数据库连接和创建数据库
echo 正在测试数据库连接...
python create_database.py
if %errorlevel% neq 0 (
    echo.
    echo ❌ 数据库连接失败！
    echo.
    echo 💡 解决建议：
    echo 1. 检查 backend\.env 中的 DATABASE_URL 配置
    echo 2. 确认PostgreSQL密码是否正确
    echo 3. 确认PostgreSQL服务正在运行
    echo 4. 确认数据库端口5432未被占用
    echo.
    pause
    exit /b 1
) else (
    echo ✅ 数据库连接成功
)

:: 启动后端（在新窗口）
echo ✅ 启动后端服务器...
start "IT资产管理-后端" cmd /k "cd /d "%PROJECT_ROOT%backend" && python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000"

:: 等待后端启动
echo 等待后端启动...
timeout /t 3 /nobreak >nul

cd /d "%PROJECT_ROOT%frontend"

:: 检查并安装前端依赖
if not exist node_modules (
    echo 正在安装前端依赖...
    npm install
)

:: 启动前端（在新窗口）
echo ✅ 启动前端服务器...
start "IT资产管理-前端" cmd /k "cd /d "%PROJECT_ROOT%frontend" && npm run dev"

echo.
echo ========================================
echo   启动完成！
echo ========================================
echo.
echo 🌐 访问地址:
echo   前端: http://localhost:5173
echo   后端: 
echo   API文档: /docs
echo.
echo 💡 提示:
echo   - 两个服务窗口会自动打开
echo   - 关闭窗口即可停止服务
echo.
pause
