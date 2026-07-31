# Implementation Plan: 资产分类与发放管理

## Overview

按技术设计使用 Python/FastAPI、SQLAlchemy 2.0 与 React JSX 增量实现三层资产模型。仓储分类统一采用可维护的“一级分类 + 二级分类”：先建立数据库约束、种子和可重复迁移，再实现分类服务、API、物料校验与筛选，随后接入固定资产、低值领用、专业用途追踪和仓储前端。所有写操作通过同一事务写入业务数据与审计日志；所有任务保持未执行状态。

## Tasks

- [x] 1. 建立分类策略、两级目录模型与事务基础
  - [x] 1.1 在 `backend/category_policy.py` 与 `backend/schemas.py` 定义分类、状态、策略及两级目录请求响应契约
    - 定义 PC/NB/PD、历史“移动设备”规范化、八个一级分类代码、领用策略、固定资产状态、分类树、物料双分类、迁移解决和中文错误模式。
    - 限制非固定品类建卡并返回“请改入低值领用或仓储物料”，限制低值与办公耗材策略。
    - _Requirements: 1.1–1.4, 5.5–5.8, 7.1–7.7, 11.1, 12.1_

  - [x] 1.2 扩展 `backend/models.py`，创建一级/二级目录、映射、迁移问题及领域记录的 SQLAlchemy 模型
    - 新增 `warehouse_primary_categories`、`warehouse_secondary_categories`、`warehouse_category_mappings`、`warehouse_category_migration_issues`，确保二级分类具有非空且唯一的一级父项。
    - 为二级表建立 `UNIQUE(primary_category_id, id)`；为 `warehouse_assets(primary_category_id, secondary_category_id)` 与映射表建立指向二级表的复合外键，并补充单列外键、`ON DELETE RESTRICT`、索引、启停和 `ACTIVE`/`PENDING_MIGRATION` 约束。
    - 扩展固定资产、入库、发放、生命周期、低值发放/归还、维修备件、网络耗材和工具借用模型及库存/余额约束。
    - _Requirements: 2.1–2.3, 2.7, 3.1, 4.1–4.4, 5.3, 6.4–6.9, 7.2–7.5, 7.8–7.9, 8.2–8.4, 9.2–9.3, 10.2–10.6_

  - [x] 1.3 新建 `backend/transaction_audit.py`，封装领域事务、行锁、UTC+8 变更快照和审计失败回滚
    - 提供统一 `flush`/`commit`/`rollback` 边界，将 `operation_logs` 与分类、物料、库存、状态、绑定和历史记录置于同一事务。
    - _Requirements: 3.1, 3.3, 4.1–4.5, 6.4–6.10, 8.3, 8.5, 9.3–9.4, 10.2–10.7, 11.3–11.4, 12.2–12.3_

  - [x] 1.4 在 `backend/requirements.txt` 固定 `pytest==8.3.5`、`hypothesis==6.131.14` 并配置后端测试基础
    - 保持与现有 Python/FastAPI 环境兼容，测试使用启用外键的 SQLite 临时库及可选 PostgreSQL 集成库。
    - _Requirements: 1.1–12.5（自动化测试基础）_

  - [x] 1.5 在 `backend/tests/test_property_01_category_policy.py` 编写属性 1 测试
    - **Property 1: 分类、命名与领用策略受限**
    - **Validates: Requirements 1.1, 1.2, 1.4, 5.3, 5.5, 5.8, 11.1**

- [x] 2. 实现分类目录种子与历史单层分类迁移
  - [ ] 2.1 新建 `backend/warehouse_category_seed.py`，定义一级/二级分类种子及可重复写入函数
    - 按稳定代码 upsert Requirement 7.1 的八个一级分类和设计确认的二级分类；重复执行不得重复创建、重置管理员维护值或改变有效从属关系。
    - _Requirements: 7.1–7.3_

  - [x] 2.2 新建 `backend/migrate_asset_category_and_issuance.py`，实现目录建表、种子、历史映射和字段迁移
    - 标准化历史单层分类并仅使用唯一精确映射；唯一有效命中时保留原主键、库存、已分配数量、位置和其他非分类字段，只写一级/二级外键并标记 `ACTIVE`。
    - 零命中、歧义、停用目标或错误从属时保留原分类及非分类字段，标记 `PENDING_MIGRATION`，按 `UNMAPPED`、`AMBIGUOUS`、`INACTIVE_TARGET` 或 `INVALID_PAIR` 幂等创建待处理项。
    - 增加迁移前后记录数、数量和非分类摘要核对，失败整批回滚；重复运行不得重复报告、改变已迁移/已解决记录或创建固定资产卡。
    - _Requirements: 1.2, 2.2, 5.3–5.4, 7.1–7.5, 7.8–7.9_

  - [x] 2.3 在 `backend/tests/test_warehouse_category_seed.py` 编写目录种子示例与幂等测试
    - 断言一级分类名称和代码完整准确、二级项恰有一个父项、重复运行数据不重复且维护值不被覆盖。
    - _Requirements: 7.1–7.3_

  - [x] 2.4 在 `backend/tests/test_warehouse_category_migration.py` 编写迁移脚本集成测试
    - 在隔离数据库执行两次迁移，覆盖唯一映射、零映射、歧义、停用目标、错误从属、`PENDING_MIGRATION`、报告原因、数据摘要保真和失败回滚。
    - _Requirements: 7.8–7.9_

  - [x] 2.5 在 `backend/tests/test_property_11_legacy_category_migration.py` 编写属性 11 测试
    - **Property 11: 历史单层分类迁移保真与待处理可追溯**
    - **Validates: Requirements 7.8, 7.9**

- [x] 3. 实现仓储分类目录服务、API 与物料有效组合校验
  - [ ] 3.1 新建 `backend/warehouse_category_service.py`，实现目录读取、维护、有效组合校验和迁移解决
    - 返回树形目录、一级列表和指定一级下的启用二级列表；校验一级/二级存在、启用且从属有效。
    - 实现一级/二级新增、改名、排序、启停；阻止硬删除、被引用分类停用或二级直接换父，并在受控引用迁移时更新物料。
    - 实现待处理报告查询/导出数据和解决操作：单事务写入有效组合、将物料转为 `ACTIVE`、关闭问题并记录分类审计。
    - _Requirements: 7.1–7.5, 7.8–7.9, 12.2–12.5_

  - [ ] 3.2 修改 `backend/main.py`，发布分类目录读取、维护和迁移解决 API
    - 增加 `GET /warehouse/categories`、`/primary`、`/primary/{id}/secondary`、待处理报告查询，以及一级/二级 POST/PATCH 和迁移解决端点。
    - 查询允许已登录只读用户；维护和解决端点使用 `require_write_permission`，映射中文 400/403/404/409/422 错误。
    - _Requirements: 7.1–7.6, 7.8–7.9, 12.1–12.5_

  - [ ] 3.3 新建 `backend/warehouse_material_service.py`，实现物料创建、编辑、详情和 AND 组合筛选
    - 创建/编辑必须同时提交启用且从属有效的一级/二级 ID，并保存名称、可用库存、已分配数量、位置和低库存阈值；拒绝编辑 `PENDING_MIGRATION` 记录。
    - 列表按名称、一级、二级、可用/已分配数量、位置、阈值和低库存状态对全部已指定条件执行 AND；一级和二级同时指定但不从属时返回中文 400。
    - 列表与详情响应返回稳定 ID、一级/二级名称；仅当 `available_quantity < low_stock_threshold` 时返回 `low_stock=true` 和“低库存预警”。
    - _Requirements: 5.1–5.4, 7.3–7.11, 11.5_

  - [ ] 3.4 修改 `backend/main.py`，接入仓储物料创建、编辑、列表、详情和采购入库 API
    - 通过 `warehouse_category_service` 校验组合，不允许前端绕过；非固定物料按数量入库且不要求序列号、不创建固定资产卡。
    - 所有响应包含一级/二级字段和库存摘要，查询允许只读角色，写操作统一鉴权和审计。
    - _Requirements: 2.5, 5.1–5.4, 7.4–7.11, 12.2–12.5_

  - [x] 3.5 在 `backend/tests/test_property_09_category_integrity.py` 编写属性 9 测试
    - **Property 9: 两级分类从属与物料组合完整性**
    - 生成跨父级、缺失、停用及不存在的组合，并同时验证服务拒绝和数据库复合外键约束。
    - **Validates: Requirements 7.2, 7.3, 7.4, 7.5**

  - [x] 3.6 在 `backend/tests/test_property_10_material_filters.py` 编写属性 10 测试
    - **Property 10: 两级组合筛选与严格低库存判定**
    - 生成任意筛选条件子集，断言结果是所有条件的交集，并覆盖一级/二级有效组合和阈值等号边界。
    - **Validates: Requirements 7.7, 7.10, 7.11, 11.5**

  - [x] 3.7 在 `backend/tests/test_warehouse_category_api.py` 编写分类目录 API 集成测试
    - 覆盖树形/平铺/按父读取、维护唯一性、启停引用冲突、迁移待处理查询与解决、双分类响应，以及 PostgreSQL/SQLite 复合外键拒绝交叉组合。
    - _Requirements: 7.1–7.9, 12.4–12.5_

  - [x] 3.8 在 `backend/tests/test_property_16_audit_atomicity.py` 编写属性 16 测试
    - **Property 16: 所有业务及分类目录写操作与审计同成同败**
    - 覆盖分类新增、改名、排序、启停、引用迁移及代表性业务命令；成功时审计含层级、父项、经办人、UTC+8 时间和前后值，注入审计失败时全部回滚并返回中文错误。
    - **Validates: Requirements 12.2, 12.3**

  - [x] 3.9 在 `backend/tests/test_warehouse_permissions.py` 编写分类和物料权限集成测试
    - 验证只读角色可查询目录、物料和待处理详情，但所有分类维护、物料写入及迁移解决均返回中文 403 且数据不变。
    - _Requirements: 12.4–12.5_

- [x] 4. 实现受控固定资产入库与生命周期
  - [ ] 4.1 新建 `backend/asset_lifecycle_service.py`，实现受控入库、终端库存发放、归还、转移、送修和维修完成
    - 仅允许 PC/NB/PD 经 `SCAN`/`MANUAL` 以唯一非空资产编号和序列号创建闲置卡；按稳定顺序锁定资产与终端库存。
    - 原子更新状态、当前绑定、可用/已分配库存，并创建入库、发放、生命周期和审计记录；任一步失败完整回滚。
    - _Requirements: 1.1–1.4, 2.1–2.8, 3.1–3.3, 4.1–4.5_

  - [ ] 4.2 修改 `backend/main.py`，发布固定资产受控入库和生命周期 API 并封堵旧绕过路径
    - 增加单件/批量入库、发放、归还、转移、送修和维修完成端点；批量入库逐项独立事务返回结果。
    - 拒绝通用 `POST /assets/` 和库房分配路径为 PC/NB/PD 临时建卡，接入写权限及中文错误映射。
    - _Requirements: 1.3–1.4, 2.1–2.8, 3.1–3.3, 4.1–4.5, 12.1–12.5_

  - [ ] 4.3 修改 `frontend/src/components/ScanWorkstation.jsx`，接入三类固定资产的扫码与手动受控入库
    - 仅显示台式机、笔记本电脑和平板电脑，提交单件或逐项批量 API，展示中文逐项结果并保留失败输入。
    - _Requirements: 1.2–1.3, 2.1–2.4, 12.1_

  - [x] 4.4 在 `backend/tests/test_property_02_controlled_inbound.py` 编写属性 2 测试
    - **Property 2: 受控固定资产入库创建唯一可追溯卡**
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.7**

  - [x] 4.5 在 `backend/tests/test_property_03_invalid_inbound.py` 编写属性 3 测试
    - **Property 3: 非法或非受控固定资产建卡无副作用**
    - **Validates: Requirements 1.4, 2.4, 2.5, 2.8, 3.2, 5.2, 5.4**

  - [x] 4.6 在 `backend/tests/test_property_04_asset_lifecycle.py` 编写属性 4 测试
    - **Property 4: 合法固定资产生命周期原子转换**
    - **Validates: Requirements 2.6, 3.1, 4.1, 4.2, 4.3, 4.4**

  - [x] 4.7 在 `backend/tests/test_property_05_asset_lifecycle_rollback.py` 编写属性 5 测试
    - **Property 5: 非法固定资产生命周期操作完全回滚**
    - **Validates: Requirements 3.3, 4.5**

  - [x] 4.8 在 `backend/tests/test_fixed_asset_api.py` 编写固定资产 API 集成测试
    - 覆盖批量逐项结果、唯一性、库存联动、状态转换、中文错误、只读查询/写拒绝和旧入口不建卡。
    - _Requirements: 2.1–2.8, 3.1–3.3, 4.1–4.5, 12.4–12.5_

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. 实现低值物料发放与归还
  - [ ] 6.1 新建 `backend/material_issuance_service.py`，实现普通非固定物料发放和待归还记录归还事务
    - 复用 `warehouse_category_service` 验证活动物料和有效组合；校验正数量、库存、策略、日期时间及经办人，原样保存选填领用人、工号、部门和用途。
    - 按策略互斥创建待归还或一次性消耗记录；部分/全量归还精确减少未归还余额并回补库存，禁止消耗品归还。
    - _Requirements: 5.3–5.8, 6.1–6.10, 7.4–7.5_

  - [x] 6.2 修改 `backend/main.py`，发布普通非固定物料发放与归还 API
    - 增加 `POST /material-issues` 与 `POST /material-issues/{id}/returns`，返回结构化记录、库存和审计标识；使用写权限依赖及中文错误映射。
    - _Requirements: 6.1–6.10, 12.1–12.5_

  - [x] 6.3 新建 `frontend/src/components/MaterialIssueManagement.jsx`，实现低值发放与部分/全量归还中文界面
    - 将领用人、工号、部门、用途作为选填字段；显示策略快照和未归还余额，禁止对一次性消耗完成记录提交归还。
    - _Requirements: 5.5–5.8, 6.1–6.10, 12.1, 12.4–12.5_

  - [x] 6.4 在 `backend/tests/test_property_06_material_issue_validation.py` 编写属性 6 测试
    - **Property 6: 非固定资产发放验证与可选信息保真**
    - **Validates: Requirements 6.1, 6.2, 6.3**

  - [x] 6.5 在 `backend/tests/test_property_07_material_issue_policy.py` 编写属性 7 测试
    - **Property 7: 低值发放按策略创建互斥记录并原子扣库**
    - **Validates: Requirements 6.4, 6.5, 6.6**

  - [x] 6.6 在 `backend/tests/test_property_08_material_returns.py` 编写属性 8 测试
    - **Property 8: 待归还余额与消耗品禁止归还**
    - **Validates: Requirements 6.7, 6.8, 6.9, 6.10**

  - [x] 6.7 在 `backend/tests/test_material_issue_api.py` 编写低值发放/归还 API 集成测试
    - 覆盖选填信息全空、策略非法、库存不足、部分/全量归还、消耗品拒绝归还、事务故障和只读写拒绝。
    - _Requirements: 5.5–5.8, 6.1–6.10, 12.4–12.5_

- [x] 7. 实现维修、网络、工具和办公物料用途追踪
  - [ ] 7.1 扩展 `backend/material_issuance_service.py`，实现四类专业物料事务
    - 实现维修备件发放及有效资产/维修单关联和选填硬盘序列号；实现网络机房耗材选填用途关联及填写后的有效性校验。
    - 实现工具借出、部分/全量归还、`BORROWED`/`RETURNED` 余额状态机和选填贵重工具标识；办公通用耗材固定按一次性消耗处理。
    - 所有流程锁定库存行，并将记录、扣减/回补和审计原子提交。
    - _Requirements: 8.1–8.5, 9.1–9.4, 10.1–10.7, 11.1–11.4, 12.2–12.3_

  - [ ] 7.2 修改 `backend/main.py`，发布专业物料语义化 API
    - 增加 `/repair-parts/issues`、`/network-consumables/issues`、`/tool-loans`、`/tool-loans/{id}/returns` 和 `/office-consumables/issues`。
    - 返回领域记录、库存与审计标识，使用中文 400/403/404/409/422 语义并阻止只读写操作。
    - _Requirements: 8.1–8.5, 9.1–9.4, 10.1–10.7, 11.1–11.4, 12.1–12.5_

  - [ ] 7.3 新建 `frontend/src/components/ToolLoanManagement.jsx`，实现工具借出和部分/全量归还界面
    - 显示未归还数量和借用状态，支持选填工具编号/二维码；只读角色仅可查看列表与详情。
    - _Requirements: 10.1–10.7, 12.1, 12.4–12.5_

  - [ ] 7.4 扩展 `frontend/src/components/MaterialIssueManagement.jsx`，接入维修、网络和办公耗材表单
    - 按物料类型显示维修关联、硬盘序列号或网络用途；用途为空时允许网络耗材发放，填写时提交至少一个有效关联；办公耗材固定显示一次性消耗策略。
    - _Requirements: 8.1–8.5, 9.1–9.4, 11.1–11.4, 12.1_

  - [x] 7.5 在 `backend/tests/test_property_12_repair_parts.py` 编写属性 12 测试
    - **Property 12: 维修备件用途关联与扣库原子性**
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.5**

  - [x] 7.6 在 `backend/tests/test_property_13_network_consumables.py` 编写属性 13 测试
    - **Property 13: 网络机房耗材用途关联与扣库原子性**
    - **Validates: Requirements 9.1, 9.2, 9.3, 9.4**

  - [x] 7.7 在 `backend/tests/test_property_14_tool_loans.py` 编写属性 14 测试
    - **Property 14: 工具借还余额状态机**
    - **Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.5, 10.7**

  - [x] 7.8 在 `backend/tests/test_property_15_office_consumables.py` 编写属性 15 测试
    - **Property 15: 办公耗材作为一次性消耗品原子发放**
    - **Validates: Requirements 11.2, 11.3, 11.4**

  - [x] 7.9 在 `backend/tests/test_specialized_material_api.py` 编写专业物料 API 集成测试
    - 覆盖关联、可选字段、余额状态、库存原子性、故障回滚、低库存预警和只读查询/写拒绝。
    - _Requirements: 8.1–8.5, 9.1–9.4, 10.1–10.7, 11.1–11.5, 12.4–12.5_

- [x] 8. 改造仓储一级/二级分类展示与维护界面
  - [ ] 8.1 修改 `frontend/src/components/Warehouse.jsx`，实现物料创建/编辑级联分类和双列列表
    - 先加载一级分类；未选一级时禁用二级选择，选择后按一级 ID 加载二级项，切换一级必须立即清空旧二级值，两项均有效才允许提交。
    - 编辑时先回填一级、加载对应二级后再回填二级；列表使用独立“一级分类”“二级分类”列并显示严格低库存文案。
    - 移除通过仓储入口临时建立 PC/NB/PD 固定资产卡的行为；只读用户不可见或不可用新增、编辑和分类维护控件。
    - _Requirements: 2.5, 5.1–5.4, 7.1–7.6, 7.10–7.11, 12.1, 12.4–12.5_

  - [ ] 8.2 修改 `frontend/src/components/WarehouseSidebar.jsx`，实现一级/二级级联筛选和 AND 查询参数
    - 一级筛选改变时清空不再从属的二级筛选；将名称、一级、二级、数量、位置、阈值和低库存条件共同提交，由后端执行 AND 筛选。
    - 只读用户仍可使用全部查询和筛选能力。
    - _Requirements: 7.6–7.7, 7.10–7.11, 12.1, 12.4_

  - [ ] 8.3 修改 `frontend/src/components/WarehouseAssetDetail.jsx`，实现双分类详情、编辑回填和分类迁移状态展示
    - 详情分开显示一级/二级分类；编辑遵循先一级后二级的回填顺序，切换一级清空二级并阻止无效组合提交。
    - 对 `PENDING_MIGRATION` 记录显示原分类、待处理原因和只读提示；移除旧的前端扣库后逐件建卡编排。
    - _Requirements: 2.5, 7.4–7.6, 7.8–7.9, 12.1, 12.4–12.5_

  - [ ] 8.4 新建 `frontend/src/components/WarehouseCategoryManagement.jsx`，实现分类目录后期维护和迁移解决界面
    - 提供一级/二级新增、改名、排序、启停和按一级查看二级；展示引用冲突中文提示，不提供硬删除或直接换父操作。
    - 展示待处理报告并允许有写权限用户选择有效组合解决；只读角色可查看但不能维护或解决。
    - _Requirements: 7.1–7.5, 7.8–7.9, 12.1–12.5_

  - [x] 8.5 在 `frontend/src/components/Warehouse.test.jsx` 编写仓储主界面组件测试
    - 验证未选一级时二级禁用、按父加载、切换一级清空二级、有效组合提交、编辑回填顺序、双列展示、低库存边界和只读控件隐藏。
    - _Requirements: 7.4–7.6, 7.10–7.11, 12.1, 12.4–12.5_

  - [x] 8.6 在 `frontend/src/components/WarehouseSidebar.test.jsx` 编写级联 AND 筛选测试
    - 验证一级切换清空二级，并断言名称、一级、二级、数量、位置、阈值和低库存条件同时形成查询参数。
    - _Requirements: 7.7, 12.1, 12.4_

  - [x] 8.7 在 `frontend/src/components/WarehouseAssetDetail.test.jsx` 编写详情与编辑测试
    - 验证一级/二级双字段、先父后子回填、父项切换清空、`PENDING_MIGRATION` 只读提示和旧建卡编排已移除。
    - _Requirements: 2.5, 7.4–7.6, 7.8–7.9, 12.1, 12.4–12.5_

  - [x] 8.8 在 `frontend/src/components/WarehouseCategoryManagement.test.jsx` 编写目录维护与迁移解决测试
    - 覆盖新增/编辑/启停、引用冲突、待处理报告、解决刷新、中文错误和只读角色写控件隐藏。
    - _Requirements: 7.1–7.5, 7.8–7.9, 12.1–12.5_

- [x] 9. 完成前端测试配置、应用接线与跨领域验证
  - [x] 9.1 修改 `frontend/package.json`、锁文件和 `frontend/vite.config.js`，固定 Vitest 与 React Testing Library 兼容版本并增加单次测试脚本
    - 不新增状态管理或浏览器端到端框架，确保测试命令非 watch 模式。
    - _Requirements: 7.5–7.7, 12.1, 12.4–12.5（前端自动化测试基础）_

  - [x] 9.2 修改 `frontend/src/App.jsx` 及 `frontend/src/components/Sidebar.jsx`，接入新增中文页面与权限路由
    - 串联受控入库、固定资产生命周期、仓储目录维护、迁移解决、低值领用、专业发放和工具借还；成功后刷新关联数据，失败时保留输入并显示后端中文 `detail`。
    - 只读角色保留资产、仓储、领用、归还、维修和借用列表/详情入口，不显示业务写入口。
    - _Requirements: 1.3, 2.1–2.8, 3.1–3.3, 4.1–4.5, 5.1–5.8, 6.1–6.10, 7.1–7.11, 8.1–8.5, 9.1–9.4, 10.1–10.7, 11.1–11.5, 12.1, 12.4–12.5_

  - [x] 9.3 在 `frontend/src/components/AssetCategoryFlows.test.jsx` 编写跨页面组件流程测试
    - 覆盖三类固定资产选项、仓储不建卡、低值可选字段、维修/网络/工具/办公表单、中文成功/错误提示和只读导航。
    - _Requirements: 1.3, 2.5, 5.2, 6.3, 8.1–8.4, 9.1–9.3, 10.1–10.6, 11.1–11.3, 12.1, 12.4–12.5_

  - [x] 9.4 在 `backend/tests/test_cross_domain_permissions_and_concurrency.py` 编写跨领域权限、审计和并发集成测试
    - 验证只读用户对各领域列表/详情可读且代表性写操作均无副作用；在 PostgreSQL 测试环境用并发请求验证库存行锁只允许合法事务提交。
    - _Requirements: 3.1, 3.3, 6.4–6.10, 8.3, 9.3, 10.2–10.4, 11.3, 12.2–12.5_

- [x] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- 标注 `*` 的测试及测试基础任务为可选；执行实现任务时不得自动执行这些可选任务。
- 设计中的 16 项正确性属性均各自对应一个独立属性测试任务，并应使用设计规定的注释标识和至少 100 次 Hypothesis 生成。
- 后端测试文件按属性/领域拆分，前端组件测试按目标组件拆分，避免并行任务写入同一文件。
- 验证时按变更范围运行后端目标 pytest、前端 Vitest 单次运行和 `npm run build`；迁移仅在隔离副本测试，不修改生产数据。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.3", "1.4", "9.1"] },
    { "id": 1, "tasks": ["1.2", "1.5"] },
    { "id": 2, "tasks": ["2.1", "4.1", "6.1"] },
    { "id": 3, "tasks": ["2.2", "3.1", "4.4", "4.5", "4.6", "4.7", "6.4", "6.5", "6.6", "7.1"] },
    { "id": 4, "tasks": ["2.3", "2.4", "2.5", "3.2", "3.3", "7.5", "7.6", "7.7", "7.8"] },
    { "id": 5, "tasks": ["3.4", "3.5", "3.6", "3.7", "3.8"] },
    { "id": 6, "tasks": ["3.9", "4.2", "8.1", "8.2", "8.3", "8.4"] },
    { "id": 7, "tasks": ["4.3", "4.8", "6.2", "8.5", "8.6", "8.7", "8.8"] },
    { "id": 8, "tasks": ["6.3", "6.7", "7.2"] },
    { "id": 9, "tasks": ["7.3", "7.4", "7.9", "9.4"] },
    { "id": 10, "tasks": ["9.2"] },
    { "id": 11, "tasks": ["9.3"] }
  ]
}
```
