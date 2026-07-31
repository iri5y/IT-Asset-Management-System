# Requirements Document

## Introduction

本功能将 IT 资产管理系统的批量导入能力从单步同步流程重设计为企业级 Wizard 多步导入流程。
新模块在保留旧接口向后兼容的前提下，新增数据预览、主数据映射、重复处理策略选择和完整事务回滚能力，
消除脏数据写入风险，并通过模块化 Pipeline 架构为未来接入 LDAP、飞书等数据源预留扩展接口。

## Glossary

- **Import_Pipeline**：串联 Normalizer → Resolver → Validator → Classifier → ImportPolicy 各层的编排器，负责将原始数据转化为带分类标签的 AssetRecord 列表，不负责写库
- **AssetRecord**：流经 Pipeline 全生命周期的数据载体，包含原始快照 `raw_fields`（只读）、标准化字段 `fields`、未知列 `extra_fields`、主数据引用 `resolved`、分类标签 `classification` 及策略决定 `policy_decision`
- **ImportContext**：Pipeline 运行时共享上下文，包含 `request_id`（全链路追踪）、数据库 Session、当前操作用户、导入策略实例及 `dry_run` 开关
- **ImportSession**：Wizard 多步流程的服务端会话，保存 Parse 阶段产生的 AssetRecord 列表、用户 Mapping 选择和重复处理策略，默认 TTL 为 30 分钟
- **ExcelSource**：从 `.xlsx` 文件读取数据并生成 AssetRecord 列表的数据源层，负责列头映射和品类推断
- **Normalizer**：对 AssetRecord.fields 执行文本标准化的处理层（去除首尾空格、NA 占位符转 None、品类名称标准化等）
- **Resolver**：查询数据库将部门名、品牌名、位置名解析为带 ID 的强类型引用对象（DepartmentRef / BrandRef / LocationRef）的处理层
- **Validator**：执行业务规则校验的处理层（必填项、状态合法性、asset_tag 格式、PO 号格式、文件内重复等），结果写入 AssetRecord.validation_errors
- **Classifier**：根据 Validator 结果和数据库唯一性查询，为每条记录打分类标签（VALID / MAPPING_REQUIRED / DUPLICATE / ERROR）的处理层
- **ImportPolicy**：根据策略类型（INSERT_ONLY / UPDATE_EXISTING / REPLACE_EXISTING / DRY_RUN）对 DUPLICATE 记录决定 PolicyDecision（SKIP / UPDATE / REPLACE）的无状态策略对象
- **Executor**：读取 AssetRecord.policy_decision 在单一数据库事务中执行批量写库（INSERT / UPDATE / REPLACE）的执行层，失败时全量回滚
- **Import_API**：FastAPI 路由层，对外暴露 `/assets/import/parse`、`/assets/import/apply-mapping`、`/assets/import/execute` 三个 Wizard 接口及向后兼容的 `/assets/import` 旧接口
- **Import_UI**：前端 Wizard 多步导入弹窗组件，依次引导用户完成文件上传、数据预览、主数据映射和执行确认四个步骤
- **Asset**：IT 资产记录，对应数据库 `assets` 表
- **asset_tag**：资产编号，格式为 `ZS-[A-Za-z0-9]{4}-\d{6}`（如 ZS-PC26-000001），在系统中全局唯一
- **主数据**：系统已有的受控参照数据，包括部门（Department）、品牌（Brand）、位置（WarehouseLocation / OfficeLocation）
- **VALID**：Classifier 分类标签，表示记录格式正确、主数据已解析、无重复，可直接写库
- **MAPPING_REQUIRED**：Classifier 分类标签，表示部门/品牌/位置名称在系统中找不到精确匹配，需用户手动选择对应主数据
- **DUPLICATE**：Classifier 分类标签，表示 asset_tag 或 serial_number 与数据库已有未删除记录冲突，由 Policy 决定处理方式
- **ERROR**：Classifier 分类标签，表示格式错误、必填缺失或状态非法，禁止写库
- **干运行（DRY_RUN）**：演习模式，Pipeline 完整执行但 Executor 不提交事务，用于验证数据质量


## Requirements

### 需求 1：Excel 文件解析与 AssetRecord 生成

**用户故事：** 作为 IT 资产管理员，我希望上传 `.xlsx` 文件后系统能立即解析内容并生成结构化预览，以便在正式导入前了解每行数据的处理结果。

#### 验收标准

1. WHEN 用户向 `/assets/import/parse` 上传 `.xlsx` 文件时，THE Import_API SHALL 在 30 秒内返回 `session_id`（有效期 30 分钟）和 `preview_summary`（包含 total、valid、mapping_required、duplicate、error 五个字段，且 total = 其余四项之和）
2. IF 上传文件扩展名（大小写不敏感）不是 `.xlsx`，THEN THE Import_API SHALL 返回 HTTP 400 并在 `detail` 字段说明"仅支持 .xlsx 格式文件"
3. IF 上传文件大小超过 10MB，THEN THE Import_API SHALL 返回 HTTP 400 并在 `detail` 字段说明"文件大小不能超过 10MB"
4. IF Excel 文件仅含列头行（数据行数为 0），THEN THE Import_API SHALL 返回 HTTP 200，`preview_summary.total` 为 0，`records` 为空列表
5. THE ExcelSource SHALL 将 Excel 第一行识别为列头，列头匹配时先去除首尾空白字符再执行精确比较
6. THE ExcelSource SHALL 支持以下标准中文列头映射（同时支持 FUZZY_ALIAS 中定义的别名变体）：`资产编号`→`asset_tag`、`品类`→`category`、`品牌`→`brand`、`型号`→`model`、`序列号`→`serial_number`、`状态`→`status`、`使用人`→`employee_name`、`工号`→`employee_id`、`部门`→`department`、`资产名`→`hostname`、`MAC地址`→`mac_address`、`IP地址`→`ip_address`、`固定资产编号`→`fixed_asset_number`、`位置`→`location`、`备注`→`notes`、`系统版本`→`system_version`、`杀毒软件`→`antivirus_software`、`锁号`→`lock_number`、`直属领导`→`supervisor`、`数量`→`quantity`、`采购日期`→`purchase_date`、`PO号`→`po_number`
7. WHEN 同一英文字段名对应多个列头（如"资产编号"和"编号"同时存在）时，THE ExcelSource SHALL 取列表中先出现的列头，后续重复映射到相同字段的列头作为未知列存入 extra_fields
8. IF Excel 文件缺少必填列头 `资产编号` 或 `状态`（含别名），THEN THE ExcelSource SHALL 抛出 ValueError，Import_API 返回 HTTP 400 并在 `detail` 字段列出缺失的原始列头名称
9. WHEN Excel 文件包含无法解析为已知字段的列头时，THE ExcelSource SHALL 将该列数据存入 AssetRecord.extra_fields（key 为原始列头文本），而非丢弃
10. THE ExcelSource SHALL 从文件名推断品类（大小写不敏感，按以下优先级顺序匹配首个命中项）：含"笔记本"/"laptop"/"notebook"/"nb"→"笔记本电脑"，含"台式"/"desktop"/"pc"→"台式机"，含"服务器"/"server"/"srv"→"服务器"，含"移动设备"/"pad"/"ipad"/"平板"/"tablet"→"移动设备"，含"手机"/"phone"/"mobile"→"手机"，含"显示器"/"monitor"/"display"→"显示器"，含"打印机"/"printer"→"打印机"，含"网络"/"network"/"路由"/"交换机"/"switch"→"网络设备"，含"鼠标"/"mouse"→"无线鼠标"；无匹配时 inferred_category 为 None
11. WHEN Excel 文件中不含"品类"列（原始列头中无"品类"及其别名）时，THE Normalizer SHALL 使用 inferred_category（若非 None）填充每行的 category 字段，并在 Pipeline 警告列表中为每行追加 CATEGORY_INFERRED 警告；IF inferred_category 为 None，THEN category 字段保持空值，不追加警告
12. THE ExcelSource SHALL 将每行原始单元格值（未经任何转换的字符串）存入 AssetRecord.raw_fields；经 Pipeline 全部层处理完成后，AssetRecord.raw_fields 各 key 对应的值与读取时完全一致


### 需求 2：数据标准化（Normalizer）

**用户故事：** 作为系统，我希望对原始导入数据执行自动标准化处理，以便消除因大小写、空格、NA 占位符等格式差异导致的主数据匹配失败和校验误报。

#### 验收标准

1. THE Normalizer SHALL 对 AssetRecord.fields 中所有字段值去除首尾空白字符（含半角空格和全角空格 `\u3000`）；IF 去除后为空字符串，THEN 将该字段值设为 None
2. THE Normalizer SHALL 将以下占位符（大小写不敏感）统一转为 None：`n/a`、`na`、`none`、`null`、`-`、`无`、`暂无`、`不适用`
3. THE Normalizer SHALL 将 `serial_number` 字段值转换为全大写；IF `serial_number` 为 None，THEN 跳过，不产生错误
4. THE Normalizer SHALL 对 `category` 字段执行品类名称标准化（大小写不敏感）：`台式电脑`/`台式`/`desktop`→`台式机`，`笔记本`/`laptop`/`notebook`→`笔记本电脑`，`平板`/`ipad`/`tablet`/`pad`→`移动设备`；无匹配时保留原值不变
5. WHEN `category` 字段为 None 且 ImportContext.inferred_category 非 None 时，THE Normalizer SHALL 将 ImportContext.inferred_category 写入 `category` 字段
6. THE Normalizer SHALL 在所有标准化操作完成后，AssetRecord.raw_fields 中的值与标准化前完全一致（不得修改 raw_fields）
7. THE Normalizer SHALL 对 AssetRecord.fields 中值为非字符串类型（如 int、float）的字段保持原值不变，不做类型转换


### 需求 3：主数据解析（Resolver）

**用户故事：** 作为 IT 资产管理员，我希望系统自动将 Excel 中填写的部门名、品牌名、位置名匹配到数据库中的受控主数据，以便避免因名称不一致导致脏数据写入。

#### 验收标准

1. THE Resolver SHALL 在 Normalizer 执行完成后运行，以标准化后的字段值作为查询输入
2. WHEN `department` 字段值与数据库 departments 表中某条记录的 name 精确匹配时，THE Resolver SHALL 将该部门的 id、name 和 parent_id 存入 AssetRecord.resolved.department（DepartmentRef 对象）
3. WHEN `brand` 字段值与数据库 brands 表中某条记录的 name 精确匹配时，THE Resolver SHALL 将该品牌的 id 和 name 存入 AssetRecord.resolved.brand（BrandRef 对象）
4. WHEN `location` 字段值与数据库 warehouse_locations 或 office_locations 表中某条记录的 name 精确匹配时，THE Resolver SHALL 将该位置的 id、name 和位置类型（WAREHOUSE / OFFICE）存入 AssetRecord.resolved.location（LocationRef 对象）
5. WHEN 某主数据字段值在数据库中找不到任何匹配记录时，THE Resolver SHALL 在 AssetRecord.resolver_issues 中追加一条 ResolverIssue，issue_type 为 UNKNOWN，记录 field（字段名）和 raw_value（原始值），candidates 为空列表
6. WHEN 某主数据字段值在数据库中匹配到多条记录时，THE Resolver SHALL 在 AssetRecord.resolver_issues 中追加一条 ResolverIssue，issue_type 为 MULTIPLE_MATCH，并在 candidates 列表中记录所有匹配记录的名称
7. THE Resolver SHALL 对批量记录使用 IN 查询一次性检索所有唯一值，而非为每条记录单独查询；每种主数据类型（department、brand、location）各执行不超过两次 SQL 查询（warehouse + office 各一次）
8. WHEN `department`、`brand` 或 `location` 字段值为 None 时，THE Resolver SHALL 跳过对应字段的解析，不产生 ResolverIssue，resolved 中对应字段保持 None
9. WHEN 同一 location 名称在 warehouse_locations 和 office_locations 中各有一条匹配时，THE Resolver SHALL 产生 MULTIPLE_MATCH ResolverIssue，candidates 中标注来源类型（如"库房: 北京仓库"和"办公室: 北京研发办公室"）


### 需求 4：业务规则校验（Validator）

**用户故事：** 作为系统，我希望在写库前对每行数据执行完整的业务规则校验，以便确保导入数据满足系统的数据完整性约束。

#### 验收标准

1. WHEN 某行数据缺少必填字段 `asset_tag`、`category` 或 `status`（值为 None 或空字符串）时，THE Validator SHALL 在 AssetRecord.validation_errors 中追加对应字段的缺失错误，message 格式为"{字段中文名}为必填项，不能为空"
2. THE Validator SHALL 验证 `asset_tag` 符合正则 `^ZS-[A-Za-z0-9]{4}-\d{6}$`；IF 格式不符，THEN THE Validator SHALL 追加格式错误，message 格式为"格式错误「{asset_tag}」，应为 ZS-XXXX-NNNNNN（如 ZS-PC26-000001）"；IF `asset_tag` 为 None，THEN 跳过格式校验（缺失已由标准 1 报告）
3. THE Validator SHALL 验证 `status` 属于合法状态值集合（`闲置`、`使用中`、`维修中`、`报废`）；IF 不合法，THEN THE Validator SHALL 追加状态错误，message 格式为"非法状态值「{status}」，允许: {合法值逗号分隔列表}"；IF `status` 为 None，THEN 跳过合法值校验（缺失已由标准 1 报告）
4. WHEN `category` 属于需要序列号的品类（笔记本电脑、台式机、服务器、移动设备）且 `serial_number` 为 None 时，THE Validator SHALL 追加必填错误，message 为"品类为「{category}」时，序列号为必填项"
5. WHEN `category` 属于需要 PO 号的品类（笔记本电脑、台式机）且 `po_number` 为 None 时，THE Validator SHALL 追加必填错误，message 为"品类为「{category}」时，PO号为必填项"；WHEN `po_number` 非 None 且不是纯数字字符串时，THE Validator SHALL 追加格式错误，message 为"PO号格式错误，必须为纯数字（例如：12000327）"；此规则同样适用于非必填品类中填写了 PO 号的情况
6. WHEN `status` 为"使用中"且 `employee_name` 为 None 时，THE Validator SHALL 追加必填错误，message 为"状态为「使用中」时，使用人为必填项"
7. THE Validator SHALL 在文件内检测 `asset_tag` 重复（仅对无 asset_tag 格式错误的记录参与去重）：WHEN 同一文件中出现相同 `asset_tag` 时，THE Validator SHALL 对第二次及之后出现的行追加错误，message 格式为"资产编号「{asset_tag}」在文件中重复，首次出现于第 {行号} 行"
8. THE Validator SHALL 对所有记录完成全部规则校验后返回，不因单行错误中断整批校验；同一条记录可同时携带多条 ValidationError


### 需求 5：记录分类（Classifier）

**用户故事：** 作为系统，我希望对每条记录打上明确的处理分类标签，以便前端能够直观展示数据质量，用户在执行写库前对导入结果有完整认知。

#### 验收标准

1. WHEN AssetRecord.has_errors 为 True（validation_errors 非空）时，THE Classifier SHALL 将 AssetRecord.classification 设置为 ERROR，跳过后续 DB 唯一性检查
2. WHEN AssetRecord.has_errors 为 False 且 `asset_tag` 与数据库中 is_deleted=False 的资产记录冲突时，THE Classifier SHALL 将 classification 设置为 DUPLICATE，并将冲突资产的 id、asset_tag、serial_number、status 和 conflict_field="asset_tag" 写入 AssetRecord.duplicate_info
3. WHEN AssetRecord.has_errors 为 False 且无 asset_tag 冲突且 `serial_number` 非 None 且与数据库中 is_deleted=False 的资产记录冲突时，THE Classifier SHALL 将 classification 设置为 DUPLICATE，并在 duplicate_info 中记录 conflict_field="serial_number"
4. WHEN AssetRecord.has_errors 为 False 且无重复冲突且 AssetRecord.needs_mapping 为 True（resolver_issues 非空）时，THE Classifier SHALL 将 classification 设置为 MAPPING_REQUIRED
5. WHEN AssetRecord.has_errors 为 False 且无重复冲突且 AssetRecord.needs_mapping 为 False 时，THE Classifier SHALL 将 classification 设置为 VALID
6. THE Classifier SHALL 对批量记录使用两次 IN 查询（asset_tags 一次、serial_numbers 一次）检索冲突情况，而非逐条单独查询
7. THE Classifier SHALL 严格遵循优先级 ERROR > DUPLICATE > MAPPING_REQUIRED > VALID；当 asset_tag 和 serial_number 均冲突时，以 asset_tag 冲突优先，conflict_field 记录为"asset_tag"


### 需求 6：导入策略（ImportPolicy）

**用户故事：** 作为 IT 资产管理员，我希望在正式写库前选择重复数据的处理方式，以便根据不同的业务场景（首次导入、数据补录、全量刷新）灵活控制导入行为。

#### 验收标准

1. THE ImportPolicy SHALL 支持四种策略类型：INSERT_ONLY（默认）、UPDATE_EXISTING、REPLACE_EXISTING、DRY_RUN
2. WHILE 策略为 DRY_RUN 时，THE ImportPolicy SHALL 对所有记录（无论 classification）决定 policy_decision 为 SKIP；此规则优先于其他所有策略规则
3. WHILE 策略为 INSERT_ONLY 时，THE ImportPolicy SHALL 对 classification 为 DUPLICATE 的记录决定 policy_decision 为 SKIP
4. WHILE 策略为 UPDATE_EXISTING 时，THE ImportPolicy SHALL 对 classification 为 DUPLICATE 的记录决定 policy_decision 为 UPDATE
5. WHILE 策略为 REPLACE_EXISTING 时，THE ImportPolicy SHALL 对 classification 为 DUPLICATE 的记录决定 policy_decision 为 REPLACE
6. THE ImportPolicy SHALL 对 classification 为 VALID 的记录决定 policy_decision 为 INSERT，不受 INSERT_ONLY / UPDATE_EXISTING / REPLACE_EXISTING 策略类型影响
7. THE ImportPolicy SHALL 对 classification 为 ERROR 的记录决定 policy_decision 为 SKIP，不受任何策略类型影响
8. THE ImportPolicy SHALL 对 classification 为 MAPPING_REQUIRED 的记录决定 policy_decision 为 SKIP（用户完成 Mapping 后 Classifier 将重新分类，届时再重新决策）
9. THE ImportPolicy SHALL 为无状态对象（所有字段仅在构造时设置），可跨批次复用同一实例，不在对象内部累积任何记录状态


### 需求 7：Wizard 会话管理（ImportSession）

**用户故事：** 作为系统，我希望在服务端保存 Wizard 多步流程的中间状态，以便用户在预览、Mapping 和执行三个步骤之间切换时无需重新上传文件。

#### 验收标准

1. WHEN Import_API 完成文件 Parse 时，THE Import_API SHALL 通过 InMemorySessionStore 创建一个 ImportSession，存储 parsed_records 列表、preview_summary 和 source_filename，并将 UUID4 格式的 session_id 返回给前端
2. THE ImportSession SHALL 使用状态机管理生命周期，合法转换路径为：PARSED→MAPPING_APPLIED、MAPPING_APPLIED→EXECUTING、EXECUTING→COMPLETED、EXECUTING→PARSED（失败回滚后允许重试）；IF 发生非法状态转换，THEN 抛出 ValueError，Import_API 返回 HTTP 409
3. THE ImportSession SHALL 将 session_id 与创建者用户 ID（owner_user_id）绑定；WHEN 非创建者使用相同 session_id 请求时，THE Import_API SHALL 返回 HTTP 403 错误，附带消息"无权访问此导入会话"
4. THE ImportSession SHALL 默认 TTL 为 30 分钟（从创建时刻起算）；WHEN 执行完成（状态转为 COMPLETED）时，THE ImportSession SHALL 将过期时间延长至 `now + 10分钟`（取与当前过期时间的最大值）
5. WHEN 访问 session_id 时 ImportSession 已过期或不存在，THE Import_API SHALL 返回 HTTP 404 错误，附带消息"导入会话不存在或已过期，请重新上传文件"
6. WHEN 同一 Session 处于 EXECUTING 状态时收到重复的 execute 请求，THE Import_API SHALL 返回 HTTP 409 错误，附带消息"导入正在执行中，请勿重复提交"
7. THE ImportSession SHALL 使用 InMemorySessionStore（Python 字典单例）实现；该存储类 SHALL 实现 AbstractSessionStore 抽象接口（含 create / get / save / delete / purge_expired 方法），以便未来切换 Redis 时仅替换注入实现


### 需求 8：主数据映射（Mapping）

**用户故事：** 作为 IT 资产管理员，当 Excel 中的部门名、品牌名或位置名与系统记录不完全一致时，我希望能手动将其映射到系统中已有的主数据，以便在不修改 Excel 文件的情况下完成正确导入。

#### 验收标准

1. WHEN Import_API 收到 `/assets/import/apply-mapping` 请求时，THE Import_API SHALL 验证 session_id 对应的 ImportSession 存在且状态为 PARSED；IF 状态不为 PARSED，THEN 返回 HTTP 409 并说明当前状态
2. THE Import_API SHALL 接受用户提交的 MappingEntry 列表，每条 MappingEntry 包含 raw_value（原始文本）、field_type（DEPARTMENT / BRAND / LOCATION）、resolved_id（目标主数据 ID，action 为 map_existing 时必填）、resolved_name（展示用名称）和 action（"map_existing" 或 "skip"）
3. WHEN action 为 map_existing 且 resolved_id 指向的主数据在数据库中不存在时，THE Import_API SHALL 返回 HTTP 400 错误，附带消息"映射目标 ID {resolved_id} 不存在"
4. THE ImportSession SHALL 将提交的 MappingEntry 以 `{field_type}:{raw_value}` 为键存储到 mapping 字典；多次调用 apply-mapping 时，新 Entry 追加或覆盖已有 Entry，不清空未被覆盖的 Entry
5. WHEN 用户提交 Mapping 后，THE Import_Pipeline SHALL 对 classification 为 MAPPING_REQUIRED 的记录重新执行 Resolver（使用用户 mapping 中的 resolved_id 直接填充 resolved，跳过数据库查询），然后重新执行 Classifier 和 ImportPolicy，更新 classification 和 policy_decision
6. WHEN 重新分类后所有记录的 classification 均不为 MAPPING_REQUIRED 且不为 ERROR 时，THE Import_API SHALL 在响应中将 ready_to_execute 设为 True；否则设为 False
7. THE Import_API SHALL 在 apply-mapping 响应中返回更新后的 preview_summary，反映重新分类后各分类的最新计数
8. WHEN 某条 MappingEntry 的 action 为 "skip" 时，THE Import_Pipeline SHALL 不为该记录执行主数据解析，该记录 classification 保持 MAPPING_REQUIRED，policy_decision 保持 SKIP


### 需求 9：事务性批量写库（Executor）

**用户故事：** 作为 IT 资产管理员，我希望导入写库操作具有完整的事务保障，以便在任何一条记录写入失败时系统能自动回滚全部操作，不产生部分写入的不一致状态。

#### 验收标准

1. THE Executor SHALL 在单一数据库事务中顺序执行所有 policy_decision 不为 SKIP 的记录的写库操作；policy_decision 为 SKIP 的记录直接跳过，不产生任何 SQL
2. THE Executor SHALL 按 policy_decision 执行对应操作：INSERT→新建 Asset 记录（含所有字段）；UPDATE→更新已有 Asset 记录的全部非 asset_tag 字段；REPLACE→先删除旧记录再插入新记录（或覆盖全部字段包括 asset_tag）
3. WHEN 事务执行过程中任意一条写库操作失败时，THE Executor SHALL 回滚整个事务，确保本批次零记录被持久化
4. WHEN 事务回滚发生时，THE Executor SHALL 使用独立的新数据库 Session（与回滚的 Session 完全独立）写入一条操作失败审计日志，记录 request_id、operator_name、失败原因和影响行数；此日志不受主事务回滚影响
5. THE Executor SHALL 对涉及 WarehouseAsset 数量字段的更新使用 `SELECT ... FOR UPDATE` 行锁，防止并发导入导致库存数量不一致
6. WHEN policy_decision 为 INSERT 且资产 `status` 为"闲置"时，THE Executor SHALL 在同一事务中查找该品类的 WarehouseAsset 记录（加行锁）并递增 available_quantity；IF 对应品类的 WarehouseAsset 不存在，THEN 跳过库存更新，不抛出错误
7. WHEN policy_decision 为 UPDATE 且原资产状态不为"闲置"而新状态为"闲置"时，THE Executor SHALL 在同一事务中递增对应品类 WarehouseAsset.available_quantity；WHEN 原资产状态为"闲置"而新状态不为"闲置"时，THE Executor SHALL 递减 available_quantity（最小值为 0）
8. WHILE ImportContext.dry_run 为 True 时，THE Executor SHALL 构建所有 SQL 语句并执行（含 Validator 重新校验），但在返回前执行 ROLLBACK 而非 COMMIT，并在返回结果中将 dry_run 标记为 True
9. FOR ALL policy_decision 为 INSERT 或 UPDATE 的成功操作，THE Executor SHALL 在同一事务中为每条 Asset 记录创建一条 AssetLog，action 为"批量导入"，description 格式为"{INSERT/UPDATE}: {asset_tag}"
10. WHEN 整批写库操作完成（无论成功或失败）时，THE Executor SHALL 创建一条 OperationLog，记录 operator_name、操作类型"import"、资源类型"asset"，以及 success_count、skip_count、fail_count 的数量统计


### 需求 10：Wizard 多步 API 接口

**用户故事：** 作为前端开发者，我希望后端提供清晰的三步 Wizard API，以便前端能准确引导用户完成上传、预览、映射和执行四个步骤。

#### 验收标准

1. THE Import_API SHALL 提供 `POST /assets/import/parse` 接口，接受 multipart/form-data 文件上传，成功时返回：`session_id`、`request_id`、`preview_summary`（含 total / valid / mapping_required / duplicate / error）、`records`（含每行 row_number、asset_tag、classification、validation_errors、resolver_issues、duplicate_info）、`warnings` 列表和 `inferred_category`
2. THE Import_API SHALL 提供 `POST /assets/import/apply-mapping` 接口，接受 JSON 请求体（session_id、mapping_entries 列表、duplicate_policy），返回：`request_id`、更新后的 `preview_summary` 和 `ready_to_execute` 布尔值
3. THE Import_API SHALL 提供 `POST /assets/import/execute` 接口，接受 JSON 请求体（session_id，可选 dry_run 布尔值），返回：`request_id`、`ImportResult`（success_count、fail_count、skip_count、dry_run、各记录处理结果明细）
4. THE Import_API SHALL 在上述三个接口中验证用户已认证且角色不为只读（read_only=False）；WHEN 只读用户调用时，THE Import_API SHALL 返回 HTTP 403 错误，附带消息"只读账号无权限执行修改或新增操作"
5. THE Import_API SHALL 在每个接口的请求入口处通过 ImportContext.create() 生成 UUID4 格式的 request_id，贯穿 Pipeline 全生命周期，并在所有响应体中透传 `request_id` 字段
6. WHEN `/assets/import/execute` 接口调用时 ImportSession 状态不为 MAPPING_APPLIED 时，THE Import_API SHALL 返回 HTTP 409 错误，附带消息"请先完成主数据映射步骤再执行导入"
7. THE Import_API SHALL 对所有接口的错误响应使用统一格式 `{"detail": "错误说明", "request_id": "..."}` 以便前端统一处理


### 需求 11：旧接口向后兼容

**用户故事：** 作为现有系统用户，我希望原有的 `POST /assets/import` 单步导入接口继续正常工作，以便在新 Wizard 功能上线后不中断现有使用场景。

#### 验收标准

1. THE Import_API SHALL 保留 `POST /assets/import` 接口，接受 `.xlsx` 文件上传，不需要 Wizard 会话，单次请求完成解析和写库
2. THE Import_API SHALL 使旧接口经过同一套 Import_Pipeline（Normalizer → Resolver → Validator → Classifier → ImportPolicy），确保数据处理逻辑与新接口完全一致
3. WHEN 旧接口调用时，THE Import_API SHALL 默认使用 INSERT_ONLY 策略；对 MAPPING_REQUIRED 记录（主数据无法解析）直接按 policy_decision=SKIP 处理，不阻塞整批导入
4. WHEN 旧接口调用时，THE Import_API SHALL 在响应中返回与现有 schema 兼容的结构（total、success_count、fail_count、failed_rows）；新增字段（如 request_id、warnings）作为可选字段附加，不影响现有前端解析逻辑
5. THE Import_API SHALL 确保旧接口响应中已有字段的含义和数据类型不发生变化（无破坏性变更）


### 需求 12：前端 Wizard 导入界面（Import_UI）

**用户故事：** 作为 IT 资产管理员，我希望通过直观的多步向导界面完成导入操作，以便在每个步骤清楚了解数据状态并在执行写库前做出有根据的决策。

#### 验收标准

1. THE Import_UI SHALL 在资产管理页面提供"批量导入"按钮，点击后弹出多步 Wizard 对话框（共四步：上传 → 预览 → 映射 → 结果）
2. THE Import_UI SHALL 在第一步（上传）提供文件选择区域，文件类型限制为 `.xlsx`，并提供"下载导入模板"链接；步骤指示器显示当前处于第一步
3. WHILE 文件上传和 Parse 处理进行中时，THE Import_UI SHALL 显示加载状态指示器，禁用上传按钮，防止重复提交
4. WHEN Parse 完成后，THE Import_UI SHALL 自动进入第二步（预览），展示分类汇总卡片（VALID / MAPPING_REQUIRED / DUPLICATE / ERROR 各分类数量）和逐行明细表格（行号、asset_tag、分类标签、错误原因或重复信息）
5. WHEN preview_summary.mapping_required 大于 0 时，THE Import_UI SHALL 显示第三步（映射）；第三步展示所有需要映射的原始值，为每条 MAPPING_REQUIRED 条目提供下拉选择器（从系统已有主数据中选择）或"跳过"选项
6. THE Import_UI SHALL 在第三步提供重复数据处理策略选择器（跳过 / 更新 / 替换），默认选中"跳过"；WHEN preview_summary.mapping_required 为 0 时，THE Import_UI SHALL 直接跳过映射步骤，从第二步进入第四步的确认界面
7. WHEN 第三步所有 MAPPING_REQUIRED 条目均已选择处理方式（map_existing 或 skip）且后端返回 ready_to_execute=True 时，THE Import_UI SHALL 激活"确认执行导入"按钮；WHILE 仍有未处理的 MAPPING_REQUIRED 条目时，该按钮保持禁用状态
8. WHEN 导入执行完成后，THE Import_UI SHALL 自动进入第四步（结果），展示 success_count、skip_count、fail_count，以及每条失败记录的行号、asset_tag 和失败原因
9. WHEN 导入成功且 success_count 大于 0 时，THE Import_UI SHALL 自动触发父组件的资产列表刷新回调，使新数据立即可见
10. THE Import_UI SHALL 在 Wizard 每一步显示"取消"按钮；WHEN 用户点击取消时，THE Import_UI SHALL 关闭对话框，重置本地状态（不需要调用后端删除 Session，Session 超时自动清理）


### 需求 13：导入模板下载

**用户故事：** 作为 IT 资产管理员，我希望能下载标准导入模板，以便按照正确的列头格式准备批量导入数据。

#### 验收标准

1. THE Import_API SHALL 保留 `GET /assets/import-template` 接口，返回 Content-Type 为 `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` 的 `.xlsx` 文件，文件名为"资产导入模板.xlsx"
2. THE Import_API SHALL 在模板第一行按 COLUMN_MAPPING 中定义的顺序输出所有中文列头（加粗、蓝色背景），列头数量与 excel_source.py 的 COLUMN_MAPPING 保持一致
3. THE Import_API SHALL 在模板第二行提供一行示例数据，asset_tag 示例值为"ZS-NB26-000001"，status 示例值为"闲置"，其余字段参考 `_TEMPLATE_EXAMPLE_ROW` 定义
4. THE Import_API SHALL 要求用户具有已认证的活跃用户身份才能下载模板；IF 未认证，THEN 返回 HTTP 401


### 需求 14：Pipeline 模块化与数据源扩展性

**用户故事：** 作为系统架构师，我希望 Pipeline 各层职责单一且通过数据接口解耦，以便未来新增 LDAP 或飞书等数据源时无需修改 Pipeline 内部逻辑。

#### 验收标准

1. THE Import_Pipeline SHALL 以 AssetRecord 列表作为各层之间的唯一数据传递格式；Normalizer、Resolver、Validator、Classifier 各层的方法签名中不得出现 ExcelSource 或任何具体数据源类型的引用
2. THE Import_Pipeline SHALL 通过构造函数依赖注入接受各层实例（source、normalizer、department_resolver、brand_resolver、location_resolver、validator、classifier），所有参数均有默认实现，可在测试中替换为 Mock 实现
3. THE Import_Pipeline SHALL 通过 ImportContext 向各层传递运行时依赖（db Session、current_user、import_policy、dry_run）；各层方法中不得从全局变量、模块级单例或 FastAPI Depends 直接获取这些依赖
4. THE Import_Pipeline 实例 SHALL 本身不持有任何请求级状态；同一 ImportPipeline 实例在两次并发调用中，使用不同的 ImportContext 实例时，两次调用的结果互不干扰
5. WHERE 未来需要接入新数据源时，THE 新数据源 SHALL 只需生成符合 AssetRecord 结构的列表（填充 row_number、source_filename、raw_fields、fields、extra_fields），即可接入现有 Pipeline，无需修改 Normalizer、Resolver、Validator、Classifier 或 Executor 中的任何代码

