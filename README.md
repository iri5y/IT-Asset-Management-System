# IT Asset Management System

面向企业内部 IT 团队的资产全生命周期与仓储库存管理平台。系统采用中文界面，覆盖固定资产采购、领用、维修、归还、闲置、报废，以及配件和耗材库存管理。

> React 18 + FastAPI + PostgreSQL，支持 Excel 批量导入、条码扫描、角色权限、操作审计和低库存预警。

- [📌 Project Overview](#-project-overview)
- [🎯 Problem](#-problem)
- [🛠️ Technologies](#️-technologies)
- [✨ Key Features](#-key-features)
- [🖥️ Screenshots](#️-screenshots)
- [🏗️ Architecture](#️-architecture)
- [🔐 Security Considerations](#-security-considerations)
- [📖 Documentation](#-documentation)
- [🚀 Deployment](#-deployment)

## 📌 Project Overview

IT Asset Management System（IT 资产管理系统）集中管理企业 IT 固定资产、仓储配件和资产归还流程，为IT用户、资产管理员和只读用户提供统一的数据入口与可追溯的操作记录。

| 项目 | 说明 |
|---|---|
| 管理范围 | 台式机、笔记本电脑、平板电脑、配件、工具与办公耗材 |
| 生命周期 | 采购 → 入库 → 领用 → 维修 → 归还 → 闲置/报废 |
| 使用对象 | IT用户、系统管理员、审计及只读用户 |
| 界面语言 | 简体中文 |
| 数据库 | PostgreSQL；开发环境可使用 SQLite |
| 运行方式 | 前后端分离，可在 Windows 本机或局域网中部署 |

## 🎯 Problem

传统的 Excel 台账和分散登记方式容易带来以下问题：

- 资产标签、使用人、位置和状态分散，难以获得可信的实时库存。
- 资产领用、维修、归还与报废缺少完整流程，历史责任难以追踪。
- 固定资产和配件耗材混合管理，账面数量与实际库存容易不一致。
- 批量录入依赖人工复制，重复资产、无效字段和格式错误难以及时发现。
- 管理员、IT用户和审计人员权限边界不清，敏感操作缺少审计记录。

本项目通过统一数据模型、状态管理、库存预警、批量导入和操作日志，把资产与仓储数据集中到一套可查询、可审计的系统中。

## 🛠️ Technologies

| 层级 | 技术 |
|---|---|
| Frontend | React 18、React Router 7、Axios、Tailwind CSS 4、Lucide React |
| Build & Test | Vite 5、Vitest、Testing Library |
| Barcode & Excel | ZXing、SheetJS、Pandas、OpenPyXL |
| Backend | Python 3.10+、FastAPI、Uvicorn、Pydantic v2 |
| Data | SQLAlchemy 2.0、PostgreSQL、SQLite（开发支持） |
| Authentication | JWT（python-jose）、bcrypt |
| Configuration | `.env`、python-dotenv |

## ✨ Key Features

- **固定资产管理**：统一维护资产标签、序列号、固定资产编号、品牌、型号、员工、部门、位置和网络信息。
- **生命周期跟踪**：支持“闲置、使用中、维修中、报废”等状态，并保留资产操作和主机名变更历史。
- **仓储库存管理**：管理显示设备、音频设备、手机、输入设备、存储设备、线缆、工具及办公耗材。
- **库存预警与记录**：配置最低库存阈值，记录入库、领用和配件更换/新增操作。
- **Excel 批量导入**：提供映射、校验、预览和结果报告流程，降低批量录入成本。
- **扫码工作台**：通过摄像头或扫码枪识别序列号，辅助快速查询、创建和入库。
- **归还管理**：跟踪离职归还、设备更换、待归还和已归还记录。
- **统计看板**：展示资产状态、分类、品牌、部门、位置及仓储库存分布。
- **基础资料管理**：支持品牌、办公位置、库房位置以及两级部门结构。
- **用户与审计**：提供 `admin`、`helpdesk`、`readonly` 角色和关键操作日志。

## 🖥️ Screenshots

### Dashboard

资产状态、分类、品牌和位置等核心指标集中展示。

![资产统计看板](docs/dashboard.png)

### Asset Management

资产详情页集中展示基础信息、领用信息、网络配置和操作历史。

![固定资产详情](docs/assets-detail-page.png)

归还模块支持待处理、已完成和历史记录等业务场景。

![资产归还管理](docs/assets-return.png)

<details>
<summary>查看更多归还流程截图</summary>

![资产归还处理](docs/assets-return2.png)

![资产归还历史](docs/assets-return3.png)

</details>

### Excel Import

Excel 导入与扫码工作台用于批量录入、序列号识别和快速入库。

![扫码与批量录入工作台](docs/scan-workstation.png)

![批量录入操作界面](docs/scan-workstation2.png)

### Warehouse

仓储看板展示库存规模、品类分布和低库存状态。

![仓储统计看板](docs/warehouse-dashboard.png)

配件和耗材按业务品类进行库存管理。

![仓储配件管理](docs/warehouse-peripherals.png)

<details>
<summary>查看更多仓储与基础资料截图</summary>

![闲置资产管理](docs/warehouse-idle-items.png)

![报废资产管理](docs/warehouse-abandon-assets.png)

![部门层级管理](docs/department-management.png)

![办公位置管理](docs/office-locations.png)

</details>

## 🏗️ Architecture

```mermaid
flowchart LR
    U[浏览器 / 局域网用户] --> F[React SPA<br/>Vite + Tailwind CSS]
    F -->|Axios + JWT| A[FastAPI REST API]
    A --> S[业务服务<br/>资产 / 仓储 / 归还 / 导入]
    S --> O[SQLAlchemy ORM]
    O --> D[(PostgreSQL)]
    A --> X[Excel / 条码处理]
    A --> L[操作与资产日志]
```

项目采用前后端分离的单仓库结构：

```text
├── backend/                  # FastAPI API、ORM、认证、导入和运维脚本
│   ├── main.py               # 资产、仓储、归还及基础资料接口
│   ├── auth_routes.py        # 登录、用户和密码接口
│   ├── models.py             # SQLAlchemy 数据模型
│   ├── import_v2/            # Excel 导入管线、校验和报告
│   └── seed_demo_data.py     # 可重复执行的演示数据脚本
├── frontend/                 # React 单页应用
│   └── src/components/       # 看板、资产、仓储、归还和系统管理页面
├── docs/                     # README 界面截图
├── DEPLOYMENT_GUIDE.md       # 部署与故障排查
└── LAN_ACCESS_GUIDE.md       # 局域网访问配置
```

后端通过 REST API 提供数据；前端使用 Axios 携带 JWT 调用接口。SQLAlchemy 负责持久化，业务写操作同时生成资产日志或系统操作日志。所有业务时间以中国时区（UTC+8）的无时区时间存储。

## 🔐 Security Considerations

系统已实现以下基础安全控制：

- JWT 身份认证与基于角色的接口访问控制。
- bcrypt 密码哈希，不保存明文密码。
- 非管理员密码 90 天过期、首次登录改密及密码历史检查。
- 关键增删改操作记录用户、资源和时间，支持审计追踪。
- 资产删除需要管理员权限及删除原因，并保留删除记录。
- 系统始终保留至少一个可用管理员账号。

生产部署前还应完成：

1. 修改默认管理员密码，不在生产环境继续使用 `admin123`。
2. 使用随机长字符串配置 `SECRET_KEY`，禁止提交真实 `.env` 文件。
3. 使用最小权限数据库账号，并定期备份 PostgreSQL 数据。
4. 通过 Nginx、IIS 或其他反向代理启用 HTTPS，不直接暴露开发服务器。
5. 仅开放必要端口，并按实际域名/IP限制 CORS 和局域网访问范围。

## 📖 Documentation

- [部署与故障排查手册](DEPLOYMENT_GUIDE.md)：环境准备、首次部署、迁移、测试和常见问题。
- [局域网访问指南](LAN_ACCESS_GUIDE.md)：局域网地址、端口和 Windows 防火墙配置。
- [项目架构总结](项目架构总结.md)：模块、目录、数据表和开发约定说明。
- [版本更新说明](update_notes.md)：功能变化与维护记录。
- [FastAPI 在线接口文档](http://localhost:8000/docs)：后端启动后可访问的 OpenAPI/Swagger UI。

## 🚀 Deployment

### Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL 12+
- Windows 10/11 或 Windows Server

### 1. 创建数据库

```sql
CREATE DATABASE it_assets;
```

### 2. 配置环境变量

```bat
copy backend\.env.example backend\.env
copy frontend\.env.example frontend\.env
```

编辑 `backend/.env`：

```env
DATABASE_URL=postgresql+psycopg://postgres:你的密码@localhost:5432/it_assets
SECRET_KEY=请替换为随机且足够长的密钥
```

本机开发时，`frontend/.env` 可配置为：

```env
VITE_API_URL=http://localhost:8000
```

### 3. 安装依赖并初始化

```bat
cd backend
pip install -r requirements.txt
python init_admin.py

cd ..\frontend
npm install
```

如需加载可重复执行的演示数据：

```bat
cd /d backend
python seed_demo_data.py
```

### 4. 启动系统

在项目根目录执行：

```bat
start_system.bat
```

也可以分别启动：

```bat
backend\start_backend.bat
start_frontend.bat
```

| 服务 | 地址 |
|---|---|
| Web UI | http://localhost:5173 |
| REST API | http://localhost:8000 |
| API 文档 | http://localhost:8000/docs |

首次初始化会创建默认管理员 `admin / admin123`。登录后请立即修改密码。完整部署、迁移和排查步骤请参阅[部署与故障排查手册](DEPLOYMENT_GUIDE.md)。
