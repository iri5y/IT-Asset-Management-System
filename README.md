# IT资产管理系统

企业级 IT 资产全生命周期管理系统，基于 FastAPI + React 构建，支持资产入库、分配、维修、归还、报废的完整流程，以及库房耗材库存管理。

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.10+、FastAPI、SQLAlchemy 2.0、PostgreSQL、JWT |
| 前端 | React 18、React Router v7、Axios、Tailwind CSS v4、Vite 5 |

## 快速启动

```bash
# 一键启动（自动检测 PostgreSQL 并启动前后端）
start_system.bat

# 或分别启动
start_backend.bat
start_frontend.bat
```

启动后访问：
- **前端界面**：http://localhost:5173
- **后端 API 文档**：/docs

## 默认账号

| 账号 | 密码 | 角色 |
|---|---|---|
| admin | admin123 | 管理员 |

**首次登录后请立即修改默认密码。**

## 项目结构

```
├── backend/                  # FastAPI 后端
│   ├── main.py               # 所有资产/库房/归还路由
│   ├── auth_routes.py        # 认证/用户路由
│   ├── models.py             # SQLAlchemy ORM 模型
│   ├── schemas.py            # Pydantic 请求/响应 Schema
│   ├── database.py           # 数据库连接配置
│   ├── auth.py               # JWT 工具、密码哈希
│   ├── import_service.py     # Excel 批量导入服务
│   ├── reconcile_inventory.py # 库存数据对账工具
│   ├── init_admin.py         # 初始化管理员账号
│   ├── init_brands.py        # 初始化品牌数据
│   ├── init_departments.py   # 初始化部门数据
│   ├── init_locations.py     # 初始化库房位置
│   ├── create_database.py    # 创建 PostgreSQL 数据库
│   ├── migrate_*.py          # 历史数据库迁移脚本
│   ├── tests/                # 集成测试
│   ├── requirements.txt      # Python 依赖
│   └── .env                  # 环境变量（不提交）
│
├── frontend/                 # React 前端
│   ├── src/
│   │   ├── App.jsx           # 根组件、路由、顶层状态
│   │   ├── main.jsx          # ReactDOM 入口
│   │   ├── index.css         # 全局样式
│   │   ├── contexts/
│   │   │   └── AuthContext.jsx  # 认证状态管理
│   │   └── components/       # 所有页面组件（平铺结构）
│   ├── package.json
│   └── vite.config.js
│
├── start_system.bat          # 一键启动脚本
├── start_backend.bat         # 单独启动后端
├── start_frontend.bat        # 单独启动前端
├── setup_auth.bat            # 首次部署认证初始化
├── setup_lan.bat             # 局域网访问配置
├── README.md                 # 本文件
└── LAN_ACCESS_GUIDE.md       # 局域网访问详细指南
```

## 详细文档

- [部署与排查手册](DEPLOYMENT_GUIDE.md) — 完整部署步骤、环境配置、常见问题排查
- [局域网访问指南](LAN_ACCESS_GUIDE.md) — 多设备局域网访问配置
