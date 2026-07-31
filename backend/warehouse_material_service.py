"""非固定仓储物料创建、编辑、查询与组合筛选领域服务。"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

import models
from category_policy import (
    CategoryPolicyError,
    is_fixed_asset_category,
    require_issue_policy,
)
from transaction_audit import domain_transaction, snapshot
from warehouse_category_service import (
    WarehouseCategoryNotFoundError,
    WarehouseCategoryPendingError,
    WarehouseCategoryServiceError,
    validate_active_category_pair,
)


class WarehouseMaterialServiceError(ValueError):
    """仓储物料业务规则不满足时的中文错误。"""


class WarehouseMaterialNotFoundError(WarehouseMaterialServiceError):
    """仓储物料不存在。"""


class WarehouseMaterialConflictError(WarehouseMaterialServiceError):
    """仓储物料状态或库存组合发生冲突。"""


def create_material(
    db: Session,
    *,
    payload: dict[str, Any],
    operator_id: int,
) -> tuple[models.WarehouseAsset, models.OperationLog]:
    """以采购到货方式创建非固定资产物料库存，不创建固定资产卡。"""
    _require_operator_id(operator_id)
    name = _require_name(payload.get("name"))
    _reject_fixed_asset_material(name)
    available_quantity = _require_non_negative(
        payload.get("available_quantity", 0), "可用库存"
    )
    allocated_quantity = _require_non_negative(
        payload.get("allocated_quantity", 0), "已分配数量"
    )
    low_stock_threshold = _require_non_negative(
        payload.get("low_stock_threshold", 0), "低库存阈值"
    )
    primary_id, secondary_id = _require_category_pair(payload)

    with domain_transaction(db) as transaction:
        operator = _lock_active_operator(transaction, operator_id)
        primary, secondary = validate_active_category_pair(db, primary_id, secondary_id)
        policy = _validate_issue_policy(payload.get("issue_policy"), primary, name)
        material = models.WarehouseAsset(
            name=name,
            category=primary.name,
            subcategory=secondary.name,
            brand=payload.get("brand"),
            model=payload.get("model"),
            total_quantity=available_quantity + allocated_quantity,
            available_quantity=available_quantity,
            allocated_quantity=allocated_quantity,
            minimum_stock=low_stock_threshold,
            low_stock_threshold=low_stock_threshold,
            location=_optional_text(payload.get("location")),
            notes=payload.get("notes"),
            primary_category_id=primary.id,
            secondary_category_id=secondary.id,
            classification_status="ACTIVE",
            legacy_category=None,
            material_kind="NON_FIXED",
            issue_policy=policy.value,
        )
        db.add(material)
        transaction.flush()
        db.add(models.WarehouseAssetLog(
            asset_id=material.id,
            action="采购入库",
            description=f"非固定资产物料入库：{material.name}，数量：{material.total_quantity}",
            operator=operator.full_name or operator.username,
        ))
        transaction.flush()
        audit = transaction.record_audit(
            user_id=operator.id,
            action="create_warehouse_material",
            resource_type="warehouse_material",
            resource_id=material.id,
            description=f"采购入库非固定资产物料“{material.name}”",
            before=None,
            after=_material_snapshot(material),
            related_records={
                "primary_category_id": primary.id,
                "secondary_category_id": secondary.id,
                "inbound_type": "NON_FIXED_PURCHASE",
            },
        )
    return material, audit


def update_material(
    db: Session,
    material_id: int,
    *,
    changes: dict[str, Any],
    operator_id: int,
) -> tuple[models.WarehouseAsset, models.OperationLog]:
    """编辑活动物料，始终在服务端重验有效分类组合和库存摘要。"""
    _require_operator_id(operator_id)
    if not changes:
        raise WarehouseMaterialServiceError("未提供可更新的物料字段")
    with domain_transaction(db) as transaction:
        operator = _lock_active_operator(transaction, operator_id)
        material = transaction.lock_one(models.WarehouseAsset, material_id)
        if material is None:
            raise WarehouseMaterialNotFoundError("仓储物料不存在")
        if material.classification_status == "PENDING_MIGRATION":
            raise WarehouseCategoryPendingError(
                "该物料分类待处理，请先完成一级和二级分类映射"
            )
        if material.classification_status != "ACTIVE":
            raise WarehouseMaterialConflictError("仓储物料当前不是可编辑状态")
        before = _material_snapshot(material)
        primary_id, secondary_id = _updated_category_pair(material, changes)
        primary, secondary = validate_active_category_pair(db, primary_id, secondary_id)

        name = _require_name(changes.get("name", material.name))
        available_quantity = _require_non_negative(
            changes.get("available_quantity", material.available_quantity), "可用库存"
        )
        allocated_quantity = _require_non_negative(
            changes.get("allocated_quantity", material.allocated_quantity), "已分配数量"
        )
        low_stock_threshold = _require_non_negative(
            changes.get("low_stock_threshold", material.low_stock_threshold),
            "低库存阈值",
        )
        policy_value = changes.get("issue_policy", material.issue_policy)
        policy = _validate_issue_policy(policy_value, primary, name)

        material.name = name
        material.primary_category_id = primary.id
        material.secondary_category_id = secondary.id
        material.category = primary.name
        material.subcategory = secondary.name
        material.available_quantity = available_quantity
        material.allocated_quantity = allocated_quantity
        material.total_quantity = available_quantity + allocated_quantity
        material.minimum_stock = low_stock_threshold
        material.low_stock_threshold = low_stock_threshold
        material.issue_policy = policy.value
        for field in ("location", "brand", "model", "notes"):
            if field in changes:
                setattr(
                    material,
                    field,
                    _optional_text(changes[field]) if field == "location" else changes[field],
                )
        transaction.flush()
        db.add(models.WarehouseAssetLog(
            asset_id=material.id,
            action="编辑",
            description="仓储物料目录及库存摘要已更新",
            operator=operator.full_name or operator.username,
        ))
        transaction.flush()
        audit = transaction.record_audit(
            user_id=operator.id,
            action="update_warehouse_material",
            resource_type="warehouse_material",
            resource_id=material.id,
            description=f"编辑仓储物料“{material.name}”",
            before=before,
            after=_material_snapshot(material),
            related_records={
                "primary_category_id": primary.id,
                "secondary_category_id": secondary.id,
            },
        )
    return material, audit


def get_material(db: Session, material_id: int) -> dict[str, Any]:
    material = db.query(models.WarehouseAsset).filter(
        models.WarehouseAsset.id == material_id
    ).one_or_none()
    if material is None:
        raise WarehouseMaterialNotFoundError("仓储物料不存在")
    return serialize_material(material)


def list_materials(
    db: Session,
    *,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    """按所有已传入字段执行 AND 筛选，并预先拒绝交叉分类组合。"""
    primary_id = filters.get("primary_category_id")
    secondary_id = filters.get("secondary_category_id")
    if primary_id is not None and secondary_id is not None:
        validate_active_category_pair(db, primary_id, secondary_id)
    elif primary_id is not None:
        _require_existing_primary(db, primary_id)
    elif secondary_id is not None:
        _require_existing_secondary(db, secondary_id)

    query = db.query(models.WarehouseAsset).filter(
        models.WarehouseAsset.classification_status == "ACTIVE"
    )
    if filters.get("name"):
        query = query.filter(models.WarehouseAsset.name.ilike(f"%{filters['name'].strip()}%"))
    for field in (
        "primary_category_id",
        "secondary_category_id",
        "available_quantity",
        "allocated_quantity",
        "low_stock_threshold",
    ):
        if filters.get(field) is not None:
            query = query.filter(getattr(models.WarehouseAsset, field) == filters[field])
    if filters.get("location") is not None:
        query = query.filter(models.WarehouseAsset.location == filters["location"])
    if filters.get("low_stock") is True:
        query = query.filter(
            models.WarehouseAsset.available_quantity < models.WarehouseAsset.low_stock_threshold
        )
    elif filters.get("low_stock") is False:
        query = query.filter(
            models.WarehouseAsset.available_quantity >= models.WarehouseAsset.low_stock_threshold
        )
    materials = query.order_by(models.WarehouseAsset.id.desc()).all()
    return [serialize_material(material) for material in materials]


def serialize_material(material: models.WarehouseAsset) -> dict[str, Any]:
    """构建稳定的物料详情/列表响应，严格按新阈值计算低库存。"""
    if material.classification_status == "PENDING_MIGRATION":
        raise WarehouseCategoryPendingError(
            "该物料分类待处理，请先完成一级和二级分类映射"
        )
    primary = material.primary_category
    secondary = material.secondary_category
    if primary is None or secondary is None:
        raise WarehouseMaterialConflictError("物料缺少有效的一级和二级分类组合")
    if secondary.primary_category_id != primary.id:
        raise WarehouseMaterialConflictError("物料一级和二级分类组合无效")
    low_stock = material.available_quantity < material.low_stock_threshold
    return {
        "id": material.id,
        "name": material.name,
        "primary_category_id": primary.id,
        "primary_category_code": primary.code,
        "primary_category_name": primary.name,
        "secondary_category_id": secondary.id,
        "secondary_category_code": secondary.code,
        "secondary_category_name": secondary.name,
        "available_quantity": material.available_quantity,
        "allocated_quantity": material.allocated_quantity,
        "location": material.location,
        "low_stock_threshold": material.low_stock_threshold,
        "low_stock": low_stock,
        "low_stock_message": "低库存预警" if low_stock else None,
        "issue_policy": material.issue_policy,
        "classification_status": material.classification_status,
        "legacy_category": material.legacy_category,
        "brand": material.brand,
        "model": material.model,
        "notes": material.notes,
        "created_at": material.created_at,
        "updated_at": material.updated_at,
    }


def _require_operator_id(operator_id: int) -> None:
    if not isinstance(operator_id, int) or isinstance(operator_id, bool) or operator_id <= 0:
        raise WarehouseMaterialServiceError("经办人标识无效")


def _lock_active_operator(transaction, operator_id: int) -> models.User:
    operator = transaction.lock_one(models.User, operator_id)
    if operator is None or operator.is_active is not True:
        raise WarehouseMaterialServiceError("经办人不存在或已停用")
    return operator


def _require_name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WarehouseMaterialServiceError("物料名称不能为空")
    return value.strip()


def _reject_fixed_asset_material(name: str) -> None:
    if is_fixed_asset_category(name):
        raise WarehouseMaterialServiceError(
            "固定资产不得通过库房物料入库，请改用受控固定资产入库"
        )


def _require_non_negative(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise WarehouseMaterialServiceError(f"{label}必须为非负整数")
    return value


def _require_category_pair(payload: dict[str, Any]) -> tuple[int, int]:
    primary_id = payload.get("primary_category_id")
    secondary_id = payload.get("secondary_category_id")
    if not isinstance(primary_id, int) or isinstance(primary_id, bool) or primary_id <= 0:
        raise WarehouseMaterialServiceError("一级分类标识无效")
    if not isinstance(secondary_id, int) or isinstance(secondary_id, bool) or secondary_id <= 0:
        raise WarehouseMaterialServiceError("二级分类标识无效")
    return primary_id, secondary_id


def _updated_category_pair(
    material: models.WarehouseAsset,
    changes: dict[str, Any],
) -> tuple[int, int]:
    has_primary = "primary_category_id" in changes
    has_secondary = "secondary_category_id" in changes
    if has_primary != has_secondary:
        raise WarehouseMaterialServiceError("一级分类和二级分类必须同时提交")
    if not has_primary:
        return material.primary_category_id, material.secondary_category_id
    return _require_category_pair(changes)


def _validate_issue_policy(
    value: Any,
    primary: models.WarehousePrimaryCategory,
    material_name: str,
):
    try:
        return require_issue_policy(
            value,
            primary_category=primary.code,
            material_name=material_name,
        )
    except (CategoryPolicyError, ValueError, TypeError) as error:
        raise WarehouseMaterialServiceError(str(error)) from error


def _require_existing_primary(db: Session, primary_id: int) -> None:
    primary = db.query(models.WarehousePrimaryCategory).filter(
        models.WarehousePrimaryCategory.id == primary_id
    ).one_or_none()
    if primary is None:
        raise WarehouseCategoryNotFoundError("一级分类不存在")
    if primary.is_active is not True:
        raise WarehouseCategoryServiceError("一级分类已停用")


def _require_existing_secondary(db: Session, secondary_id: int) -> None:
    secondary = db.query(models.WarehouseSecondaryCategory).filter(
        models.WarehouseSecondaryCategory.id == secondary_id
    ).one_or_none()
    if secondary is None:
        raise WarehouseCategoryNotFoundError("二级分类不存在")
    if secondary.is_active is not True:
        raise WarehouseCategoryServiceError("二级分类已停用")


def _optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise WarehouseMaterialServiceError("存放位置格式无效")
    return value.strip() or None


def _material_snapshot(material: models.WarehouseAsset) -> dict[str, Any]:
    return snapshot(
        material,
        fields=(
            "id",
            "name",
            "primary_category_id",
            "secondary_category_id",
            "classification_status",
            "available_quantity",
            "allocated_quantity",
            "total_quantity",
            "location",
            "low_stock_threshold",
            "issue_policy",
        ),
    ) or {}
