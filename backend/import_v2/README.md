# import_v2 资产导入模块

## 模块目标

`import_v2` 提供企业级资产批量导入能力：先解析和校验，再由用户完成主数据映射及重复策略选择，最后在单一事务中执行。模块保留旧 `POST /assets/import` 接口，不修改数据库表结构，也不依赖具体数据源。

## 目录职责

- `sources/excel_source.py`：读取 `.xlsx`、映射列头、保存原始快照和未知列、从文件名推断品类。
- `normalizer.py`：清理文本、占位符、序列号和品类名称。
- `resolvers/`：批量解析部门、品牌、库房或办公室位置。
- `validator.py`：必填、格式、状态、条件字段和文件内重复校验。
- `classifier.py`：按 `ERROR > DUPLICATE > MAPPING_REQUIRED > VALID` 分类。
- `import_policy.py`：把分类转换成 `INSERT / UPDATE / REPLACE / SKIP`。
- `pipeline.py`：按固定顺序编排各层，只产生 `AssetRecord`，不写数据库。
- `executor.py`：事务写入资产、资产日志、库存和操作审计。
- `reporting.py`：从本批记录和真实执行变化生成统计、跳过原因和库存明细。
- `domain_models.py`：跨层数据对象、枚举和运行时上下文。
- `import_session.py`：Wizard 会话、状态机、TTL 和内存存储接口。

## Pipeline 顺序

```text
Source → Normalizer → Resolver → Validator → Classifier → ImportPolicy → Executor
```

前六步负责数据转换、解析、校验、分类及决策；只有 Executor 可以写库。新增 LDAP、飞书等来源时，应实现只负责生成 `AssetRecord` 的 Source，不应把来源逻辑放进 Pipeline 处理层。

## 核心数据对象

### AssetRecord

每个 Excel 数据行对应一个 `AssetRecord`：

- `raw_fields`：Source 读取到的原始字符串快照，后续层不得修改。
- `fields`：标准化后的业务字段。
- `extra_fields`：未知列，执行时进入资产附加信息。
- `resolved`：部门、品牌、位置的强类型引用。
- `validation_errors` / `resolver_issues`：校验与映射问题。
- `classification` / `policy_decision`：分类及最终执行决策。

### ImportContext

`ImportContext` 是请求级依赖容器，包含数据库 Session、当前用户、策略、`request_id`、可选 `session_id`、推断品类和 `dry_run`。处理层通过参数接收它，不从 FastAPI 依赖或模块全局变量取请求状态。

### ImportSession

`ImportSession` 保存解析后的记录、预览汇总、用户映射、重复策略、来源文件和执行结果。默认 TTL 为 30 分钟；完成后保证至少再保留 10 分钟，供结果展示或下载。

## 三步 API

1. `POST /assets/import/parse`：上传 `.xlsx`，创建会话，返回分类预览和逐行问题。
2. `POST /assets/import/apply-mapping`：应用主数据映射和重复策略，重新分类并判断是否可执行。
3. `POST /assets/import/execute`：校验会话状态，在单一事务中执行并返回完整报告。

所有入口都要求非只读认证用户。`request_id` 贯穿响应和审计，用于定位一次请求。

## Session 状态机与 TTL

```text
PARSED → MAPPING_APPLIED → EXECUTING → COMPLETED
                               └────失败回滚────→ PARSED
任意有效状态可因过期转为 EXPIRED
```

非法状态转换返回冲突错误；`EXECUTING` 防止重复提交。TTL 是从创建时起计算的绝对过期时间，普通访问只更新最近访问时间，不无限延长会话。

## 四种策略

- `INSERT_ONLY`：有效记录新增，重复记录跳过（默认）。
- `UPDATE_EXISTING`：有效记录新增，重复记录更新；不更新现有资产编号。
- `REPLACE_EXISTING`：有效记录新增，重复记录完整覆盖导入字段。
- `DRY_RUN`：策略层支持全部跳过；Wizard 的 `dry_run` 执行模式会实际构建并执行 SQL，随后整体回滚，以验证完整执行路径。

错误和未完成映射的记录始终跳过。结果报告同时保留兼容字段 `success_count`、`fail_count`、`skip_count`、`dry_run`、`records`，并新增带默认值的 `errors`、`warnings` 和 `statistics`。`statistics` 包含总行数、`by_decision`（同时保留 `decision_counts` 兼容别名）、真实 INSERT/UPDATE/REPLACE/SKIP/FAILED 数量、品类/状态/错误分布及库存同步明细；因此旧客户端可以继续只读取原字段，新客户端可以渐进展示结构化报告。

`errors` 用于 ERROR 与 MAPPING_REQUIRED 等不可执行记录，包含行号、资产编号、错误类型、字段、中文原因和 `request_id`；重复策略跳过及未知列等非致命情况进入 `warnings`。逐行 `records` 不删除，继续作为 Phase 5/6 UI 的兼容明细。

## 事务、回滚和审计

Executor 在一个事务中依次执行资产 INSERT/UPDATE/REPLACE、`AssetLog`、库存变化、`WarehouseAssetLog` 和成功 `OperationLog`。任意一步失败会回滚主事务，因此不会留下部分资产、库存或成功日志。

失败后使用 `audit_session_factory` 创建完全独立的数据库 Session，写入 `import_failed` 操作日志。失败日志明确标记 `rolled_back=true`；其中库存明细是已回滚的尝试，不表示持久化成功。不要把失败审计改回主事务 Session。

## 库存同步与行锁

闲置资产会按映射后的库存品类调整 `WarehouseAsset.available_quantity`，并按 `total_quantity - available_quantity` 更新 `allocated_quantity`。查询使用 `SELECT ... FOR UPDATE` 锁定目标库存行；多个候选按可用数量降序、主键升序确定目标。同一批次对同一库存对象的多次变化聚合为可用量和已分配量的“首次前值 → 最终后值”，并报告可用量净 `delta`。每条 `warehouse_synced` 还包含 `committed`、`dry_run`、`rolled_back`，用于区分正式提交、演练变化和失败回滚尝试。找不到库存对象时不失败，返回 `WAREHOUSE_NOT_FOUND` warning，且不生成虚构库存明细。

## DRY_RUN

干运行执行与正式导入相同的校验、资产 SQL、日志 SQL、库存锁和库存调整，但返回报告前调用 `ROLLBACK`。因此报告会描述本次演练产生的决策和库存变化，同时资产、库存及成功审计均保持零持久化。

## 旧接口兼容

`POST /assets/import` 继续返回旧 `ImportResult`：`total_rows`、`success_count`、`failed_count`、`errors`、`message`。Wizard Schema 和报告增强不得改变这些字段的类型、含义或旧接口行为。旧模板下载接口同样保留。

模板两条下载路径（`GET /assets/import-template` 和 `generate_import_template()`）使用相同的 22 列顺序：
`资产编号，品类，工号，姓名，部门，直属领导，资产名，状态，型号，序列号，品牌，MAC地址，IP地址，备注，系统版本，杀毒软件，锁号，位置，数量，采购日期，固定资产编号，PO号`。
其中“姓名”是标准模板列头并映射到内部字段 `employee_name`；“使用人”“员工姓名”“姓名”等既有列头仍可作为导入别名解析。

## 多 Worker 限制与未来扩展

当前 `InMemorySessionStore` 是进程内字典。多 worker 部署时，同一 `session_id` 可能被路由到另一个进程而无法找到；进程重启也会丢失未完成会话。当前生产部署应保持单 worker。

未来切换 Redis 时：

1. 实现 `AbstractSessionStore` 的 `create / get / save / delete / purge_expired`。
2. 为 `AssetRecord`、映射、预览和会话时间提供显式序列化/反序列化。
3. 使用 Redis TTL 表达过期时间，并用原子操作保护 `MAPPING_APPLIED → EXECUTING`。
4. 在 FastAPI 依赖注入点替换 Store，不修改 Pipeline 或 Executor。

未来新增 Source 时，只需把外部数据转换成 `AssetRecord` 列表，并填充行号、来源名、`raw_fields`、`fields`、`extra_fields`。不得在 Source 中执行资产持久化，也不需要修改 Normalizer、Resolver、Validator、Classifier 或 Executor。

## 示例执行响应

以下为精简示例；实际 `records`、`errors`、`warnings` 和库存明细可包含多项：

```json
{
  "request_id": "c83f4a16-6ca8-4eed-bb22-a71f489915e1",
  "result": {
    "success_count": 1,
    "fail_count": 0,
    "skip_count": 1,
    "dry_run": false,
    "records": [
      {"row_number": 2, "asset_tag": "ZS-MR26-000001", "decision": "INSERT", "status": "SUCCESS", "message": "导入成功"},
      {"row_number": 3, "asset_tag": "ZS-MR26-000002", "decision": "SKIP", "status": "SKIPPED", "message": "重复数据按 INSERT_ONLY 策略跳过"}
    ],
    "errors": [],
    "warnings": [{"row_number": 3, "asset_tag": "ZS-MR26-000002", "warning_type": "CONFLICT", "message": "重复数据按 INSERT_ONLY 策略跳过"}],
    "statistics": {
      "by_category": {"显示器": 2},
      "by_status": {"闲置": 2},
      "by_error_type": {"CONFLICT": 1},
      "by_decision": {"INSERT": 1, "UPDATE": 0, "REPLACE": 0, "SKIP": 1},
      "warehouse_synced": [{
        "warehouse_asset_id": 8,
        "warehouse_asset_name": "显示器库存",
        "warehouse_category": "显示设备",
        "delta": 1,
        "before_available": 2,
        "after_available": 3,
        "before_allocated": 8,
        "after_allocated": 7,
        "committed": true,
        "dry_run": false,
        "rolled_back": false
      }]
    }
  }
}
```

## request_id 排障

1. 从 Wizard 结果页、错误响应或浏览器网络请求复制 `request_id`。
2. 在 `operation_logs.new_value` 或 `description` 中按该完整 ID 检索；成功日志 action 为 `import`，失败日志为 `import_failed`。
3. 对照同一审计 JSON 中的 `session_id`、`source_filename`、`operator_name`、策略、决策数量和库存摘要判断影响范围。
4. 若只有失败审计，表示主事务已回滚；其 `reason` 和 `statistics.warehouse_synced[*].rolled_back` 用于定位原始数据库错误和已撤销的库存尝试。

失败审计写入异常会被隔离，不会覆盖或替换原始导入异常。日志中的来源文件名只用于排障，不应作为文件内容真实性证明。

## 扩展 Source 与 Resolver

新增数据源时，实现与 `ExcelSource` 等价的适配器，输出完整 `AssetRecord` 列表并填充 `row_number`、`source_filename`、`raw_fields`、`fields`、`extra_fields`；随后把 Source 注入 `ImportPipeline`，不改写后续层。

新增受控主数据解析器时：

1. 返回 `DepartmentRef`、`BrandRef`、`LocationRef` 或新增的强类型 Ref，禁止只返回无 ID 文本。
2. 汇总本批唯一输入后使用批量查询，避免逐行 N+1 查询。
3. 无匹配或多匹配时写入 `ResolverIssue`，不要在 Resolver 内创建主数据。
4. 通过 `ImportPipeline` 构造参数注入解析器，并为精确匹配、无匹配、多匹配和空值编写测试。
5. 若新增映射字段，需同步扩展 Mapping API 的枚举、目标校验和前端中文选择器。

## 当前限制

- PostgreSQL 的并发 `SELECT ... FOR UPDATE` 行锁行为仍需在真实 PostgreSQL 环境执行并发集成测试；SQLite 测试只能验证查询路径和事务结果，不能证明生产锁竞争语义。
- Session 仍是单进程内存状态，服务重启会丢失；多 worker 前必须迁移到共享存储。
- 报告随 execute 响应和短期 Session 保存，尚无独立的长期报告下载表。
- 库存按品类选择一个匹配条目，不在本阶段处理同品类多仓库的人工分摊。

## 测试

- `test_import_v2_phase4_api.py`：三步 API、会话权限与旧接口兼容。
- `test_import_v2_phase6_executor.py`：事务原子性、三种正式策略、库存锁、失败审计和干运行。
- `test_import_v2_phase7_reporting.py`：增强统计、库存聚合、跳过原因、审计 JSON、回滚及兼容字段。

测试使用 SQLite 独立数据库，不应读取或修改开发环境 `.env` 中的业务数据库。

## Windows 常用命令

在项目根目录的 PowerShell 中执行：

```powershell
# Python 语法编译检查
backend\venv\Scripts\python.exe -m compileall -q backend

# 全部后端测试
backend\venv\Scripts\python.exe -m pytest backend\tests -q

# 仅导入模块测试
backend\venv\Scripts\python.exe -m pytest backend\tests\test_import_v2_phase4_api.py backend\tests\test_import_v2_phase6_executor.py backend\tests\test_import_v2_phase7_reporting.py -q

# 前端生产构建
npm --prefix frontend run build
```

若虚拟环境不在 `backend\venv`，可在已激活的虚拟环境中把 `backend\venv\Scripts\python.exe` 替换为 `python`。不要用开发服务器或 watch 模式代替上述验证命令。
