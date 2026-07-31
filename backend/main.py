from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
import inspect
from backup_service import execute_backup, BACKUP_DIR

import csv
import os
import json
import io

import import_service
import asset_lifecycle_service
import warehouse_category_service
import warehouse_material_service
from category_policy import is_fixed_asset_category
from transaction_audit import DomainTransactionError

from import_v2.classifier import Classifier
from import_v2.domain_models import (
    BrandRef,
    DepartmentRef,
    ImportContext,
    LocationRef,
    LocationType,
    PolicyDecision,
    RecordClassification,
)
from import_v2.import_policy import ImportPolicy, ImportPolicyType
from import_v2.import_session import (
    InMemorySessionStore,
    MappingEntry,
    MappingFieldType,
    SessionStatus,
    get_session_store,
    make_mapping_key,
)
from import_v2.pipeline import ImportPipeline, PreviewSummary
from import_v2.executor import Executor, ImportExecutionError

import models
import schemas
from database import engine, get_db
from auth import get_current_active_user, require_admin
from auth_routes import router as auth_router

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="IT Asset Management API")


class WizardImportAPIError(Exception):
    """Wizard 导入接口的可追踪业务错误。"""

    def __init__(self, status_code: int, detail, request_id: str):
        self.status_code = status_code
        self.detail = detail
        self.request_id = request_id


@app.exception_handler(WizardImportAPIError)
async def handle_wizard_import_error(
    request: Request,
    exc: WizardImportAPIError,
):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "request_id": exc.request_id},
    )


def require_write_permission(current_user: models.User = Depends(get_current_active_user)):
    """检查当前用户是否拥有写入权限（拦截只读用户）"""
    if current_user.role == 'readonly':
        raise HTTPException(status_code=403, detail="只读账号无权限执行修改或新增操作")
    return current_user

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


# ========== 合法状态转换表 ==========
# 定义每个状态允许转换到哪些目标状态，防止非法跳变
VALID_STATUS_TRANSITIONS = {
    "闲置":  {"使用中", "维修中", "报废"},
    "使用中": {"闲置", "维修中", "报废"},
    "维修中": {"闲置", "使用中", "报废"},
    "报废":  set(),  # 报废是终态，不允许再转换
}
ALL_VALID_STATUSES = set(VALID_STATUS_TRANSITIONS.keys())


def create_log(db, asset_id, action, description=None, old_value=None, new_value=None, operator=None):
    log = models.AssetLog(asset_id=asset_id, action=action, description=description, old_value=old_value, new_value=new_value, operator=operator)
    db.add(log)
    db.flush()


def create_hostname_history(db, asset_id, old_hostname, new_hostname, reason=None):
    history = models.HostnameHistory(asset_id=asset_id, old_hostname=old_hostname, new_hostname=new_hostname, change_reason=reason or "资产名变更")
    db.add(history)
    db.flush()


def create_operation_log(db, user_id, action, resource_type, resource_id=None, description=None, old_value=None, new_value=None):
    log = models.OperationLog(user_id=user_id, action=action, resource_type=resource_type, resource_id=resource_id, description=description, old_value=old_value, new_value=new_value)
    db.add(log)
    db.flush()


@app.get("/")
def read_root():
    return {"message": "IT Asset Management API"}


# Employee Schema 由员工主数据任务提供；回退为 dict 可保持旧部署可导入。
EmployeeCreateSchema = getattr(schemas, "EmployeeCreate", dict)
EmployeeUpdateSchema = getattr(schemas, "EmployeeUpdate", dict)


def _request_data(payload, *, exclude_unset: bool = False) -> dict:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_unset=exclude_unset)
    if hasattr(payload, "dict"):
        return payload.dict(exclude_unset=exclude_unset)
    return dict(payload)


def _employee_snapshot_ref(employee: "models.Employee") -> str:
    return f"{employee.name}（{employee.employee_number}）"


def _employee_payload(employee: "models.Employee") -> dict:
    return {
        "id": employee.id,
        "employee_number": employee.employee_number,
        "name": employee.name,
        "department": employee.department,
        "status": employee.status,
        "departure_date": employee.departure_date,
        "created_at": employee.created_at,
        "updated_at": employee.updated_at,
    }


def _employee_brief_payload(employee: Optional["models.Employee"]) -> Optional[dict]:
    if employee is None:
        return None
    return {
        "id": employee.id,
        "employee_number": employee.employee_number,
        "name": employee.name,
        "department": employee.department,
        "status": employee.status,
    }


def _normalize_employee_state(data: dict, current: Optional["models.Employee"] = None) -> dict:
    status = str(data.get("status", current.status if current else "ACTIVE")).strip().upper()
    if not status:
        raise HTTPException(status_code=400, detail="员工状态不能为空")
    data["status"] = status
    if status == "ACTIVE":
        # ACTIVE 员工不得残留离职日期，创建和更新统一清空。
        data["departure_date"] = None
    else:
        departure_date = data.get(
            "departure_date", current.departure_date if current else None
        )
        if departure_date is None:
            raise HTTPException(status_code=400, detail="非在职员工必须填写离职日期")
        data["departure_date"] = departure_date
    return data


def _lock_active_employee(db: Session, employee_id: int) -> "models.Employee":
    employee = (
        db.query(models.Employee)
        .filter(models.Employee.id == employee_id)
        .with_for_update()
        .one_or_none()
    )
    if employee is None:
        raise HTTPException(status_code=404, detail="员工不存在")
    if employee.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="仅可绑定在职员工")
    return employee


def _apply_employee_asset_snapshot(asset_data: dict, employee: "models.Employee") -> None:
    asset_data["employee_ref_id"] = employee.id
    asset_data["employee_name"] = employee.name
    asset_data["employee_id"] = employee.employee_number
    asset_data["department"] = employee.department


def _asset_current_payload(asset: models.Asset) -> dict:
    return {
        "id": asset.id,
        "asset_tag": asset.asset_tag,
        "category": asset.category,
        "status": asset.status,
        "employee_ref_id": asset.employee_ref_id,
        "employee_name": asset.employee_name,
        "employee_id": asset.employee_id,
        "department": asset.department,
        "hostname": asset.hostname,
    }


@app.post("/employees")
def create_employee(
    payload: EmployeeCreateSchema,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_write_permission),
):
    data = _normalize_employee_state(_request_data(payload))
    employee_number = str(data.get("employee_number") or "").strip()
    name = str(data.get("name") or "").strip()
    if not employee_number or not name:
        raise HTTPException(status_code=400, detail="员工姓名和工号不能为空")
    data["employee_number"] = employee_number
    data["name"] = name
    if db.query(models.Employee.id).filter(
        models.Employee.employee_number == employee_number
    ).first():
        raise HTTPException(status_code=409, detail="员工工号已存在")
    try:
        employee = models.Employee(**data)
        db.add(employee)
        db.flush()
        create_operation_log(
            db,
            current_user.id,
            "create",
            "employee",
            employee.id,
            f"新建员工 {employee.name}（{employee.employee_number}）",
            new_value=json.dumps(_employee_payload(employee), ensure_ascii=False, default=str),
        )
        db.commit()
        db.refresh(employee)
        return _employee_payload(employee)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="员工工号已存在") from error
    except HTTPException:
        db.rollback()
        raise
    except Exception as error:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"创建员工失败：{error}") from error


@app.get("/employees")
def read_employees(
    status: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    query = db.query(models.Employee)
    if status:
        query = query.filter(models.Employee.status == status.strip().upper())
    if search and search.strip():
        keyword = f"%{search.strip()}%"
        query = query.filter(or_(
            models.Employee.name.ilike(keyword),
            models.Employee.employee_number.ilike(keyword),
            models.Employee.department.ilike(keyword),
        ))
    employees = query.order_by(models.Employee.employee_number.asc()).all()
    return [_employee_payload(employee) for employee in employees]


@app.get("/employees/reports/inactive-held")
@app.get("/reports/inactive-employee-holdings", include_in_schema=False)
@app.get("/reports/inactive-employees-held-assets", include_in_schema=False)
def read_inactive_employee_holdings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """列出非在职员工仍绑定的当前资产和未归还工具。"""
    employees = (
        db.query(models.Employee)
        .filter(models.Employee.status != "ACTIVE")
        .order_by(models.Employee.employee_number.asc())
        .all()
    )
    records = []
    total_assets = 0
    total_tool_loans = 0
    for employee in employees:
        assets = (
            db.query(models.Asset)
            .filter(
                models.Asset.employee_ref_id == employee.id,
                models.Asset.is_deleted.is_(False),
            )
            .order_by(models.Asset.asset_tag.asc())
            .all()
        )
        loans = (
            db.query(models.ToolLoan)
            .filter(
                models.ToolLoan.borrower_id == employee.id,
                models.ToolLoan.status == "BORROWED",
                models.ToolLoan.unreturned_quantity > 0,
            )
            .order_by(models.ToolLoan.borrowed_at.desc())
            .all()
        )
        if not assets and not loans:
            continue
        total_assets += len(assets)
        total_tool_loans += len(loans)
        records.append({
            "employee": _employee_payload(employee),
            "assets": [_asset_current_payload(asset) for asset in assets],
            "tool_loans": [
                _tool_loan_payload(loan, loan.warehouse_asset, db) for loan in loans
            ],
            "asset_count": len(assets),
            "tool_loan_count": len(loans),
        })
    return {
        "employees": records,
        "employee_count": len(records),
        "asset_count": total_assets,
        "tool_loan_count": total_tool_loans,
    }


@app.get("/employees/{employee_id}")
def read_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    employee = db.query(models.Employee).filter(models.Employee.id == employee_id).one_or_none()
    if employee is None:
        raise HTTPException(status_code=404, detail="员工不存在")
    return _employee_payload(employee)


@app.patch("/employees/{employee_id}")
def update_employee(
    employee_id: int,
    payload: EmployeeUpdateSchema,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_write_permission),
):
    employee = (
        db.query(models.Employee)
        .filter(models.Employee.id == employee_id)
        .with_for_update()
        .one_or_none()
    )
    if employee is None:
        raise HTTPException(status_code=404, detail="员工不存在")
    data = _normalize_employee_state(_request_data(payload, exclude_unset=True), employee)
    for field in ("employee_number", "name"):
        if field in data:
            data[field] = str(data[field] or "").strip()
            if not data[field]:
                raise HTTPException(status_code=400, detail="员工姓名和工号不能为空")
    employee_number = data.get("employee_number", employee.employee_number)
    duplicate = db.query(models.Employee.id).filter(
        models.Employee.employee_number == employee_number,
        models.Employee.id != employee.id,
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="员工工号已存在")

    try:
        before = _employee_payload(employee)
        snapshot_changed = any(
            field in data and data[field] != getattr(employee, field)
            for field in ("name", "employee_number", "department")
        )
        for field, value in data.items():
            setattr(employee, field, value)

        if snapshot_changed:
            assets = (
                db.query(models.Asset)
                .filter(
                    models.Asset.employee_ref_id == employee.id,
                    models.Asset.is_deleted.is_(False),
                )
                .with_for_update()
                .all()
            )
            for asset in assets:
                asset.employee_name = employee.name
                asset.employee_id = employee.employee_number
                asset.department = employee.department

            loans = (
                db.query(models.ToolLoan)
                .filter(
                    models.ToolLoan.borrower_id == employee.id,
                    models.ToolLoan.status == "BORROWED",
                    models.ToolLoan.unreturned_quantity > 0,
                )
                .with_for_update()
                .all()
            )
            borrower_ref = _employee_snapshot_ref(employee)
            for loan in loans:
                loan.borrower_ref = borrower_ref

        db.flush()
        after = _employee_payload(employee)
        create_operation_log(
            db,
            current_user.id,
            "update",
            "employee",
            employee.id,
            f"更新员工 {employee.name}（{employee.employee_number}）",
            old_value=json.dumps(before, ensure_ascii=False, default=str),
            new_value=json.dumps(after, ensure_ascii=False, default=str),
        )
        db.commit()
        db.refresh(employee)
        return _employee_payload(employee)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="员工工号已存在") from error
    except HTTPException:
        db.rollback()
        raise
    except Exception as error:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"更新员工失败：{error}") from error


@app.get("/employees/{employee_id}/assets")
def read_employee_assets(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    employee = db.query(models.Employee).filter(models.Employee.id == employee_id).one_or_none()
    if employee is None:
        raise HTTPException(status_code=404, detail="员工不存在")
    assets = (
        db.query(models.Asset)
        .filter(
            models.Asset.employee_ref_id == employee.id,
            models.Asset.is_deleted.is_(False),
        )
        .order_by(models.Asset.asset_tag.asc())
        .all()
    )
    return [_asset_current_payload(asset) for asset in assets]




def _sync_warehouse_quantity(db: Session, category: str, delta: int, operator_name: str = None):
    """同步库房资产可用数量（在已有事务中调用，不单独 commit）。
    使用 with_for_update() 加行锁，防止并发操作导致数量不一致。
    资产品类与库房品类的映射关系：
      台式机/笔记本电脑 → 计算机设备
      显示器           → 显示设备
      移动设备/手机     → 移动设备
      无线鼠标         → 输入设备
      打印机           → 其他配件
      网络设备         → 网络设备
    """
    if delta == 0:
        return

    # 资产品类 → 库房品类 映射
    ASSET_TO_WAREHOUSE_CATEGORY = {
        "台式机":    "计算机设备",
        "笔记本电脑": "计算机设备",
        "显示器":    "显示设备",
        "移动设备":  "移动设备",
        "手机":      "移动设备",
        "无线鼠标":  "输入设备",
        "打印机":    "其他配件",
        "网络设备":  "网络设备",
    }
    warehouse_category = ASSET_TO_WAREHOUSE_CATEGORY.get(category, category)

    # 加行锁查询，防止并发更新
    wh_asset = (
        db.query(models.WarehouseAsset)
        .filter(models.WarehouseAsset.category == warehouse_category)
        .order_by(models.WarehouseAsset.available_quantity.desc())
        .with_for_update()
        .first()
    )
    if not wh_asset:
        return
    old_available = wh_asset.available_quantity
    old_allocated = wh_asset.allocated_quantity
    new_available = wh_asset.available_quantity + delta
    if new_available < 0:
        raise HTTPException(status_code=409, detail=f"库房品类「{warehouse_category}」可用库存不足，无法扣减")
    wh_asset.available_quantity = new_available
    wh_asset.allocated_quantity = max(0, wh_asset.total_quantity - wh_asset.available_quantity)
    db.flush()
    action = "入库（资产归还）" if delta > 0 else "出库（资产分配）"
    desc = (f"资产状态联动更新: 可用数量 {old_available} → {wh_asset.available_quantity}, "
            f"已分配 {old_allocated} → {wh_asset.allocated_quantity}")
    wh_log = models.WarehouseAssetLog(
        asset_id=wh_asset.id, action=action, description=desc, operator=operator_name
    )
    db.add(wh_log)
    db.flush()

@app.post("/api/system/backup/export")
def export_database_backup():
    """
    触发数据库备份并直接下载.sql文件
    """
    #1.执行备份生成文件
    backup_file_path = execute_backup()
    
    if not backup_file_path or not os.path.exists(backup_file_path):
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="数据库备份失败，请检查服务器 pg_dump 配置")
    
    #2.将文件作为响应返回给前端下载
    return FileResponse(
        path=backup_file_path,
        filename=os.path.basename(backup_file_path),
        media_type="application/octet-stream"
    )


@app.post("/assets/", response_model=schemas.Asset)
def create_asset(asset: schemas.AssetCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_write_permission)):
    # PC/NB/PD 必须经受控入库建立可追溯资产卡，禁止旧通用入口绕过。
    if is_fixed_asset_category(asset.category):
        raise HTTPException(
            status_code=400,
            detail="台式机、笔记本电脑和平板电脑仅可通过受控固定资产入库创建",
        )

    # 校验状态合法性
    if asset.status not in ALL_VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"非法状态值「{asset.status}」，允许: {', '.join(ALL_VALID_STATUSES)}")

    try:
        asset_data = asset.dict()
        # 空字符串的唯一字段转为 None，避免唯一约束冲突
        for field in ['serial_number', 'fixed_asset_number']:
            if field in asset_data and not asset_data[field]:
                asset_data[field] = None

        employee_ref_id = asset_data.get("employee_ref_id")
        if asset.status == "闲置":
            if hasattr(models.Asset, "employee_ref_id"):
                asset_data["employee_ref_id"] = None
            for field in (
                "employee_id", "employee_name", "department", "supervisor", "issue_date",
            ):
                asset_data[field] = None
        elif employee_ref_id is not None:
            employee = _lock_active_employee(db, employee_ref_id)
            _apply_employee_asset_snapshot(asset_data, employee)
        elif asset.status == "使用中":
            raise HTTPException(
                status_code=400,
                detail="新建使用中资产必须指定在职员工 employee_ref_id",
            )

        db_asset = models.Asset(**asset_data)
        db.add(db_asset)
        db.flush()  # 获取 id，但不提交

        desc = f"新建资产 {asset.asset_tag}，品类: {asset.category}，状态: {asset.status}"
        operator_name = current_user.full_name or current_user.username
        create_log(db, db_asset.id, "创建资产", desc, operator=operator_name)
        create_operation_log(db, current_user.id, "create", "asset", db_asset.id, desc)

        # 如果新建资产状态为"闲置"，同步增加库房可用数量
        if asset.status == "闲置":
            _sync_warehouse_quantity(db, db_asset.category, +1, operator_name)

        db.commit()
        db.refresh(db_asset)
        return db_asset
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"创建资产失败: {str(e)}")


# ========== 受控固定资产入库与生命周期 API ==========

def _fixed_asset_result_payload(
    result: asset_lifecycle_service.AssetLifecycleResult,
) -> dict:
    """将领域结果显式序列化，避免路由层泄漏 ORM 关系对象。"""
    asset = result.asset
    inventory = result.terminal_inventory
    return {
        "asset": {
            "id": asset.id,
            "asset_tag": asset.asset_tag,
            "fixed_asset_number": asset.fixed_asset_number,
            "serial_number": asset.serial_number,
            "category": asset.category,
            "asset_category_code": asset.asset_category_code,
            "status": asset.status,
            "inbound_source": asset.inbound_source,
            "terminal_inventory_id": asset.terminal_inventory_id,
            "employee_ref_id": getattr(asset, "employee_ref_id", None),
            "employee_name": asset.employee_name,
            "employee_id": asset.employee_id,
            "department": asset.department,
            "issue_date": asset.issue_date,
        },
        "terminal_inventory": {
            "id": inventory.id,
            "total_quantity": inventory.total_quantity,
            "available_quantity": inventory.available_quantity,
            "allocated_quantity": inventory.allocated_quantity,
        },
        "inbound_id": result.inbound.id if result.inbound else None,
        "issuance_id": result.issuance.id if result.issuance else None,
        "lifecycle_event_id": (
            result.lifecycle_event.id if result.lifecycle_event else None
        ),
        "audit_log_id": result.audit_log.id,
    }


def _fixed_asset_error_status(error: Exception) -> int:
    if isinstance(error, asset_lifecycle_service.AssetLifecycleNotFoundError):
        return 404
    if isinstance(error, asset_lifecycle_service.AssetLifecycleConflictError):
        return 409
    if isinstance(error, asset_lifecycle_service.AssetLifecycleError):
        return 400
    if isinstance(error, DomainTransactionError):
        return 500
    return 500


def _fixed_asset_error_detail(error: Exception) -> str:
    # 生命周期业务异常继承领域事务异常；必须先保留其具体中文原因。
    if isinstance(error, asset_lifecycle_service.AssetLifecycleError):
        return str(error)
    if isinstance(error, DomainTransactionError):
        return error.detail
    return "固定资产业务保存失败，请稍后重试"


def _raise_fixed_asset_api_error(db: Session, error: Exception) -> None:
    db.rollback()
    raise HTTPException(
        status_code=_fixed_asset_error_status(error),
        detail=_fixed_asset_error_detail(error),
    ) from error


def _fixed_asset_binding_kwargs(callable_, payload, *, include_issued_at: bool) -> dict:
    """新契约传员工主键，旧姓名/工号/部门字段继续原样透传。"""
    kwargs = {
        "recipient_name": getattr(payload, "recipient_name", None),
        "recipient_employee_id": getattr(payload, "recipient_employee_id", None),
        "recipient_department": getattr(payload, "recipient_department", None),
    }
    if include_issued_at:
        kwargs["issued_at"] = getattr(payload, "issued_at", None)
    employee_id = getattr(payload, "employee_id", None)
    parameters = inspect.signature(callable_).parameters.values()
    supports_employee_ref = any(
        parameter.name == "employee_ref_id"
        or parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters
    )
    if employee_id is not None and supports_employee_ref:
        kwargs["employee_ref_id"] = employee_id
    return kwargs


def _controlled_inbound_from_payload(
    db: Session,
    payload: schemas.FixedAssetInboundCommand,
    current_user: models.User,
) -> asset_lifecycle_service.AssetLifecycleResult:
    return asset_lifecycle_service.controlled_inbound(
        db,
        operator_id=current_user.id,
        operator_name=current_user.full_name or current_user.username,
        terminal_inventory_id=payload.terminal_inventory_id,
        source=payload.source,
        asset_category_code=payload.asset_category_code,
        fixed_asset_number=payload.fixed_asset_number,
        serial_number=payload.serial_number,
        brand=payload.brand,
        model=payload.model,
        purchase_date=payload.purchase_date,
        notes=payload.notes,
    )


@app.post("/fixed-assets/inbound")
def inbound_fixed_asset(
    payload: schemas.FixedAssetInboundCommand,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_write_permission),
):
    try:
        return _fixed_asset_result_payload(
            _controlled_inbound_from_payload(db, payload, current_user)
        )
    except Exception as error:
        _raise_fixed_asset_api_error(db, error)


@app.post("/fixed-assets/inbound/batch")
def inbound_fixed_assets_batch(
    payload: schemas.FixedAssetInboundBatchRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_write_permission),
):
    """每项调用独立领域事务；某个 SN 失败不会回滚已成功的其它项。"""
    results = []
    for index, item in enumerate(payload.items):
        try:
            result = _controlled_inbound_from_payload(db, item, current_user)
            results.append({
                "index": index,
                "success": True,
                "status": "SUCCESS",
                "message": "受控入库成功",
                "fixed_asset_number": item.fixed_asset_number,
                "serial_number": item.serial_number,
                "result": _fixed_asset_result_payload(result),
            })
        except Exception as error:
            db.rollback()
            results.append({
                "index": index,
                "success": False,
                "status": "FAILED",
                "status_code": _fixed_asset_error_status(error),
                "message": _fixed_asset_error_detail(error),
                "fixed_asset_number": item.fixed_asset_number,
                "serial_number": item.serial_number,
            })
    success_count = sum(1 for item in results if item["success"])
    return {
        "results": results,
        "success_count": success_count,
        "failed_count": len(results) - success_count,
    }


@app.post("/fixed-assets/{asset_id}/issue")
def issue_controlled_fixed_asset(
    asset_id: int,
    payload: schemas.FixedAssetBindingRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_write_permission),
):
    try:
        result = asset_lifecycle_service.issue_fixed_asset(
            db,
            asset_id=asset_id,
            operator_id=current_user.id,
            operator_name=current_user.full_name or current_user.username,
            **_fixed_asset_binding_kwargs(
                asset_lifecycle_service.issue_fixed_asset,
                payload,
                include_issued_at=True,
            ),
        )
        return _fixed_asset_result_payload(result)
    except Exception as error:
        _raise_fixed_asset_api_error(db, error)


@app.post("/fixed-assets/{asset_id}/return")
def return_controlled_fixed_asset(
    asset_id: int,
    payload: schemas.FixedAssetReturnRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_write_permission),
):
    try:
        result = asset_lifecycle_service.return_fixed_asset(
            db,
            asset_id=asset_id,
            operator_id=current_user.id,
            operator_name=current_user.full_name or current_user.username,
            **_fixed_asset_binding_kwargs(
                asset_lifecycle_service.return_fixed_asset,
                payload,
                include_issued_at=False,
            ),
        )
        return _fixed_asset_result_payload(result)
    except Exception as error:
        _raise_fixed_asset_api_error(db, error)


@app.post("/fixed-assets/{asset_id}/transfer")
def transfer_controlled_fixed_asset(
    asset_id: int,
    payload: schemas.FixedAssetBindingRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_write_permission),
):
    try:
        result = asset_lifecycle_service.transfer_fixed_asset(
            db,
            asset_id=asset_id,
            operator_id=current_user.id,
            operator_name=current_user.full_name or current_user.username,
            **_fixed_asset_binding_kwargs(
                asset_lifecycle_service.transfer_fixed_asset,
                payload,
                include_issued_at=True,
            ),
        )
        return _fixed_asset_result_payload(result)
    except Exception as error:
        _raise_fixed_asset_api_error(db, error)


@app.post("/fixed-assets/{asset_id}/repair")
def send_controlled_fixed_asset_for_repair(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_write_permission),
):
    try:
        result = asset_lifecycle_service.send_for_repair(
            db,
            asset_id=asset_id,
            operator_id=current_user.id,
            operator_name=current_user.full_name or current_user.username,
        )
        return _fixed_asset_result_payload(result)
    except Exception as error:
        _raise_fixed_asset_api_error(db, error)


@app.post("/fixed-assets/{asset_id}/repair-complete")
def complete_controlled_fixed_asset_repair(
    asset_id: int,
    payload: schemas.FixedAssetRepairCompletionRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_write_permission),
):
    try:
        result = asset_lifecycle_service.complete_repair(
            db,
            asset_id=asset_id,
            operator_id=current_user.id,
            operator_name=current_user.full_name or current_user.username,
            **_fixed_asset_binding_kwargs(
                asset_lifecycle_service.complete_repair,
                payload,
                include_issued_at=True,
            ),
        )
        return _fixed_asset_result_payload(result)
    except Exception as error:
        _raise_fixed_asset_api_error(db, error)


@app.get("/assets/", response_model=List[schemas.Asset])
def read_assets(
    skip: int = 0,
    limit: int = 10000,
    category: Optional[str] = None,
    brand: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    department: Optional[str] = None,
    po_number: Optional[str] = None,
    location: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    query = db.query(models.Asset).filter(models.Asset.is_deleted == False)
    if category:
        query = query.filter(models.Asset.category == category)
    if brand:
        query = query.filter(models.Asset.brand.ilike(f"%{brand}%"))
    if status:
        query = query.filter(models.Asset.status == status)
    if department:
        query = query.filter(models.Asset.department == department)
    if po_number:
        query = query.filter(models.Asset.po_number.ilike(f"%{po_number}%"))
    if location:
        query = query.filter(models.Asset.location == location)
    if search:
        query = query.filter(
            (models.Asset.asset_tag.ilike(f"%{search}%")) |
            (models.Asset.brand.ilike(f"%{search}%")) |
            (models.Asset.model.ilike(f"%{search}%")) |
            (models.Asset.employee_name.ilike(f"%{search}%")) |
            (models.Asset.hostname.ilike(f"%{search}%")) |
            (models.Asset.employee_id.ilike(f"%{search}%")) |
            (models.Asset.department.ilike(f"%{search}%")) |
            (models.Asset.po_number.ilike(f"%{search}%"))
        )
    return query.offset(skip).limit(limit).all()


@app.get("/assets/weekly-distribution")
def get_weekly_distribution(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    """获取本周发放资产统计（上周五到本周四）"""
    today = datetime.now()
    weekday = today.weekday()
    if weekday >= 4:
        days_since_fri = weekday - 4
    else:
        days_since_fri = weekday + 3
    week_start = (today - timedelta(days=days_since_fri)).replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = (week_start + timedelta(days=6)).replace(hour=23, minute=59, second=59)

    from sqlalchemy import or_
    distributed_logs = db.query(models.AssetLog).filter(
        models.AssetLog.created_at >= week_start,
        models.AssetLog.created_at <= week_end,
        or_(
            models.AssetLog.action.like('%使用中%'),
            models.AssetLog.description.like('%状态: 使用中%')
        )
    ).all()

    asset_ids = list(set(log.asset_id for log in distributed_logs))
    assets = db.query(models.Asset).filter(models.Asset.id.in_(asset_ids)).all() if asset_ids else []

    categories = {}
    all_category_names = ['台式机', '笔记本电脑', '移动设备', '手机', '无线鼠标', '显示器', '打印机', '网络设备', '其他设备']
    for cat in all_category_names:
        categories[cat] = {"count": 0, "items": []}
    for asset in assets:
        cat = asset.category or '其他设备'
        if cat not in categories:
            categories[cat] = {"count": 0, "items": []}
        categories[cat]["count"] += 1
        sub = f"{asset.brand or ''} {asset.model or ''}".strip() or "未知型号"
        display_name = asset.hostname or asset.asset_tag
        categories[cat]["items"].append({"name": display_name, "model": sub})

    result = []
    for cat in all_category_names:
        data = categories.get(cat, {"count": 0, "items": []})
        result.append({"category": cat, "count": data["count"], "items": data["items"]})
    for cat, data in categories.items():
        if cat not in all_category_names:
            result.append({"category": cat, "count": data["count"], "items": data["items"]})
    result.sort(key=lambda x: x["count"], reverse=True)

    return {
        "week_start": week_start.strftime("%Y-%m-%d"),
        "week_end": week_end.strftime("%Y-%m-%d"),
        "total": len(assets),
        "categories": result
    }


@app.get("/assets/import-template")
async def download_import_template(
    current_user: models.User = Depends(get_current_active_user)
):
    """
    生成并返回包含正确中文列头和示例数据的 .xlsx 模板文件。
    使用 openpyxl 生成，支持列宽和样式控制。
    """
    template_bytes = import_service.generate_template()
    return StreamingResponse(
        io.BytesIO(template_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=asset_import_template.xlsx"},
    )


@app.get("/assets/next-tag/{category}")
def get_next_asset_tag(
    category: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    根据资产品类生成下一个可用的 asset_tag。

    品类前缀映射：
      台式机     → ZS-PC{YY}-NNNNNN
      笔记本电脑  → ZS-NB{YY}-NNNNNN
      显示器     → ZS-MR{YY}-NNNNNN
      移动设备   → ZS-PD{YY}-NNNNNN
      手机       → ZS-PH{YY}-NNNNNN
      打印机     → ZS-PR{YY}-NNNNNN
      网络设备   → ZS-NW{YY}-NNNNNN
      无线鼠标   → ZS-MS{YY}-NNNNNN
      其他设备   → ZS-OT{YY}-NNNNNN

    YY = 当前年份后两位（如 2026 → 26）
    NNNNNN = 该前缀下最大序号 + 1，保持6位补零

    返回：{ "suggested_tag": "ZS-PC26-000012", "category": "台式机" }
    """
    import re as _re
    from datetime import datetime as _dt

    CATEGORY_PREFIX = {
        "台式机":    "PC",
        "笔记本电脑": "NB",
        "显示器":    "MR",
        "移动设备":  "PD",
        "手机":      "PH",
        "打印机":    "PR",
        "网络设备":  "NW",
        "无线鼠标":  "MS",
        "其他设备":  "OT",
        "服务器":    "SV",
    }

    year_suffix = str(_dt.now().year)[2:]  # "26"
    prefix_code = CATEGORY_PREFIX.get(category, "OT")
    prefix = f"ZS-{prefix_code}{year_suffix}-"  # e.g. "ZS-PC26-"

    # 查询该前缀下所有已存在的编号（含已删除，防止重复）
    ASSET_TAG_RE = _re.compile(rf"^ZS-{prefix_code}{year_suffix}-(\d{{6}})$")
    all_tags = (
        db.query(models.Asset.asset_tag)
        .filter(models.Asset.asset_tag.like(f"{prefix}%"))
        .all()
    )

    max_num = 0
    for (tag,) in all_tags:
        if not tag:
            continue
        m = ASSET_TAG_RE.match(tag)
        if m:
            num = int(m.group(1))
            if num > max_num:
                max_num = num

    suggested_tag = f"{prefix}{max_num + 1:06d}"
    return {"suggested_tag": suggested_tag, "category": category}

@app.get("/assets/identify-by-sn/{sn}")
def identify_asset_by_sn(
    sn: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    通过序列号识别资产。

    - SN 已存在（未删除）→ 返回资产详情，action = "VIEW"（闲置/维修/报废）或 "UPDATE"（使用中）
    - SN 不存在 → 计算下一个可用 asset_tag，action = "CREATE"

    asset_tag 自增规则：
      查询所有未删除资产中格式为 IT-XXXX-NNNNNN 的编号，
      取数字部分最大值 +1，保持6位补零格式，前缀沿用最新记录的前缀。
    """
    import re as _re

    sn_upper = sn.strip().upper()

    # ── 1. 查询 SN 是否已存在 ──
    existing = db.query(models.Asset).filter(
        models.Asset.serial_number == sn_upper,
        models.Asset.is_deleted == False,
    ).first()

    if existing:
        action = "UPDATE" if existing.status == "使用中" else "VIEW"
        return {
            "action": action,
            "sn": sn_upper,
            "asset": {
                "id": existing.id,
                "asset_tag": existing.asset_tag,
                "category": existing.category,
                "brand": existing.brand,
                "model": existing.model,
                "serial_number": existing.serial_number,
                "status": existing.status,
                "hostname": existing.hostname,
                "employee_name": existing.employee_name,
                "employee_id": existing.employee_id,
                "department": existing.department,
                "mac_address": existing.mac_address,
                "ip_address": existing.ip_address,
                "system_version": existing.system_version,
                "location": existing.location,
                "notes": existing.notes,
            },
        }

    # ── 2. SN 不存在，计算下一个 asset_tag ──
    ASSET_TAG_RE = _re.compile(r"^(ZS-[A-Za-z0-9]{4}-)(\d{6})$")

    # 取所有符合格式的 asset_tag，排除 ZS-WH 开头的临时编号，找数字部分最大值
    all_tags = (
        db.query(models.Asset.asset_tag)
        .filter(
            models.Asset.is_deleted == False,
            ~models.Asset.asset_tag.like("ZS-WH%"),  # 排除出库分配生成的临时编号
        )
        .all()
    )

    max_num = 0
    latest_prefix = "ZS-NEW0-"  # 兜底前缀

    for (tag,) in all_tags:
        if not tag:
            continue
        m = ASSET_TAG_RE.match(tag)
        if m:
            prefix, num_str = m.group(1), m.group(2)
            num = int(num_str)
            if num > max_num:
                max_num = num
                latest_prefix = prefix

    next_num = max_num + 1
    suggested_tag = f"{latest_prefix}{next_num:06d}"

    return {
        "action": "CREATE",
        "sn": sn_upper,
        "suggested_tag": suggested_tag,
        "asset": None,
    }


@app.get("/assets/{asset_id}", response_model=schemas.AssetWithLogs)
def read_asset(asset_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    asset = db.query(models.Asset).filter(models.Asset.id == asset_id, models.Asset.is_deleted == False).first()
    if not asset:
        raise HTTPException(status_code=404, detail="asset not found")
    return asset


# 字段中文名映射
FIELD_LABELS = {
    "asset_tag": "资产编号", "category": "品类", "brand": "品牌", "model": "型号",
    "serial_number": "序列号", "status": "状态", "hostname": "资产名",
    "employee_ref_id": "员工主数据", "employee_id": "工号", "employee_name": "使用人", "department": "部门",
    "mac_address": "MAC地址", "ip_address": "IP地址",
    "fixed_asset_number": "固定资产编号",
    "system_version": "系统版本", "antivirus_software": "杀毒软件",
    "lock_number": "锁号", "location": "位置", "quantity": "数量", "notes": "备注",
    "supervisor": "直属领导", "bios_password": "BIOS密码", "tpm_status": "TPM状态",
    "has_desktop": "是否有台式机",
    # 库房资产字段
    "name": "资产名称", "subcategory": "子分类", "receiver_name": "入库人",
    "total_quantity": "总数量", "available_quantity": "可用数量",
    "allocated_quantity": "已分配数量", "minimum_stock": "最低库存",
}


@app.put("/assets/{asset_id}", response_model=schemas.Asset)
def update_asset(asset_id: int, asset: schemas.AssetUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(require_write_permission)):
    # 加行锁读取，防止并发修改同一资产
    db_asset = db.query(models.Asset).filter(
        models.Asset.id == asset_id, models.Asset.is_deleted == False
    ).with_for_update().first()
    if not db_asset:
        raise HTTPException(status_code=404, detail="asset not found")

    update_data = asset.dict(exclude_unset=True)
    if db_asset.asset_category_code and {
        "status", "employee_ref_id", "employee_name", "employee_id", "department", "issue_date"
    }.intersection(update_data):
        raise HTTPException(
            status_code=400,
            detail="受控固定资产的状态和领用绑定只能通过固定资产生命周期接口变更",
        )

    old_hostname = db_asset.hostname
    old_status = db_asset.status
    new_status = update_data.get("status")

    # ── 状态机校验 ──
    if new_status:
        if new_status not in ALL_VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"非法状态值「{new_status}」，允许: {', '.join(ALL_VALID_STATUSES)}")
        if new_status != old_status:
            allowed = VALID_STATUS_TRANSITIONS.get(old_status, set())
            if new_status not in allowed:
                raise HTTPException(
                    status_code=400,
                    detail=f"非法状态转换: 「{old_status}」→「{new_status}」。「{old_status}」仅允许转换到: {', '.join(allowed) if allowed else '(终态，不可转换)'}"
                )

    # ── 从非使用中改为“使用中”必须显式绑定员工主数据 ──
    if new_status == "使用中" and old_status != "使用中":
        if update_data.get("employee_ref_id") is None:
            raise HTTPException(
                status_code=400,
                detail="资产改为使用中时必须指定在职员工 employee_ref_id",
            )

    try:
        effective_status = new_status or old_status
        if effective_status == "闲置":
            # 闲置资产不保留任何当前员工引用或显示快照。
            update_data["employee_ref_id"] = None
            for field in [
                "employee_id", "employee_name", "department", "supervisor", "issue_date"
            ]:
                update_data[field] = None
        elif "employee_ref_id" in update_data:
            employee_ref_id = update_data.get("employee_ref_id")
            if employee_ref_id is None:
                if effective_status == "使用中":
                    raise HTTPException(
                        status_code=400,
                        detail="使用中资产不能清除 employee_ref_id",
                    )
            else:
                employee = _lock_active_employee(db, employee_ref_id)
                _apply_employee_asset_snapshot(update_data, employee)

        # 如果状态变为"使用中"且没有传 issue_date，自动设置为当前时间
        if new_status == "使用中" and old_status != "使用中":
            if "issue_date" not in update_data or not update_data.get("issue_date"):
                update_data["issue_date"] = models.china_now()

        # 逐字段对比，收集变更
        changes = []
        for key, new_val in update_data.items():
            old_val = getattr(db_asset, key, None)
            old_str = (str(old_val).strip() if old_val is not None else "")
            new_str = (str(new_val).strip() if new_val is not None else "")
            if not old_str and not new_str:
                continue
            if old_str != new_str:
                label = FIELD_LABELS.get(key, key)
                changes.append({"field": label, "old": old_str or "(空)", "new": new_str or "(空)"})

        for key, value in update_data.items():
            setattr(db_asset, key, value)

        if 'hostname' in update_data and old_hostname != update_data['hostname']:
            create_hostname_history(db, asset_id, old_hostname, update_data['hostname'])

        # 根据变更类型生成可读的日志
        operator_name = current_user.full_name or current_user.username
        if not changes:
            create_log(db, asset_id, "update", "未检测到变更", None, None, operator=operator_name)
        else:
            status_change = next((c for c in changes if c["field"] == "状态"), None)
            if status_change:
                action = f"状态变更: {status_change['old']} → {status_change['new']}"
            else:
                action = "update"

            desc_parts = [f"{c['field']}: {c['old']} → {c['new']}" for c in changes]
            description = "; ".join(desc_parts)
            old_json = json.dumps({c["field"]: c["old"] for c in changes}, ensure_ascii=False)
            new_json = json.dumps({c["field"]: c["new"] for c in changes}, ensure_ascii=False)
            create_log(db, asset_id, action, description, old_json, new_json, operator=operator_name)
            create_operation_log(db, current_user.id, "update", "asset", asset_id, description, old_json, new_json)

        # 状态变更时同步库房可用数量
        # from_warehouse=True 的资产由库房模块独立管理库存数量，不参与自动同步
        if new_status and new_status != old_status and not db_asset.from_warehouse:
            if old_status == "闲置" and new_status != "闲置":
                _sync_warehouse_quantity(db, db_asset.category, -1, operator_name)
            elif new_status == "闲置" and old_status != "闲置":
                _sync_warehouse_quantity(db, db_asset.category, +1, operator_name)

        db.commit()
        db.refresh(db_asset)
        return db_asset
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"更新资产失败: {str(e)}")


@app.delete("/assets/{asset_id}")
def delete_asset(asset_id: int, deletion_request: schemas.AssetDeletionRequest, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin())):
    # 加行锁，防止并发删除
    db_asset = db.query(models.Asset).filter(
        models.Asset.id == asset_id, models.Asset.is_deleted == False
    ).with_for_update().first()
    if not db_asset:
        raise HTTPException(status_code=404, detail="asset not found")

    deletion_blocked_detail = "当前资产处于使用中或维修中状态，请先归还、完成维修或执行报废流程"
    if db_asset.status in {"使用中", "维修中"}:
        raise HTTPException(status_code=409, detail=deletion_blocked_detail)

    # 即使状态数据异常，也不能删除仍带当前领用绑定的资产。
    binding_fields = (
        "employee_ref_id", "employee_name", "employee_id", "department", "issue_date"
    )
    if any(getattr(db_asset, field, None) not in (None, "") for field in binding_fields):
        raise HTTPException(status_code=409, detail=deletion_blocked_detail)

    try:
        asset_tag = db_asset.asset_tag
        asset_status = db_asset.status
        asset_category = db_asset.category
        operator_name = current_user.full_name or current_user.username
        asset_info = {
            "id": db_asset.id, "asset_tag": asset_tag, "category": db_asset.category,
            "brand": db_asset.brand, "model": db_asset.model, "status": db_asset.status,
            "employee_ref_id": getattr(db_asset, "employee_ref_id", None),
            "employee_id": db_asset.employee_id, "employee_name": db_asset.employee_name,
            "department": db_asset.department, "issue_date": db_asset.issue_date,
            "hostname": db_asset.hostname, "fixed_asset_number": db_asset.fixed_asset_number,
            "serial_number": db_asset.serial_number,
            "terminal_inventory_id": db_asset.terminal_inventory_id,
        }

        # 受控闲置固定资产删除时，必须锁定并精确扣减其关联终端库存。
        # 一张闲置卡对应一份可用库存，因此同时扣减总量和可用量，保持数量守恒。
        if db_asset.asset_category_code and asset_status == "闲置":
            terminal_inventory = (
                db.query(models.WarehouseAsset)
                .filter(models.WarehouseAsset.id == db_asset.terminal_inventory_id)
                .with_for_update()
                .first()
            )
            if (
                terminal_inventory is None
                or terminal_inventory.total_quantity < 1
                or terminal_inventory.available_quantity < 1
            ):
                raise HTTPException(
                    status_code=409,
                    detail="固定资产关联库存数据异常，无法删除",
                )
            old_total = terminal_inventory.total_quantity
            old_available = terminal_inventory.available_quantity
            terminal_inventory.total_quantity -= 1
            terminal_inventory.available_quantity -= 1
            db.add(models.WarehouseAssetLog(
                asset_id=terminal_inventory.id,
                action="固定资产删除出库",
                description=(
                    f"删除资产 {asset_tag}: 总库存 {old_total} → {terminal_inventory.total_quantity}, "
                    f"可用库存 {old_available} → {terminal_inventory.available_quantity}"
                ),
                operator=operator_name,
            ))
        elif asset_status == "闲置" and not db_asset.from_warehouse:
            # 历史非受控资产继续沿用旧库存联动逻辑。
            _sync_warehouse_quantity(db, asset_category, -1, operator_name)

        deletion_record = models.AssetDeletionRecord(
            asset_id=db_asset.id, asset_tag=asset_tag,
            asset_data=json.dumps(asset_info, ensure_ascii=False, default=str),
            deletion_reason=deletion_request.reason, deleted_by=current_user.id
        )
        db.add(deletion_record)
        create_operation_log(
            db, current_user.id, "delete", "asset", db_asset.id,
            f"删除资产 {asset_tag}，原因: {deletion_request.reason}",
            json.dumps(asset_info, ensure_ascii=False, default=str),
            json.dumps({"is_deleted": True}, ensure_ascii=False),
        )
        create_log(db, db_asset.id, "删除资产", f"软删除资产 {asset_tag}，原因: {deletion_request.reason}", operator=operator_name)
        # 软删除：历史入库、领用和生命周期记录均保留，仅隐藏资产卡。
        db_asset.is_deleted = True
        db_asset.deleted_at = models.china_now()

        db.commit()
        return {"message": f"资产 {asset_tag} 已删除"}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"删除资产失败: {str(e)}")


@app.get("/assets/{asset_id}/logs", response_model=List[schemas.AssetLog])
def read_asset_logs(asset_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    return db.query(models.AssetLog).filter(models.AssetLog.asset_id == asset_id).order_by(models.AssetLog.created_at.desc()).all()


@app.get("/assets/{asset_id}/hostname-history", response_model=List[schemas.HostnameHistory])
def read_hostname_history(asset_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    return db.query(models.HostnameHistory).filter(models.HostnameHistory.asset_id == asset_id).order_by(models.HostnameHistory.changed_at.desc()).all()


# ========== 资产配件更换记录 ==========

@app.get("/assets/{asset_id}/parts", response_model=List[schemas.AssetPartLogResponse])
def list_asset_parts(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """获取指定资产的配件更换/新增记录，按时间倒序"""
    return (
        db.query(models.AssetPartLog)
        .filter(models.AssetPartLog.asset_id == asset_id)
        .order_by(models.AssetPartLog.created_at.desc())
        .all()
    )


@app.post("/assets/{asset_id}/parts", response_model=schemas.AssetPartLogResponse)
def add_asset_part(
    asset_id: int,
    data: schemas.AssetPartLogCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_write_permission),
):
    """
    新增配件更换/新增记录，并联动库房库存：
    - 操作类型"更换"：从库房取出 quantity 件（available_quantity - quantity）
    - 操作类型"新增"：从库房取出 quantity 件（available_quantity - quantity）
    - 两种操作都消耗库房库存；"更换"时旧配件默认不归还（如需归还可在备注说明）
    """
    asset = db.query(models.Asset).filter(
        models.Asset.id == asset_id,
        models.Asset.is_deleted == False,
    ).first()
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")

    if data.quantity <= 0:
        raise HTTPException(status_code=400, detail="数量必须大于 0")

    operator_name = current_user.full_name or current_user.username

    # 联动库房库存
    wh_item = None
    if data.warehouse_item_id:
        wh_item = (
            db.query(models.WarehouseAsset)
            .filter(models.WarehouseAsset.id == data.warehouse_item_id)
            .with_for_update()
            .first()
        )
        if not wh_item:
            raise HTTPException(status_code=404, detail="库房配件不存在")
        if wh_item.available_quantity < data.quantity:
            raise HTTPException(
                status_code=409,
                detail=f"库房「{wh_item.name}」可用数量不足（当前 {wh_item.available_quantity}，需要 {data.quantity}）",
            )
        # 扣减可用数量，增加已分配数量
        wh_item.available_quantity -= data.quantity
        wh_item.allocated_quantity += data.quantity
        db.flush()

        # 记录库房操作日志
        wh_log = models.WarehouseAssetLog(
            asset_id=wh_item.id,
            action=f"配件出库（{data.action}）",
            description=(
                f"资产 {asset.hostname or asset.asset_tag} {data.action}配件，"
                f"出库 {data.quantity} 件，"
                f"剩余可用 {wh_item.available_quantity}"
            ),
            operator=operator_name,
        )
        db.add(wh_log)

    # 写入配件记录
    part_log = models.AssetPartLog(
        asset_id=asset_id,
        warehouse_item_id=data.warehouse_item_id,
        warehouse_item_name=data.warehouse_item_name,
        action=data.action,
        quantity=data.quantity,
        notes=data.notes,
        operator=operator_name,
    )
    db.add(part_log)
    db.flush()

    # 写入资产操作日志
    asset_log = models.AssetLog(
        asset_id=asset_id,
        action=f"配件{data.action}",
        description=(
            f"{data.action}配件「{data.warehouse_item_name}」× {data.quantity}"
            + (f"，备注: {data.notes}" if data.notes else "")
        ),
        operator=operator_name,
    )
    db.add(asset_log)
    db.commit()
    db.refresh(part_log)
    return part_log


@app.delete("/assets/{asset_id}/parts/{part_id}")
def delete_asset_part(
    asset_id: int,
    part_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin()),
):
    """
    删除配件记录（仅管理员），并回滚库房库存：
    将对应数量归还到库房 available_quantity
    """
    part = db.query(models.AssetPartLog).filter(
        models.AssetPartLog.id == part_id,
        models.AssetPartLog.asset_id == asset_id,
    ).first()
    if not part:
        raise HTTPException(status_code=404, detail="配件记录不存在")

    operator_name = current_user.full_name or current_user.username

    # 回滚库房库存
    if part.warehouse_item_id:
        wh_item = (
            db.query(models.WarehouseAsset)
            .filter(models.WarehouseAsset.id == part.warehouse_item_id)
            .with_for_update()
            .first()
        )
        if wh_item:
            wh_item.available_quantity += part.quantity
            wh_item.allocated_quantity = max(0, wh_item.allocated_quantity - part.quantity)
            db.flush()
            wh_log = models.WarehouseAssetLog(
                asset_id=wh_item.id,
                action="配件回库（撤销记录）",
                description=f"撤销配件记录，归还 {part.quantity} 件「{part.warehouse_item_name}」，可用数量恢复至 {wh_item.available_quantity}",
                operator=operator_name,
            )
            db.add(wh_log)

    db.delete(part)
    db.commit()
    return {"message": f"配件记录已删除，库房库存已回滚"}


# ========== 资产批量导入 ==========


def _wizard_error(status_code: int, detail: str, request_id: str) -> None:
    raise WizardImportAPIError(status_code, detail, request_id)


def _get_wizard_session(
    store: InMemorySessionStore,
    session_id: str,
    user_id: int,
    request_id: str,
):
    session = store.get(session_id)
    if session is None:
        _wizard_error(404, "导入会话不存在或已过期，请重新上传文件", request_id)
    if session.owner_user_id != user_id:
        _wizard_error(403, "无权访问此导入会话", request_id)
    session.touch(request_id)
    return session


def _build_preview_summary(records) -> PreviewSummary:
    summary = PreviewSummary(total=len(records))
    for record in records:
        if record.classification == RecordClassification.VALID:
            summary.valid += 1
        elif record.classification == RecordClassification.MAPPING_REQUIRED:
            summary.mapping_required += 1
        elif record.classification == RecordClassification.DUPLICATE:
            summary.duplicate += 1
        elif record.classification == RecordClassification.ERROR:
            summary.error += 1
    return summary


def _serialize_preview_record(record) -> dict:
    duplicate = record.duplicate_info
    return {
        "row_number": record.row_number,
        "asset_tag": record.fields.get("asset_tag"),
        "classification": record.classification.value if record.classification else "",
        "validation_errors": [
            {"field": error.field, "message": error.message}
            for error in record.validation_errors
        ],
        "resolver_issues": [
            {
                "field": issue.field,
                "raw_value": issue.raw_value,
                "issue_type": issue.issue_type.value,
                "candidates": issue.candidates,
            }
            for issue in record.resolver_issues
        ],
        "duplicate_info": None if duplicate is None else {
            "asset_id": duplicate.asset_id,
            "asset_tag": duplicate.asset_tag,
            "serial_number": duplicate.serial_number,
            "status": duplicate.status,
            "conflict_field": duplicate.conflict_field,
            "conflict_scope": duplicate.conflict_scope,
            "first_row_number": duplicate.first_row_number,
        },
    }


def _serialize_pipeline_warning(warning) -> dict:
    return {
        "row_number": warning.row_number,
        "asset_tag": warning.asset_tag,
        "warning_type": warning.warning_type.value,
        "message": warning.message,
    }


def _validate_mapping_targets(db: Session, mapping: dict, request_id: str) -> dict:
    """一次校验完整 mapping，并缓存 Ref；失败时不修改 Session。"""
    refs = {}
    for key, entry in mapping.items():
        if entry.action == "skip":
            continue
        target = None
        if entry.field_type == MappingFieldType.DEPARTMENT:
            target = db.query(models.Department).filter(
                models.Department.id == entry.resolved_id
            ).first()
            if target:
                refs[key] = DepartmentRef(
                    id=target.id, name=target.name, parent_id=target.parent_id
                )
        elif entry.field_type == MappingFieldType.BRAND:
            target = db.query(models.Brand).filter(
                models.Brand.id == entry.resolved_id
            ).first()
            if target:
                refs[key] = BrandRef(id=target.id, name=target.name)
        else:
            target = db.query(models.WarehouseLocation).filter(
                models.WarehouseLocation.id == entry.resolved_id
            ).first()
            if target:
                refs[key] = LocationRef(
                    id=target.id,
                    name=target.name,
                    location_type=LocationType.WAREHOUSE,
                )
            else:
                target = db.query(models.OfficeLocation).filter(
                    models.OfficeLocation.id == entry.resolved_id
                ).first()
                if target:
                    refs[key] = LocationRef(
                        id=target.id,
                        name=target.name,
                        location_type=LocationType.OFFICE,
                    )
        if target is None:
            _wizard_error(
                400,
                f"映射目标 ID {entry.resolved_id} 不存在",
                request_id,
            )
    return refs


@app.post("/assets/import/parse", response_model=schemas.ImportParseResponse)
async def parse_assets_for_import(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_write_permission),
    store: InMemorySessionStore = Depends(get_session_store),
):
    context = ImportContext.create(db, current_user, ImportPolicy.insert_only())
    filename = file.filename or ""
    if not filename.lower().endswith(".xlsx"):
        _wizard_error(400, "仅支持 .xlsx 格式文件", context.request_id)

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        _wizard_error(400, "文件大小不能超过 10MB", context.request_id)

    try:
        result = ImportPipeline().parse_only(content, filename, context)
    except ValueError as exc:
        _wizard_error(400, str(exc), context.request_id)

    session = store.create(current_user.id, filename, context.request_id)
    session.parsed_records = result.records
    session.preview_summary = result.summary
    store.save(session)
    return {
        "session_id": session.session_id,
        "request_id": context.request_id,
        "preview_summary": result.summary.to_dict(),
        "records": [_serialize_preview_record(r) for r in result.records],
        "warnings": [_serialize_pipeline_warning(w) for w in result.warnings],
        "inferred_category": result.inferred_category,
    }


@app.post("/assets/import/apply-mapping", response_model=schemas.ImportMappingResponse)
def apply_asset_import_mapping(
    payload: schemas.ImportApplyMappingRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_write_permission),
    store: InMemorySessionStore = Depends(get_session_store),
):
    policy_type = ImportPolicyType(payload.duplicate_policy)
    context = ImportContext.create(
        db, current_user, ImportPolicy(policy_type), session_id=payload.session_id
    )
    session = _get_wizard_session(
        store, payload.session_id, current_user.id, context.request_id
    )
    if session.status != SessionStatus.PARSED:
        _wizard_error(
            409,
            f"当前会话状态为 {session.status.value}，仅 PARSED 状态可应用映射",
            context.request_id,
        )

    merged_mapping = dict(session.mapping)
    for item in payload.mapping_entries:
        field_type = MappingFieldType(item.field_type.lower())
        entry = MappingEntry(
            raw_value=item.raw_value,
            field_type=field_type,
            resolved_id=item.resolved_id,
            resolved_name=item.resolved_name,
            action=item.action,
        )
        merged_mapping[make_mapping_key(field_type, item.raw_value)] = entry

    refs = _validate_mapping_targets(db, merged_mapping, context.request_id)
    session.mapping = merged_mapping

    for record in session.parsed_records:
        if record.classification != RecordClassification.MAPPING_REQUIRED:
            continue
        unresolved = []
        for issue in record.resolver_issues:
            try:
                field_type = MappingFieldType(issue.field)
            except ValueError:
                unresolved.append(issue)
                continue
            key = make_mapping_key(field_type, issue.raw_value)
            entry = merged_mapping.get(key)
            if entry is None or entry.action == "skip":
                unresolved.append(issue)
                continue
            resolved_ref = refs[key]
            if field_type == MappingFieldType.DEPARTMENT:
                record.resolved.department = resolved_ref
            elif field_type == MappingFieldType.BRAND:
                record.resolved.brand = resolved_ref
            else:
                record.resolved.location = resolved_ref
        record.resolver_issues = unresolved

    Classifier().classify_batch(session.parsed_records, context)
    context.import_policy.decide_batch(session.parsed_records)
    summary = _build_preview_summary(session.parsed_records)
    ready = summary.mapping_required == 0 and summary.error == 0

    session.preview_summary = summary
    session.duplicate_policy_type = payload.duplicate_policy
    if ready:
        try:
            session.transition_to(SessionStatus.MAPPING_APPLIED)
        except ValueError as exc:
            _wizard_error(409, str(exc), context.request_id)
    store.save(session)
    return {
        "request_id": context.request_id,
        "preview_summary": summary.to_dict(),
        "ready_to_execute": ready,
    }


def _record_to_legacy_insert_row(record) -> dict:
    """把 Pipeline record 转换为旧批量写入器所需的已验证行。"""
    data = dict(record.fields)
    if record.resolved.department:
        data["department"] = record.resolved.department.name
    if record.resolved.brand:
        data["brand"] = record.resolved.brand.name
    if record.resolved.location:
        data["location"] = record.resolved.location.name
    if record.extra_fields:
        data["additional_info"] = dict(record.extra_fields)
    validated = schemas.AssetCreate(**data).model_dump()
    validated["_row_number"] = record.row_number
    return validated


def get_import_executor() -> Executor:
    """创建 Phase 6 Executor；测试可覆盖依赖以注入独立审计 Session 工厂。"""
    return Executor()


@app.post("/assets/import/execute", response_model=schemas.ImportExecuteResponse)
def execute_asset_import(
    payload: schemas.ImportExecuteRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_write_permission),
    store: InMemorySessionStore = Depends(get_session_store),
    executor: Executor = Depends(get_import_executor),
):
    context = ImportContext.create(
        db,
        current_user,
        ImportPolicy.insert_only(),
        session_id=payload.session_id,
        dry_run=payload.dry_run,
    )
    session = _get_wizard_session(
        store, payload.session_id, current_user.id, context.request_id
    )
    if session.status == SessionStatus.EXECUTING:
        _wizard_error(409, "导入正在执行中，请勿重复提交", context.request_id)
    if session.status == SessionStatus.COMPLETED:
        _wizard_error(409, "导入已完成，请勿重复提交", context.request_id)
    if session.status != SessionStatus.MAPPING_APPLIED:
        _wizard_error(409, "请先完成主数据映射步骤再执行导入", context.request_id)

    try:
        policy_type = ImportPolicyType(session.duplicate_policy_type)
    except ValueError:
        _wizard_error(409, "导入会话中的重复策略无效，请重新应用映射", context.request_id)
    context.import_policy = ImportPolicy(policy_type)
    context.import_policy.decide_batch(session.parsed_records)

    try:
        session.transition_to(SessionStatus.EXECUTING)
        store.save(session)
        result = executor.execute(session.parsed_records, context)
        session.transition_to(SessionStatus.COMPLETED)
        session.extend_after_execute()
    except ImportExecutionError as exc:
        if session.status == SessionStatus.EXECUTING:
            session.transition_to(SessionStatus.PARSED)
        session.last_request_id = context.request_id
        store.save(session)
        detail = (
            {"message": str(exc), "errors": exc.issues}
            if exc.issues
            else "数据库写入失败，事务已回滚，请使用请求 ID 联系管理员"
        )
        _wizard_error(exc.status_code, detail, context.request_id)

    session.execute_result = result
    session.last_request_id = context.request_id
    store.save(session)
    return {"request_id": context.request_id, "result": result}


@app.post("/assets/import", response_model=schemas.ImportResult)
async def import_assets(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_write_permission)
):
    """
    接受 .xlsx 文件上传，解析并批量导入资产数据。

    新特性:
    - 模糊列头匹配：自动识别常见别名（如"SN"→序列号、"主机名"→资产名）
    - 品类自动推断：文件名含"笔记本"等关键词时自动填充品类
    - 未知列捕获：Excel 中不认识的列自动存入 additional_info JSON 字段
    - 分级校验：资产编号/序列号冲突时跳过该行并记录原因，不中断整批导入

    返回: ImportResult JSON 报告（成功数、失败数、失败明细含跳过原因）
    """
    # 1. 文件类型检查
    filename = file.filename or ""
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 格式文件")

    # 2. 读取文件内容并检查大小
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件大小不能超过 10MB")

    # 3. 用 pandas 解析 Excel（传入文件名用于品类推断）
    try:
        headers, rows, inferred_category = import_service.parse_excel(content, filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not rows:
        raise HTTPException(status_code=400, detail="文件中没有数据行")

    # 4. 逐行验证（支持品类推断填充）
    valid_rows, errors = import_service.validate_rows(rows, db, inferred_category)

    # 5. 批量写入（带事务保护）
    inserted_count = 0
    if valid_rows:
        try:
            inserted_count = import_service.bulk_insert_assets(valid_rows, db, current_user)
            db.commit()
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"数据库写入失败: {str(e)}")

    # 6. 返回详细 JSON 报告（含跳过原因分类）
    conflict_count = sum(1 for e in errors if e.get("skip_reason") == "conflict")
    format_count = sum(1 for e in errors if e.get("skip_reason") == "format")
    validation_count = sum(1 for e in errors if e.get("skip_reason") == "validation")

    error_items = [
        schemas.ImportError(
            row_number=err["row_number"],
            asset_tag=err.get("asset_tag"),
            message=err["message"],
        )
        for err in errors
    ]

    summary_parts = [f"成功导入 {inserted_count} 条，失败 {len(errors)} 条"]
    if conflict_count:
        summary_parts.append(f"其中编号/序列号冲突跳过 {conflict_count} 条")
    if inferred_category:
        summary_parts.append(f"品类已从文件名推断为「{inferred_category}」")

    return schemas.ImportResult(
        total_rows=len(rows),
        success_count=inserted_count,
        failed_count=len(errors),
        errors=error_items,
        message="；".join(summary_parts),
    )


@app.post("/warehouse/", response_model=schemas.WarehouseAsset)
def create_warehouse_asset(asset: schemas.WarehouseAssetCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_write_permission)):
    raise HTTPException(
        status_code=400,
        detail="库房物料必须通过 /warehouse/materials 提交一级和二级分类组合",
    )
    # 守恒校验
    if asset.total_quantity != asset.available_quantity + asset.allocated_quantity:
        raise HTTPException(
            status_code=400,
            detail=f"数量守恒校验失败: 总数量({asset.total_quantity}) ≠ 可用数量({asset.available_quantity}) + 已分配数量({asset.allocated_quantity})"
        )
    if asset.total_quantity < 0 or asset.available_quantity < 0 or asset.allocated_quantity < 0:
        raise HTTPException(status_code=400, detail="数量不能为负数")

    try:
        db_asset = models.WarehouseAsset(**asset.dict())
        db.add(db_asset)
        db.flush()
        operator_name = current_user.full_name or current_user.username
        wh_log = models.WarehouseAssetLog(asset_id=db_asset.id, action="入库", description=f"新增库房资产: {db_asset.name}，数量: {db_asset.total_quantity}", operator=operator_name)
        db.add(wh_log)
        db.commit()
        db.refresh(db_asset)
        return db_asset
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"创建库房资产失败: {str(e)}")


@app.get("/warehouse/", response_model=List[schemas.WarehouseAsset])
def read_warehouse_assets(skip: int = 0, limit: int = 10000, category: Optional[str] = None, low_stock: Optional[bool] = None, search: Optional[str] = None, since: Optional[str] = None, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    query = db.query(models.WarehouseAsset)
    if category:
        query = query.filter(models.WarehouseAsset.category == category)
    if low_stock:
        query = query.filter(models.WarehouseAsset.available_quantity <= models.WarehouseAsset.minimum_stock)
    if search:
        query = query.filter((models.WarehouseAsset.name.ilike(f"%{search}%")) | (models.WarehouseAsset.brand.ilike(f"%{search}%")))
    if since:
        try:
            since_date = datetime.strptime(since, "%Y-%m-%d")
            query = query.filter(models.WarehouseAsset.created_at >= since_date)
        except ValueError:
            pass
    query = query.order_by(models.WarehouseAsset.created_at.desc())
    return query.offset(skip).limit(limit).all()


@app.get("/warehouse/stats")
def get_warehouse_stats(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    #1.计算总商品数
    total_items = db.query(models.WarehouseAsset).count()

    #2.计算库存预警数（排除掉数量为空的脏数据，防止计算不准）
    low_stock_items = db.query(models.WarehouseAsset).filter(
        models.WarehouseAsset.available_quantity.isnot(None),
        models.WarehouseAsset.minimum_stock.isnot(None),
        models.WarehouseAsset.available_quantity <= models.WarehouseAsset.minimum_stock).count()
    
    #3.按分类统计（使用正确的func）
    category_stats = db.query(
        models.WarehouseAsset.category, 
        func.count(models.WarehouseAsset.id).label('count'), 
        func.sum(models.WarehouseAsset.total_quantity).label('total_qty'), 
        func.sum(models.WarehouseAsset.available_quantity).label('available_qty')).group_by(models.WarehouseAsset.category).all()
    
    #4.安全地处理和转换数据类型，防止JSON序列化引发500错误
    processed_category_stats = []
    for stat in category_stats:
        processed_category_stats.append({
        #如果分类为空，给一个默认字符串，防止前端图表因为null崩溃
        "category": stat[0] if stat[0] is not None else "未分类",
        "item_count": stat[1],
        #显式转换为int（如果是小数则用float),并处理sum结果为none的情况
        "total_quantity": int(stat[2]) if stat[2] is not None else 0,
        "available_quantity": int(stat[3]) if stat[3] is not None else 0
        })
    return {
        "total_items": total_items, 
        "low_stock_items": low_stock_items, 
        "category_stats": processed_category_stats
    }

# ========== 仓储分类目录与两级物料 API ==========

def _raise_warehouse_api_error(error: Exception) -> None:
    """将领域服务的中文错误稳定映射为仓储 API 状态码。"""
    if isinstance(
        error,
        (
            warehouse_category_service.WarehouseCategoryNotFoundError,
            warehouse_material_service.WarehouseMaterialNotFoundError,
        ),
    ):
        raise HTTPException(status_code=404, detail=str(error)) from error
    if isinstance(
        error,
        (
            warehouse_category_service.WarehouseCategoryConflictError,
            warehouse_material_service.WarehouseMaterialConflictError,
        ),
    ):
        raise HTTPException(status_code=409, detail=str(error)) from error
    if isinstance(error, DomainTransactionError):
        raise HTTPException(status_code=500, detail=error.detail) from error
    if isinstance(
        error,
        (
            warehouse_category_service.WarehouseCategoryServiceError,
            warehouse_material_service.WarehouseMaterialServiceError,
        ),
    ):
        raise HTTPException(status_code=400, detail=str(error)) from error
    raise HTTPException(status_code=500, detail="仓储业务保存失败，请稍后重试") from error


@app.get("/warehouse/categories", response_model=schemas.WarehouseCategoryTreeResponse)
def read_warehouse_category_tree(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    if include_inactive and current_user.role == "readonly":
        raise HTTPException(status_code=403, detail="只读账号无权限查看已停用分类")
    try:
        return {
            "categories": warehouse_category_service.list_category_tree(
                db, include_inactive=include_inactive
            )
        }
    except Exception as error:
        _raise_warehouse_api_error(error)


@app.get(
    "/warehouse/categories/primary",
    response_model=List[schemas.WarehousePrimaryCategoryResponse],
)
def read_warehouse_primary_categories(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    return warehouse_category_service.list_active_primary_categories(db)


@app.get(
    "/warehouse/categories/primary/{primary_category_id}/secondary",
    response_model=List[schemas.WarehouseSecondaryCategoryResponse],
)
def read_warehouse_secondary_categories(
    primary_category_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    try:
        return warehouse_category_service.list_active_secondary_categories(
            db, primary_category_id
        )
    except Exception as error:
        _raise_warehouse_api_error(error)


@app.post(
    "/warehouse/categories/primary",
    response_model=schemas.WarehousePrimaryCategoryResponse,
)
def create_warehouse_primary_category(
    category: schemas.WarehousePrimaryCategoryCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_write_permission),
):
    try:
        created, _audit = warehouse_category_service.create_primary_category(
            db,
            code=category.code,
            name=category.name,
            sort_order=category.sort_order,
            operator_id=current_user.id,
        )
        return created
    except Exception as error:
        _raise_warehouse_api_error(error)


@app.patch(
    "/warehouse/categories/primary/{primary_category_id}",
    response_model=schemas.WarehousePrimaryCategoryResponse,
)
def update_warehouse_primary_category(
    primary_category_id: int,
    category: schemas.WarehousePrimaryCategoryUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_write_permission),
):
    try:
        updated, _audit = warehouse_category_service.update_primary_category(
            db,
            primary_category_id,
            changes=category.model_dump(exclude_unset=True),
            operator_id=current_user.id,
        )
        return updated
    except Exception as error:
        _raise_warehouse_api_error(error)


@app.post(
    "/warehouse/categories/secondary",
    response_model=schemas.WarehouseSecondaryCategoryResponse,
)
def create_warehouse_secondary_category(
    category: schemas.WarehouseSecondaryCategoryCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_write_permission),
):
    try:
        created, _audit = warehouse_category_service.create_secondary_category(
            db,
            primary_category_id=category.primary_category_id,
            code=category.code,
            name=category.name,
            sort_order=category.sort_order,
            operator_id=current_user.id,
        )
        return created
    except Exception as error:
        _raise_warehouse_api_error(error)


@app.patch(
    "/warehouse/categories/secondary/{secondary_category_id}",
    response_model=schemas.WarehouseSecondaryCategoryResponse,
)
def update_warehouse_secondary_category(
    secondary_category_id: int,
    category: schemas.WarehouseSecondaryCategoryUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_write_permission),
):
    try:
        updated, _audit = warehouse_category_service.update_secondary_category(
            db,
            secondary_category_id,
            changes=category.model_dump(exclude_unset=True),
            operator_id=current_user.id,
        )
        return updated
    except Exception as error:
        _raise_warehouse_api_error(error)


@app.get(
    "/warehouse/category-migration-issues",
    response_model=List[schemas.WarehouseCategoryMigrationIssueResponse],
)
def read_warehouse_category_migration_issues(
    status: Optional[str] = "OPEN",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    try:
        return warehouse_category_service.list_migration_issues(db, status=status)
    except Exception as error:
        _raise_warehouse_api_error(error)


@app.get("/warehouse/category-migration-issues/export")
def export_warehouse_category_migration_issues(
    status: Optional[str] = "OPEN",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    try:
        rows = warehouse_category_service.export_migration_issues(db, status=status)
        columns = [
            "问题编号", "物料标识", "物料名称", "原分类", "标准化分类",
            "处理原因代码", "处理原因", "状态", "创建时间", "解决时间",
        ]
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": "attachment; filename=warehouse-category-migration-issues.csv"
            },
        )
    except Exception as error:
        _raise_warehouse_api_error(error)


@app.post(
    "/warehouse/category-migration-issues/{migration_issue_id}/resolve",
    response_model=schemas.WarehouseCategoryMigrationResolutionResponse,
)
def resolve_warehouse_category_migration_issue(
    migration_issue_id: int,
    resolution: schemas.WarehouseCategoryMigrationResolutionRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_write_permission),
):
    try:
        issue, material, audit = warehouse_category_service.resolve_migration_issue(
            db,
            migration_issue_id,
            primary_category_id=resolution.primary_category_id,
            secondary_category_id=resolution.secondary_category_id,
            operator_id=current_user.id,
            resolution_note=resolution.resolution_note,
        )
        return {
            "warehouse_asset_id": material.id,
            "primary_category_id": material.primary_category_id,
            "secondary_category_id": material.secondary_category_id,
            "issue_id": issue.id,
            "audit_log_id": audit.id,
        }
    except Exception as error:
        _raise_warehouse_api_error(error)


@app.post("/warehouse/materials", response_model=schemas.WarehouseMaterialResponse)
def create_warehouse_material(
    material: schemas.WarehouseMaterialCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_write_permission),
):
    """采购到货的非固定资产物料按数量入库；不要求序列号，也不建资产卡。"""
    try:
        created, _audit = warehouse_material_service.create_material(
            db,
            payload=material.model_dump(),
            operator_id=current_user.id,
        )
        return warehouse_material_service.serialize_material(created)
    except Exception as error:
        _raise_warehouse_api_error(error)


@app.get("/warehouse/materials", response_model=List[schemas.WarehouseMaterialResponse])
def read_warehouse_materials(
    name: Optional[str] = None,
    primary_category_id: Optional[int] = None,
    secondary_category_id: Optional[int] = None,
    available_quantity: Optional[int] = None,
    allocated_quantity: Optional[int] = None,
    location: Optional[str] = None,
    low_stock_threshold: Optional[int] = None,
    low_stock: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    try:
        return warehouse_material_service.list_materials(
            db,
            filters={
                "name": name,
                "primary_category_id": primary_category_id,
                "secondary_category_id": secondary_category_id,
                "available_quantity": available_quantity,
                "allocated_quantity": allocated_quantity,
                "location": location,
                "low_stock_threshold": low_stock_threshold,
                "low_stock": low_stock,
            },
        )
    except Exception as error:
        _raise_warehouse_api_error(error)


@app.get("/warehouse/materials/{material_id}", response_model=schemas.WarehouseMaterialResponse)
def read_warehouse_material(
    material_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    try:
        return warehouse_material_service.get_material(db, material_id)
    except Exception as error:
        _raise_warehouse_api_error(error)


@app.put("/warehouse/materials/{material_id}", response_model=schemas.WarehouseMaterialResponse)
def update_warehouse_material(
    material_id: int,
    material: schemas.WarehouseMaterialUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_write_permission),
):
    try:
        updated, _audit = warehouse_material_service.update_material(
            db,
            material_id,
            changes=material.model_dump(exclude_unset=True),
            operator_id=current_user.id,
        )
        return warehouse_material_service.serialize_material(updated)
    except Exception as error:
        _raise_warehouse_api_error(error)


@app.get("/warehouse/{asset_id}", response_model=schemas.WarehouseAsset)
def read_warehouse_asset(asset_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    asset = db.query(models.WarehouseAsset).filter(models.WarehouseAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="warehouse asset not found")
    return asset


@app.put("/warehouse/{asset_id}", response_model=schemas.WarehouseAsset)
def update_warehouse_asset(asset_id: int, asset: schemas.WarehouseAssetUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(require_write_permission)):
    raise HTTPException(
        status_code=400,
        detail="仓储物料必须通过 /warehouse/materials/{id} 提交受控分类和库存变更",
    )
    # 加行锁，防止并发修改库存数量
    db_asset = db.query(models.WarehouseAsset).filter(
        models.WarehouseAsset.id == asset_id
    ).with_for_update().first()
    if not db_asset:
        raise HTTPException(status_code=404, detail="warehouse asset not found")

    try:
        update_data = asset.dict(exclude_unset=True)

        # dispatch_note 只用于日志描述，不写入数据库字段
        dispatch_note = update_data.pop("dispatch_note", None)

        # 守恒校验
        new_total = update_data.get("total_quantity", db_asset.total_quantity)
        new_available = update_data.get("available_quantity", db_asset.available_quantity)
        new_allocated = update_data.get("allocated_quantity", db_asset.allocated_quantity)

        qty_fields = {"total_quantity", "available_quantity", "allocated_quantity"}
        if qty_fields & set(update_data.keys()):
            if "total_quantity" in update_data and "available_quantity" not in update_data and "allocated_quantity" not in update_data:
                diff = new_total - db_asset.total_quantity
                new_available = max(0, db_asset.available_quantity + diff)
                update_data["available_quantity"] = new_available
            if new_available + new_allocated != new_total:
                if all(f in update_data for f in qty_fields):
                    raise HTTPException(
                        status_code=400,
                        detail=f"数量守恒校验失败: 总数量({new_total}) ≠ 可用数量({new_available}) + 已分配数量({new_allocated})"
                    )

        # 数量不能为负数
        for field in ["total_quantity", "available_quantity", "allocated_quantity"]:
            if field in update_data and update_data[field] is not None and update_data[field] < 0:
                label = FIELD_LABELS.get(field, field)
                raise HTTPException(status_code=400, detail=f"{label}不能为负数")

        changes = []
        for key, new_val in update_data.items():
            old_val = getattr(db_asset, key, None)
            old_str = (str(old_val).strip() if old_val is not None else "")
            new_str = (str(new_val).strip() if new_val is not None else "")
            if not old_str and not new_str:
                continue
            if old_str != new_str:
                label = FIELD_LABELS.get(key, key)
                changes.append(f"{label}: {old_str or '(空)'} → {new_str or '(空)'}")
        for key, value in update_data.items():
            setattr(db_asset, key, value)

        operator_name = current_user.full_name or current_user.username
        if dispatch_note:
            # 消耗品分配：用传入的分配说明作为日志描述
            wh_log = models.WarehouseAssetLog(
                asset_id=asset_id,
                action="出库（分配）",
                description=dispatch_note,
                operator=operator_name,
            )
            db.add(wh_log)
        elif changes:
            wh_log = models.WarehouseAssetLog(asset_id=asset_id, action="编辑", description="; ".join(changes), operator=operator_name)
            db.add(wh_log)

        db.commit()
        db.refresh(db_asset)
        return db_asset
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"更新库房资产失败: {str(e)}")


@app.get("/warehouse/{asset_id}/logs", response_model=List[schemas.WarehouseAssetLogResponse])
def read_warehouse_asset_logs(asset_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    return db.query(models.WarehouseAssetLog).filter(models.WarehouseAssetLog.asset_id == asset_id).order_by(models.WarehouseAssetLog.created_at.desc()).all()


@app.delete("/warehouse/{asset_id}")
def delete_warehouse_asset(asset_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin())):
    db_asset = db.query(models.WarehouseAsset).filter(models.WarehouseAsset.id == asset_id).first()
    if not db_asset:
        raise HTTPException(status_code=404, detail="warehouse asset not found")
    db.delete(db_asset)
    db.commit()
    return {"message": "warehouse asset deleted"}


# ========== 库房位置管理 ==========

@app.get("/locations/")
def list_locations(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    locations = db.query(models.WarehouseLocation).order_by(models.WarehouseLocation.name).all()
    return [{"id": loc.id, "name": loc.name, "description": loc.description} for loc in locations]


@app.post("/locations/")
def create_location(location_in: schemas.LocationCreate,
                    db: Session = Depends(get_db), 
                    current_user: models.User = Depends(require_admin)):
    name = location_in.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="位置名称不能为空")
    existing = db.query(models.WarehouseLocation).filter(models.WarehouseLocation.name == name).first()
    if existing:
        raise HTTPException(status_code=400, detail="该位置已存在")
    description = location_in.description.strip() or None
    loc = models.WarehouseLocation(name=name, description=description)
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return {"id": loc.id, "name": loc.name, "description": loc.description}


@app.delete("/locations/{location_id}")
def delete_location(location_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin())):
    loc = db.query(models.WarehouseLocation).filter(models.WarehouseLocation.id == location_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="位置不存在")
    db.delete(loc)
    db.commit()
    return {"message": f"位置 {loc.name} 已删除"}

# ========== 办公室使用位置管理（台式机） ==========

@app.get("/office-locations/")
def list_office_locations(db: Session = Depends(get_db)):
    locations = db.query(models.OfficeLocation).order_by(models.OfficeLocation.name).all()
    return [{"id": loc.id, "name": loc.name, "description": loc.description} for loc in locations]

@app.post("/office-locations/")
def create_office_location(
    location_in: schemas.LocationCreate,
    db: Session = Depends(get_db), 
    current_user: models.User = Depends(require_admin)
    ):
    name = location_in.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="位置名称不能为空")
    existing = db.query(models.OfficeLocation).filter(models.OfficeLocation.name == name).first()
    if existing:
        raise HTTPException(status_code=400, detail="该位置已存在")
    description = location_in.description.strip()  if location_in.description else None
    loc = models.OfficeLocation(name=name, description=description)
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return {"id": loc.id, "name": loc.name, "description": loc.description}


@app.delete("/office-locations/{location_id}")
def delete_office_location(location_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin())):
    loc = db.query(models.OfficeLocation).filter(models.OfficeLocation.id == location_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="位置不存在")
    db.delete(loc)
    db.commit()
    return {"message": f"位置 {loc.name} 已删除"}


# ========== 品牌管理 ==========

@app.get("/brands/")
def list_brands(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    brands = db.query(models.Brand).order_by(models.Brand.name).all()
    return [{"id": b.id, "name": b.name} for b in brands]


@app.post("/brands/")
def create_brand(data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin())):
    name = data.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="品牌名称不能为空")
    if db.query(models.Brand).filter(models.Brand.name == name).first():
        raise HTTPException(status_code=400, detail="该品牌已存在")
    brand = models.Brand(name=name)
    db.add(brand)
    db.commit()
    db.refresh(brand)
    return {"id": brand.id, "name": brand.name}


@app.delete("/brands/{brand_id}")
def delete_brand(brand_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin())):
    brand = db.query(models.Brand).filter(models.Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="品牌不存在")
    db.delete(brand)
    db.commit()
    return {"message": f"品牌 {brand.name} 已删除"}


# ========== 部门管理 ==========

@app.get("/departments/")
def list_departments(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    """返回树形部门列表"""
    all_depts = db.query(models.Department).order_by(models.Department.name).all()
    # 构建树形结构
    parents = [d for d in all_depts if d.parent_id is None]
    result = []
    for p in parents:
        children = [{"id": c.id, "name": c.name} for c in all_depts if c.parent_id == p.id]
        result.append({"id": p.id, "name": p.name, "children": children})
    return result


@app.get("/departments/flat")
def list_departments_flat(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    """返回扁平部门列表（用于下拉选择，格式: 主分类 - 子分类）"""
    all_depts = db.query(models.Department).order_by(models.Department.name).all()
    parent_map = {d.id: d.name for d in all_depts if d.parent_id is None}
    result = []
    for d in all_depts:
        if d.parent_id is None:
            # 主分类本身也可选
            result.append({"id": d.id, "name": d.name, "display": d.name})
        else:
            parent_name = parent_map.get(d.parent_id, "")
            result.append({"id": d.id, "name": d.name, "display": f"{parent_name} - {d.name}"})
    result.sort(key=lambda x: x["display"])
    return result


@app.post("/departments/")
def create_department(data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin())):
    name = data.get("name", "").strip()
    parent_id = data.get("parent_id")
    if not name:
        raise HTTPException(status_code=400, detail="部门名称不能为空")
    # 检查同级是否重名
    existing = db.query(models.Department).filter(
        models.Department.name == name,
        models.Department.parent_id == parent_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="该部门已存在")
    if parent_id:
        parent = db.query(models.Department).filter(models.Department.id == parent_id).first()
        if not parent:
            raise HTTPException(status_code=400, detail="父级部门不存在")
        if parent.parent_id is not None:
            raise HTTPException(status_code=400, detail="仅支持两级结构")
    dept = models.Department(name=name, parent_id=parent_id)
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return {"id": dept.id, "name": dept.name, "parent_id": dept.parent_id}


@app.delete("/departments/{dept_id}")
def delete_department(dept_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin())):
    conflict_detail = "该部门仍被资产或历史记录引用，请停用部门或迁移资产后再删除"
    try:
        dept = (
            db.query(models.Department)
            .filter(models.Department.id == dept_id)
            .with_for_update()
            .first()
        )
        if not dept:
            raise HTTPException(status_code=404, detail="部门不存在")

        # 删除父部门会同时删除直接子部门，因此必须检查整个待删除集合。
        children = (
            db.query(models.Department)
            .filter(models.Department.parent_id == dept_id)
            .with_for_update()
            .all()
        )
        departments_to_delete = [dept, *children]
        department_ids = [item.id for item in departments_to_delete]
        department_names = [item.name for item in departments_to_delete]

        has_reference = (
            db.query(models.Asset.id)
            .filter(models.Asset.department.in_(department_names))
            .first()
            is not None
        )
        if not has_reference:
            has_reference = (
                db.query(models.MaterialIssue.id)
                .filter(models.MaterialIssue.recipient_department.in_(department_names))
                .first()
                is not None
            )
        if not has_reference:
            has_reference = (
                db.query(models.FixedAssetIssuance.id)
                .filter(models.FixedAssetIssuance.recipient_department.in_(department_names))
                .first()
                is not None
            )
        if not has_reference:
            has_reference = (
                db.query(models.ReturnRecord.id)
                .filter(models.ReturnRecord.department.in_(department_names))
                .first()
                is not None
            )
        if not has_reference:
            has_reference = (
                db.query(models.NetworkConsumableIssue.id)
                .filter(models.NetworkConsumableIssue.department_id.in_(department_ids))
                .first()
                is not None
            )

        # 生命周期部门位于 JSON 绑定中；在 Python 层检查以兼容 SQLite 与 PostgreSQL。
        if not has_reference:
            for previous_binding, new_binding in (
                db.query(
                    models.AssetLifecycleEvent.previous_binding,
                    models.AssetLifecycleEvent.new_binding,
                )
                .yield_per(500)
            ):
                bindings = (previous_binding, new_binding)
                if any(
                    isinstance(binding, dict)
                    and binding.get("department") in department_names
                    for binding in bindings
                ):
                    has_reference = True
                    break

        if has_reference:
            raise HTTPException(status_code=409, detail=conflict_detail)

        for child in children:
            db.delete(child)
        db.delete(dept)
        db.commit()
        return {"message": f"部门 {dept.name} 已删除"}
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="删除部门失败")


@app.post("/return-records/", response_model=schemas.ReturnRecord)
def create_return_record(record: schemas.ReturnRecordCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_write_permission)):
    db_record = models.ReturnRecord(**record.dict())
    db.add(db_record)
    db.commit()
    db.refresh(db_record)
    return db_record


@app.get("/return-records/", response_model=List[schemas.ReturnRecord])
def read_return_records(
    skip: int = 0,
    limit: int = 100,
    is_returned: Optional[bool] = None,
    department: Optional[str] = None,
    return_reason: Optional[str] = None,
    employee_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    query = db.query(models.ReturnRecord)
    if is_returned is not None:
        query = query.filter(models.ReturnRecord.is_returned == is_returned)
    if department:
        query = query.filter(models.ReturnRecord.department == department)
    if return_reason:
        query = query.filter(models.ReturnRecord.return_reason == return_reason)
    if employee_name:
        query = query.filter(models.ReturnRecord.employee_name.ilike(f"%{employee_name}%"))
    if date_from:
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d")
            query = query.filter(models.ReturnRecord.created_at >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(models.ReturnRecord.created_at < dt_to)
        except ValueError:
            pass
    return query.order_by(models.ReturnRecord.created_at.desc()).offset(skip).limit(limit).all()


@app.get("/return-records/history/summary")
def get_return_history_summary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """归还历史统计：按原因分组、按部门分组、近30天趋势"""
    from sqlalchemy import func

    # 按归还原因统计
    by_reason = db.query(
        models.ReturnRecord.return_reason,
        func.count(models.ReturnRecord.id).label("count")
    ).group_by(models.ReturnRecord.return_reason).all()

    # 按部门统计（已归还）
    by_dept = db.query(
        models.ReturnRecord.department,
        func.count(models.ReturnRecord.id).label("count")
    ).filter(
        models.ReturnRecord.is_returned == True,
        models.ReturnRecord.department != None
    ).group_by(models.ReturnRecord.department).order_by(func.count(models.ReturnRecord.id).desc()).limit(10).all()

    # 近30天每天归还数量
    thirty_days_ago = datetime.now() - timedelta(days=30)
    recent = db.query(models.ReturnRecord).filter(
        models.ReturnRecord.is_returned == True,
        models.ReturnRecord.return_date >= thirty_days_ago
    ).all()
    daily_counts: dict = {}
    for r in recent:
        if r.return_date:
            day = r.return_date.strftime("%Y-%m-%d")
            daily_counts[day] = daily_counts.get(day, 0) + 1

    return {
        "by_reason": [{"reason": r.return_reason, "count": r.count} for r in by_reason],
        "by_department": [{"department": r.department or "未知", "count": r.count} for r in by_dept],
        "daily_trend": [{"date": k, "count": v} for k, v in sorted(daily_counts.items())],
    }


@app.put("/return-records/{record_id}", response_model=schemas.ReturnRecord)
def update_return_record(record_id: int, record: schemas.ReturnRecordUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(require_write_permission)):
    db_record = db.query(models.ReturnRecord).filter(models.ReturnRecord.id == record_id).first()
    if not db_record:
        raise HTTPException(status_code=404, detail="return record not found")

    update_data = record.dict(exclude_unset=True)
    was_returned = db_record.is_returned
    now_returned = update_data.get("is_returned", was_returned)

    for key, value in update_data.items():
        setattr(db_record, key, value)

    # ── 归还状态从"待归还"变为"已归还"时，联动更新对应资产状态为"闲置" ──
    if not was_returned and now_returned:
        asset_name = db_record.asset_name
        # 优先通过 hostname 匹配，其次通过 asset_tag 匹配
        linked_asset = db.query(models.Asset).filter(
            models.Asset.is_deleted == False,
            models.Asset.hostname == asset_name
        ).first()
        if not linked_asset:
            linked_asset = db.query(models.Asset).filter(
                models.Asset.is_deleted == False,
                models.Asset.asset_tag == asset_name
            ).first()

        if linked_asset and linked_asset.status != "闲置":
            old_status = linked_asset.status
            linked_asset.status = "闲置"
            linked_asset.employee_name = None
            linked_asset.employee_id = None
            linked_asset.department = None
            linked_asset.supervisor = None
            linked_asset.issue_date = None
            db.flush()

            # 同步库房可用数量
            _sync_warehouse_quantity(db, linked_asset.category, +1,
                                     current_user.full_name or current_user.username)

            # 记录资产操作日志
            operator_name = current_user.full_name or current_user.username
            create_log(db, linked_asset.id, f"状态变更: {old_status} → 闲置",
                       f"归还处理联动：归还记录 #{record_id}，资产状态变更为闲置",
                       None, None, operator=operator_name)
            create_operation_log(db, current_user.id, "update", "asset", linked_asset.id,
                                 f"归还处理联动：资产 {linked_asset.asset_tag} 状态变更为闲置")

    db.commit()
    db.refresh(db_record)
    return db_record


@app.get("/return-records/stats")
def get_return_stats(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    total = db.query(models.ReturnRecord).count()
    returned = db.query(models.ReturnRecord).filter(models.ReturnRecord.is_returned == True).count()
    pending = db.query(models.ReturnRecord).filter(models.ReturnRecord.is_returned == False).count()
    return {"total_records": total, "returned_count": returned, "pending_count": pending}



# ========== 维修、网络、工具和办公物料用途追踪 API ==========
# 保持这些端点的所有写入都由 material_issuance_service 的领域事务完成，
# 路由层只负责请求契约、权限依赖与中文 HTTP 语义映射。
import material_issuance_service


def _special_material_error_status(error: Exception) -> int:
    if isinstance(
        error,
        (
            material_issuance_service.MaterialNotFoundError,
            material_issuance_service.MaterialIssueNotFoundError,
        ),
    ):
        return 404
    if isinstance(error, material_issuance_service.MaterialStockConflictError):
        return 409
    if isinstance(error, material_issuance_service.MaterialIssuanceError):
        return 400
    if isinstance(error, DomainTransactionError):
        return 500
    return 500


def _special_material_error_detail(error: Exception) -> str:
    if isinstance(error, DomainTransactionError):
        return error.detail
    if isinstance(error, material_issuance_service.MaterialIssuanceError):
        return str(error)
    return "物料业务保存失败，请稍后重试"


def _raise_special_material_api_error(db: Session, error: Exception) -> None:
    db.rollback()
    raise HTTPException(
        status_code=_special_material_error_status(error),
        detail=_special_material_error_detail(error),
    ) from error


def _inventory_payload(material: models.WarehouseAsset) -> dict:
    return {
        "id": material.id,
        "name": material.name,
        "total_quantity": material.total_quantity,
        "available_quantity": material.available_quantity,
        "allocated_quantity": material.allocated_quantity,
        "low_stock": material.available_quantity < material.low_stock_threshold,
        "low_stock_message": (
            "低库存预警" if material.available_quantity < material.low_stock_threshold else None
        ),
    }


def _ordinary_material_issue_payload(
    result: material_issuance_service.MaterialIssueResult,
) -> dict:
    issue = result.issue
    return {
        "material_issue": {
            "id": issue.id,
            "warehouse_asset_id": issue.warehouse_asset_id,
            "record_type": issue.record_type,
            "issue_policy": issue.issue_policy,
            "quantity": issue.quantity,
            "unreturned_quantity": issue.unreturned_quantity,
            "consumed_completed": issue.consumed_completed,
            "recipient_name": issue.recipient_name,
            "recipient_employee_id": issue.recipient_employee_id,
            "recipient_department": issue.recipient_department,
            "purpose": issue.purpose,
            "operator_id": issue.operator_id,
            "issued_at": issue.issued_at,
        },
        "inventory": _inventory_payload(result.warehouse_asset),
        "audit_log_id": result.audit_log.id,
    }


def _ordinary_material_return_payload(
    result: material_issuance_service.MaterialReturnResult,
) -> dict:
    return {
        "material_return": {
            "id": result.material_return.id,
            "material_issue_id": result.material_return.material_issue_id,
            "quantity": result.material_return.quantity,
            "returned_at": result.material_return.returned_at,
            "operator_id": result.material_return.operator_id,
        },
        "material_issue": {
            "id": result.issue.id,
            "record_type": result.issue.record_type,
            "issue_policy": result.issue.issue_policy,
            "quantity": result.issue.quantity,
            "unreturned_quantity": result.issue.unreturned_quantity,
            "consumed_completed": result.issue.consumed_completed,
        },
        "inventory": _inventory_payload(result.warehouse_asset),
        "audit_log_id": result.audit_log.id,
    }


@app.post("/material-issues")
def create_material_issue(
    payload: schemas.MaterialIssueCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_write_permission),
):
    try:
        return _ordinary_material_issue_payload(
            material_issuance_service.issue_material(
                db,
                warehouse_asset_id=payload.warehouse_asset_id,
                quantity=payload.quantity,
                issued_at=payload.issued_at,
                operator_id=current_user.id,
                recipient_name=payload.recipient_name,
                recipient_employee_id=payload.recipient_employee_id,
                recipient_department=payload.recipient_department,
                purpose=payload.purpose,
                ip_address=request.client.host if request.client else None,
            )
        )
    except Exception as error:
        _raise_special_material_api_error(db, error)


@app.post("/material-issues/{material_issue_id}/returns")
def create_material_issue_return(
    material_issue_id: int,
    payload: schemas.MaterialReturnCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_write_permission),
):
    try:
        return _ordinary_material_return_payload(
            material_issuance_service.return_material(
                db,
                material_issue_id=material_issue_id,
                quantity=payload.quantity,
                returned_at=payload.returned_at,
                operator_id=current_user.id,
                ip_address=request.client.host if request.client else None,
            )
        )
    except Exception as error:
        _raise_special_material_api_error(db, error)


def _material_issue_payload(
    result: material_issuance_service.SpecializedMaterialIssueResult,
) -> dict:
    issue = result.issue
    specialized = result.specialized_issue
    return {
        "material_issue": {
            "id": issue.id,
            "warehouse_asset_id": issue.warehouse_asset_id,
            "record_type": issue.record_type,
            "issue_policy": issue.issue_policy,
            "quantity": issue.quantity,
            "unreturned_quantity": issue.unreturned_quantity,
            "consumed_completed": issue.consumed_completed,
            "issued_at": issue.issued_at,
        },
        "domain_record": (
            {
                "id": specialized.id,
                "type": specialized.__tablename__,
                "material_issue_id": specialized.material_issue_id,
            }
            if specialized is not None
            else None
        ),
        "inventory": _inventory_payload(result.warehouse_asset),
        "audit_log_id": result.audit_log.id,
    }


def _tool_loan_payload(
    loan: models.ToolLoan,
    material: models.WarehouseAsset,
    db: Optional[Session] = None,
) -> dict:
    borrower = getattr(loan, "borrower", None)
    borrower_id = getattr(loan, "borrower_id", None)
    if borrower is None and borrower_id is not None and db is not None:
        borrower = db.query(models.Employee).filter(models.Employee.id == borrower_id).one_or_none()
    return {
        "id": loan.id,
        "warehouse_asset_id": loan.warehouse_asset_id,
        "material_name": material.name,
        "borrower_id": borrower_id,
        "borrower_ref": loan.borrower_ref,
        "employee": _employee_brief_payload(borrower),
        "quantity": loan.quantity,
        "unreturned_quantity": loan.unreturned_quantity,
        "status": loan.status,
        "borrowed_at": loan.borrowed_at,
        "expected_return_at": loan.expected_return_at,
        "returned_at": loan.returned_at,
        "tool_identifier": loan.tool_identifier,
        "operator_id": loan.operator_id,
    }


@app.post("/repair-parts/issues")
def create_repair_part_issue(
    payload: schemas.RepairPartIssueRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_write_permission),
):
    try:
        result = material_issuance_service.issue_repair_part(
            db,
            warehouse_asset_id=payload.warehouse_asset_id,
            quantity=payload.quantity,
            issued_at=payload.issued_at,
            operator_id=current_user.id,
            target_asset_id=payload.target_asset_id,
            repair_order_ref=payload.repair_order_ref,
            disk_serial_number=payload.disk_serial_number,
            ip_address=request.client.host if request.client else None,
        )
        response = _material_issue_payload(result)
        repair_issue = result.specialized_issue
        response["domain_record"].update({
            "target_asset_id": repair_issue.target_asset_id,
            "repair_order_ref": repair_issue.repair_order_ref,
            "disk_serial_number": repair_issue.disk_serial_number,
        })
        return response
    except Exception as error:
        _raise_special_material_api_error(db, error)


@app.post("/network-consumables/issues")
def create_network_consumable_issue(
    payload: schemas.NetworkConsumableIssueRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_write_permission),
):
    try:
        result = material_issuance_service.issue_network_consumable(
            db,
            warehouse_asset_id=payload.warehouse_asset_id,
            quantity=payload.quantity,
            issued_at=payload.issued_at,
            operator_id=current_user.id,
            department_id=payload.department_id,
            project_ref=payload.project_ref,
            server_room_ref=payload.server_room_ref,
            work_order_ref=payload.work_order_ref,
            ip_address=request.client.host if request.client else None,
        )
        response = _material_issue_payload(result)
        network_issue = result.specialized_issue
        response["domain_record"].update({
            "department_id": network_issue.department_id,
            "project_ref": network_issue.project_ref,
            "server_room_ref": network_issue.server_room_ref,
            "work_order_ref": network_issue.work_order_ref,
        })
        return response
    except Exception as error:
        _raise_special_material_api_error(db, error)


@app.post("/office-consumables/issues")
def create_office_consumable_issue(
    payload: schemas.OfficeConsumableIssueRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_write_permission),
):
    try:
        return _material_issue_payload(
            material_issuance_service.issue_office_consumable(
                db,
                warehouse_asset_id=payload.warehouse_asset_id,
                quantity=payload.quantity,
                issued_at=payload.issued_at,
                operator_id=current_user.id,
                ip_address=request.client.host if request.client else None,
            )
        )
    except Exception as error:
        _raise_special_material_api_error(db, error)


@app.post("/tool-loans")
def create_tool_loan(
    payload: schemas.ToolLoanCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_write_permission),
):
    try:
        result = material_issuance_service.borrow_tool(
            db,
            warehouse_asset_id=payload.warehouse_asset_id,
            borrower_id=getattr(payload, "borrower_id", None),
            borrower_ref=getattr(payload, "borrower_ref", None),
            quantity=payload.quantity,
            borrowed_at=payload.borrowed_at,
            expected_return_at=payload.expected_return_at,
            tool_identifier=payload.tool_identifier,
            operator_id=current_user.id,
            ip_address=request.client.host if request.client else None,
        )
        return {
            "tool_loan": _tool_loan_payload(
                result.loan, result.warehouse_asset, db
            ),
            "inventory": _inventory_payload(result.warehouse_asset),
            "audit_log_id": result.audit_log.id,
        }
    except Exception as error:
        _raise_special_material_api_error(db, error)


@app.post("/tool-loans/{tool_loan_id}/returns")
def create_tool_loan_return(
    tool_loan_id: int,
    payload: schemas.ToolLoanReturnRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_write_permission),
):
    try:
        result = material_issuance_service.return_tool(
            db,
            tool_loan_id=tool_loan_id,
            quantity=payload.quantity,
            returned_at=payload.returned_at,
            operator_id=current_user.id,
            ip_address=request.client.host if request.client else None,
        )
        return {
            "return_event": {
                "id": result.return_event.id,
                "tool_loan_id": result.return_event.tool_loan_id,
                "quantity": result.return_event.quantity,
                "is_partial": result.return_event.is_partial,
                "returned_at": result.return_event.returned_at,
            },
            "tool_loan": _tool_loan_payload(
                result.loan, result.warehouse_asset, db
            ),
            "inventory": _inventory_payload(result.warehouse_asset),
            "audit_log_id": result.audit_log.id,
        }
    except Exception as error:
        _raise_special_material_api_error(db, error)


@app.get("/tool-loans")
def read_tool_loans(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    query = db.query(models.ToolLoan).order_by(models.ToolLoan.borrowed_at.desc())
    if status is not None:
        if status not in {"BORROWED", "RETURNED"}:
            raise HTTPException(status_code=400, detail="工具借用状态仅支持 BORROWED 或 RETURNED")
        query = query.filter(models.ToolLoan.status == status)
    loans = query.all()
    return [_tool_loan_payload(loan, loan.warehouse_asset, db) for loan in loans]


@app.get("/tool-loans/{tool_loan_id}")
def read_tool_loan(
    tool_loan_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    loan = db.query(models.ToolLoan).filter(models.ToolLoan.id == tool_loan_id).one_or_none()
    if loan is None:
        raise HTTPException(status_code=404, detail="工具借用记录不存在")
    payload = _tool_loan_payload(loan, loan.warehouse_asset, db)
    payload["return_events"] = [
        {
            "id": event.id,
            "quantity": event.quantity,
            "is_partial": event.is_partial,
            "returned_at": event.returned_at,
            "operator_id": event.operator_id,
        }
        for event in sorted(loan.return_events, key=lambda item: item.returned_at)
    ]
    return payload



def _repair_part_issue_payload(record: models.RepairPartIssue) -> dict:
    issue = record.material_issue
    material = issue.warehouse_asset
    return {
        "id": record.id,
        "material_issue_id": record.material_issue_id,
        "warehouse_asset_id": material.id,
        "material_name": material.name,
        "quantity": issue.quantity,
        "issued_at": issue.issued_at,
        "target_asset_id": record.target_asset_id,
        "repair_order_ref": record.repair_order_ref,
        "disk_serial_number": record.disk_serial_number,
        "operator_id": issue.operator_id,
    }


def _network_consumable_issue_payload(record: models.NetworkConsumableIssue) -> dict:
    issue = record.material_issue
    material = issue.warehouse_asset
    return {
        "id": record.id,
        "material_issue_id": record.material_issue_id,
        "warehouse_asset_id": material.id,
        "material_name": material.name,
        "quantity": issue.quantity,
        "issued_at": issue.issued_at,
        "department_id": record.department_id,
        "project_ref": record.project_ref,
        "server_room_ref": record.server_room_ref,
        "work_order_ref": record.work_order_ref,
        "operator_id": issue.operator_id,
    }


def _office_consumable_issue_payload(issue: models.MaterialIssue) -> dict:
    material = issue.warehouse_asset
    return {
        "id": issue.id,
        "warehouse_asset_id": material.id,
        "material_name": material.name,
        "quantity": issue.quantity,
        "record_type": issue.record_type,
        "issue_policy": issue.issue_policy,
        "consumed_completed": issue.consumed_completed,
        "issued_at": issue.issued_at,
        "operator_id": issue.operator_id,
    }


@app.get("/repair-parts/issues")
def read_repair_part_issues(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    records = db.query(models.RepairPartIssue).order_by(models.RepairPartIssue.id.desc()).all()
    return [_repair_part_issue_payload(record) for record in records]


@app.get("/repair-parts/issues/{issue_id}")
def read_repair_part_issue(
    issue_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    record = db.query(models.RepairPartIssue).filter(models.RepairPartIssue.id == issue_id).one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="维修备件发放记录不存在")
    return _repair_part_issue_payload(record)


@app.get("/network-consumables/issues")
def read_network_consumable_issues(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    records = db.query(models.NetworkConsumableIssue).order_by(models.NetworkConsumableIssue.id.desc()).all()
    return [_network_consumable_issue_payload(record) for record in records]


@app.get("/network-consumables/issues/{issue_id}")
def read_network_consumable_issue(
    issue_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    record = db.query(models.NetworkConsumableIssue).filter(models.NetworkConsumableIssue.id == issue_id).one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="网络与机房耗材发放记录不存在")
    return _network_consumable_issue_payload(record)


@app.get("/office-consumables/issues")
def read_office_consumable_issues(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    records = (
        db.query(models.MaterialIssue)
        .join(models.WarehouseAsset, models.MaterialIssue.warehouse_asset_id == models.WarehouseAsset.id)
        .join(
            models.WarehousePrimaryCategory,
            models.WarehouseAsset.primary_category_id == models.WarehousePrimaryCategory.id,
        )
        .filter(
            models.WarehousePrimaryCategory.code == "OFFICE_GENERAL_CONSUMABLES",
            models.MaterialIssue.record_type == "CONSUMABLE",
            models.MaterialIssue.consumed_completed.is_(True),
        )
        .order_by(models.MaterialIssue.id.desc())
        .all()
    )
    return [_office_consumable_issue_payload(record) for record in records]


@app.get("/office-consumables/issues/{issue_id}")
def read_office_consumable_issue(
    issue_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    record = (
        db.query(models.MaterialIssue)
        .join(models.WarehouseAsset, models.MaterialIssue.warehouse_asset_id == models.WarehouseAsset.id)
        .join(
            models.WarehousePrimaryCategory,
            models.WarehouseAsset.primary_category_id == models.WarehousePrimaryCategory.id,
        )
        .filter(
            models.MaterialIssue.id == issue_id,
            models.WarehousePrimaryCategory.code == "OFFICE_GENERAL_CONSUMABLES",
            models.MaterialIssue.record_type == "CONSUMABLE",
            models.MaterialIssue.consumed_completed.is_(True),
        )
        .one_or_none()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="办公与通用耗材发放记录不存在")
    return _office_consumable_issue_payload(record)



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
