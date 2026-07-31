# 实现计划：基于 pytest 的自动化集成测试

## 概述

将设计文档中的集成测试方案转化为可执行的编码任务。按照"基础设施 → 认证测试 → 生命周期链路 → 状态流转链路"的顺序递进实现，每个任务构建在前一个任务的基础上，最终形成完整的测试套件。

## 任务

- [x] 1. 搭建测试基础设施
  - [x] 1.1 安装测试依赖并配置 pytest
    - 在 `backend/requirements.txt` 中添加 `pytest` 和 `httpx` 依赖
    - 创建 `backend/pytest.ini` 文件，注册自定义 markers（`lifecycle`、`status_flow`、`auth`）
    - 创建 `backend/tests/__init__.py` 空文件作为包标识
    - _需求: 7.1, 7.2_

  - [x] 1.2 实现 conftest.py 核心 fixtures
    - 创建 `backend/tests/conftest.py`
    - 实现 `test_engine`（session scope）：通过 `TEST_DATABASE_URL` 环境变量连接独立的 PostgreSQL 测试数据库，默认 `postgresql://postgres:postgres@localhost:5432/it_asset_test`
    - 实现 `test_tables`（session scope）：会话开始时 `Base.metadata.create_all()`，会话结束时 `Base.metadata.drop_all()`
    - 实现 `test_db`（function scope）：提供带事务回滚的数据库 Session，确保测试间数据隔离
    - 实现 `admin_user`（session scope）：创建管理员用户（username: admin, password: admin123, role: admin, is_active: True, must_change_password: False）
    - 实现 `client`（function scope）：创建 TestClient 实例，通过 `app.dependency_overrides[get_db]` 替换数据库依赖
    - 实现 `auth_token`（session scope）：通过 `POST /auth/login` 获取真实 JWT access_token
    - 实现 `auth_client`（function scope）：封装 TestClient，所有请求自动携带 `Authorization: Bearer {token}` header
    - 实现 `unique_asset_tag`（function scope）：生成唯一的 `IT-TEST-NNNN` 格式资产标签
    - 实现 `test_employee`（session scope）：提供预定义的测试员工信息字典（EMP001/测试员工/IT部门）
    - _需求: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 6.1, 6.2, 6.3_

- [x] 2. 检查点 - 验证测试基础设施
  - 确保 `pytest backend/tests/ --co` 能正确收集到 fixtures，无导入错误。如有问题请询问用户。

- [x] 3. 实现认证流程测试
  - [x] 3.1 创建 test_auth.py 认证测试模块
    - 创建 `backend/tests/test_auth.py`
    - 所有测试函数添加 `@pytest.mark.auth` 标记
    - 实现 `test_login_success`：使用正确凭据（admin/admin123）调用 `POST /auth/login`，断言返回 200 且响应包含 `access_token`、`refresh_token`、`token_type` 字段
    - 实现 `test_login_wrong_password`：使用错误密码调用 `POST /auth/login`，断言返回 401
    - 实现 `test_access_without_token`：不携带 token 调用 `GET /assets/`，断言返回 403（FastAPI HTTPBearer 默认行为）
    - 实现 `test_access_with_token`：使用 `auth_client` 调用 `GET /assets/`，断言返回 200
    - 每个断言包含描述性失败消息，格式：`f"[步骤名称] 期望状态码 X，实际 {response.status_code}，响应: {response.text}"`
    - _需求: 2.1, 2.2, 2.3, 2.4, 6.4, 7.4_

  - [ ]* 3.2 编写认证测试的单元测试补充
    - 验证 token 响应中 `user` 字段包含正确的用户名和角色信息
    - 验证 `token_type` 为 `"bearer"`
    - _需求: 2.1_

- [x] 4. 实现资产全生命周期链路测试
  - [x] 4.1 创建 test_asset_lifecycle.py 生命周期测试模块
    - 创建 `backend/tests/test_asset_lifecycle.py`
    - 使用 pytest 测试类 `TestAssetLifecycle` 组织，类内方法按顺序执行
    - 整个类添加 `@pytest.mark.lifecycle` 标记
    - 使用类变量共享资产 ID、归还记录 ID 等状态
    - _需求: 3.1_

  - [x] 4.2 实现步骤 1-2：新资产入库与分配给员工
    - 实现 `test_step1_create_asset`：调用 `POST /assets/` 创建新资产（category: "笔记本电脑", status: "In Storage"），断言返回 200 且 status 为 "In Storage"，employee_id 为空；将资产 ID 保存到类变量
    - 实现 `test_step2_assign_to_employee`：调用 `PUT /assets/{id}` 更新 employee_id、employee_name、department、status 为 "Active"，断言返回的 status 为 "Active"、employee_name 正确；再调用 `GET /assets/{id}` 二次验证
    - _需求: 3.1, 3.2, 3.3, 3.4_

  - [x] 4.3 实现步骤 3：验证变更日志
    - 实现 `test_step3_verify_logs`：调用 `GET /assets/{id}/logs` 查询日志，断言包含至少两条记录，一条 action 为 "创建资产"，一条 action 包含 "状态变更"；验证状态变更日志的 description 包含 "In Storage" 和 "Active"；验证每条日志的 created_at 非空
    - _需求: 3.5, 3.6, 5.1, 5.2, 5.3, 5.4_

  - [x] 4.4 实现步骤 4-5：离职归还与重新变更为闲置
    - 实现 `test_step4_return_record`：调用 `POST /return-records/` 创建归还记录（包含 asset_name、employee_id、employee_name、return_reason），断言返回 200 且 is_returned 为 false；调用 `PUT /return-records/{id}` 将 is_returned 设为 true，断言更新成功
    - 实现 `test_step5_back_to_storage`：调用 `PUT /assets/{id}` 将 status 设为 "In Storage" 并清空 employee_id 和 employee_name，断言 status 为 "In Storage"；调用 `GET /assets/{id}` 验证 employee_id 和 employee_name 为空字符串；调用 `GET /assets/{id}/logs` 验证完整日志链，最新日志 action 包含 "状态变更"
    - _需求: 3.7, 3.8, 3.9, 3.10, 3.11, 5.5_

- [x] 5. 检查点 - 验证生命周期链路测试
  - 确保 `pytest backend/tests/test_asset_lifecycle.py -v` 所有步骤通过。如有问题请询问用户。

- [x] 6. 实现资产状态流转链路测试
  - [x] 6.1 创建 test_asset_status_flow.py 状态流转测试模块
    - 创建 `backend/tests/test_asset_status_flow.py`
    - 使用 pytest 测试类 `TestAssetStatusFlow` 组织
    - 整个类添加 `@pytest.mark.status_flow` 标记
    - 使用类变量共享资产 ID 等状态
    - _需求: 4.1_

  - [x] 6.2 实现步骤 1-3：入库、分配与信息变更
    - 实现 `test_step1_create_in_storage`：调用 `POST /assets/` 创建资产（status: "In Storage"），断言返回 200 且 status 正确
    - 实现 `test_step2_assign_active`：调用 `PUT /assets/{id}` 设置 employee_id（EMP001）、employee_name（测试员工）、department（IT部门）、status 为 "Active"，断言 status 为 "Active"；调用 `GET /assets/{id}` 二次验证
    - 实现 `test_step3_update_info`：调用 `PUT /assets/{id}` 同时更新 hostname 和 employee_name，断言返回包含新值；调用 `GET /assets/{id}/logs` 验证日志 description 包含 "资产名" 和 "使用人" 关键字
    - _需求: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 6.3 实现步骤 4-6：状态验证、维修与重新分配
    - 实现 `test_step4_verify_still_active`：调用 `GET /assets/{id}` 验证 status 仍为 "Active"，确认信息变更不影响状态
    - 实现 `test_step5_to_repair`：调用 `PUT /assets/{id}` 将 status 设为 "In Repair"，断言返回 status 正确；调用 `GET /assets/{id}` 二次验证；调用 `GET /assets/{id}/logs` 验证日志包含 "状态变更" 且 description 包含 "Active" 和 "In Repair"
    - 实现 `test_step6_reassign`：调用 `PUT /assets/{id}` 将 status 设为 "Active" 并更新 employee_id（EMP002）、employee_name（测试员工B），断言返回正确；调用 `GET /assets/{id}` 验证新员工信息；调用 `GET /assets/{id}/logs` 验证至少五条日志记录，覆盖完整流转过程
    - _需求: 4.6, 4.7, 4.8, 4.9, 4.10, 4.11, 4.12, 5.3, 5.4, 5.5_

- [x] 7. 最终检查点 - 执行完整测试套件
  - 执行 `pytest backend/tests/ -v` 确保所有测试通过
  - 验证 `pytest backend/tests/ -m lifecycle` 仅执行生命周期链路测试
  - 验证 `pytest backend/tests/ -m status_flow` 仅执行状态流转链路测试
  - 验证 `pytest backend/tests/ -m auth` 仅执行认证测试
  - 确保所有测试通过，如有问题请询问用户。

## 说明

- 任务标记 `*` 的为可选子任务，可跳过以加快 MVP 进度
- 每个任务引用了具体的需求编号，便于追溯
- 检查点任务用于阶段性验证，确保增量开发的正确性
- 所有测试使用 Python + pytest 编写，与项目技术栈一致
- 链路测试使用测试类组织，类内方法按顺序执行并共享状态
