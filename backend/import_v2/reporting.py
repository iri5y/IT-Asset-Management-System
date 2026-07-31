"""Phase 7 导入结果统计与逐行说明工具。"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from .domain_models import (
    AssetRecord,
    ErrorType,
    PolicyDecision,
    RecordClassification,
    WarningType,
)


_EMPTY_LABEL = "未填写"


def strategy_name(context: Any) -> str:
    """安全读取当前策略名称，兼容测试中注入的自定义策略。"""
    policy_type = getattr(getattr(context, "import_policy", None), "policy_type", None)
    return getattr(policy_type, "value", str(policy_type or "UNKNOWN"))


def source_filenames(records: Iterable[AssetRecord]) -> list[str]:
    """返回稳定排序且去重后的来源文件列表。"""
    return sorted({record.source_filename for record in records if record.source_filename})


def decision_counts(records: Iterable[AssetRecord]) -> dict[str, int]:
    """统计本批策略决策，始终返回四个固定键。"""
    counts = {decision.value: 0 for decision in PolicyDecision}
    for record in records:
        decision = record.policy_decision or PolicyDecision.SKIP
        counts[decision.value] += 1
    return counts


def _field_distribution(
    records: Iterable[AssetRecord],
    field_name: str,
) -> dict[str, int]:
    counts = Counter(
        str(record.fields.get(field_name) or _EMPTY_LABEL)
        for record in records
    )
    return dict(sorted(counts.items()))


def base_statistics(records: Iterable[AssetRecord]) -> dict[str, Any]:
    """从本批 AssetRecord 生成可序列化基础统计，不访问数据库。"""
    batch = list(records)
    decisions = decision_counts(batch)
    return {
        "total_rows": len(batch),
        # decision_counts 为 Phase 7 早期字段；by_decision 是对外语义更清晰的别名。
        "decision_counts": dict(decisions),
        "by_decision": dict(decisions),
        "inserted_count": 0,
        "updated_count": 0,
        "replaced_count": 0,
        "skipped_count": decisions[PolicyDecision.SKIP.value],
        "failed_count": 0,
        "by_category": _field_distribution(batch, "category"),
        "by_status": _field_distribution(batch, "status"),
        "by_error_type": {},
        "warehouse_synced": [],
    }


def apply_execution_counts(
    statistics: dict[str, Any],
    *,
    inserted: int,
    updated: int,
    replaced: int,
    skipped: int,
    failed: int,
) -> None:
    """把真实执行数量写回统计对象，区分计划决策和最终执行。"""
    statistics.update({
        "inserted_count": inserted,
        "updated_count": updated,
        "replaced_count": replaced,
        "skipped_count": skipped,
        "failed_count": failed,
    })


def error_type_for_skip(record: AssetRecord) -> str | None:
    """按实际跳过原因归类错误类型，每行只计入一个确定类型。"""
    if record.classification == RecordClassification.DUPLICATE:
        return ErrorType.CONFLICT.value
    if record.validation_errors:
        if any("格式" in error.message for error in record.validation_errors):
            return ErrorType.FORMAT.value
        return ErrorType.VALIDATION.value
    if record.classification == RecordClassification.MAPPING_REQUIRED:
        return ErrorType.MAPPING.value
    return None


def skip_message(record: AssetRecord, strategy: str) -> str:
    """为不同跳过来源生成准确、可面向用户展示的中文说明。"""
    if record.classification == RecordClassification.ERROR:
        messages = "；".join(error.message for error in record.validation_errors)
        return f"数据校验失败：{messages or '存在未说明的校验错误'}"
    if record.classification == RecordClassification.MAPPING_REQUIRED:
        issues = "；".join(
            f"{issue.field}「{issue.raw_value}」({issue.issue_type.value})"
            for issue in record.resolver_issues
        )
        return f"主数据待映射，已跳过：{issues or '存在未完成的映射'}"
    if record.classification == RecordClassification.DUPLICATE:
        conflict = record.duplicate_info
        detail = (
            f"，冲突字段 {conflict.conflict_field}，现有资产 {conflict.asset_tag}"
            if conflict is not None
            else ""
        )
        return f"重复数据按 {strategy} 策略跳过{detail}"
    return f"按 {strategy} 策略跳过"


def build_result_issues(
    records: Iterable[AssetRecord],
    strategy: str,
    request_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """生成逐行错误和警告；records 明细仍作为兼容主数据源保留。"""
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for record in records:
        asset_tag = record.fields.get("asset_tag")
        decision = record.policy_decision or PolicyDecision.SKIP
        if record.extra_fields:
            warnings.append({
                "row_number": record.row_number,
                "asset_tag": asset_tag,
                "warning_type": "EXTRA_COLUMNS",
                "message": "存在未知列，已保存到资产附加信息",
            })
        if decision != PolicyDecision.SKIP:
            continue

        message = skip_message(record, strategy)
        error_type = error_type_for_skip(record)
        if record.classification in {
            RecordClassification.ERROR,
            RecordClassification.MAPPING_REQUIRED,
        }:
            field_name = None
            if record.validation_errors:
                field_name = record.validation_errors[0].field
            elif record.resolver_issues:
                field_name = record.resolver_issues[0].field
            errors.append({
                "row_number": record.row_number,
                "asset_tag": asset_tag,
                "error_type": error_type or ErrorType.VALIDATION.value,
                "message": message,
                "field": field_name,
                "request_id": request_id,
            })
        else:
            warnings.append({
                "row_number": record.row_number,
                "asset_tag": asset_tag,
                "warning_type": (
                    error_type
                    if error_type == ErrorType.CONFLICT.value
                    else WarningType.POLICY_SKIP.value
                ),
                "message": message,
            })
    return errors, warnings


def merge_warehouse_sync(
    changes: dict[int, dict[str, Any]],
    warehouse_asset: Any,
    mapped_category: str,
    before_available: int,
    after_available: int,
    before_allocated: int,
    after_allocated: int,
) -> None:
    """按库存对象聚合同批多次变化，保留首次前值和最终后值。"""
    entry = changes.get(warehouse_asset.id)
    if entry is None:
        entry = {
            "warehouse_asset_id": warehouse_asset.id,
            "warehouse_asset_name": warehouse_asset.name,
            "warehouse_category": mapped_category,
            "before_available": before_available,
            "after_available": after_available,
            "before_allocated": before_allocated,
            "after_allocated": after_allocated,
            "delta": after_available - before_available,
        }
        changes[warehouse_asset.id] = entry
        return
    entry["after_available"] = after_available
    entry["after_allocated"] = after_allocated
    entry["delta"] = after_available - entry["before_available"]


def warehouse_sync_list(
    changes: dict[int, dict[str, Any]],
    *,
    dry_run: bool,
    rolled_back: bool = False,
) -> list[dict[str, Any]]:
    """按库存主键输出确定性明细，并明确本次变化是否真正提交。"""
    committed = not dry_run and not rolled_back
    return [
        {
            **changes[key],
            "committed": committed,
            "dry_run": dry_run,
            "rolled_back": rolled_back,
        }
        for key in sorted(changes)
    ]
