# 技术设计文档：基于 pytest 的自动化集成测试

## 概述

本设计文档描述 IT 资产管理系统集成测试的技术实现方案。测试通过 FastAPI TestClient 在进程内发送 HTTP 请求，使用独立的 PostgreSQL 测试数据库，覆盖两条核心业务链路：**资产全生命周期**和**资产状态流转**。

### 设计目标

1. **环境隔离**：测试数据库与生产数据库完全隔离，使用相同的 PostgreSQL 引擎确保行为一致性
2. **数据隔离**：每个测试函数之间通过事务回滚机制实现数据隔离
3. **认证集成**：通过 dependency override 机制替换 `get_db`，并通过 `/auth/login` 获取真实 JWT token
4. **链路完整性**：每条链路内的测试步骤按顺序执行，每步操作后通过 API 查询验证状态
5. **可维护性**：使用 pytest fixture 和 marker 组织测试，便于单独执行和维护

### 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 测试数据库引擎 | PostgreSQL（非 SQLite） | 与生产环境一致，避免 SQL 方言差异导致的假阳性/假阴性 |
| 数据隔离策略 | 会话级建表/销表 + 函数级事务回滚 | 会话级减少建表开销，函数级保证测试独立性 |
| 认证方式 | 通过 `/auth/login` API 获取真实 token | 测试真实认证流程，而非绕过认证 |
| 链路测试组织 | 使用测试类 + 有序方法 | 链路内步骤有依赖关系，需要顺序执行并共享状态 |
| HTTP 客户端 | FastAPI TestClient | 进程内调用，无需启动服务器，速度快且可靠 |

## 架构

### 整体架构

```mermaid
graph TB
    subgraph 测试层
        TC[TestClient] --> APP[FastAPI App]
        TF[pytest fixtures] --> TC
        TM[pytest markers] --> TC
    end

    subgraph 应用层
        APP --> AUTH[auth.py / auth_routes.py]
        APP --> MAIN[main.py routes]
        AUTH --> DB_DEP[get_db dependency]
        MAIN --> DB_DEP
    end

    subgraph 数据层
        DB_DEP -->|override| TEST_DB[(PostgreSQL 测试数据库)]
        DB_DEP -->|生产| PROD_DB[(PostgreSQL 生产数据库)]
    end

    style TEST_DB fill:#4CAF50,color:#fff
    style PROD_DB fill:#f44336,color:#fff
```

### 测试执行流程

```mermaid
sequenceDiagram
    participant P as pytest
    participant F as Fixtures
    participant TC as TestClient
    participant API as FastAPI App
    participant DB as 测试数据库

    P->>F: 会话开始 (session scope)
    F->>DB: create_all() 创建所有表
    F->>DB: 插入管理员用户
    F->>TC: 创建 TestClient (override get_db)
    F->>API: POST /auth/login
    API-->>F: JWT access_token

    loop 每个测试函数
        P->>F: 函数开始 (function scope)
        F->>DB: BEGIN 事务
        P->>TC: 执行测试步骤
        TC->>API: HTTP 请求 (带 Authorization header)
        API->>DB: 数据库操作
        DB-->>API: 查询结果
        API-->>TC: HTTP 响应
        TC-->>P: 断言验证
        P->>F: 函数结束
        F->>DB: ROLLBACK 事务
    end

    P->>F: 会话结束
    F->>DB: drop_all() 清理所有表
```

## 组件与接口

### 文件结构

```
backend/
├── tests/
│   ├── __init__.py              # 包标识文件
│   ├── conftest.py              # pytest fixtures（数据库、客户端、认证）
│   ├── test_auth.py             # 认证流程测试（需求 2）
│   ├── test_asset_lifecycle.py  # 资产全生命周期链路测试（需求 3）
│   └── test_asset_status_flow.py # 资产状态流转链路测试（需求 4）
```

### 组件说明

#### 1. conftest.py — 测试基础设施

负责提供所有测试共享的 fixture，包括数据库连接、表创建/销毁、管理员用户、已认证客户端。

**核心 Fixtures：**

| Fixture 名称 | Scope | 职责 |
|-------------|-------|------|
| `test_engine` | session | 创建连接测试数据库的 SQLAlchemy Engine |
| `test_tables` | session | 调用 `create_all()` / `drop_all()` 管理表生命周期 |
| `test_db` | function | 提供带事务回滚的数据库 Session |
| `admin_user` | session | 在测试数据库中创建管理员用户 |
| `client` | function | 提供已 override `get_db` 的 TestClient 实例 |
| `auth_token` | session | 通过 `/auth/login` 获取 JWT token |
| `auth_client` | function | 提供自动携带 Authorization header 的 TestClient 封装 |
| `unique_asset_tag` | function | 生成唯一的 `IT-YYYY-NNNN` 格式资产标签 |
| `test_employee` | session | 提供预定义的测试员工信息字典 |

**Dependency Override 机制：**

```python
# conftest.py 中的关键实现思路
from main import app
from database import get_db

def override_get_db():
    """替换 get_db 依赖，使用测试数据库 Session"""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
```

#### 2. test_auth.py — 认证流程测试

验证 JWT 认证的四个核心场景：正确登录、错误密码、无 token 访问、有 token 访问。

**接口：**
- `POST /auth/login` — 登录获取 token
- `GET /assets/` — 受保护端点（用于验证认证）

#### 3. test_asset_lifecycle.py — 资产全生命周期链路

使用 pytest 测试类组织，类内方法按顺序执行，通过类变量共享资产 ID 等状态。

**测试链路：**
```
新资产入库 → 分配给员工 → 验证变更日志 → 离职归还 → 重新变更为闲置 → 验证完整日志链
```

**接口：**
- `POST /assets/` — 创建资产
- `GET /assets/{id}` — 查询资产详情
- `PUT /assets/{id}` — 更新资产
- `GET /assets/{id}/logs` — 查询资产日志
- `POST /return-records/` — 创建归还记录
- `PUT /return-records/{id}` — 更新归还记录

#### 4. test_asset_status_flow.py — 资产状态流转链路

验证资产在多种状态之间的流转，包括信息变更不影响状态的场景。

**测试链路：**
```
入库(In Storage) → 分配(Active) → 变更信息(仍为Active) → 维修(In Repair) → 重新分配(Active)
```

**接口：** 与生命周期测试相同的 API 端点。

### Fixture 依赖关系

```mermaid
graph TD
    TE[test_engine<br/>session] --> TT[test_tables<br/>session]
    TT --> AU[admin_user<br/>session]
    TT --> TD[test_db<br/>function]
    AU --> AT[auth_token<br/>session]
    TD --> CL[client<br/>function]
    AT --> AC[auth_client<br/>function]
    CL --> AC
    
    style TE fill:#e3f2fd
    style TT fill:#e3f2fd
    style AU fill:#fff3e0
    style AT fill:#fff3e0
    style TD fill:#e8f5e9
    style CL fill:#e8f5e9
    style AC fill:#fce4ec
```

## 数据模型

### 测试数据库配置

测试数据库通过环境变量 `TEST_DATABASE_URL` 配置，默认值为：
```
postgresql://postgres:postgres@localhost:5432/it_asset_test
```

测试数据库使用与生产环境完全相同的 SQLAlchemy 模型（`models.py` 中定义的所有表），通过 `Base.metadata.create_all()` 自动创建。

### 测试数据

#### 管理员用户

| 字段 | 值 |
|------|-----|
| username | admin |
| password | admin123 |
| role | admin |
| is_active | True |
| must_change_password | False |

#### 测试员工信息

| 字段 | 值 |
|------|-----|
| employee_id | EMP001 |
| employee_name | 测试员工 |
| department | IT部门 |

#### 第二测试员工（用于重新分配场景）

| 字段 | 值 |
|------|-----|
| employee_id | EMP002 |
| employee_name | 测试员工B |
| department | 研发部门 |

#### 资产标签生成

使用 `IT-TEST-{counter:04d}` 格式，其中 counter 为自增计数器，确保每个测试生成唯一标签。例如：`IT-TEST-0001`、`IT-TEST-0002`。

### 数据隔离策略

```mermaid
graph LR
    subgraph Session Scope
        CREATE[create_all] --> T1[Test 1]
        T1 --> T2[Test 2]
        T2 --> TN[Test N]
        TN --> DROP[drop_all]
    end

    subgraph Function Scope
        BEGIN[BEGIN] --> OPS[测试操作]
        OPS --> ROLLBACK[ROLLBACK]
    end
```

**注意**：链路测试（lifecycle、status_flow）由于步骤间有依赖关系，使用类级别的 fixture scope，在整个类执行完毕后才回滚。非链路测试（auth）使用函数级别回滚。

## 错误处理

### 测试失败信息

每个断言都包含描述性的失败消息，格式为：

```python
assert response.status_code == 200, \
    f"[步骤名称] 期望状态码 200，实际 {response.status_code}，响应: {response.text}"
```

### 常见错误场景处理

| 场景 | 处理方式 |
|------|---------|
| 测试数据库连接失败 | fixture 阶段报错，所有测试跳过 |
| 管理员用户创建失败 | fixture 阶段报错，依赖该 fixture 的测试跳过 |
| API 返回非预期状态码 | assert 失败，包含完整响应体信息 |
| 链路中间步骤失败 | 后续步骤通过 pytest 的 `xfail` 或类级别 fixture 自动跳过 |
| 日志记录不完整 | 断言失败，包含实际日志列表信息 |

### 测试数据库不存在时的处理

如果 `TEST_DATABASE_URL` 指向的数据库不存在，`create_engine` 会在首次连接时抛出 `OperationalError`。测试框架会在 fixture 阶段捕获此错误并给出清晰的提示信息，指导用户创建测试数据库。

## 测试策略

### 测试类型

本功能的测试全部为**集成测试**，通过 HTTP API 与完整的 FastAPI 应用交互，使用真实的 PostgreSQL 数据库。

**为什么不使用属性基测试（PBT）：**
- 集成测试验证的是特定业务流程的端到端正确性，而非通用属性
- 测试场景是有序的链路步骤，每步依赖前一步的结果
- 每次测试涉及数据库 I/O，100+ 次迭代成本过高且无额外收益
- 业务流程是确定性的——相同输入总是产生相同输出

### 测试组织

#### pytest markers

| Marker | 用途 | 执行命令 |
|--------|------|---------|
| `@pytest.mark.lifecycle` | 资产全生命周期链路 | `pytest -m lifecycle` |
| `@pytest.mark.status_flow` | 资产状态流转链路 | `pytest -m status_flow` |
| `@pytest.mark.auth` | 认证流程测试 | `pytest -m auth` |

#### pytest 配置

在 `backend/pytest.ini` 或 `backend/pyproject.toml` 中注册自定义 markers：

```ini
[pytest]
markers =
    lifecycle: 资产全生命周期链路测试
    status_flow: 资产状态流转链路测试
    auth: 认证流程测试
```

### 测试用例清单

#### 认证流程（test_auth.py）

| 测试函数 | 验证内容 | 对应需求 |
|---------|---------|---------|
| `test_login_success` | 正确凭据返回 200 + token | 2.1 |
| `test_login_wrong_password` | 错误密码返回 401 | 2.2 |
| `test_access_without_token` | 无 token 返回 403 | 2.3 |
| `test_access_with_token` | 有效 token 返回 200 | 2.4 |

#### 资产全生命周期（test_asset_lifecycle.py）

| 测试方法 | 验证内容 | 对应需求 |
|---------|---------|---------|
| `test_step1_create_asset` | 创建资产，状态为 In Storage | 3.1, 3.2 |
| `test_step2_assign_to_employee` | 分配给员工，状态变为 Active | 3.3, 3.4 |
| `test_step3_verify_logs` | 验证创建和状态变更日志 | 3.5, 3.6 |
| `test_step4_return_record` | 创建并完成归还记录 | 3.7, 3.8 |
| `test_step5_back_to_storage` | 重新变为闲置，验证完整日志链 | 3.9, 3.10, 3.11 |

#### 资产状态流转（test_asset_status_flow.py）

| 测试方法 | 验证内容 | 对应需求 |
|---------|---------|---------|
| `test_step1_create_in_storage` | 创建资产，状态为 In Storage | 4.1 |
| `test_step2_assign_active` | 分配给员工，状态变为 Active | 4.2, 4.3 |
| `test_step3_update_info` | 变更资产名和使用人信息 | 4.4, 4.5 |
| `test_step4_verify_still_active` | 确认信息变更不影响状态 | 4.6 |
| `test_step5_to_repair` | 状态变为 In Repair | 4.7, 4.8, 4.9 |
| `test_step6_reassign` | 重新分配给新员工 | 4.10, 4.11, 4.12 |

### 日志完整性验证（贯穿所有链路测试）

日志验证嵌入在链路测试的各个步骤中，覆盖需求 5 的所有验收标准：

| 验证点 | 验证内容 | 对应需求 |
|--------|---------|---------|
| 创建后查日志 | action 为 "创建资产"，description 包含 asset_tag | 5.1 |
| 更新后查日志 | 最新记录包含旧值和新值 | 5.2 |
| 状态变更后查日志 | action 包含 "状态变更" | 5.3 |
| 所有日志记录 | created_at 非空 | 5.4 |
| 多次更新后查日志 | 按 created_at 倒序，数量与操作次数一致 | 5.5 |

### 依赖项

需要安装的额外 Python 包：

| 包名 | 用途 |
|------|------|
| `pytest` | 测试框架 |
| `httpx` | FastAPI TestClient 的底层依赖 |

安装命令：
```bash
cd backend && pip install pytest httpx
```

### 执行命令

```bash
# 执行所有集成测试
pytest backend/tests/

# 仅执行资产全生命周期链路
pytest backend/tests/ -m lifecycle

# 仅执行资产状态流转链路
pytest backend/tests/ -m status_flow

# 仅执行认证测试
pytest backend/tests/ -m auth

# 详细输出模式
pytest backend/tests/ -v
```
