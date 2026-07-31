@echo off
chcp 65001 >nul
echo ========================================
echo   IT资产管理系统 - 局域网配置
echo ========================================
echo.

echo 正在获取本机IP地址...
echo.

for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    set IP=%%a
    goto :found
)

:found
set IP=%IP:~1%
echo ✓ 你的IP地址是: %IP%
echo.

echo ========================================
echo   配置步骤
echo ========================================
echo.
echo 1. 编辑 frontend\.env 文件
echo    将 VITE_API_URL 设置为: http://%IP%:8000
echo.
echo 2. 配置防火墙（需要管理员权限）
echo    允许端口 8000 和 5173
echo.
echo 3. 启动后端:
echo    cd backend
echo    python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
echo.
echo 4. 启动前端:
echo    cd frontend
echo    npm run dev
echo.
echo 5. 访问地址:
echo    本机: http://localhost:5173
echo    局域网: http://%IP%:5173
echo.
echo ========================================
echo.

echo 是否自动配置防火墙规则？（需要管理员权限）
echo 按任意键继续，或关闭窗口取消...
pause >nul

echo.
echo 正在配置防火墙...
netsh advfirewall firewall add rule name="IT Asset Backend" dir=in action=allow protocol=TCP localport=8000 >nul 2>&1
if %errorlevel% equ 0 (
    echo ✓ 后端端口 8000 已允许
) else (
    echo ✗ 配置失败，请以管理员权限运行
)

netsh advfirewall firewall add rule name="IT Asset Frontend" dir=in action=allow protocol=TCP localport=5173 >nul 2>&1
if %errorlevel% equ 0 (
    echo ✓ 前端端口 5173 已允许
) else (
    echo ✗ 配置失败，请以管理员权限运行
)

echo.
echo ========================================
echo   配置完成
echo ========================================
echo.
echo 请手动编辑 frontend\.env 文件:
echo VITE_API_URL=http://%IP%:8000
echo.
echo 然后启动服务即可！
echo.
pause
