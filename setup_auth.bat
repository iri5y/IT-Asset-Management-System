@echo off
chcp 65001 >nul
echo ========================================
echo   IT资产管理系统 - 首次部署初始化
echo ========================================
echo.

cd /d "%~dp0backend"

echo [1/4] 安装 Python 依赖...
pip install -r requirements.txt
if errorlevel 1 (
    echo ❌ 安装依赖失败，请检查 Python 环境
    pause
    exit /b 1
)

echo.
echo [2/4] 执行数据库迁移（按顺序）...
python migrate_auth.py
python migrate_soft_delete.py
python migrate_asset_log_operator.py
python migrate_asset_new_fields.py
python migrate_laptop_fields.py
python migrate_dept_tree.py
python migrate_must_change_password.py
python migrate_warehouse_assets.py
python migrate_pad_to_mobile.py
python migrate_return_record.py
python migrate_fix_data_consistency.py
python migrate_from_warehouse.py
if errorlevel 1 (
    echo ❌ 数据库迁移失败，请检查数据库连接和 .env 配置
    pause
    exit /b 1
)

echo.
echo [3/4] 创建管理员账号...
python init_admin.py

echo.
echo [4/4] 初始化基础数据（品牌、部门、库房位置）...
python init_brands.py
python init_departments.py
python init_locations.py

echo.
echo ========================================
echo   初始化完成！
echo ========================================
echo.
echo 默认管理员账号：
echo   用户名: admin
echo   密码:   admin123
echo.
echo ⚠️  请立即登录并修改默认密码！
echo.
pause
