"""仓储两级分类目录、有效组合及迁移问题的领域服务。"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

import models
from category_policy import IssuePolicy, allowed_issue_policies, require_issue_policy
from transaction_audit import DomainTransactionError, domain_transaction, snapshot


class WarehouseCategoryServiceError(ValueError):
    """仓储分类领域校验失败时返回的中文错误。"""


class WarehouseCategoryNotFoundError(WarehouseCategoryServiceError):
    """一级、二级分类或迁移问题不存在。"""


class WarehouseCategoryConflictError(WarehouseCategoryServiceError):
    """目录唯一性、引用或状态冲突。"""


class WarehouseCategoryPendingError(WarehouseCategoryConflictError):
    """待迁移记录不可作为活动物料处理。"""


def validate_active_category_pair(
    db: Session,
    primary_category_id: int,
    secondary_category_id: int,
) -> tuple[models.WarehousePrimaryCategory, models.WarehouseSecondaryCategory]:
    """校验一级/二级存在、启用且具备正确从属关系。"""
    primary = db.query(models.WarehousePrimaryCategory).filter(
        models.WarehousePrimaryCategory.id == primary_category_id
    ).one_or_none()
    if primary is None:
        raise WarehouseCategoryNotFoundError("一级分类不存在")

    secondary = db.query(models.WarehouseSecondaryCategory).filter(
        models.WarehouseSecondaryCategory.id == secondary_category_id
    ).one_or_none()
    if secondary is None:
        raise WarehouseCategoryNotFoundError("二级分类不存在")
    if secondary.primary_category_id != primary.id:
        raise WarehouseCategoryServiceError("二级分类不隶属于所选一级分类")
    if primary.is_active is not True:
        raise WarehouseCategoryServiceError("一级分类已停用")
    if secondary.is_active is not True:
        raise WarehouseCategoryServiceError("二级分类已停用")
    return primary, secondary


def list_category_tree(
    db: Session,
    *,
    include_inactive: bool = False,
) -> list[dict[str, Any]]:
    """按排序返回目录树；默认只暴露可供选择的启用项。"""
    query = db.query(models.WarehousePrimaryCategory)
    if not include_inactive:
        query = query.filter(models.WarehousePrimaryCategory.is_active.is_(True))
    categories = query.order_by(
        models.WarehousePrimaryCategory.sort_order,
        models.WarehousePrimaryCategory.id,
    ).all()
    result: list[dict[str, Any]] = []
    for primary in categories:
        secondary_query = db.query(models.WarehouseSecondaryCategory).filter(
            models.WarehouseSecondaryCategory.primary_category_id == primary.id
        )
        if not include_inactive:
            secondary_query = secondary_query.filter(
                models.WarehouseSecondaryCategory.is_active.is_(True)
            )
        result.append({
            "id": primary.id,
            "code": primary.code,
            "name": primary.name,
            "is_active": primary.is_active,
            "sort_order": primary.sort_order,
            "created_at": primary.created_at,
            "updated_at": primary.updated_at,
            "secondary_categories": secondary_query.order_by(
                models.WarehouseSecondaryCategory.sort_order,
                models.WarehouseSecondaryCategory.id,
            ).all(),
        })
    return result


def list_active_primary_categories(
    db: Session,
) -> list[models.WarehousePrimaryCategory]:
    return (
        db.query(models.WarehousePrimaryCategory)
        .filter(models.WarehousePrimaryCategory.is_active.is_(True))
        .order_by(
            models.WarehousePrimaryCategory.sort_order,
            models.WarehousePrimaryCategory.id,
        )
        .all()
    )


def list_active_secondary_categories(
    db: Session,
    primary_category_id: int,
) -> list[models.WarehouseSecondaryCategory]:
    primary = db.query(models.WarehousePrimaryCategory).filter(
        models.WarehousePrimaryCategory.id == primary_category_id
    ).one_or_none()
    if primary is None:
        raise WarehouseCategoryNotFoundError("一级分类不存在")
    if primary.is_active is not True:
        raise WarehouseCategoryServiceError("一级分类已停用")
    return (
        db.query(models.WarehouseSecondaryCategory)
        .filter(
            models.WarehouseSecondaryCategory.primary_category_id == primary.id,
            models.WarehouseSecondaryCategory.is_active.is_(True),
        )
        .order_by(
            models.WarehouseSecondaryCategory.sort_order,
            models.WarehouseSecondaryCategory.id,
        )
        .all()
    )


def create_primary_category(
    db: Session,
    *,
    code: str,
    name: str,
    sort_order: int,
    operator_id: int,
) -> tuple[models.WarehousePrimaryCategory, models.OperationLog]:
    """新增一级分类并在同一事务内记录分类审计。"""
    _require_operator_id(operator_id)
    _assert_primary_identity_available(db, code=code, name=name)
    with domain_transaction(db) as transaction:
        _lock_active_operator(transaction, operator_id)
        category = models.WarehousePrimaryCategory(
            code=code,
            name=name,
            sort_order=sort_order,
            is_active=True,
        )
        db.add(category)
        transaction.flush()
        audit = _record_category_audit(
            transaction,
            operator_id=operator_id,
            action="create_warehouse_primary_category",
            category_level="PRIMARY",
            category=category,
            before=None,
            after=snapshot(category),
        )
    return category, audit


def update_primary_category(
    db: Session,
    primary_category_id: int,
    *,
    changes: dict[str, Any],
    operator_id: int,
) -> tuple[models.WarehousePrimaryCategory, models.OperationLog]:
    """改名、排序或启停一级分类；被引用项不能停用。"""
    _require_operator_id(operator_id)
    update_values = _supported_changes(
        changes, {"code", "name", "sort_order", "is_active"}
    )
    with domain_transaction(db) as transaction:
        _lock_active_operator(transaction, operator_id)
        category = transaction.lock_one(
            models.WarehousePrimaryCategory, primary_category_id
        )
        if category is None:
            raise WarehouseCategoryNotFoundError("一级分类不存在")
        before = snapshot(category)
        _assert_primary_identity_available(
            db,
            code=update_values.get("code", category.code),
            name=update_values.get("name", category.name),
            excluding_id=category.id,
        )
        if update_values.get("is_active") is False and category.is_active is True:
            _ensure_primary_can_be_deactivated(db, category.id)
        for field, value in update_values.items():
            setattr(category, field, value)
        transaction.flush()
        audit = _record_category_audit(
            transaction,
            operator_id=operator_id,
            action="update_warehouse_primary_category",
            category_level="PRIMARY",
            category=category,
            before=before,
            after=snapshot(category),
        )
    return category, audit


def create_secondary_category(
    db: Session,
    *,
    primary_category_id: int,
    code: str,
    name: str,
    sort_order: int,
    operator_id: int,
) -> tuple[models.WarehouseSecondaryCategory, models.OperationLog]:
    """在启用一级分类下新增二级分类。"""
    _require_operator_id(operator_id)
    with domain_transaction(db) as transaction:
        _lock_active_operator(transaction, operator_id)
        primary = transaction.lock_one(
            models.WarehousePrimaryCategory, primary_category_id
        )
        if primary is None:
            raise WarehouseCategoryNotFoundError("一级分类不存在")
        if primary.is_active is not True:
            raise WarehouseCategoryServiceError("一级分类已停用，不能新增二级分类")
        _assert_secondary_identity_available(
            db, primary_category_id=primary.id, code=code, name=name
        )
        category = models.WarehouseSecondaryCategory(
            primary_category_id=primary.id,
            code=code,
            name=name,
            sort_order=sort_order,
            is_active=True,
        )
        db.add(category)
        transaction.flush()
        audit = _record_category_audit(
            transaction,
            operator_id=operator_id,
            action="create_warehouse_secondary_category",
            category_level="SECONDARY",
            category=category,
            before=None,
            after=snapshot(category),
        )
    return category, audit


def update_secondary_category(
    db: Session,
    secondary_category_id: int,
    *,
    changes: dict[str, Any],
    operator_id: int,
) -> tuple[models.WarehouseSecondaryCategory, models.OperationLog]:
    """改名、排序或启停二级分类，明确禁止直接修改父级。"""
    _require_operator_id(operator_id)
    if "primary_category_id" in changes:
        raise WarehouseCategoryConflictError(
            "二级分类不允许直接更换一级分类，请新建二级分类后迁移引用"
        )
    update_values = _supported_changes(changes, {"code", "name", "sort_order", "is_active"})
    with domain_transaction(db) as transaction:
        _lock_active_operator(transaction, operator_id)
        category = transaction.lock_one(
            models.WarehouseSecondaryCategory, secondary_category_id
        )
        if category is None:
            raise WarehouseCategoryNotFoundError("二级分类不存在")
        before = snapshot(category)
        _assert_secondary_identity_available(
            db,
            primary_category_id=category.primary_category_id,
            code=update_values.get("code", category.code),
            name=update_values.get("name", category.name),
            excluding_id=category.id,
        )
        if update_values.get("is_active") is False and category.is_active is True:
            _ensure_secondary_can_be_deactivated(db, category.id)
        if update_values.get("is_active") is True:
            parent = db.query(models.WarehousePrimaryCategory).filter(
                models.WarehousePrimaryCategory.id == category.primary_category_id
            ).one_or_none()
            if parent is None or parent.is_active is not True:
                raise WarehouseCategoryServiceError("所属一级分类已停用，不能启用二级分类")
        for field, value in update_values.items():
            setattr(category, field, value)
        transaction.flush()
        audit = _record_category_audit(
            transaction,
            operator_id=operator_id,
            action="update_warehouse_secondary_category",
            category_level="SECONDARY",
            category=category,
            before=before,
            after=snapshot(category),
        )
    return category, audit


def migrate_secondary_references(
    db: Session,
    source_secondary_category_id: int,
    *,
    target_primary_category_id: int,
    target_secondary_category_id: int,
    operator_id: int,
) -> tuple[int, models.OperationLog]:
    """受控迁移活动物料引用，供新建替代二级分类后的维护流程使用。"""
    _require_operator_id(operator_id)
    with domain_transaction(db) as transaction:
        _lock_active_operator(transaction, operator_id)
        source = transaction.lock_one(
            models.WarehouseSecondaryCategory, source_secondary_category_id
        )
        if source is None:
            raise WarehouseCategoryNotFoundError("待迁移二级分类不存在")
        target_primary, target_secondary = validate_active_category_pair(
            db, target_primary_category_id, target_secondary_category_id
        )
        if source.id == target_secondary.id:
            raise WarehouseCategoryConflictError("迁移目标不能是原二级分类")
        materials = (
            db.query(models.WarehouseAsset)
            .filter(
                models.WarehouseAsset.secondary_category_id == source.id,
                models.WarehouseAsset.classification_status == "ACTIVE",
            )
            .order_by(models.WarehouseAsset.id)
            .with_for_update()
            .all()
        )
        before = [snapshot(material) for material in materials]
        for material in materials:
            try:
                require_issue_policy(
                    material.issue_policy,
                    primary_category=target_primary.code,
                    material_name=material.name,
                )
            except ValueError as error:
                raise WarehouseCategoryServiceError(
                    f"物料“{material.name}”的领用策略不适用于迁移目标：{error}"
                ) from error
            material.primary_category_id = target_primary.id
            material.secondary_category_id = target_secondary.id
            material.subcategory = target_secondary.name
        transaction.flush()
        audit = _record_category_audit(
            transaction,
            operator_id=operator_id,
            action="migrate_warehouse_secondary_references",
            category_level="SECONDARY",
            category=source,
            before={"materials": before},
            after={"target_primary_category_id": target_primary.id,
                   "target_secondary_category_id": target_secondary.id,
                   "migrated_material_count": len(materials)},
            related_records={
                "source_secondary_category_id": source.id,
                "target_primary_category_id": target_primary.id,
                "target_secondary_category_id": target_secondary.id,
                "warehouse_asset_ids": [material.id for material in materials],
            },
        )
    return len(materials), audit


def list_migration_issues(
    db: Session,
    *,
    status: Optional[str] = "OPEN",
) -> list[dict[str, Any]]:
    """返回待处理/已解决报告，不修改迁移历史记录。"""
    query = db.query(models.WarehouseCategoryMigrationIssue)
    if status is not None:
        normalized_status = status.strip().upper()
        if normalized_status not in {"OPEN", "RESOLVED"}:
            raise WarehouseCategoryServiceError("迁移问题状态仅支持 OPEN 或 RESOLVED")
        query = query.filter(
            models.WarehouseCategoryMigrationIssue.status == normalized_status
        )
    issues = query.order_by(
        models.WarehouseCategoryMigrationIssue.created_at.desc(),
        models.WarehouseCategoryMigrationIssue.id.desc(),
    ).all()
    return [_migration_issue_dict(issue) for issue in issues]


def export_migration_issues(
    db: Session,
    *,
    status: Optional[str] = "OPEN",
) -> list[dict[str, Any]]:
    """返回可直接导出 CSV 的报告行。"""
    return [
        {
            "问题编号": item["id"],
            "物料标识": item["warehouse_asset_id"],
            "物料名称": item["material_name"] or "",
            "原分类": item["original_category"],
            "标准化分类": item["normalized_category"] or "",
            "处理原因代码": item["reason_code"],
            "处理原因": item["reason_detail"],
            "状态": item["status"],
            "创建时间": item["created_at"].isoformat(),
            "解决时间": (
                item["resolved_at"].isoformat()
                if item["resolved_at"] is not None
                else ""
            ),
        }
        for item in list_migration_issues(db, status=status)
    ]


def resolve_migration_issue(
    db: Session,
    migration_issue_id: int,
    *,
    primary_category_id: int,
    secondary_category_id: int,
    operator_id: int,
    resolution_note: Optional[str] = None,
) -> tuple[
    models.WarehouseCategoryMigrationIssue,
    models.WarehouseAsset,
    models.OperationLog,
]:
    """受控解决历史问题：写有效组合、激活物料、关闭问题并审计。"""
    _require_operator_id(operator_id)
    with domain_transaction(db) as transaction:
        operator = _lock_active_operator(transaction, operator_id)
        issue = transaction.lock_one(
            models.WarehouseCategoryMigrationIssue, migration_issue_id
        )
        if issue is None:
            raise WarehouseCategoryNotFoundError("待处理迁移问题不存在")
        if issue.status != "OPEN":
            raise WarehouseCategoryConflictError("该迁移问题已解决，不能重复处理")
        material = transaction.lock_one(models.WarehouseAsset, issue.warehouse_asset_id)
        if material is None:
            raise WarehouseCategoryNotFoundError("待处理迁移问题关联的物料不存在")
        if material.classification_status != "PENDING_MIGRATION":
            raise WarehouseCategoryConflictError("关联物料不是待处理迁移状态")
        primary, secondary = validate_active_category_pair(
            db, primary_category_id, secondary_category_id
        )
        before = {
            "migration_issue": snapshot(issue),
            "warehouse_material": snapshot(material),
        }
        material.primary_category_id = primary.id
        material.secondary_category_id = secondary.id
        material.classification_status = "ACTIVE"
        material.legacy_category = material.legacy_category or material.category
        material.category = material.category or primary.name
        material.subcategory = secondary.name
        material.issue_policy = _resolved_issue_policy(material, primary)
        issue.status = "RESOLVED"
        issue.resolved_by = operator.id
        issue.resolved_at = models.china_now()
        transaction.flush()
        audit = _record_category_audit(
            transaction,
            operator_id=operator.id,
            action="resolve_warehouse_category_migration_issue",
            category_level="MIGRATION",
            category=issue,
            before=before,
            after={
                "migration_issue": snapshot(issue),
                "warehouse_material": snapshot(material),
                "resolution_note": resolution_note,
            },
            related_records={
                "warehouse_asset_id": material.id,
                "primary_category_id": primary.id,
                "secondary_category_id": secondary.id,
            },
        )
    return issue, material, audit


def _migration_issue_dict(
    issue: models.WarehouseCategoryMigrationIssue,
) -> dict[str, Any]:
    return {
        "id": issue.id,
        "warehouse_asset_id": issue.warehouse_asset_id,
        "material_name": (
            issue.warehouse_asset.name if issue.warehouse_asset is not None else None
        ),
        "original_category": issue.original_category,
        "normalized_category": issue.normalized_category,
        "reason_code": issue.reason_code,
        "reason_detail": issue.reason_detail,
        "status": issue.status,
        "created_at": issue.created_at,
        "resolved_at": issue.resolved_at,
    }


def _resolved_issue_policy(
    material: models.WarehouseAsset,
    primary: models.WarehousePrimaryCategory,
) -> str:
    try:
        return require_issue_policy(
            material.issue_policy,
            primary_category=primary.code,
            material_name=material.name,
        ).value
    except (ValueError, TypeError):
        allowed = allowed_issue_policies(primary.code, material.name)
        if len(allowed) == 1:
            return next(iter(allowed)).value
        return IssuePolicy.CONSUMABLE.value


def _supported_changes(
    changes: dict[str, Any],
    allowed: set[str],
) -> dict[str, Any]:
    unsupported = set(changes) - allowed
    if unsupported:
        raise WarehouseCategoryServiceError(
            f"不支持修改字段：{', '.join(sorted(unsupported))}"
        )
    values = {key: value for key, value in changes.items() if value is not None}
    if not values:
        raise WarehouseCategoryServiceError("未提供可更新的分类字段")
    return values


def _require_operator_id(operator_id: int) -> None:
    if not isinstance(operator_id, int) or isinstance(operator_id, bool) or operator_id <= 0:
        raise WarehouseCategoryServiceError("经办人标识无效")


def _lock_active_operator(transaction, operator_id: int) -> models.User:
    operator = transaction.lock_one(models.User, operator_id)
    if operator is None or operator.is_active is not True:
        raise WarehouseCategoryServiceError("经办人不存在或已停用")
    return operator


def _assert_primary_identity_available(
    db: Session,
    *,
    code: str,
    name: str,
    excluding_id: Optional[int] = None,
) -> None:
    query = db.query(models.WarehousePrimaryCategory).filter(
        models.WarehousePrimaryCategory.code == code
    )
    if excluding_id is not None:
        query = query.filter(models.WarehousePrimaryCategory.id != excluding_id)
    if query.first() is not None:
        raise WarehouseCategoryConflictError("一级分类代码已存在")
    query = db.query(models.WarehousePrimaryCategory).filter(
        models.WarehousePrimaryCategory.name == name
    )
    if excluding_id is not None:
        query = query.filter(models.WarehousePrimaryCategory.id != excluding_id)
    if query.first() is not None:
        raise WarehouseCategoryConflictError("一级分类名称已存在")


def _assert_secondary_identity_available(
    db: Session,
    *,
    primary_category_id: int,
    code: str,
    name: str,
    excluding_id: Optional[int] = None,
) -> None:
    code_query = db.query(models.WarehouseSecondaryCategory).filter(
        models.WarehouseSecondaryCategory.primary_category_id == primary_category_id,
        models.WarehouseSecondaryCategory.code == code,
    )
    name_query = db.query(models.WarehouseSecondaryCategory).filter(
        models.WarehouseSecondaryCategory.primary_category_id == primary_category_id,
        models.WarehouseSecondaryCategory.name == name,
    )
    if excluding_id is not None:
        code_query = code_query.filter(
            models.WarehouseSecondaryCategory.id != excluding_id
        )
        name_query = name_query.filter(
            models.WarehouseSecondaryCategory.id != excluding_id
        )
    if code_query.first() is not None:
        raise WarehouseCategoryConflictError("同一一级分类下的二级分类代码已存在")
    if name_query.first() is not None:
        raise WarehouseCategoryConflictError("同一一级分类下的二级分类名称已存在")


def _ensure_primary_can_be_deactivated(db: Session, primary_category_id: int) -> None:
    if db.query(models.WarehouseSecondaryCategory).filter(
        models.WarehouseSecondaryCategory.primary_category_id == primary_category_id,
        models.WarehouseSecondaryCategory.is_active.is_(True),
    ).first() is not None:
        raise WarehouseCategoryConflictError("一级分类下仍有启用的二级分类，不能停用")
    if db.query(models.WarehouseAsset).filter(
        models.WarehouseAsset.primary_category_id == primary_category_id,
        models.WarehouseAsset.classification_status == "ACTIVE",
    ).first() is not None:
        raise WarehouseCategoryConflictError("一级分类已被活动仓储物料引用，不能停用")
    if db.query(models.WarehouseCategoryMapping).filter(
        models.WarehouseCategoryMapping.primary_category_id == primary_category_id,
        models.WarehouseCategoryMapping.is_active.is_(True),
    ).first() is not None:
        raise WarehouseCategoryConflictError("一级分类已被活动迁移映射引用，不能停用")


def _ensure_secondary_can_be_deactivated(db: Session, secondary_category_id: int) -> None:
    if db.query(models.WarehouseAsset).filter(
        models.WarehouseAsset.secondary_category_id == secondary_category_id,
        models.WarehouseAsset.classification_status == "ACTIVE",
    ).first() is not None:
        raise WarehouseCategoryConflictError("二级分类已被活动仓储物料引用，不能停用")
    if db.query(models.WarehouseCategoryMapping).filter(
        models.WarehouseCategoryMapping.secondary_category_id == secondary_category_id,
        models.WarehouseCategoryMapping.is_active.is_(True),
    ).first() is not None:
        raise WarehouseCategoryConflictError("二级分类已被活动迁移映射引用，不能停用")


def _record_category_audit(
    transaction,
    *,
    operator_id: int,
    action: str,
    category_level: str,
    category: Any,
    before: Any,
    after: Any,
    related_records: Optional[dict[str, Any]] = None,
) -> models.OperationLog:
    category_id = getattr(category, "id", None)
    primary_id = getattr(category, "primary_category_id", None)
    relation_data = {
        "category_level": category_level,
        "category_id": category_id,
        "primary_category_id": primary_id,
    }
    if related_records:
        relation_data.update(related_records)
    return transaction.record_audit(
        user_id=operator_id,
        action=action,
        resource_type="warehouse_category",
        resource_id=category_id,
        description=f"仓储分类目录{category_level}维护",
        before=before,
        after=after,
        related_records=relation_data,
    )
