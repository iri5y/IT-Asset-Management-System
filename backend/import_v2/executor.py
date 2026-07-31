"""Phase 6 导入执行器：在单一事务内执行资产、库存和审计写入。"""

from __future__ import annotations

import copy
import json
from typing import Any, Callable, Iterable

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
import schemas
from database import SessionLocal
from .domain_models import (
    AssetRecord,
    ImportContext,
    PolicyDecision,
    WarningType,
)
from .reporting import (
    apply_execution_counts,
    base_statistics,
    build_result_issues,
    decision_counts,
    error_type_for_skip,
    merge_warehouse_sync,
    skip_message,
    source_filenames,
    strategy_name,
    warehouse_sync_list,
)
from .sources.excel_source import COLUMN_MAPPING
from .validator import Validator


_IMPORT_FIELDS = frozenset(COLUMN_MAPPING.values()) | {"additional_info"}
_UNIQUE_NULLABLE_FIELDS = frozenset({"serial_number", "fixed_asset_number"})
_ASSET_TO_WAREHOUSE_CATEGORY = {
    "平板电脑": "移动设备",
    "台式机": "计算机设备",
    "笔记本电脑": "计算机设备",
    "显示器": "显示设备",
    "移动设备": "移动设备",
    "手机": "移动设备",
    "无线鼠标": "输入设备",
    "打印机": "其他配件",
    "网络设备": "网络设备",
}


class ImportExecutionError(RuntimeError):
    """主事务失败且已回滚；业务错误携带 HTTP 状态和逐行原因。"""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 500,
        issues: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.issues = issues or []


class Executor:
    """读取 ``policy_decision`` 并执行可独立测试的事务性写库。"""

    def __init__(
        self,
        audit_session_factory: Callable[[], Session] = SessionLocal,
        validator: Validator | None = None,
    ) -> None:
        self.audit_session_factory = audit_session_factory
        self.validator = validator or Validator()
    def execute(
        self,
        records: Iterable[AssetRecord],
        context: ImportContext,
    ) -> dict[str, Any]:
        """执行整批记录；报告只使用本批记录和本次真实执行结果。"""
        batch = list(records)
        strategy = strategy_name(context)
        decisions = decision_counts(batch)
        statistics = base_statistics(batch)
        warehouse_changes: dict[int, dict[str, Any]] = {}
        warehouse_warnings: list[dict[str, Any]] = []
        error_counts: dict[str, int] = {}
        for record in batch:
            if (record.policy_decision or PolicyDecision.SKIP) != PolicyDecision.SKIP:
                continue
            error_type = error_type_for_skip(record)
            if error_type:
                error_counts[error_type] = error_counts.get(error_type, 0) + 1
        statistics["by_error_type"] = dict(sorted(error_counts.items()))

        actionable = [
            record
            for record in batch
            if (record.policy_decision or PolicyDecision.SKIP) != PolicyDecision.SKIP
        ]
        skip_count = len(batch) - len(actionable)
        audit_user_id = context.current_user.id

        current_record: AssetRecord | None = None
        try:
            self._revalidate(actionable)
            self._check_intra_batch_unique_conflicts(actionable)
            details: list[dict[str, Any]] = []
            operation_counts = {
                PolicyDecision.INSERT: 0,
                PolicyDecision.UPDATE: 0,
                PolicyDecision.REPLACE: 0,
            }

            for record in batch:
                decision = record.policy_decision or PolicyDecision.SKIP
                if decision == PolicyDecision.SKIP:
                    details.append(self._result_row(
                        record,
                        decision,
                        "SKIPPED",
                        skip_message(record, strategy),
                        error_type_for_skip(record),
                    ))
                    continue

                current_record = record
                asset_data, provided_fields = self._prepare_asset_data(record)
                if decision == PolicyDecision.INSERT:
                    asset = self._insert(
                        record,
                        asset_data,
                        context,
                        warehouse_changes,
                        warehouse_warnings,
                    )
                elif decision == PolicyDecision.UPDATE:
                    asset = self._update(
                        record,
                        asset_data,
                        provided_fields,
                        context,
                        warehouse_changes,
                        warehouse_warnings,
                    )
                elif decision == PolicyDecision.REPLACE:
                    asset = self._replace(
                        record,
                        asset_data,
                        context,
                        warehouse_changes,
                        warehouse_warnings,
                    )
                else:
                    raise ValueError(f"不支持的导入决策: {decision}")

                self._add_asset_log(asset, decision, context)
                operation_counts[decision] += 1
                message = (
                    "干运行验证通过（所有变更已回滚）"
                    if context.dry_run
                    else "导入成功"
                )
                details.append(
                    self._result_row(record, decision, "SUCCESS", message)
                )

            inserted_count = operation_counts[PolicyDecision.INSERT]
            updated_count = operation_counts[PolicyDecision.UPDATE]
            replaced_count = operation_counts[PolicyDecision.REPLACE]
            success_count = inserted_count + updated_count + replaced_count
            apply_execution_counts(
                statistics,
                inserted=inserted_count,
                updated=updated_count,
                replaced=replaced_count,
                skipped=skip_count,
                failed=0,
            )
            statistics["warehouse_synced"] = warehouse_sync_list(
                warehouse_changes,
                dry_run=context.dry_run,
            )
            errors, warnings = build_result_issues(
                batch,
                strategy,
                context.request_id,
            )
            warnings.extend(warehouse_warnings)
            result = {
                "success_count": success_count,
                "fail_count": 0,
                "skip_count": skip_count,
                "dry_run": context.dry_run,
                "records": details,
                "total_rows": len(batch),
                "inserted_count": inserted_count,
                "updated_count": updated_count,
                "replaced_count": replaced_count,
                "skipped_count": skip_count,
                "failed_count": 0,
                "message": (
                    f"处理 {len(batch)} 行：成功 {success_count} 行，"
                    f"跳过 {skip_count} 行，失败 0 行"
                ),
                "request_id": context.request_id,
                "session_id": context.session_id,
                "strategy": strategy,
                "source_filenames": source_filenames(batch),
                "executed_at": models.china_now().isoformat(),
                "errors": errors,
                "warnings": warnings,
                "statistics": statistics,
            }
            audit_payload = self._build_audit_payload(
                context, result, decisions, rolled_back=False
            )
            self._add_operation_log(context, audit_payload)
            context.db.flush()
            if context.dry_run:
                context.db.rollback()
            else:
                context.db.commit()
            return result
        except Exception as exc:
            if isinstance(exc, ImportExecutionError):
                execution_error = exc
            elif isinstance(exc, ValidationError):
                issues = [
                    {
                        "row_number": current_record.row_number if current_record else 0,
                        "field": ".".join(str(part) for part in error.get("loc", ())) or "记录",
                        "reason": str(error.get("msg", "业务校验失败")).removeprefix("Value error, "),
                    }
                    for error in exc.errors()
                ]
                execution_error = ImportExecutionError(
                    "导入数据未通过业务校验", status_code=400, issues=issues
                )
            elif isinstance(exc, IntegrityError):
                message = str(exc.orig).lower()
                field = next(
                    (
                        label
                        for key, label in (
                            ("serial_number", "序列号"),
                            ("fixed_asset_number", "固定资产编号"),
                            ("asset_tag", "资产编号"),
                        )
                        if key in message
                    ),
                    "唯一字段",
                )
                execution_error = ImportExecutionError(
                    "导入数据存在唯一性冲突",
                    status_code=409,
                    issues=[{
                        "row_number": current_record.row_number if current_record else 0,
                        "field": field,
                        "reason": f"{field}已存在或在本批次中重复",
                    }],
                )
            elif isinstance(exc, ValueError):
                execution_error = ImportExecutionError(
                    "导入业务规则校验失败",
                    status_code=400,
                    issues=[{
                        "row_number": current_record.row_number if current_record else 0,
                        "field": "记录",
                        "reason": str(exc),
                    }],
                )
            else:
                execution_error = ImportExecutionError(
                    "数据库写入失败，事务已回滚，请使用请求 ID 联系管理员"
                )

            context.db.rollback()
            apply_execution_counts(
                statistics,
                inserted=0,
                updated=0,
                replaced=0,
                skipped=skip_count,
                failed=len(actionable),
            )
            statistics["warehouse_synced"] = warehouse_sync_list(
                warehouse_changes,
                dry_run=context.dry_run,
                rolled_back=True,
            )
            self._write_failure_audit(
                context,
                execution_error,
                user_id=audit_user_id,
                affected_count=len(actionable),
                skip_count=skip_count,
                total_rows=len(batch),
                decisions=decisions,
                statistics=statistics,
                sources=source_filenames(batch),
            )
            if execution_error is exc:
                raise
            raise execution_error from exc

    def _revalidate(self, records: list[AssetRecord]) -> None:
        """在写库前重新运行无数据库业务校验并返回逐行、逐字段错误。"""
        probes = copy.deepcopy(records)
        for probe in probes:
            probe.validation_errors = []
        self.validator.validate_batch(probes)
        issues = [
            {
                "row_number": probe.row_number,
                "field": error.field,
                "reason": error.message,
            }
            for probe in probes
            for error in probe.validation_errors
        ]
        if issues:
            raise ImportExecutionError(
                "执行前业务校验失败", status_code=400, issues=issues
            )

    @staticmethod
    def _check_intra_batch_unique_conflicts(records: list[AssetRecord]) -> None:
        """防止 preview 后被篡改的批次把唯一性冲突推迟到数据库。"""
        unique_fields = (
            ("asset_tag", "资产编号"),
            ("serial_number", "序列号"),
            ("fixed_asset_number", "固定资产编号"),
        )
        issues: list[dict[str, Any]] = []
        for field_name, label in unique_fields:
            seen: dict[str, int] = {}
            for record in records:
                value = record.fields.get(field_name)
                if value in (None, ""):
                    continue
                normalized = str(value).strip().upper()
                if normalized in seen:
                    issues.append({
                        "row_number": record.row_number,
                        "field": label,
                        "reason": (
                            f"{label}「{value}」在导入文件中重复，"
                            f"首次出现于第 {seen[normalized]} 行"
                        ),
                    })
                else:
                    seen[normalized] = record.row_number
        if issues:
            raise ImportExecutionError(
                "导入数据存在唯一性冲突", status_code=409, issues=issues
            )

    def _prepare_asset_data(
        self,
        record: AssetRecord,
    ) -> tuple[dict[str, Any], set[str]]:
        """使用 Resolver 已提供的名称构建 ORM 数据，不重新查询主数据。"""
        raw_data = {
            key: value for key, value in record.fields.items() if key in _IMPORT_FIELDS
        }
        if record.resolved.department is not None:
            raw_data["department"] = record.resolved.department.name
        if record.resolved.brand is not None:
            raw_data["brand"] = record.resolved.brand.name
        if record.resolved.location is not None:
            raw_data["location"] = record.resolved.location.name
        if record.extra_fields:
            raw_data["additional_info"] = {
                **(raw_data.get("additional_info") or {}),
                **record.extra_fields,
            }

        provided_fields = set(raw_data)
        validated = schemas.AssetCreate(**raw_data).model_dump()
        for field_name in _UNIQUE_NULLABLE_FIELDS:
            if not validated.get(field_name):
                validated[field_name] = None
        return validated, provided_fields
    def _insert(
        self,
        record: AssetRecord,
        asset_data: dict[str, Any],
        context: ImportContext,
        warehouse_changes: dict[int, dict[str, Any]],
        warehouse_warnings: list[dict[str, Any]],
    ) -> models.Asset:
        asset = models.Asset(**asset_data)
        context.db.add(asset)
        context.db.flush()
        if asset.status == "闲置":
            self._adjust_inventory(
                context.db,
                asset.category,
                1,
                context.operator_name,
                warehouse_changes,
                warehouse_warnings,
                record,
            )
        return asset

    def _load_duplicate_target(
        self,
        record: AssetRecord,
        db: Session,
    ) -> models.Asset:
        if record.duplicate_info is None or record.duplicate_info.asset_id is None:
            raise ValueError(f"第 {record.row_number} 行缺少数据库重复资产定位信息")
        target = db.get(models.Asset, record.duplicate_info.asset_id)
        if target is None or target.is_deleted:
            raise ValueError(
                f"冲突资产 ID {record.duplicate_info.asset_id} 不存在或已删除"
            )
        return target

    def _update(
        self,
        record: AssetRecord,
        asset_data: dict[str, Any],
        provided_fields: set[str],
        context: ImportContext,
        warehouse_changes: dict[int, dict[str, Any]],
        warehouse_warnings: list[dict[str, Any]],
    ) -> models.Asset:
        asset = self._load_duplicate_target(record, context.db)
        old_status, old_category = asset.status, asset.category
        update_fields = (provided_fields & _IMPORT_FIELDS) - {"asset_tag"}
        for field_name in update_fields:
            setattr(asset, field_name, asset_data[field_name])
        context.db.flush()
        self._sync_inventory_transition(
            context.db,
            old_status,
            old_category,
            asset.status,
            asset.category,
            context.operator_name,
            warehouse_changes,
            warehouse_warnings,
            record,
        )
        return asset

    def _replace(
        self,
        record: AssetRecord,
        asset_data: dict[str, Any],
        context: ImportContext,
        warehouse_changes: dict[int, dict[str, Any]],
        warehouse_warnings: list[dict[str, Any]],
    ) -> models.Asset:
        """原地完整覆盖导入字段，保留主键及现有外键关联。"""
        asset = self._load_duplicate_target(record, context.db)
        old_status, old_category = asset.status, asset.category
        for field_name in _IMPORT_FIELDS:
            setattr(asset, field_name, asset_data.get(field_name))
        context.db.flush()
        self._sync_inventory_transition(
            context.db,
            old_status,
            old_category,
            asset.status,
            asset.category,
            context.operator_name,
            warehouse_changes,
            warehouse_warnings,
            record,
        )
        return asset

    def _sync_inventory_transition(
        self,
        db: Session,
        old_status: str,
        old_category: str,
        new_status: str,
        new_category: str,
        operator_name: str,
        warehouse_changes: dict[int, dict[str, Any]],
        warehouse_warnings: list[dict[str, Any]],
        record: AssetRecord,
    ) -> None:
        old_idle = old_status == "闲置"
        new_idle = new_status == "闲置"
        old_warehouse = self._warehouse_category(old_category)
        new_warehouse = self._warehouse_category(new_category)
        if old_idle and new_idle and old_warehouse == new_warehouse:
            return
        if old_idle:
            self._adjust_inventory(
                db,
                old_category,
                -1,
                operator_name,
                warehouse_changes,
                warehouse_warnings,
                record,
            )
        if new_idle:
            self._adjust_inventory(
                db,
                new_category,
                1,
                operator_name,
                warehouse_changes,
                warehouse_warnings,
                record,
            )

    @staticmethod
    def _warehouse_category(category: str) -> str:
        return _ASSET_TO_WAREHOUSE_CATEGORY.get(category, category)

    def _adjust_inventory(
        self,
        db: Session,
        category: str,
        delta: int,
        operator_name: str,
        warehouse_changes: dict[int, dict[str, Any]],
        warehouse_warnings: list[dict[str, Any]],
        record: AssetRecord,
    ) -> None:
        warehouse_category = self._warehouse_category(category)
        statement = (
            select(models.WarehouseAsset)
            .where(models.WarehouseAsset.category == warehouse_category)
            .order_by(
                models.WarehouseAsset.available_quantity.desc(),
                models.WarehouseAsset.id.asc(),
            )
            .with_for_update()
        )
        warehouse_asset = db.execute(statement).scalars().first()
        if warehouse_asset is None:
            warehouse_warnings.append({
                "row_number": record.row_number,
                "asset_tag": record.fields.get("asset_tag"),
                "warning_type": WarningType.WAREHOUSE_NOT_FOUND.value,
                "message": (
                    f"未找到品类「{warehouse_category}」的库存条目，"
                    "资产处理继续，未同步库存"
                ),
            })
            return

        old_available = warehouse_asset.available_quantity or 0
        old_allocated = warehouse_asset.allocated_quantity or 0
        warehouse_asset.available_quantity = max(0, old_available + delta)
        warehouse_asset.allocated_quantity = max(
            0,
            (warehouse_asset.total_quantity or 0)
            - warehouse_asset.available_quantity,
        )
        db.flush()
        merge_warehouse_sync(
            warehouse_changes,
            warehouse_asset,
            warehouse_category,
            old_available,
            warehouse_asset.available_quantity,
            old_allocated,
            warehouse_asset.allocated_quantity,
        )
        db.add(models.WarehouseAssetLog(
            asset_id=warehouse_asset.id,
            action="批量导入库存同步",
            description=(
                f"可用数量 {old_available} → {warehouse_asset.available_quantity}，"
                f"已分配 {old_allocated} → {warehouse_asset.allocated_quantity}"
            ),
            operator=operator_name,
        ))

    @staticmethod
    def _add_asset_log(
        asset: models.Asset,
        decision: PolicyDecision,
        context: ImportContext,
    ) -> None:
        context.db.add(models.AssetLog(
            asset_id=asset.id,
            action="批量导入",
            description=f"{decision.value}: {asset.asset_tag}",
            operator=context.operator_name,
        ))

    @staticmethod
    def _warehouse_sync_summary(statistics: dict[str, Any]) -> dict[str, int]:
        entries = statistics.get("warehouse_synced", [])
        return {
            "item_count": len(entries),
            "net_available_delta": sum(item.get("delta", 0) for item in entries),
            "committed_count": sum(bool(item.get("committed")) for item in entries),
        }

    @classmethod
    def _build_audit_payload(
        cls,
        context: ImportContext,
        result: dict[str, Any],
        decisions: dict[str, int],
        rolled_back: bool,
    ) -> dict[str, Any]:
        """构建与 ORM 字段解耦的可序列化审计摘要。"""
        sources = result["source_filenames"]
        return {
            "request_id": context.request_id,
            "session_id": context.session_id,
            "source_filename": sources[0] if sources else None,
            "source_filenames": sources,
            "operator_name": context.operator_name,
            # operator 保留给已读取 Phase 7 早期审计的工具兼容使用。
            "operator": context.operator_name,
            "strategy": result["strategy"],
            "dry_run": context.dry_run,
            "total": result["total_rows"],
            "success": result["success_count"],
            "skip": result["skip_count"],
            "fail": result["fail_count"],
            "total_rows": result["total_rows"],
            "success_count": result["success_count"],
            "skip_count": result["skip_count"],
            "fail_count": result["fail_count"],
            "inserted_count": result["inserted_count"],
            "updated_count": result["updated_count"],
            "replaced_count": result["replaced_count"],
            "decision_counts": decisions,
            "warehouse_sync_summary": cls._warehouse_sync_summary(
                result["statistics"]
            ),
            "statistics": result["statistics"],
            "rolled_back": rolled_back,
        }

    @staticmethod
    def _add_operation_log(
        context: ImportContext,
        payload: dict[str, Any],
    ) -> None:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        context.db.add(models.OperationLog(
            user_id=context.current_user.id,
            action="import",
            resource_type="asset",
            description=(
                f"[{context.request_id}] 批量导入资产；操作人: "
                f"{context.operator_name}；success={payload['success_count']}, "
                f"skip={payload['skip_count']}, fail={payload['fail_count']}；"
                f"审计摘要: {serialized}"
            ),
            new_value=serialized,
        ))

    def _write_failure_audit(
        self,
        context: ImportContext,
        error: Exception,
        user_id: int,
        affected_count: int,
        skip_count: int,
        total_rows: int,
        decisions: dict[str, int],
        statistics: dict[str, Any],
        sources: list[str],
    ) -> None:
        """主事务回滚后使用完全独立的 Session 持久化失败审计。"""
        audit_db: Session | None = None
        try:
            audit_db = self.audit_session_factory()
            failed_statistics = copy.deepcopy(statistics)
            error_counts = dict(failed_statistics.get("by_error_type", {}))
            error_counts["SYSTEM"] = error_counts.get("SYSTEM", 0) + affected_count
            failed_statistics["by_error_type"] = dict(sorted(error_counts.items()))
            failed_statistics["warehouse_synced"] = [
                {**entry, "rolled_back": True}
                for entry in failed_statistics.get("warehouse_synced", [])
            ]
            payload = {
                "request_id": context.request_id,
                "session_id": context.session_id,
                "source_filename": sources[0] if sources else None,
                "source_filenames": sources,
                "operator_name": context.operator_name,
                "operator": context.operator_name,
                "strategy": strategy_name(context),
                "dry_run": context.dry_run,
                "total": total_rows,
                "success": 0,
                "skip": skip_count,
                "fail": affected_count,
                "total_rows": total_rows,
                "success_count": 0,
                "skip_count": skip_count,
                "fail_count": affected_count,
                "inserted_count": 0,
                "updated_count": 0,
                "replaced_count": 0,
                "decision_counts": decisions,
                "warehouse_sync_summary": self._warehouse_sync_summary(
                    failed_statistics
                ),
                "statistics": failed_statistics,
                "rolled_back": True,
                "reason": str(error),
            }
            serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            audit_db.add(models.OperationLog(
                user_id=user_id,
                action="import_failed",
                resource_type="asset",
                description=(
                    f"[{context.request_id}] 批量导入资产失败；操作人: "
                    f"{context.operator_name}；策略: {payload['strategy']}；"
                    f"影响行数: {affected_count}；原因: {error}；"
                    f"审计摘要: {serialized}"
                ),
                new_value=serialized,
            ))
            audit_db.commit()
        except Exception:
            if audit_db is not None:
                try:
                    audit_db.rollback()
                except Exception:
                    pass
        finally:
            if audit_db is not None:
                audit_db.close()

    @staticmethod
    def _result_row(
        record: AssetRecord,
        decision: PolicyDecision,
        status: str,
        message: str,
        error_type: str | None = None,
    ) -> dict[str, Any]:
        return {
            "row_number": record.row_number,
            "asset_tag": record.fields.get("asset_tag"),
            "decision": decision.value,
            "status": status,
            "message": message,
            "category": record.fields.get("category"),
            "asset_status": record.fields.get("status"),
            "error_type": error_type,
        }
