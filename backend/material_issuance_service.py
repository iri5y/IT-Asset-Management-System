"""普通非固定物料发放及待归还记录归还的领域事务服务。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from importlib import import_module
from typing import Any, Optional

from sqlalchemy.orm import Session

import models
from category_policy import CategoryPolicyError, IssuePolicy, require_issue_policy
from transaction_audit import DomainTransaction, domain_transaction, snapshot


class MaterialIssuanceError(ValueError):
    """低值物料发放或归还不满足业务规则时抛出的中文领域错误。"""


class MaterialNotFoundError(MaterialIssuanceError):
    """发放关联的物料不存在。"""


class MaterialIssueNotFoundError(MaterialIssuanceError):
    """待归还关联的发放记录不存在。"""


class MaterialStockConflictError(MaterialIssuanceError):
    """库存或未归还余额不足时拒绝本次写操作。"""


@dataclass(frozen=True)
class MaterialIssueResult:
    """普通物料发放提交后的领域记录、库存和审计结果。"""

    issue: models.MaterialIssue
    warehouse_asset: models.WarehouseAsset
    audit_log: models.OperationLog


@dataclass(frozen=True)
class MaterialReturnResult:
    """低值物料归还提交后的领域记录、库存和审计结果。"""

    material_return: models.MaterialReturn
    issue: models.MaterialIssue
    warehouse_asset: models.WarehouseAsset
    audit_log: models.OperationLog


def issue_material(
    db: Session,
    *,
    warehouse_asset_id: int,
    quantity: int,
    issued_at: datetime,
    operator_id: int,
    recipient_name: Optional[str] = None,
    recipient_employee_id: Optional[str] = None,
    recipient_department: Optional[str] = None,
    purpose: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> MaterialIssueResult:
    """发放一笔活动非固定物料，并按策略创建互斥的低值领用记录。

    领用人、工号、部门和用途都是补充字段，服务不会清洗或补默认值，
    以确保经办人填写的内容原样保存在结构化发放记录中。
    """
    _require_positive_id(warehouse_asset_id, "物料")
    _require_positive_quantity(quantity, "发放数量")
    issued_at = _require_datetime(issued_at, "发放日期和时间")
    _require_positive_id(operator_id, "经办人")

    with domain_transaction(db) as transaction:
        operator = _lock_active_operator(transaction, operator_id)
        material = transaction.lock_one(models.WarehouseAsset, warehouse_asset_id)
        if material is None:
            raise MaterialNotFoundError("物料不存在")

        _validate_active_material(db, material)
        policy = _require_material_policy(material)
        _ensure_available_stock(material, quantity)
        material_before = _inventory_snapshot(material)

        if policy is IssuePolicy.RETURNABLE:
            record_type = IssuePolicy.RETURNABLE.value
            unreturned_quantity = quantity
            consumed_completed = False
        else:
            record_type = IssuePolicy.CONSUMABLE.value
            unreturned_quantity = 0
            consumed_completed = True

        material.available_quantity -= quantity
        material.allocated_quantity += quantity
        issue = models.MaterialIssue(
            warehouse_asset_id=material.id,
            record_type=record_type,
            issue_policy=policy.value,
            quantity=quantity,
            unreturned_quantity=unreturned_quantity,
            consumed_completed=consumed_completed,
            recipient_name=recipient_name,
            recipient_employee_id=recipient_employee_id,
            recipient_department=recipient_department,
            purpose=purpose,
            operator_id=operator.id,
            issued_at=issued_at,
        )
        db.add(issue)
        transaction.flush()

        audit_log = transaction.record_audit(
            user_id=operator.id,
            action="issue_material",
            resource_type="material_issue",
            resource_id=issue.id,
            description=f"发放物料「{material.name}」数量 {quantity}",
            before={"warehouse_inventory": material_before},
            after={
                "material_issue": snapshot(issue),
                "warehouse_inventory": _inventory_snapshot(material),
            },
            related_records={
                "warehouse_asset_id": material.id,
                "issue_policy": policy.value,
            },
            ip_address=ip_address,
        )

    return MaterialIssueResult(issue=issue, warehouse_asset=material, audit_log=audit_log)


def return_material(
    db: Session,
    *,
    material_issue_id: int,
    quantity: int,
    returned_at: datetime,
    operator_id: int,
    ip_address: Optional[str] = None,
) -> MaterialReturnResult:
    """部分或全量归还待归还记录，并原子回补实际归还数量的库存。"""
    _require_positive_id(material_issue_id, "低值领用记录")
    _require_positive_quantity(quantity, "归还数量")
    returned_at = _require_datetime(returned_at, "归还日期和时间")
    _require_positive_id(operator_id, "经办人")

    with domain_transaction(db) as transaction:
        operator = _lock_active_operator(transaction, operator_id)
        issue = transaction.lock_one(models.MaterialIssue, material_issue_id)
        if issue is None:
            raise MaterialIssueNotFoundError("待归还记录不存在")

        _require_returnable_issue(issue)
        material = transaction.lock_one(models.WarehouseAsset, issue.warehouse_asset_id)
        if material is None:
            raise MaterialNotFoundError("待归还记录关联的物料不存在")

        _validate_active_material(db, material)
        _ensure_return_quantity(issue, material, quantity)
        issue_before = _issue_snapshot(issue)
        material_before = _inventory_snapshot(material)

        issue.unreturned_quantity -= quantity
        material.available_quantity += quantity
        material.allocated_quantity -= quantity
        material_return = models.MaterialReturn(
            material_issue_id=issue.id,
            quantity=quantity,
            returned_at=returned_at,
            operator_id=operator.id,
        )
        db.add(material_return)
        transaction.flush()

        audit_log = transaction.record_audit(
            user_id=operator.id,
            action="return_material",
            resource_type="material_return",
            resource_id=material_return.id,
            description=f"归还物料「{material.name}」数量 {quantity}",
            before={
                "material_issue": issue_before,
                "warehouse_inventory": material_before,
            },
            after={
                "material_return": snapshot(material_return),
                "material_issue": _issue_snapshot(issue),
                "warehouse_inventory": _inventory_snapshot(material),
            },
            related_records={
                "material_issue_id": issue.id,
                "warehouse_asset_id": material.id,
            },
            ip_address=ip_address,
        )

    return MaterialReturnResult(
        material_return=material_return,
        issue=issue,
        warehouse_asset=material,
        audit_log=audit_log,
    )


def _lock_active_operator(
    transaction: DomainTransaction,
    operator_id: int,
) -> models.User:
    operator = transaction.lock_one(models.User, operator_id)
    if operator is None or operator.is_active is not True:
        raise MaterialIssuanceError("经办人不存在或已停用")
    return operator


def _validate_active_material(db: Session, material: models.WarehouseAsset) -> None:
    """验证物料是活动的非固定资产物料，且分类组合仍然有效。"""
    if material.material_kind != "NON_FIXED":
        raise MaterialIssuanceError("仅非固定资产物料可办理低值领用")
    if material.classification_status != "ACTIVE":
        raise MaterialIssuanceError("该物料分类待处理，请先完成一级和二级分类映射")
    if material.primary_category_id is None or material.secondary_category_id is None:
        raise MaterialIssuanceError("物料缺少有效的一级和二级分类组合")

    _delegate_category_pair_validation(db, material)


def _delegate_category_pair_validation(
    db: Session,
    material: models.WarehouseAsset,
) -> None:
    """复用仓储分类服务校验一级、二级分类均启用且从属关系有效。"""
    try:
        category_service = import_module("warehouse_category_service")
        validator = getattr(category_service, "validate_active_category_pair")
        validator(db, material.primary_category_id, material.secondary_category_id)
    except ValueError as error:
        raise MaterialIssuanceError(str(error)) from error


def _require_material_policy(material: models.WarehouseAsset) -> IssuePolicy:
    """校验活动目录项存储的领用策略及其分类限制。"""
    primary_name = None
    if material.primary_category is not None:
        primary_name = material.primary_category.name
    else:
        primary = (
            material.__dict__.get("primary_category")
            or None
        )
        if primary is not None:
            primary_name = primary.name

    try:
        return require_issue_policy(
            material.issue_policy,
            primary_category=primary_name,
            material_name=material.name,
        )
    except (CategoryPolicyError, AttributeError, TypeError) as error:
        raise MaterialIssuanceError(f"物料领用策略无效：{error}") from error


def _require_returnable_issue(issue: models.MaterialIssue) -> None:
    if (
        issue.record_type == IssuePolicy.CONSUMABLE.value
        or issue.issue_policy == IssuePolicy.CONSUMABLE.value
        or issue.consumed_completed is True
    ):
        raise MaterialIssuanceError("一次性消耗品不允许归还")
    if (
        issue.record_type != IssuePolicy.RETURNABLE.value
        or issue.issue_policy != IssuePolicy.RETURNABLE.value
        or issue.consumed_completed is not False
    ):
        raise MaterialIssuanceError("低值领用记录不是有效的待归还记录")


def _ensure_available_stock(material: models.WarehouseAsset, quantity: int) -> None:
    available_quantity = material.available_quantity
    if not isinstance(available_quantity, int) or isinstance(available_quantity, bool):
        raise MaterialIssuanceError("物料可用库存无效")
    if available_quantity < quantity:
        raise MaterialStockConflictError("物料可用库存不足")


def _ensure_return_quantity(
    issue: models.MaterialIssue,
    material: models.WarehouseAsset,
    quantity: int,
) -> None:
    unreturned_quantity = issue.unreturned_quantity
    if not isinstance(unreturned_quantity, int) or isinstance(unreturned_quantity, bool):
        raise MaterialIssuanceError("待归还记录的未归还数量无效")
    if unreturned_quantity <= 0:
        raise MaterialStockConflictError("待归还记录已全部归还")
    if quantity > unreturned_quantity:
        raise MaterialStockConflictError("归还数量不能超过未归还数量")

    allocated_quantity = material.allocated_quantity
    if not isinstance(allocated_quantity, int) or isinstance(allocated_quantity, bool):
        raise MaterialIssuanceError("物料已分配库存无效")
    if allocated_quantity < quantity:
        raise MaterialStockConflictError("物料已分配库存不足，无法归还")


def _require_positive_id(value: Any, label: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise MaterialIssuanceError(f"{label}标识无效")


def _require_positive_quantity(value: Any, label: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise MaterialIssuanceError(f"{label}必须为大于零的整数")


def _require_datetime(value: Any, label: str) -> datetime:
    if not isinstance(value, datetime):
        raise MaterialIssuanceError(f"{label}无效")
    if value.tzinfo is not None:
        return value.astimezone(models.CHINA_TZ).replace(tzinfo=None)
    return value


def _inventory_snapshot(material: models.WarehouseAsset) -> dict[str, Any]:
    return snapshot(
        material,
        fields=(
            "id",
            "available_quantity",
            "allocated_quantity",
            "total_quantity",
            "classification_status",
            "primary_category_id",
            "secondary_category_id",
            "issue_policy",
        ),
    ) or {}


def _issue_snapshot(issue: models.MaterialIssue) -> dict[str, Any]:
    return snapshot(
        issue,
        fields=(
            "id",
            "warehouse_asset_id",
            "record_type",
            "issue_policy",
            "quantity",
            "unreturned_quantity",
            "consumed_completed",
        ),
    ) or {}


@dataclass(frozen=True)
class SpecializedMaterialIssueResult:
    """维修、网络和办公耗材发放的领域记录、库存与审计结果。"""

    issue: models.MaterialIssue
    specialized_issue: models.RepairPartIssue | models.NetworkConsumableIssue | None
    warehouse_asset: models.WarehouseAsset
    audit_log: models.OperationLog


@dataclass(frozen=True)
class ToolLoanResult:
    """工具借出后的借用记录、库存和审计结果。"""

    loan: models.ToolLoan
    warehouse_asset: models.WarehouseAsset
    audit_log: models.OperationLog


@dataclass(frozen=True)
class ToolLoanReturnResult:
    """工具归还后的归还事件、借用状态、库存和审计结果。"""

    return_event: models.ToolLoanReturnEvent
    loan: models.ToolLoan
    warehouse_asset: models.WarehouseAsset
    audit_log: models.OperationLog


def issue_repair_part(
    db: Session,
    *,
    warehouse_asset_id: int,
    quantity: int,
    issued_at: datetime,
    operator_id: int,
    target_asset_id: Optional[int] = None,
    repair_order_ref: Optional[str] = None,
    disk_serial_number: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> SpecializedMaterialIssueResult:
    """发放维修备件，并保存有效资产或外部维修单关联。"""
    _require_positive_id(warehouse_asset_id, "维修备件物料")
    _require_positive_quantity(quantity, "发放数量")
    issued_at = _require_datetime(issued_at, "发放日期和时间")
    _require_positive_id(operator_id, "经办人")
    repair_order_ref = _clean_optional_reference(repair_order_ref, "维修单号")
    disk_serial_number = _clean_optional_reference(disk_serial_number, "硬盘序列号")
    if target_asset_id is None and repair_order_ref is None:
        raise MaterialIssuanceError("维修备件必须关联有效资产或维修单")
    if target_asset_id is not None:
        _require_positive_id(target_asset_id, "维修资产")

    with domain_transaction(db) as transaction:
        operator = _lock_active_operator(transaction, operator_id)
        material = transaction.lock_one(models.WarehouseAsset, warehouse_asset_id)
        if material is None:
            raise MaterialNotFoundError("维修备件物料不存在")
        _validate_specialized_material(db, material, "STORAGE_REPAIR_PARTS", "维修备件")

        target_asset = None
        if target_asset_id is not None:
            target_asset = transaction.lock_one(models.Asset, target_asset_id)
            if target_asset is None or target_asset.is_deleted is True:
                raise MaterialNotFoundError("维修关联的固定资产不存在或已删除")

        issue, material_before = _create_consumable_issue(
            db, transaction, material, quantity, issued_at, operator.id
        )
        repair_issue = models.RepairPartIssue(
            material_issue_id=issue.id,
            target_asset_id=target_asset.id if target_asset else None,
            repair_order_ref=repair_order_ref,
            disk_serial_number=disk_serial_number,
        )
        db.add(repair_issue)
        transaction.flush()
        audit_log = transaction.record_audit(
            user_id=operator.id,
            action="issue_repair_part",
            resource_type="repair_part_issue",
            resource_id=repair_issue.id,
            description=f"发放维修备件「{material.name}」数量 {quantity}",
            before={"warehouse_inventory": material_before},
            after={
                "material_issue": _issue_snapshot(issue),
                "repair_part_issue": snapshot(repair_issue),
                "warehouse_inventory": _inventory_snapshot(material),
            },
            related_records={
                "warehouse_asset_id": material.id,
                "target_asset_id": target_asset.id if target_asset else None,
                "repair_order_ref": repair_order_ref,
            },
            ip_address=ip_address,
        )
    return SpecializedMaterialIssueResult(issue, repair_issue, material, audit_log)


def issue_network_consumable(
    db: Session,
    *,
    warehouse_asset_id: int,
    quantity: int,
    issued_at: datetime,
    operator_id: int,
    department_id: Optional[int] = None,
    project_ref: Optional[str] = None,
    server_room_ref: Optional[str] = None,
    work_order_ref: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> SpecializedMaterialIssueResult:
    """发放网络/机房耗材；用途可全空，填写后须含至少一个有效关联。"""
    _require_positive_id(warehouse_asset_id, "网络与机房耗材物料")
    _require_positive_quantity(quantity, "发放数量")
    issued_at = _require_datetime(issued_at, "发放日期和时间")
    _require_positive_id(operator_id, "经办人")
    if department_id is not None:
        _require_positive_id(department_id, "用途部门")
    project_ref = _clean_optional_reference(project_ref, "项目")
    server_room_ref = _clean_optional_reference(server_room_ref, "机房")
    work_order_ref = _clean_optional_reference(work_order_ref, "工单")

    with domain_transaction(db) as transaction:
        operator = _lock_active_operator(transaction, operator_id)
        material = transaction.lock_one(models.WarehouseAsset, warehouse_asset_id)
        if material is None:
            raise MaterialNotFoundError("网络与机房耗材物料不存在")
        _validate_specialized_material(
            db, material, "NETWORK_SERVER_ROOM_CONSUMABLES", "网络与机房耗材"
        )

        department = None
        if department_id is not None:
            department = transaction.lock_one(models.Department, department_id)
            if department is None:
                raise MaterialNotFoundError("用途关联的部门不存在")

        issue, material_before = _create_consumable_issue(
            db, transaction, material, quantity, issued_at, operator.id
        )
        network_issue = models.NetworkConsumableIssue(
            material_issue_id=issue.id,
            department_id=department.id if department else None,
            project_ref=project_ref,
            server_room_ref=server_room_ref,
            work_order_ref=work_order_ref,
        )
        db.add(network_issue)
        transaction.flush()
        audit_log = transaction.record_audit(
            user_id=operator.id,
            action="issue_network_consumable",
            resource_type="network_consumable_issue",
            resource_id=network_issue.id,
            description=f"发放网络与机房耗材「{material.name}」数量 {quantity}",
            before={"warehouse_inventory": material_before},
            after={
                "material_issue": _issue_snapshot(issue),
                "network_consumable_issue": snapshot(network_issue),
                "warehouse_inventory": _inventory_snapshot(material),
            },
            related_records={
                "warehouse_asset_id": material.id,
                "department_id": department.id if department else None,
                "project_ref": project_ref,
                "server_room_ref": server_room_ref,
                "work_order_ref": work_order_ref,
            },
            ip_address=ip_address,
        )
    return SpecializedMaterialIssueResult(issue, network_issue, material, audit_log)


def issue_office_consumable(
    db: Session,
    *,
    warehouse_asset_id: int,
    quantity: int,
    issued_at: datetime,
    operator_id: int,
    ip_address: Optional[str] = None,
) -> SpecializedMaterialIssueResult:
    """办公通用耗材只按一次性消耗处理。"""
    _require_positive_id(warehouse_asset_id, "办公耗材物料")
    _require_positive_quantity(quantity, "发放数量")
    issued_at = _require_datetime(issued_at, "发放日期和时间")
    _require_positive_id(operator_id, "经办人")

    with domain_transaction(db) as transaction:
        operator = _lock_active_operator(transaction, operator_id)
        material = transaction.lock_one(models.WarehouseAsset, warehouse_asset_id)
        if material is None:
            raise MaterialNotFoundError("办公耗材物料不存在")
        _validate_specialized_material(
            db, material, "OFFICE_GENERAL_CONSUMABLES", "办公与通用耗材"
        )
        if _require_material_policy(material) is not IssuePolicy.CONSUMABLE:
            raise MaterialIssuanceError("办公与通用耗材仅支持“一次性消耗品”领用策略")

        issue, material_before = _create_consumable_issue(
            db, transaction, material, quantity, issued_at, operator.id
        )
        audit_log = transaction.record_audit(
            user_id=operator.id,
            action="issue_office_consumable",
            resource_type="material_issue",
            resource_id=issue.id,
            description=f"发放办公与通用耗材「{material.name}」数量 {quantity}",
            before={"warehouse_inventory": material_before},
            after={
                "material_issue": _issue_snapshot(issue),
                "warehouse_inventory": _inventory_snapshot(material),
            },
            related_records={
                "warehouse_asset_id": material.id,
                "issue_policy": IssuePolicy.CONSUMABLE.value,
            },
            ip_address=ip_address,
        )
    return SpecializedMaterialIssueResult(issue, None, material, audit_log)


def borrow_tool(
    db: Session,
    *,
    warehouse_asset_id: int,
    quantity: int,
    borrowed_at: datetime,
    expected_return_at: datetime,
    operator_id: int,
    borrower_id: Optional[int] = None,
    borrower_ref: Optional[str] = None,
    tool_identifier: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> ToolLoanResult:
    """借出 IT 工具；优先绑定在职员工，同时兼容历史自由文本借用人。"""
    _require_positive_id(warehouse_asset_id, "IT工具物料")
    _require_positive_quantity(quantity, "借用数量")
    if borrower_id is None and borrower_ref is None:
        raise MaterialIssuanceError("借用员工或借用人文本至少填写一项")
    if borrower_id is not None:
        _require_positive_id(borrower_id, "借用员工")
    borrower_ref = _clean_optional_reference(borrower_ref, "借用人")
    borrowed_at = _require_datetime(borrowed_at, "借出日期和时间")
    expected_return_at = _require_datetime(expected_return_at, "预计归还日期")
    if expected_return_at < borrowed_at:
        raise MaterialIssuanceError("预计归还日期不能早于借出日期")
    _require_positive_id(operator_id, "经办人")
    tool_identifier = _clean_optional_reference(tool_identifier, "工具编号或二维码")

    with domain_transaction(db) as transaction:
        operator = _lock_active_operator(transaction, operator_id)
        borrower = None
        if borrower_id is not None:
            borrower = transaction.lock_one(models.Employee, borrower_id)
            if borrower is None:
                raise MaterialNotFoundError("借用员工不存在")
            if borrower.status != "ACTIVE":
                raise MaterialIssuanceError("仅在职员工可以借用IT工具")
            borrower_ref = f"{borrower.name}（{borrower.employee_number}）"

        # 旧方式仅传 borrower_ref 时保持原行为；新方式始终使用员工主数据快照。
        if borrower_ref is None:
            raise MaterialIssuanceError("借用人不能为空")

        material = transaction.lock_one(models.WarehouseAsset, warehouse_asset_id)
        if material is None:
            raise MaterialNotFoundError("IT工具物料不存在")
        _validate_specialized_material(db, material, "IT_TOOLS_LOAN_ITEMS", "IT工具")
        _ensure_available_stock(material, quantity)
        material_before = _inventory_snapshot(material)
        material.available_quantity -= quantity
        material.allocated_quantity += quantity
        loan = models.ToolLoan(
            warehouse_asset_id=material.id,
            borrower_id=borrower.id if borrower is not None else None,
            borrower_ref=borrower_ref,
            quantity=quantity,
            unreturned_quantity=quantity,
            status="BORROWED",
            borrowed_at=borrowed_at,
            expected_return_at=expected_return_at,
            tool_identifier=tool_identifier,
            operator_id=operator.id,
        )
        db.add(loan)
        transaction.flush()
        audit_log = transaction.record_audit(
            user_id=operator.id,
            action="borrow_tool",
            resource_type="tool_loan",
            resource_id=loan.id,
            description=f"借出IT工具「{material.name}」数量 {quantity}",
            before={"warehouse_inventory": material_before},
            after={
                "tool_loan": _tool_loan_snapshot(loan),
                "warehouse_inventory": _inventory_snapshot(material),
            },
            related_records={
                "warehouse_asset_id": material.id,
                "borrower_id": borrower.id if borrower is not None else None,
            },
            ip_address=ip_address,
        )
    return ToolLoanResult(loan, material, audit_log)


def return_tool(
    db: Session,
    *,
    tool_loan_id: int,
    quantity: int,
    returned_at: datetime,
    operator_id: int,
    ip_address: Optional[str] = None,
) -> ToolLoanReturnResult:
    """部分或全量归还 IT 工具，并按余额维护 BORROWED/RETURNED 状态。"""
    _require_positive_id(tool_loan_id, "工具借用记录")
    _require_positive_quantity(quantity, "归还数量")
    returned_at = _require_datetime(returned_at, "归还日期和时间")
    _require_positive_id(operator_id, "经办人")

    with domain_transaction(db) as transaction:
        operator = _lock_active_operator(transaction, operator_id)
        loan = transaction.lock_one(models.ToolLoan, tool_loan_id)
        if loan is None:
            raise MaterialIssueNotFoundError("工具借用记录不存在")
        if loan.status != "BORROWED" or loan.unreturned_quantity <= 0:
            raise MaterialStockConflictError("工具借用记录不是未归还状态")
        if quantity > loan.unreturned_quantity:
            raise MaterialStockConflictError("归还数量不能超过未归还数量")
        material = transaction.lock_one(models.WarehouseAsset, loan.warehouse_asset_id)
        if material is None:
            raise MaterialNotFoundError("工具借用记录关联的物料不存在")
        _validate_specialized_material(db, material, "IT_TOOLS_LOAN_ITEMS", "IT工具")
        if material.allocated_quantity < quantity:
            raise MaterialStockConflictError("物料已分配库存不足，无法归还")

        loan_before = _tool_loan_snapshot(loan)
        material_before = _inventory_snapshot(material)
        previous_balance = loan.unreturned_quantity
        loan.unreturned_quantity -= quantity
        loan.status = "RETURNED" if loan.unreturned_quantity == 0 else "BORROWED"
        if loan.status == "RETURNED":
            loan.returned_at = returned_at
        material.available_quantity += quantity
        material.allocated_quantity -= quantity
        return_event = models.ToolLoanReturnEvent(
            tool_loan_id=loan.id,
            quantity=quantity,
            is_partial=quantity < previous_balance,
            returned_at=returned_at,
            operator_id=operator.id,
        )
        db.add(return_event)
        transaction.flush()
        audit_log = transaction.record_audit(
            user_id=operator.id,
            action="return_tool",
            resource_type="tool_loan_return_event",
            resource_id=return_event.id,
            description=f"归还IT工具「{material.name}」数量 {quantity}",
            before={
                "tool_loan": loan_before,
                "warehouse_inventory": material_before,
            },
            after={
                "tool_loan_return_event": snapshot(return_event),
                "tool_loan": _tool_loan_snapshot(loan),
                "warehouse_inventory": _inventory_snapshot(material),
            },
            related_records={
                "tool_loan_id": loan.id,
                "warehouse_asset_id": material.id,
            },
            ip_address=ip_address,
        )
    return ToolLoanReturnResult(return_event, loan, material, audit_log)


def _create_consumable_issue(
    db: Session,
    transaction: DomainTransaction,
    material: models.WarehouseAsset,
    quantity: int,
    issued_at: datetime,
    operator_id: int,
) -> tuple[models.MaterialIssue, dict[str, Any]]:
    """扣减已锁定物料并创建固定一次性消耗发放记录。"""
    _ensure_available_stock(material, quantity)
    material_before = _inventory_snapshot(material)
    material.available_quantity -= quantity
    material.allocated_quantity += quantity
    issue = models.MaterialIssue(
        warehouse_asset_id=material.id,
        record_type=IssuePolicy.CONSUMABLE.value,
        issue_policy=IssuePolicy.CONSUMABLE.value,
        quantity=quantity,
        unreturned_quantity=0,
        consumed_completed=True,
        operator_id=operator_id,
        issued_at=issued_at,
    )
    db.add(issue)
    transaction.flush()
    return issue, material_before


def _validate_specialized_material(
    db: Session,
    material: models.WarehouseAsset,
    expected_primary_code: str,
    label: str,
) -> None:
    _validate_active_material(db, material)
    primary = db.query(models.WarehousePrimaryCategory).filter(
        models.WarehousePrimaryCategory.id == material.primary_category_id
    ).one_or_none()
    if primary is None or primary.code != expected_primary_code:
        raise MaterialIssuanceError(f"所选物料不是有效的{label}")


def _require_nonblank_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MaterialIssuanceError(f"{label}不能为空")
    return value.strip()


def _clean_optional_reference(value: Optional[str], label: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise MaterialIssuanceError(f"{label}无效")
    normalized = value.strip()
    if not normalized:
        raise MaterialIssuanceError(f"{label}不能为空")
    return normalized


def _tool_loan_snapshot(loan: models.ToolLoan) -> dict[str, Any]:
    return snapshot(
        loan,
        fields=(
            "id",
            "warehouse_asset_id",
            "borrower_id",
            "borrower_ref",
            "quantity",
            "unreturned_quantity",
            "status",
            "borrowed_at",
            "expected_return_at",
            "returned_at",
            "tool_identifier",
        ),
    ) or {}
