@echo off
chcp 65001 > nul
echo ============================================================
echo            IT资产管理系统 - 数据库自动备份
echo ============================================================
echo.

cd /d "%~dp0"

::新增自定义文件保存路径变量
set "TARGET_DIR=D:\IT-Assets-System-Backup\Database"

echo 正在调用后端备份服务...

cd backend
python backup_service.py --output "%TARGET_DIR%"

cd ..

echo ============================================================
echo 提示：备份文件已安全存放在%TARGET_DIR%目录下。
echo ============================================================

echo 备份完成，程序退出。
timeout /t 5
