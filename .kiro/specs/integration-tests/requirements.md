# 需求文档：基于 pytest 的自动化集成测试

## 简介

本功能为 IT 资产管理系统编写一套基于 pytest 的自动化集成测试脚本，覆盖两条核心业务流程链路：**资产全生命周期**和**资产状态流转**。测试通过 HTTP API 与 FastAPI 后端交互，使用独立的 PostgreSQL 测试数据库隔离测试环境，与生产数据库保持相同的数据库引擎，每一步操作后验证资产状态是否与预期一致。

## 术语表

- **Test_Client**: FastAPI 提供的 TestClient，用于在进程内发送 HTTP 请求，无需启动真实服务器
- **Test_Database**: 使用独立 PostgreSQL 测试数据库的测试数据库实例，通过 SQLAlchemy 创建，与生产数据库使用相同的数据库引擎以确保行为一致性，测试结束后自动清理数据
- **Auth_Token**: 通过 /auth/login 端点获取的 JWT Bearer Token，所有受保护的 API 请求必须携带此令牌
- **Asset**: 资产表中的一条记录，包含 asset_tag、category、status、employee_id、employee_name 等字段
- **Asset_Log**: 资产操作日志，记录资产的每次变更操作，包含 action、description、old_value、new_value、operator 字段
- **Return_Record**: 离职归还记录，关联资产与离职员工信息，包含 is_returned 状态标志
- **Asset_Status**: 资产状态枚举值，包括 Active（使用中）、In Storage（闲置）、In Repair（维修中）、Retired（报废）
- **Asset_Tag**: 资产标签，格式为 IT-YYYY-NNNN（如 IT-2025-0001）
- **Fixture**: pytest 的 fixture 机制，用于在测试前后执行初始化和清理操作

## 需求

### 需求 1：测试基础设施搭建

**用户故事：** 作为测试工程师，我希望有一套独立的测试基础设施，以便在不影响生产数据库的情况下运行集成测试。

#### 验收标准

1. THE Test_Database SHALL 使用独立的 PostgreSQL 测试数据库（连接字符串通过环境变量 TEST_DATABASE_URL 配置，默认为 postgresql://postgres:postgres@localhost:5432/it_asset_test），与生产数据库完全隔离，确保测试环境与生产环境使用相同的数据库引擎
2. WHEN 测试会话开始时，THE Test_Database SHALL 通过 SQLAlchemy Base.metadata.create_all 自动创建所有数据表
3. WHEN 测试会话结束时，THE Test_Database SHALL 通过 Base.metadata.drop_all 自动清理所有数据表
4. THE Fixture SHALL 提供一个预创建的管理员用户（用户名: admin，密码: admin123），用于测试中的认证操作
5. THE Fixture SHALL 提供一个已认证的 Test_Client 实例，该实例的所有请求自动携带有效的 Auth_Token
6. WHEN 每个测试函数执行前，THE Test_Database SHALL 通过事务回滚机制确保测试之间的数据隔离

### 需求 2：认证流程测试

**用户故事：** 作为测试工程师，我希望验证 JWT 认证流程的正确性，以确保所有受保护的 API 端点都需要有效的令牌。

#### 验收标准

1. WHEN 使用正确的用户名和密码调用 POST /auth/login 时，THE Auth_Token SHALL 返回包含 access_token、refresh_token 和 token_type 字段的 JSON 响应，HTTP 状态码为 200
2. WHEN 使用错误的密码调用 POST /auth/login 时，THE Auth_Token SHALL 返回 HTTP 401 状态码
3. WHEN 不携带 Auth_Token 调用受保护的 API 端点（如 GET /assets/）时，THE Test_Client SHALL 收到 HTTP 403 状态码
4. WHEN 携带有效的 Auth_Token 调用受保护的 API 端点时，THE Test_Client SHALL 收到 HTTP 200 状态码和正确的响应数据

### 需求 3：资产全生命周期链路测试

**用户故事：** 作为测试工程师，我希望验证资产从入库到归还的完整生命周期流程，以确保每一步状态变更都正确记录。

#### 验收标准

##### 步骤 1：新资产入库
1. WHEN 调用 POST /assets/ 创建一个新资产（status 为 "In Storage"）时，THE Asset SHALL 返回 HTTP 200 状态码和包含正确 asset_tag、category、status 的资产对象
2. WHEN 新资产创建成功后查询 GET /assets/{id} 时，THE Asset SHALL 返回 status 为 "In Storage" 且 employee_id 为空的资产详情

##### 步骤 2：分配给员工
3. WHEN 调用 PUT /assets/{id} 更新资产的 employee_id、employee_name、department 和 status 为 "Active" 时，THE Asset SHALL 返回更新后的资产对象，其中 status 为 "Active"，employee_name 为指定的员工姓名
4. WHEN 资产分配成功后查询 GET /assets/{id} 时，THE Asset SHALL 返回 status 为 "Active"、employee_id 为指定工号、employee_name 为指定姓名的资产详情

##### 步骤 3：产生变更日志
5. WHEN 资产分配成功后查询 GET /assets/{id}/logs 时，THE Asset_Log SHALL 包含至少两条日志记录：一条 action 为 "创建资产"，一条 action 包含 "状态变更" 关键字
6. THE Asset_Log 中的状态变更记录 SHALL 在 description 中包含 "In Storage" 和 "Active" 关键字，表明状态从闲置变为使用中

##### 步骤 4：离职归还
7. WHEN 调用 POST /return-records/ 创建归还记录时，THE Return_Record SHALL 返回 HTTP 200 状态码和包含正确 employee_name、return_reason 的归还记录对象，且 is_returned 为 false
8. WHEN 调用 PUT /return-records/{id} 将 is_returned 设为 true 时，THE Return_Record SHALL 返回更新后的归还记录对象，其中 is_returned 为 true

##### 步骤 5：重新变更为闲置
9. WHEN 调用 PUT /assets/{id} 将 status 设为 "In Storage" 并清空 employee_id 和 employee_name 时，THE Asset SHALL 返回 status 为 "In Storage" 的资产对象
10. WHEN 归还流程完成后查询 GET /assets/{id} 时，THE Asset SHALL 返回 status 为 "In Storage"、employee_id 为空字符串、employee_name 为空字符串的资产详情
11. WHEN 归还流程完成后查询 GET /assets/{id}/logs 时，THE Asset_Log SHALL 包含完整的生命周期日志链，按时间倒序排列，最新的日志 action 包含 "状态变更" 关键字

### 需求 4：资产状态流转链路测试

**用户故事：** 作为测试工程师，我希望验证资产在多种状态之间的流转过程，以确保状态机的正确性和日志的完整性。

#### 验收标准

##### 步骤 1：在仓库的资产
1. WHEN 调用 POST /assets/ 创建一个 status 为 "In Storage" 的新资产时，THE Asset SHALL 返回 HTTP 200 状态码和 status 为 "In Storage" 的资产对象

##### 步骤 2：分配给员工
2. WHEN 调用 PUT /assets/{id} 将 status 设为 "Active" 并设置 employee_id、employee_name、department 时，THE Asset SHALL 返回 status 为 "Active" 的资产对象
3. WHEN 分配成功后查询 GET /assets/{id} 时，THE Asset SHALL 返回 status 为 "Active"、employee_name 为指定姓名的资产详情

##### 步骤 3：更改资产名和所属人信息
4. WHEN 调用 PUT /assets/{id} 同时更新 hostname 和 employee_name 时，THE Asset SHALL 返回包含新 hostname 和新 employee_name 的资产对象
5. WHEN 资产名变更后查询 GET /assets/{id}/logs 时，THE Asset_Log SHALL 包含一条 description 中同时包含 "资产名" 和 "使用人" 关键字的变更记录

##### 步骤 4：变更为使用中（验证仍为 Active）
6. WHEN 更改资产名和所属人后查询 GET /assets/{id} 时，THE Asset SHALL 返回 status 仍为 "Active" 的资产详情，确认信息变更不影响资产状态

##### 步骤 5：变更为维修中
7. WHEN 调用 PUT /assets/{id} 将 status 设为 "In Repair" 时，THE Asset SHALL 返回 status 为 "In Repair" 的资产对象
8. WHEN 状态变更为维修中后查询 GET /assets/{id} 时，THE Asset SHALL 返回 status 为 "In Repair" 的资产详情
9. WHEN 状态变更为维修中后查询 GET /assets/{id}/logs 时，THE Asset_Log SHALL 包含一条 action 包含 "状态变更" 关键字且 description 包含 "Active" 和 "In Repair" 的日志记录

##### 步骤 6：重新分配给员工
10. WHEN 调用 PUT /assets/{id} 将 status 设为 "Active" 并更新 employee_id 和 employee_name 为新员工信息时，THE Asset SHALL 返回 status 为 "Active" 且 employee_name 为新员工姓名的资产对象
11. WHEN 重新分配成功后查询 GET /assets/{id} 时，THE Asset SHALL 返回 status 为 "Active"、employee_name 为新员工姓名的资产详情
12. WHEN 完整流转结束后查询 GET /assets/{id}/logs 时，THE Asset_Log SHALL 包含至少五条日志记录，覆盖创建、分配、信息变更、维修、重新分配的完整流转过程

### 需求 5：日志完整性验证

**用户故事：** 作为测试工程师，我希望验证每次资产变更都会产生准确的操作日志，以确保审计追踪的完整性。

#### 验收标准

1. WHEN 创建新资产后查询 GET /assets/{id}/logs 时，THE Asset_Log SHALL 包含一条 action 为 "创建资产" 的日志记录，且 description 包含资产的 asset_tag
2. WHEN 更新资产字段后查询 GET /assets/{id}/logs 时，THE Asset_Log 中最新的记录 SHALL 在 description 中包含被修改字段的旧值和新值
3. WHEN 资产状态发生变更后查询 GET /assets/{id}/logs 时，THE Asset_Log SHALL 包含一条 action 包含 "状态变更" 关键字的日志记录
4. THE Asset_Log 中的每条记录 SHALL 包含非空的 created_at 时间戳
5. WHEN 多次更新同一资产后查询 GET /assets/{id}/logs 时，THE Asset_Log SHALL 按 created_at 倒序返回所有日志记录，且记录数量与实际操作次数一致

### 需求 6：测试数据管理

**用户故事：** 作为测试工程师，我希望测试使用可预测的测试数据，以确保测试结果的可重复性。

#### 验收标准

1. THE Fixture SHALL 为每个测试生成唯一的 Asset_Tag，格式符合 IT-YYYY-NNNN 规范，避免测试间的数据冲突
2. THE Fixture SHALL 提供预定义的测试员工信息（工号、姓名、部门），用于资产分配和归还测试
3. WHEN 测试需要创建资产时，THE Test_Client SHALL 使用包含所有必填字段（asset_tag、category、status）的完整请求体
4. IF 测试中 API 调用返回非预期的 HTTP 状态码，THEN THE Test_Client SHALL 通过 pytest assert 语句立即报告失败，并在断言消息中包含实际的响应状态码和响应体

### 需求 7：测试执行与报告

**用户故事：** 作为测试工程师，我希望能够方便地执行测试并获取清晰的测试报告，以快速定位失败的测试用例。

#### 验收标准

1. THE Test_Client SHALL 支持通过 `pytest backend/tests/` 命令执行所有集成测试
2. THE Test_Client SHALL 支持通过 pytest 标记（marker）单独执行某条链路的测试，如 `pytest -m lifecycle` 或 `pytest -m status_flow`
3. WHEN 所有测试通过时，THE Test_Client SHALL 输出包含测试数量和通过状态的摘要信息
4. IF 某个测试步骤失败，THEN THE Test_Client SHALL 在失败信息中包含当前步骤名称和实际的 API 响应内容，便于定位问题
