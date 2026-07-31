---
inclusion: manual
---

# Import Domain Model 设计文档（修订版）

> **适用范围**：企业级导入模块重设计（import_v2）
> **版本**：Phase 0 修订版（含 Phase 1-3 说明）
> **最后更新**：2026-07

---

## 1. AssetRecord

采用"数据容器 + 元数据分离"结构。业务字段收进 `fields: dict`，Pipeline 框架只感知控制字段。

### 字段结构

```
AssetRecord
├─── 控制字段（强类型）
│     row_number: int
│     source_filename: str
│     classification: RecordClassification   # ERROR/DUPLICATE/MAPPING_REQUIRED/VALID
│     policy_decision: PolicyDecision?       # INSERT/UPDATE/REPLACE/SKIP
│     validation_errors: list[ValidationError]
│     resolver_issues: list[ResolverIssue]
│     duplicate_info: DuplicateInfo?
├─── raw_fields: dict   ← Source 填充，全程只读
├─── fields: dict       ← Normalizer 标准化后的业务字段
├─── extra_fields: dict ← 未知列，Executor 写入 additional_info
└─── resolved: ResolvedRefs
       department: DepartmentRef?  (id, name, parent_id)
       brand:      BrandRef?       (id, name)
       location:   LocationRef?    (id, name, location_type)
```

### 生命周期

```
ExcelSource  → 填充 raw_fields（只读）、fields、extra_fields
Normalizer   → 修改 fields（标准化）
Resolver     → 填充 resolved（Ref 对象，含 ID），批量 IN 查询
Validator    → 填充 validation_errors，含文件内去重
Classifier   → 填充 classification、duplicate_info，批量 IN 查询
ImportPolicy → 填充 policy_decision
Executor     → 读取写库，record 本身不再变化
```

---

## 2. ImportContext

Pipeline 运行时共享上下文，通过依赖注入传入各层。

| 字段 | 类型 | 用途 |
|---|---|---|
| `request_id` | `str` | UUID4，贯穿 Pipeline，写入所有日志，错误响应透传前端 |
| `db` | `Session` | 所有层共享同一 Session，保证事务范围 |
| `current_user` | `User` | 写日志时记录操作人 |
| `import_policy` | `ImportPolicy` | 封装重复处理策略 |
| `session_id` | `Optional[str]` | Wizard 多步流程时有值，旧接口单步为 None |
| `inferred_category` | `Optional[str]` | 从文件名推断的品类 |
| `dry_run` | `bool` | True 时不提交事务 |
| `operator_name` | `str` | full_name or username 缓存 |

工厂方法：`ImportContext.create(db, current_user, import_policy, ...)` 自动生成 request_id。

---

## 3. ImportSession

管理 Wizard 多步流程的中间状态，内存实现（单进程），TTL 30 分钟。

### 状态机

```
PARSED → MAPPING_APPLIED → EXECUTING → COMPLETED
                                   ↓（失败）
                              PARSED（允许重试）
```

### 保存内容

| 字段 | 填充时机 | 说明 |
|---|---|---|
| `session_id` | 创建时（UUID4） | 唯一标识 |
| `owner_user_id` | 创建时 | 安全校验 |
| `last_request_id` | 每次 API 调用更新 | 关联日志 |
| `source_filename` | Parse 阶段 | 审计用 |
| `parsed_records` | Parse 阶段 | AssetRecord 列表 |
| `preview_summary` | Parse 阶段 | 分类计数摘要 |
| `mapping` | Apply-Mapping 阶段 | 原始文本 → 标准值 |
| `duplicate_policy` | Mapping/Summary 阶段 | 重复处理策略 |
| `execute_result` | Execute 阶段 | 最终结果 |
| `created_at` | 创建时 | 创建时间 |
| `last_accessed_at` | 每次访问刷新 | 用于 TTL 计算 |
| `expire_at` | 创建时，TTL=30min | 过期时间 |
| `status` | 各阶段更新 | SessionStatus 枚举 |

**多 Worker 注意**：Session 存在于单进程内存。生产部署须 Uvicorn 单 worker，或切换 Redis 实现（预留扩展接口）。

---

## 4. ImportResult

Pipeline Execute 阶段返回的最终结果对象。

### 字段

**Summary**：`total_rows`, `inserted_count`, `updated_count`, `skipped_count`, `failed_count`, `dry_run`, `message`, `request_id`, `executed_at`

**Errors**（每条 `ImportErrorItem`）：`row_number`, `asset_tag`, `error_type`（FORMAT/VALIDATION/CONFLICT/SYSTEM）, `message`, `field`

**Warnings**（每条 `ImportWarningItem`）：`row_number`, `asset_tag`, `warning_type`（CATEGORY_INFERRED/EXTRA_COLUMNS/MAPPING_FALLBACK）, `message`

**Statistics**：`by_category: dict`, `by_status: dict`, `by_error_type: dict`, `warehouse_synced: list[WarehouseSyncEntry]`

---

## 5. 事务边界

### 事务内（原子性）

```
BEGIN TRANSACTION
  INSERT assets × N
  INSERT asset_logs × N
  UPDATE warehouse_assets × K   (WITH FOR UPDATE 行锁)
  INSERT warehouse_asset_logs × K
  INSERT operation_logs × 1
COMMIT / ROLLBACK
```

### 事务外

- Resolver / Classifier 的只读 SELECT
- ImportSession 内存状态更新
- Rollback 后的错误审计日志（独立新 Session 写入）

### Rollback 后错误日志

```python
# 主事务 rollback 后，用独立 Session 写错误日志（不受 rollback 影响）
with get_new_db_session() as audit_db:
    audit_db.add(OperationLog(
        action="import_failed",
        description=f"[{request_id}] 导入失败: {error}"
    ))
    audit_db.commit()
```

---

## 6. API 设计（新旧并存）

| 接口 | 模式 | 说明 |
|---|---|---|
| `POST /assets/import` | 旧接口（兼容） | 单步，parse_only + executor，保持不变 |
| `POST /assets/import/parse` | Wizard Step 1 | 返回 session_id + preview_summary |
| `POST /assets/import/apply-mapping` | Wizard Step 3 | 更新 Session 中的 mapping |
| `POST /assets/import/execute` | Wizard Step 6 | 正式写库，含完整事务 |
