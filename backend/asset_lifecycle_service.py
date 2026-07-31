"""受控固定资产入库与生命周期领域服务。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

import models
from category_policy import (
    ASSET_CATEGORY_NAMES,
    AssetCategoryCode,
    CategoryPolicyError,
    FixedAssetStatus,
    PrimaryCategoryCode,
    require_fixed_asset_category,
)
from transaction_audit import DomainTransactionError, domain_transaction, snapshot_json


class AssetLifecycleError(DomainTransactionError):
    """固定资产生命周期前置条件不满足时抛出的中文业务错误。"""


class AssetLifecycleConflictError(AssetLifecycleError):
    """固定资产标识、状态或库存冲突时抛出。"""


class AssetLifecycleNotFoundError(AssetLifecycleError):
    """固定资产或其受控终端库存不存在时抛出。"""


@dataclass(frozen=True)
class AssetLifecycleResult:
    """生命周期命令成功提交后返回的领域记录。"""

    asset: models.Asset
    terminal_inventory: models.WarehouseAsset
    audit_log: models.OperationLog
    inbound: Optional[models.FixedAssetInbound] = None
    issuance: Optional[models.FixedAssetIssuance] = None
    lifecycle_event: Optional[models.AssetLifecycleEvent] = None


_BINDING_FIELDS = ("employee_name", "employee_id", "department", "issue_date")
_EMPLOYEE_REF_FIELD = "employee_ref_id"


def _operator_label(operator_id: int, operator_name: Optional[str]) -> str:
    return operator_name.strip() if operator_name and operator_name.strip() else f"用户#{operator_id}"


def _require_operator(operator_id: int) -> None:
    if not isinstance(operator_id, int) or operator_id <= 0:
        raise AssetLifecycleError("经办人信息无效")


def _require_nonblank(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AssetLifecycleError(f"{field_name}不能为空")
    return value.strip()


def _require_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise AssetLifecycleError(f"{field_name}无效")
    return value


def _binding_from_values(
    *,
    recipient_name: Optional[str],
    recipient_employee_id: Optional[str],
    recipient_department: Optional[str],
    issued_at: Optional[datetime],
    employee_ref_id: Optional[int] = None,
) -> dict[str, Any]:
    binding = {
        "employee_name": _require_nonblank(recipient_name, "领用人"),  # type: ignore[arg-type]
        "employee_id": _require_nonblank(recipient_employee_id, "工号"),  # type: ignore[arg-type]
        "department": _require_nonblank(recipient_department, "部门"),  # type: ignore[arg-type]
        "issue_date": _require_datetime(issued_at, "发放日期"),  # type: ignore[arg-type]
    }
    if employee_ref_id is not None:
        binding[_EMPLOYEE_REF_FIELD] = employee_ref_id
    return binding


def _employee_value(employee: Any, *field_names: str) -> Any:
    for field_name in field_names:
        value = getattr(employee, field_name, None)
        if value is not None:
            return value
    return None


def _lock_active_employee(transaction: Any, employee_ref_id: int) -> Any:
    if not isinstance(employee_ref_id, int) or isinstance(employee_ref_id, bool) or employee_ref_id <= 0:
        raise AssetLifecycleError("员工引用编号无效")
    employee = transaction.lock_one(models.Employee, employee_ref_id)
    if employee is None:
        raise AssetLifecycleNotFoundError("员工不存在")
    if getattr(employee, "status", None) != "ACTIVE":
        raise AssetLifecycleConflictError("员工不是在职状态，不能绑定固定资产")
    return employee


def _binding_from_employee(
    transaction: Any,
    *,
    employee_ref_id: int,
    issued_at: Optional[datetime],
) -> dict[str, Any]:
    employee = _lock_active_employee(transaction, employee_ref_id)
    department = _employee_value(employee, "department", "department_name")
    if department is not None and not isinstance(department, str):
        department = getattr(department, "name", None)
    return _binding_from_values(
        recipient_name=_employee_value(employee, "employee_name", "name"),
        recipient_employee_id=_employee_value(
            employee, "employee_id", "employee_number", "employee_code"
        ),
        recipient_department=department,
        issued_at=issued_at,
        employee_ref_id=employee_ref_id,
    )


def _current_binding(asset: models.Asset) -> Optional[dict[str, Any]]:
    values = {field: getattr(asset, field) for field in _BINDING_FIELDS}
    employee_ref_id = getattr(asset, _EMPLOYEE_REF_FIELD, None)
    if all(value is None for value in values.values()) and employee_ref_id is None:
        return None
    if employee_ref_id is not None:
        values[_EMPLOYEE_REF_FIELD] = employee_ref_id
    return values


def _require_current_binding(asset: models.Asset) -> dict[str, Any]:
    binding = _current_binding(asset)
    if binding is None or any(not binding[field] for field in _BINDING_FIELDS):
        raise AssetLifecycleError("固定资产当前领用绑定无效")
    return binding


def _apply_binding(asset: models.Asset, binding: Optional[dict[str, Any]]) -> None:
    for field in _BINDING_FIELDS:
        setattr(asset, field, binding[field] if binding else None)
    setattr(
        asset,
        _EMPLOYEE_REF_FIELD,
        binding.get(_EMPLOYEE_REF_FIELD) if binding else None,
    )


def _validate_inventory(inventory: models.WarehouseAsset) -> None:
    values = (
        inventory.total_quantity,
        inventory.available_quantity,
        inventory.allocated_quantity,
    )
    if any(not isinstance(value, int) or value < 0 for value in values):
        raise AssetLifecycleError("终端设备库存数据无效")
    if inventory.total_quantity != inventory.available_quantity + inventory.allocated_quantity:
        raise AssetLifecycleError("终端设备库存数量不一致")


def _validate_terminal_inventory(inventory: models.WarehouseAsset) -> None:
    """只允许活动“终端设备库存”目录项承载受控固定资产。"""
    _validate_inventory(inventory)
    primary = inventory.primary_category
    if inventory.classification_status != "ACTIVE" or primary is None:
        raise AssetLifecycleError("源终端设备库存未完成受控分类，不能用于固定资产入库或发放")
    if primary.code != PrimaryCategoryCode.TERMINAL_EQUIPMENT.value:
        raise AssetLifecycleError("固定资产只能关联“终端设备库存”中的库存记录")


def _change_inventory(
    inventory: models.WarehouseAsset,
    *,
    total_delta: int = 0,
    available_delta: int = 0,
    allocated_delta: int = 0,
) -> None:
    _validate_inventory(inventory)
    new_total = inventory.total_quantity + total_delta
    new_available = inventory.available_quantity + available_delta
    new_allocated = inventory.allocated_quantity + allocated_delta
    if min(new_total, new_available, new_allocated) < 0:
        raise AssetLifecycleConflictError("终端设备库存不足")
    if new_total != new_available + new_allocated:
        raise AssetLifecycleError("终端设备库存更新不满足数量守恒")
    inventory.total_quantity = new_total
    inventory.available_quantity = new_available
    inventory.allocated_quantity = new_allocated


def _add_asset_log(
    db: Session,
    *,
    asset: models.Asset,
    action: str,
    description: str,
    before: Any,
    after: Any,
    operator: str,
) -> models.AssetLog:
    log = models.AssetLog(
        asset_id=asset.id,
        action=action,
        description=description,
        old_value=snapshot_json(before),
        new_value=snapshot_json(after),
        operator=operator,
    )
    db.add(log)
    return log


def _add_inventory_log(
    db: Session,
    *,
    inventory: models.WarehouseAsset,
    action: str,
    description: str,
    operator: str,
) -> models.WarehouseAssetLog:
    log = models.WarehouseAssetLog(
        asset_id=inventory.id,
        action=action,
        description=description,
        operator=operator,
    )
    db.add(log)
    return log


def _add_lifecycle_event(
    db: Session,
    *,
    asset_id: int,
    event_type: str,
    previous_binding: Optional[dict[str, Any]],
    new_binding: Optional[dict[str, Any]],
    operator_id: int,
    terminal_inventory_id: int,
) -> models.AssetLifecycleEvent:
    def json_binding(
        binding: Optional[dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        if binding is None:
            return None
        return {
            key: value.isoformat() if isinstance(value, datetime) else value
            for key, value in binding.items()
        }

    event = models.AssetLifecycleEvent(
        asset_id=asset_id,
        event_type=event_type,
        previous_binding=json_binding(previous_binding),
        new_binding=json_binding(new_binding),
        operator_id=operator_id,
        occurred_at=models.china_now(),
        event_metadata={"terminal_inventory_id": terminal_inventory_id},
    )
    db.add(event)
    return event


def _lock_controlled_asset_and_inventory(
    transaction: Any,
    *,
    asset_id: int,
) -> tuple[models.Asset, models.FixedAssetInbound, models.WarehouseAsset]:
    """固定按资产、入库证明、终端库存的顺序加锁并校验受控入库来源。"""
    asset = transaction.lock_one(models.Asset, asset_id)
    if asset is None or asset.is_deleted:
        raise AssetLifecycleNotFoundError("固定资产不存在或已删除")

    try:
        category_code = require_fixed_asset_category(asset.asset_category_code or "")
    except CategoryPolicyError as exc:
        raise AssetLifecycleError(str(exc)) from exc
    if asset.category != ASSET_CATEGORY_NAMES[category_code]:
        raise AssetLifecycleError("固定资产分类与受控入库记录不一致")
    if asset.inbound_source not in {"SCAN", "MANUAL"}:
        raise AssetLifecycleError("固定资产不是通过受控入库创建")
    if not asset.fixed_asset_number or not asset.fixed_asset_number.strip() or not asset.serial_number or not asset.serial_number.strip():
        raise AssetLifecycleError("固定资产标识无效")
    if not asset.terminal_inventory_id:
        raise AssetLifecycleError("固定资产缺少终端库存关联")

    inbound = (
        transaction.db.query(models.FixedAssetInbound)
        .filter(models.FixedAssetInbound.asset_id == asset.id)
        .with_for_update()
        .one_or_none()
    )
    if inbound is None or inbound.terminal_inventory_id != asset.terminal_inventory_id:
        raise AssetLifecycleError("固定资产缺少有效受控入库记录")

    inventory = transaction.lock_one(models.WarehouseAsset, asset.terminal_inventory_id)
    if inventory is None:
        raise AssetLifecycleNotFoundError("源终端设备库存不存在")
    _validate_terminal_inventory(inventory)
    return asset, inbound, inventory


def _record_audit(
    transaction: Any,
    *,
    operator_id: int,
    action: str,
    asset: models.Asset,
    description: str,
    before: Any,
    after: Any,
    inventory: models.WarehouseAsset,
    related_records: dict[str, Any],
) -> models.OperationLog:
    return transaction.record_audit(
        user_id=operator_id,
        action=action,
        resource_type="fixed_asset",
        resource_id=asset.id,
        description=description,
        before=before,
        after=after,
        related_records={
            "asset_id": asset.id,
            "terminal_inventory_id": inventory.id,
            **related_records,
        },
    )


def controlled_inbound(
    db: Session,
    *,
    operator_id: int,
    terminal_inventory_id: int,
    source: str,
    asset_category_code: str | AssetCategoryCode,
    fixed_asset_number: str,
    serial_number: str,
    brand: Optional[str] = None,
    model: Optional[str] = None,
    purchase_date: Optional[datetime] = None,
    notes: Optional[str] = None,
    operator_name: Optional[str] = None,
) -> AssetLifecycleResult:
    """通过 SCAN/MANUAL 为 PC、NB、PD 创建闲置卡并同步增加终端库存。"""
    _require_operator(operator_id)
    if source not in {"SCAN", "MANUAL"}:
        raise AssetLifecycleError("固定资产仅支持 SCAN 或 MANUAL 受控入库")
    if not isinstance(terminal_inventory_id, int) or terminal_inventory_id <= 0:
        raise AssetLifecycleError("终端设备库存无效")
    try:
        category_code = require_fixed_asset_category(asset_category_code)
    except CategoryPolicyError as exc:
        raise AssetLifecycleError(str(exc)) from exc
    fixed_asset_number = _require_nonblank(fixed_asset_number, "资产编号")
    serial_number = _require_nonblank(serial_number, "序列号")
    operator = _operator_label(operator_id, operator_name)

    with domain_transaction(db) as transaction:
        duplicate = (
            db.query(models.Asset)
            .filter(
                or_(
                    models.Asset.fixed_asset_number == fixed_asset_number,
                    models.Asset.serial_number == serial_number,
                    models.Asset.asset_tag == fixed_asset_number,
                )
            )
            .order_by(models.Asset.id)
            .with_for_update()
            .first()
        )
        if duplicate is not None:
            raise AssetLifecycleConflictError("资产编号或序列号已存在，不能重复入库")

        inventory = transaction.lock_one(models.WarehouseAsset, terminal_inventory_id)
        if inventory is None:
            raise AssetLifecycleNotFoundError("终端设备库存不存在")
        _validate_terminal_inventory(inventory)
        before_inventory = {
            "total_quantity": inventory.total_quantity,
            "available_quantity": inventory.available_quantity,
            "allocated_quantity": inventory.allocated_quantity,
        }
        _change_inventory(inventory, total_delta=1, available_delta=1)

        asset = models.Asset(
            asset_tag=fixed_asset_number,
            category=ASSET_CATEGORY_NAMES[category_code],
            asset_category_code=category_code.value,
            inbound_source=source,
            terminal_inventory_id=inventory.id,
            fixed_asset_number=fixed_asset_number,
            serial_number=serial_number,
            status=FixedAssetStatus.IDLE.value,
            brand=brand.strip() if isinstance(brand, str) and brand.strip() else None,
            model=model.strip() if isinstance(model, str) and model.strip() else None,
            purchase_date=purchase_date,
            notes=notes,
            quantity=1,
        )
        db.add(asset)
        transaction.flush()

        inbound = models.FixedAssetInbound(
            asset_id=asset.id,
            terminal_inventory_id=inventory.id,
            source=source,
            operator_id=operator_id,
            inbound_at=models.china_now(),
        )
        db.add(inbound)
        _add_asset_log(
            db,
            asset=asset,
            action="受控入库",
            description=f"通过 {source} 受控入库，初始状态为闲置",
            before=None,
            after={"status": asset.status, "terminal_inventory_id": inventory.id},
            operator=operator,
        )
        _add_inventory_log(
            db,
            inventory=inventory,
            action="固定资产受控入库",
            description=(
                f"资产编号 {fixed_asset_number} 入库：可用库存 "
                f"{before_inventory['available_quantity']} → {inventory.available_quantity}"
            ),
            operator=operator,
        )
        transaction.flush()
        audit_log = _record_audit(
            transaction,
            operator_id=operator_id,
            action="fixed_asset_inbound",
            asset=asset,
            description=f"固定资产 {fixed_asset_number} 受控入库",
            before={"asset": None, "inventory": before_inventory},
            after={
                "asset": {
                    "status": asset.status,
                    "asset_category_code": asset.asset_category_code,
                    "terminal_inventory_id": inventory.id,
                },
                "inventory": {
                    "total_quantity": inventory.total_quantity,
                    "available_quantity": inventory.available_quantity,
                    "allocated_quantity": inventory.allocated_quantity,
                },
            },
            inventory=inventory,
            related_records={"fixed_asset_inbound_id": inbound.id},
        )

    return AssetLifecycleResult(asset, inventory, audit_log, inbound=inbound)


inbound_fixed_asset = controlled_inbound


def _asset_state_snapshot(asset: models.Asset) -> dict[str, Any]:
    return {
        "status": asset.status,
        "binding": _current_binding(asset),
        "terminal_inventory_id": asset.terminal_inventory_id,
    }


def _inventory_snapshot(inventory: models.WarehouseAsset) -> dict[str, int]:
    return {
        "total_quantity": inventory.total_quantity,
        "available_quantity": inventory.available_quantity,
        "allocated_quantity": inventory.allocated_quantity,
    }


def issue_fixed_asset(
    db: Session,
    *,
    asset_id: int,
    operator_id: int,
    issued_at: datetime,
    recipient_name: Optional[str] = None,
    recipient_employee_id: Optional[str] = None,
    recipient_department: Optional[str] = None,
    employee_ref_id: Optional[int] = None,
    operator_name: Optional[str] = None,
) -> AssetLifecycleResult:
    """从关联终端库存发放一张已受控入库的闲置固定资产卡。"""
    _require_operator(operator_id)
    operator = _operator_label(operator_id, operator_name)

    with domain_transaction(db) as transaction:
        asset, _, inventory = _lock_controlled_asset_and_inventory(
            transaction, asset_id=asset_id
        )
        binding = (
            _binding_from_employee(
                transaction,
                employee_ref_id=employee_ref_id,
                issued_at=issued_at,
            )
            if employee_ref_id is not None
            else _binding_from_values(
                recipient_name=recipient_name,
                recipient_employee_id=recipient_employee_id,
                recipient_department=recipient_department,
                issued_at=issued_at,
            )
        )
        if asset.status != FixedAssetStatus.IDLE.value:
            raise AssetLifecycleConflictError("仅闲置固定资产可以发放")
        if inventory.available_quantity < 1:
            raise AssetLifecycleConflictError("源终端设备库存可用数量不足")

        before_asset = _asset_state_snapshot(asset)
        before_inventory = _inventory_snapshot(inventory)
        _apply_binding(asset, binding)
        asset.status = FixedAssetStatus.IN_USE.value
        _change_inventory(inventory, available_delta=-1, allocated_delta=1)

        issuance_values = {
            "asset_id": asset.id,
            "terminal_inventory_id": inventory.id,
            "recipient_name": binding["employee_name"],
            "recipient_employee_id": binding["employee_id"],
            "recipient_department": binding["department"],
            "issued_at": binding["issue_date"],
            "operator_id": operator_id,
        }
        if _EMPLOYEE_REF_FIELD in binding:
            issuance_values["recipient_employee_ref_id"] = binding[_EMPLOYEE_REF_FIELD]
        issuance = models.FixedAssetIssuance(**issuance_values)
        db.add(issuance)
        event = _add_lifecycle_event(
            db,
            asset_id=asset.id,
            event_type="ISSUE",
            previous_binding=None,
            new_binding=binding,
            operator_id=operator_id,
            terminal_inventory_id=inventory.id,
        )
        _add_asset_log(
            db,
            asset=asset,
            action="固定资产发放",
            description=f"发放给 {binding['employee_name']}（{binding['employee_id']}）",
            before=before_asset,
            after=_asset_state_snapshot(asset),
            operator=operator,
        )
        _add_inventory_log(
            db,
            inventory=inventory,
            action="固定资产发放出库",
            description=(
                f"资产编号 {asset.fixed_asset_number} 发放：可用库存 "
                f"{before_inventory['available_quantity']} → {inventory.available_quantity}，"
                f"已分配 {before_inventory['allocated_quantity']} → {inventory.allocated_quantity}"
            ),
            operator=operator,
        )
        transaction.flush()
        audit_log = _record_audit(
            transaction,
            operator_id=operator_id,
            action="fixed_asset_issue",
            asset=asset,
            description=f"发放固定资产 {asset.fixed_asset_number}",
            before={"asset": before_asset, "inventory": before_inventory},
            after={"asset": _asset_state_snapshot(asset), "inventory": _inventory_snapshot(inventory)},
            inventory=inventory,
            related_records={
                "fixed_asset_issuance_id": issuance.id,
                "asset_lifecycle_event_id": event.id,
            },
        )

    return AssetLifecycleResult(
        asset, inventory, audit_log, issuance=issuance, lifecycle_event=event
    )


def return_fixed_asset(
    db: Session,
    *,
    asset_id: int,
    operator_id: int,
    recipient_name: Optional[str] = None,
    recipient_employee_id: Optional[str] = None,
    recipient_department: Optional[str] = None,
    employee_ref_id: Optional[int] = None,
    operator_name: Optional[str] = None,
) -> AssetLifecycleResult:
    """归还使用中的固定资产；员工引用或旧文本必须匹配当前绑定。"""
    _require_operator(operator_id)
    operator = _operator_label(operator_id, operator_name)

    with domain_transaction(db) as transaction:
        asset, _, inventory = _lock_controlled_asset_and_inventory(
            transaction, asset_id=asset_id
        )
        if asset.status != FixedAssetStatus.IN_USE.value:
            raise AssetLifecycleConflictError("仅使用中的固定资产可以归还")
        current_binding = _require_current_binding(asset)
        if employee_ref_id is not None:
            if (
                not isinstance(employee_ref_id, int)
                or isinstance(employee_ref_id, bool)
                or employee_ref_id <= 0
            ):
                raise AssetLifecycleError("员工引用编号无效")
            if current_binding.get(_EMPLOYEE_REF_FIELD) != employee_ref_id:
                raise AssetLifecycleConflictError("归还员工与当前领用人不一致")
        else:
            returned_binding = {
                "employee_name": _require_nonblank(recipient_name, "领用人"),  # type: ignore[arg-type]
                "employee_id": _require_nonblank(recipient_employee_id, "工号"),  # type: ignore[arg-type]
                "department": _require_nonblank(recipient_department, "部门"),  # type: ignore[arg-type]
            }
            if any(
                current_binding[field] != returned_binding[field]
                for field in ("employee_name", "employee_id", "department")
            ):
                raise AssetLifecycleConflictError("归还信息与当前领用绑定不一致")

        before_asset = _asset_state_snapshot(asset)
        before_inventory = _inventory_snapshot(inventory)
        _apply_binding(asset, None)
        asset.status = FixedAssetStatus.IDLE.value
        _change_inventory(inventory, available_delta=1, allocated_delta=-1)
        event = _add_lifecycle_event(
            db,
            asset_id=asset.id,
            event_type="RETURN",
            previous_binding=current_binding,
            new_binding=None,
            operator_id=operator_id,
            terminal_inventory_id=inventory.id,
        )
        _add_asset_log(
            db,
            asset=asset,
            action="固定资产归还",
            description=f"{current_binding['employee_name']} 归还固定资产",
            before=before_asset,
            after=_asset_state_snapshot(asset),
            operator=operator,
        )
        _add_inventory_log(
            db,
            inventory=inventory,
            action="固定资产归还入库",
            description=(
                f"资产编号 {asset.fixed_asset_number} 归还：可用库存 "
                f"{before_inventory['available_quantity']} → {inventory.available_quantity}，"
                f"已分配 {before_inventory['allocated_quantity']} → {inventory.allocated_quantity}"
            ),
            operator=operator,
        )
        transaction.flush()
        audit_log = _record_audit(
            transaction,
            operator_id=operator_id,
            action="fixed_asset_return",
            asset=asset,
            description=f"归还固定资产 {asset.fixed_asset_number}",
            before={"asset": before_asset, "inventory": before_inventory},
            after={"asset": _asset_state_snapshot(asset), "inventory": _inventory_snapshot(inventory)},
            inventory=inventory,
            related_records={"asset_lifecycle_event_id": event.id},
        )

    return AssetLifecycleResult(asset, inventory, audit_log, lifecycle_event=event)


def transfer_fixed_asset(
    db: Session,
    *,
    asset_id: int,
    operator_id: int,
    issued_at: datetime,
    recipient_name: Optional[str] = None,
    recipient_employee_id: Optional[str] = None,
    recipient_department: Optional[str] = None,
    employee_ref_id: Optional[int] = None,
    operator_name: Optional[str] = None,
) -> AssetLifecycleResult:
    """将使用中的固定资产转移给不同的新领用人，库存数量保持不变。"""
    _require_operator(operator_id)
    operator = _operator_label(operator_id, operator_name)

    with domain_transaction(db) as transaction:
        asset, _, inventory = _lock_controlled_asset_and_inventory(
            transaction, asset_id=asset_id
        )
        new_binding = (
            _binding_from_employee(
                transaction,
                employee_ref_id=employee_ref_id,
                issued_at=issued_at,
            )
            if employee_ref_id is not None
            else _binding_from_values(
                recipient_name=recipient_name,
                recipient_employee_id=recipient_employee_id,
                recipient_department=recipient_department,
                issued_at=issued_at,
            )
        )
        if asset.status != FixedAssetStatus.IN_USE.value:
            raise AssetLifecycleConflictError("仅使用中的固定资产可以转移")
        previous_binding = _require_current_binding(asset)
        if previous_binding["employee_id"] == new_binding["employee_id"]:
            raise AssetLifecycleConflictError("转移目标领用人不能与当前领用人相同")

        before_asset = _asset_state_snapshot(asset)
        _apply_binding(asset, new_binding)
        event = _add_lifecycle_event(
            db,
            asset_id=asset.id,
            event_type="TRANSFER",
            previous_binding=previous_binding,
            new_binding=new_binding,
            operator_id=operator_id,
            terminal_inventory_id=inventory.id,
        )
        _add_asset_log(
            db,
            asset=asset,
            action="固定资产转移",
            description=(
                f"领用人由 {previous_binding['employee_name']}（{previous_binding['employee_id']}）"
                f"转移至 {new_binding['employee_name']}（{new_binding['employee_id']}）"
            ),
            before=before_asset,
            after=_asset_state_snapshot(asset),
            operator=operator,
        )
        transaction.flush()
        audit_log = _record_audit(
            transaction,
            operator_id=operator_id,
            action="fixed_asset_transfer",
            asset=asset,
            description=f"转移固定资产 {asset.fixed_asset_number}",
            before={"asset": before_asset},
            after={"asset": _asset_state_snapshot(asset)},
            inventory=inventory,
            related_records={"asset_lifecycle_event_id": event.id},
        )

    return AssetLifecycleResult(asset, inventory, audit_log, lifecycle_event=event)


def send_for_repair(
    db: Session,
    *,
    asset_id: int,
    operator_id: int,
    operator_name: Optional[str] = None,
) -> AssetLifecycleResult:
    """将闲置或使用中的有效固定资产送修并清除当前领用绑定。"""
    _require_operator(operator_id)
    operator = _operator_label(operator_id, operator_name)

    with domain_transaction(db) as transaction:
        asset, _, inventory = _lock_controlled_asset_and_inventory(
            transaction, asset_id=asset_id
        )
        if asset.status not in {FixedAssetStatus.IDLE.value, FixedAssetStatus.IN_USE.value}:
            raise AssetLifecycleConflictError("仅闲置或使用中的固定资产可以送修")

        before_asset = _asset_state_snapshot(asset)
        before_inventory = _inventory_snapshot(inventory)
        previous_binding = _current_binding(asset)
        inventory_changed = asset.status == FixedAssetStatus.IDLE.value
        if inventory_changed:
            _change_inventory(inventory, available_delta=-1, allocated_delta=1)
        _apply_binding(asset, None)
        asset.status = FixedAssetStatus.IN_REPAIR.value
        event = _add_lifecycle_event(
            db,
            asset_id=asset.id,
            event_type="REPAIR_SENT",
            previous_binding=previous_binding,
            new_binding=None,
            operator_id=operator_id,
            terminal_inventory_id=inventory.id,
        )
        _add_asset_log(
            db,
            asset=asset,
            action="固定资产送修",
            description="固定资产已送修并清除当前领用绑定",
            before=before_asset,
            after=_asset_state_snapshot(asset),
            operator=operator,
        )
        if inventory_changed:
            _add_inventory_log(
                db,
                inventory=inventory,
                action="固定资产送修出库",
                description=(
                    f"资产编号 {asset.fixed_asset_number} 送修：可用库存 "
                    f"{before_inventory['available_quantity']} → {inventory.available_quantity}，"
                    f"已分配 {before_inventory['allocated_quantity']} → {inventory.allocated_quantity}"
                ),
                operator=operator,
            )
        transaction.flush()
        audit_log = _record_audit(
            transaction,
            operator_id=operator_id,
            action="fixed_asset_repair_sent",
            asset=asset,
            description=f"固定资产 {asset.fixed_asset_number} 已送修",
            before={"asset": before_asset, "inventory": before_inventory},
            after={"asset": _asset_state_snapshot(asset), "inventory": _inventory_snapshot(inventory)},
            inventory=inventory,
            related_records={"asset_lifecycle_event_id": event.id},
        )

    return AssetLifecycleResult(asset, inventory, audit_log, lifecycle_event=event)


def complete_repair(
    db: Session,
    *,
    asset_id: int,
    operator_id: int,
    recipient_name: Optional[str] = None,
    recipient_employee_id: Optional[str] = None,
    recipient_department: Optional[str] = None,
    issued_at: Optional[datetime] = None,
    employee_ref_id: Optional[int] = None,
    operator_name: Optional[str] = None,
) -> AssetLifecycleResult:
    """完成维修；无新绑定回到闲置，有完整有效新绑定则直接恢复使用中。"""
    _require_operator(operator_id)
    operator = _operator_label(operator_id, operator_name)

    with domain_transaction(db) as transaction:
        asset, _, inventory = _lock_controlled_asset_and_inventory(
            transaction, asset_id=asset_id
        )
        if asset.status != FixedAssetStatus.IN_REPAIR.value:
            raise AssetLifecycleConflictError("仅维修中的固定资产可以完成维修")

        if employee_ref_id is not None:
            new_binding = _binding_from_employee(
                transaction,
                employee_ref_id=employee_ref_id,
                issued_at=issued_at,
            )
        else:
            binding_values = (
                recipient_name,
                recipient_employee_id,
                recipient_department,
                issued_at,
            )
            if any(value is not None for value in binding_values) and not all(
                value is not None for value in binding_values
            ):
                raise AssetLifecycleError(
                    "维修完成后使用中状态必须提交完整有效的新领用绑定"
                )
            new_binding = (
                _binding_from_values(
                    recipient_name=recipient_name,
                    recipient_employee_id=recipient_employee_id,
                    recipient_department=recipient_department,
                    issued_at=issued_at,
                )
                if all(value is not None for value in binding_values)
                else None
            )

        before_asset = _asset_state_snapshot(asset)
        before_inventory = _inventory_snapshot(inventory)
        if new_binding is None:
            _change_inventory(inventory, available_delta=1, allocated_delta=-1)
            _apply_binding(asset, None)
            asset.status = FixedAssetStatus.IDLE.value
            inventory_changed = True
        else:
            _apply_binding(asset, new_binding)
            asset.status = FixedAssetStatus.IN_USE.value
            inventory_changed = False

        event = _add_lifecycle_event(
            db,
            asset_id=asset.id,
            event_type="REPAIR_COMPLETED",
            previous_binding=None,
            new_binding=new_binding,
            operator_id=operator_id,
            terminal_inventory_id=inventory.id,
        )
        _add_asset_log(
            db,
            asset=asset,
            action="固定资产维修完成",
            description=(
                "维修完成后恢复使用中" if new_binding else "维修完成后回到闲置"
            ),
            before=before_asset,
            after=_asset_state_snapshot(asset),
            operator=operator,
        )
        if inventory_changed:
            _add_inventory_log(
                db,
                inventory=inventory,
                action="固定资产维修完成入库",
                description=(
                    f"资产编号 {asset.fixed_asset_number} 维修完成：可用库存 "
                    f"{before_inventory['available_quantity']} → {inventory.available_quantity}，"
                    f"已分配 {before_inventory['allocated_quantity']} → {inventory.allocated_quantity}"
                ),
                operator=operator,
            )
        transaction.flush()
        audit_log = _record_audit(
            transaction,
            operator_id=operator_id,
            action="fixed_asset_repair_completed",
            asset=asset,
            description=f"固定资产 {asset.fixed_asset_number} 维修完成",
            before={"asset": before_asset, "inventory": before_inventory},
            after={"asset": _asset_state_snapshot(asset), "inventory": _inventory_snapshot(inventory)},
            inventory=inventory,
            related_records={"asset_lifecycle_event_id": event.id},
        )

    return AssetLifecycleResult(asset, inventory, audit_log, lifecycle_event=event)
