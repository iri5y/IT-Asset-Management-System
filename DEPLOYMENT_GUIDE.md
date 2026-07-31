# IT资产管理系统 — 部署与排查手册

## 目录

1. [环境要求](#1-环境要求)
2. [首次部署](#2-首次部署)
3. [日常启动与停止](#3-日常启动与停止)
4. [环境变量配置](#4-环境变量配置)
5. [数据库迁移](#5-数据库迁移)
6. [局域网多设备访问](#6-局域网多设备访问)
7. [常见问题排查](#7-常见问题排查)
8. [数据对账与修复](#8-数据对账与修复)
9. [运行测试](#9-运行测试)

---

## 1. 环境要求

| 软件 | 最低版本 | 说明 |
|---|---|---|
| Python | 3.10+ | 后端运行环境 |
| Node.js | 18 LTS+ | 前端构建和开发服务器 |
| PostgreSQL | 12+ | 主数据库 |

### 验证安装

```bash
python --version
node --version
npm --version
psql --version
```

---

## 2. 首次部署

### 步骤一：克隆/复制项目

将项目文件夹放到目标机器上，例如 `C:\ProjectLab\IT Fixed Asset Inventory-pretest\`。

### 步骤二：创建 PostgreSQL 数据库

在 PostgreSQL 中创建数据库（二选一）：

**方法 A — 使用 psql 命令行：**
```bash
psql -U postgres -c "CREATE DATABASE it_assets;"
```

**方法 B — 使用项目脚本（需先配置 .env）：**
```bash
cd backend
python create_database.py
```

**方法 C — 使用 pgAdmin 图形界面：**
右键 Databases → Create → Database，名称填 `it_assets`。

### 步骤三：配置后端环境变量

复制示例文件并编辑：
```bash
cd backend
copy .env.example .env
```

编辑 `backend/.env`：
```env
DATABASE_URL=postgresql+psycopg://postgres:你的密码@localhost:5432/it_assets
SECRET_KEY=请替换为随机长字符串
```

> `SECRET_KEY` 用于 JWT 签名，建议使用 `python -c "import secrets; print(secrets.token_hex(32))"` 生成。

### 步骤四：安装后端依赖

```bash
cd backend
pip install -r requirements.txt
```

### 步骤五：初始化数据库表和管理员账号

```bash
cd backend

# 运行认证系统迁移（创建 users、operation_logs 等表）
python migrate_auth.py

# 创建管理员账号（默认 admin / admin123）
python init_admin.py

# 初始化基础数据（品牌、部门、库房位置）
python init_brands.py
python init_departments.py
python init_locations.py
```

### 步骤六：配置前端环境变量

复制示例文件：
```bash
cd frontend
copy .env.example .env
```

编辑 `frontend/.env`（本机访问保持默认即可）：
```env
VITE_API_URL=
```

### 步骤七：安装前端依赖

```bash
cd frontend
npm install
```

### 步骤八：启动系统

```bash
# 方式一：一键启动（推荐）
start_system.bat

# 方式二：分别启动
start_backend.bat   # 新窗口启动后端
start_frontend.bat  # 新窗口启动前端
```

### 步骤九：验证部署

打开浏览器访问 http://localhost:5173，使用 `admin` / `admin123` 登录。

**首次登录后请立即修改默认密码！**

---

## 3. 日常启动与停止

### 启动

```bash
start_system.bat
```

脚本会自动：
1. 检测 PostgreSQL 服务并启动（如未运行）
2. 在新窗口启动后端（端口 8000）
3. 在新窗口启动前端（端口 5173）

### 停止

直接关闭后端和前端的命令行窗口即可。

### 仅启动后端（供局域网其他设备访问）

```bash
start_backend.bat
```

后端监听 `0.0.0.0:8000`，局域网内其他设备可通过 `http://本机IP:8000` 访问。

---

## 4. 环境变量配置

### 后端 `backend/.env`

| 变量 | 说明 | 示例 |
|---|---|---|
| `DATABASE_URL` | PostgreSQL 连接字符串 | `postgresql+psycopg://postgres:password@localhost:5432/it_assets` |
| `SECRET_KEY` | JWT 签名密钥（必须保密） | 随机 64 位十六进制字符串 |

### 前端 `frontend/.env`

| 变量 | 说明 | 示例 |
|---|---|---|
| `VITE_API_URL` | 后端 API 地址 | ``（本机）或 `http://192.168.1.100:8000`（局域网） |

> 修改 `frontend/.env` 后需要重启前端服务才能生效。

---

## 5. 数据库迁移

项目使用独立的 Python 脚本管理数据库结构变更，不使用 Alembic。

### 迁移脚本列表（按执行顺序）

| 脚本 | 说明 |
|---|---|
| `migrate_auth.py` | 创建认证相关表（users、operation_logs、asset_deletion_records） |
| `migrate_soft_delete.py` | 资产软删除字段（is_deleted、deleted_at） |
| `migrate_asset_log_operator.py` | 操作日志添加 operator 字段 |
| `migrate_asset_new_fields.py` | 资产添加 ip_address、supervisor 字段 |
| `migrate_laptop_fields.py` | 笔记本专用字段（bios_password、tpm_status、has_desktop） |
| `migrate_dept_tree.py` | 部门表添加 parent_id（树形结构） |
| `migrate_must_change_password.py` | 用户表添加 must_change_password 字段 |
| `migrate_warehouse_assets.py` | 库房资产表字段调整（specifications → receiver_name） |
| `migrate_pad_to_mobile.py` | 数据迁移：PAD 品类改为移动设备 |
| `migrate_return_record.py` | 归还记录表：asset_id 外键改为 asset_name 字符串 |
| `migrate_fix_data_consistency.py` | 修复历史数据一致性问题 |
| `migrate_from_warehouse.py` | 资产表添加 from_warehouse 字段（库房发放标记） |

### 在新环境执行所有迁移

```bash
cd backend
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
```

> 所有迁移脚本均有幂等性保护（检查列是否已存在），重复执行不会报错。

---

## 6. 局域网多设备访问

详见 [LAN_ACCESS_GUIDE.md](LAN_ACCESS_GUIDE.md)，快速步骤如下：

**1. 获取本机 IP：**
```bash
ipconfig
# 找到 IPv4 地址，例如 192.168.1.100
```

**2. 修改前端配置：**
编辑 `frontend/.env`：
```env
VITE_API_URL=http://192.168.1.100:8000
```

**3. 配置防火墙（管理员权限）：**
```bash
setup_lan.bat
```

**4. 重启前端服务。**

其他设备访问：`http://192.168.1.100:5173`

---

## 7. 常见问题排查

### 7.1 后端无法启动

**症状**：运行 `start_backend.bat` 后报错退出。

**排查步骤：**

```bash
cd backend
python -m uvicorn main:app --reload --port 8000
```

查看具体错误信息：

| 错误信息 | 原因 | 解决方法 |
|---|---|---|
| `ModuleNotFoundError` | 依赖未安装 | `pip install -r requirements.txt` |
| `could not connect to server` | PostgreSQL 未运行或连接信息错误 | 检查 `.env` 中的 `DATABASE_URL` |
| `password authentication failed` | 数据库密码错误 | 修改 `.env` 中的密码 |
| `database "it_assets" does not exist` | 数据库未创建 | `python create_database.py` |
| `column "xxx" does not exist` | 迁移脚本未执行 | 执行对应的 `migrate_xxx.py` |
| `address already in use` | 8000 端口被占用 | 见下方"端口被占用"处理 |

**检查 PostgreSQL 服务：**
```bash
# 查看服务状态
sc query postgresql-x64-17

# 手动启动
net start postgresql-x64-17
```

---

### 7.2 前端无法启动

**症状**：运行 `start_frontend.bat` 后报错。

| 错误信息 | 原因 | 解决方法 |
|---|---|---|
| `npm: command not found` | Node.js 未安装 | 安装 Node.js 18 LTS |
| `Cannot find module` | 依赖未安装 | `cd frontend && npm install` |
| `Port 5173 is already in use` | 端口被占用 | 见下方"端口被占用"处理 |

---

### 7.3 前端可以打开，但数据加载失败

**症状**：页面显示但资产列表为空，或出现"获取资产失败"提示。

**排查步骤：**

1. 打开浏览器开发者工具（F12）→ Network 标签，查看 API 请求是否失败
2. 检查请求地址是否正确（应为 `/assets/`）
3. 确认后端服务正在运行：访问 /docs

**常见原因：**

| 现象 | 原因 | 解决方法 |
|---|---|---|
| 请求地址是 `undefined/assets/` | `VITE_API_URL` 未配置 | 检查 `frontend/.env` 文件 |
| 401 Unauthorized | Token 过期或未登录 | 重新登录 |
| CORS 错误 | 后端 CORS 配置问题 | 检查 `main.py` 中的 `allow_origins` |
| Network Error | 后端未运行 | 启动后端服务 |

---

### 7.4 登录失败

**症状**：输入账号密码后提示"用户名或密码错误"。

**排查步骤：**

```bash
cd backend
# 重新创建管理员账号
python init_admin.py
```

如果提示"admin 已存在"，说明账号存在但密码可能被修改。可以通过数据库直接重置：

```sql
-- 在 psql 中执行
UPDATE users SET hashed_password = '$2b$12$...' WHERE username = 'admin';
```

或者删除后重建：
```bash
# 在 psql 中
DELETE FROM users WHERE username = 'admin';
# 然后重新运行
python init_admin.py
```

---

### 7.5 端口被占用

**查找占用进程：**
```bash
# 查找占用 8000 端口的进程
netstat -ano | findstr :8000

# 查找占用 5173 端口的进程
netstat -ano | findstr :5173
```

**终止进程（替换 PID 为实际进程号）：**
```bash
taskkill /PID 12345 /F
```

**或修改端口：**
- 后端：修改 `start_backend.bat` 中的 `--port 8000` 为其他端口，同时更新 `frontend/.env` 中的 `VITE_API_URL`
- 前端：修改 `frontend/vite.config.js` 中的 `port: 5173`

---

### 7.6 资产状态变更失败

**症状**：操作资产状态时提示"非法状态转换"。

系统强制执行以下状态机，不允许跨状态跳转：

```
闲置 ──→ 使用中
闲置 ──→ 维修中
闲置 ──→ 报废
使用中 ──→ 闲置
使用中 ──→ 维修中
使用中 ──→ 报废
维修中 ──→ 闲置
维修中 ──→ 使用中
维修中 ──→ 报废
报废（终态，不可转换）
```

如果需要强制修改状态（例如历史数据修复），可以直接在数据库中更新：
```sql
UPDATE assets SET status = '闲置' WHERE asset_tag = 'IT-PC26-000001';
```

---

### 7.7 库存数量异常

**症状**：库房可用数量与实际不符，或出现负数。

**运行对账脚本：**
```bash
cd backend
python reconcile_inventory.py
```

脚本会输出：
- 各品类闲置资产数 vs 库房可用量对比
- 数量守恒异常（total ≠ available + allocated）
- 闲置资产仍绑定员工信息的异常记录

**修复历史数据一致性问题：**
```bash
cd backend
python migrate_fix_data_consistency.py
```

---

### 7.8 Excel 导入失败

**症状**：批量导入资产时报错或部分行失败。

**常见原因：**

| 错误 | 原因 | 解决方法 |
|---|---|---|
| 序列号重复 | 该 SN 已存在于数据库 | 检查并修改 Excel 中的序列号 |
| 资产编号重复 | 该 asset_tag 已存在 | 删除 Excel 中的资产编号列，让系统自动生成 |
| 品类不支持 | 品类名称不在支持列表中 | 使用标准品类名（台式机/笔记本电脑/显示器等） |
| 必填字段为空 | 笔记本/台式机/服务器/移动设备必须有序列号 | 补充序列号 |

**下载导入模板：**
登录系统后，在资产管理页面点击"导入"→"下载模板"。

---

### 7.9 密码相关问题

**密码过期无法登录：**
- 非管理员用户密码 90 天后过期，登录后会强制跳转修改密码页面
- 管理员账号密码过期只显示提醒横幅，不强制修改

**忘记密码（管理员重置）：**
管理员可在"用户管理"页面重置其他用户密码。

**管理员自己忘记密码：**
```bash
cd backend
# 删除旧管理员并重建
python -c "
from database import SessionLocal
db = SessionLocal()
from models import User
db.query(User).filter(User.username=='admin').delete()
db.commit()
db.close()
print('已删除')
"
python init_admin.py
```

---

### 7.10 归还记录功能异常

**症状**：添加归还记录后资产状态未变为闲置。

**说明**：这是正常设计。添加归还记录只是登记"待归还"意向，不会立即改变资产状态。需要在归还管理页面点击"处理归还"，将记录状态改为"已归还"，才会触发资产状态联动变更为"闲置"。

**如果处理归还后资产状态仍未变更：**
1. 检查归还记录中的"资产名"是否与资产的 hostname 或 asset_tag 完全一致（区分大小写）
2. 查看后端日志是否有报错

---

## 8. 数据对账与修复

### 运行库存对账

```bash
cd backend
python reconcile_inventory.py
```

输出示例：
```
══════════════════════════════════════════════════════════════════════
  IT 资产数据对账报告  |  2026-05-11 10:30:00
══════════════════════════════════════════════════════════════════════

── 1. assets 表中 status='闲置' 的资产统计 ──
   品类             数量
   ────────────────────────
   台式机              5
   笔记本电脑          8
   ...

── 3. 品类维度交叉对比 ──
   品类             闲置资产数   库房可用量     差额     状态
   ────────────────────────────────────────────────────────
   台式机                  5           5       +0     一致
   笔记本电脑              8           8       +0     一致
```

### 修复数据一致性

```bash
cd backend
python migrate_fix_data_consistency.py
```

修复内容：
1. 清除闲置资产上残留的员工绑定信息
2. 修复库房资产 `total_quantity ≠ available_quantity + allocated_quantity` 的记录

---

## 9. 运行测试

测试需要独立的 PostgreSQL 测试数据库。

### 配置测试数据库

```bash
# 创建测试数据库
psql -U postgres -c "CREATE DATABASE it_asset_test;"
```

设置环境变量（或在 `.env` 中添加）：
```bash
set TEST_DATABASE_URL=postgresql://postgres:你的密码@localhost:5432/it_asset_test
```

### 运行测试

```bash
cd backend
# 运行所有测试
pytest tests/ -v

# 只运行认证测试
pytest tests/test_auth.py -v

# 只运行生命周期测试
pytest tests/test_asset_lifecycle.py -v

# 只运行状态流转测试
pytest tests/test_asset_status_flow.py -v

# 运行带标记的测试
pytest tests/ -m auth -v
pytest tests/ -m lifecycle -v
pytest tests/ -m status_flow -v
```

### 测试覆盖范围

| 测试文件 | 覆盖场景 |
|---|---|
| `test_auth.py` | 登录成功/失败、Token 验证 |
| `test_asset_lifecycle.py` | 资产入库→分配→归还→闲置完整链路 |
| `test_asset_status_flow.py` | 状态流转、信息变更、日志验证 |
| `test_import_unit.py` | Excel 导入单元测试 |
| `test_import_integration.py` | Excel 导入集成测试 |

---

## 附录：常用数据库操作

```sql
-- 查看所有用户
SELECT id, username, role, is_active FROM users;

-- 查看资产状态分布
SELECT status, COUNT(*) FROM assets WHERE is_deleted = FALSE GROUP BY status;

-- 查看库房库存
SELECT name, category, available_quantity, total_quantity FROM warehouse_assets ORDER BY category;

-- 查看最近的操作日志
SELECT a.asset_tag, l.action, l.description, l.operator, l.created_at
FROM asset_logs l
JOIN assets a ON l.asset_id = a.id
ORDER BY l.created_at DESC
LIMIT 20;

-- 查看待归还记录
SELECT employee_name, asset_name, return_reason, created_at
FROM return_records
WHERE is_returned = FALSE
ORDER BY created_at DESC;
```
