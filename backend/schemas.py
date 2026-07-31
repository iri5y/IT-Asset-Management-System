from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from datetime import datetime
from typing import ClassVar, Literal, Optional, List, Set

# ========== 用户认证 Schemas ==========

class UserBase(BaseModel):
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: str = "MIS"

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    confirm_action: Optional[bool] = None  # 二次确认标志

class UserPasswordChange(BaseModel):
    old_password: Optional[str] = None  # 管理员重置时可以不提供
    new_password: str

class UserResponse(UserBase):
    id: int
    is_active: bool
    must_change_password: bool = False
    password_changed_at: Optional[datetime] = None
    last_login: Optional[datetime] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class UserLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse
    password_expired: bool = False
    password_remind: bool = False  # 提醒修改密码（admin超过90天）
    must_change_password: bool = False  # 新用户首次登录必须修改密码

class TokenRefresh(BaseModel):
    refresh_token: str

class OperationLogResponse(BaseModel):
    id: int
    user_id: int
    action: str
    resource_type: str
    resource_id: Optional[int] = None
    description: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class AssetDeletionRequest(BaseModel):
    reason: str

class AssetDeletionRecordResponse(BaseModel):
    id: int
    asset_id: int
    asset_tag: str
    asset_data: Optional[str] = None
    deletion_reason: str
    deleted_by: int
    deleted_at: datetime
    
    class Config:
        from_attributes = True

# ========== 资产管理 Schemas ==========

class EmployeeBase(BaseModel):
    employee_no: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    department: str = Field(min_length=1, max_length=100)
    status: Literal["ACTIVE", "DEPARTED"] = "ACTIVE"
    departure_date: Optional[datetime] = None

    @field_validator("employee_no", "name", "department")
    @classmethod
    def trim_required_employee_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("工号、姓名和部门不能为空")
        return normalized

    @field_validator("status", mode="before")
    @classmethod
    def normalize_employee_status(cls, value: str) -> str:
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_departure_state(self):
        if self.status == "ACTIVE" and self.departure_date is not None:
            raise ValueError("在职员工不能设置离职日期")
        if self.status == "DEPARTED" and self.departure_date is None:
            raise ValueError("离职员工必须设置离职日期")
        return self


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeUpdate(BaseModel):
    employee_no: Optional[str] = Field(default=None, min_length=1, max_length=100)
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    department: Optional[str] = Field(default=None, min_length=1, max_length=100)
    status: Optional[Literal["ACTIVE", "DEPARTED"]] = None
    departure_date: Optional[datetime] = None

    @field_validator("employee_no", "name", "department")
    @classmethod
    def trim_optional_employee_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("工号、姓名和部门不能为空")
        return normalized

    @field_validator("status", mode="before")
    @classmethod
    def normalize_optional_employee_status(cls, value):
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_departure_update(self):
        if self.status == "ACTIVE" and self.departure_date is not None:
            raise ValueError("在职员工不能设置离职日期")
        if self.status == "DEPARTED" and self.departure_date is None:
            raise ValueError("将员工设为离职时必须设置离职日期")
        return self


class EmployeeResponse(EmployeeBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AssetBase(BaseModel):
    asset_tag: str
    category: str
    brand: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    status: str
    purchase_date: Optional[datetime] = None
    notes: Optional[str] = None
    
    # 计算机专用字段
    employee_ref_id: Optional[int] = Field(default=None, gt=0)
    employee_id: Optional[str] = None
    employee_name: Optional[str] = None
    department: Optional[str] = None
    hostname: Optional[str] = None
    mac_address: Optional[str] = None
    ip_address: Optional[str] = None
    fixed_asset_number: Optional[str] = None
    system_version: Optional[str] = None
    antivirus_software: Optional[str] = None
    issue_date: Optional[datetime] = None
    lock_number: Optional[str] = None
    supervisor: Optional[str] = None
    bios_password: Optional[bool] = None
    tpm_status: Optional[bool] = None
    has_desktop: Optional[bool] = None
    po_number: Optional[str] = None
    condition: Optional[str] = None  # 资产状况：可用 / 损坏 / 待报废（主要用于闲置资产）
    
    # 库房资产字段
    location: Optional[str] = None
    quantity: Optional[int] = 1

    # 扩展字段：存储 Excel 中未映射到固定列的额外数据
    additional_info: Optional[dict] = None

    # 标记该资产是否由库房发放创建（归还时不触发库房数量自动同步）
    from_warehouse: Optional[bool] = False

class AssetCreate(AssetBase):
    # 需要 SN 的品类列表（笔记本、台式机、服务器等主要设备）
    SN_REQUIRED_CATEGORIES: ClassVar[Set[str]] = {"笔记本电脑", "台式机", "服务器", "移动设备"}
    # PO号必填的品类
    PO_REQUIRED_CATEGORIES: ClassVar[Set[str]] = {"笔记本电脑", "台式机"}

    @model_validator(mode="after")
    def validate_serial_number_by_category(self):
        """根据品类决定字段必填规则：
        - 笔记本电脑、台式机、服务器、移动设备：SN 必填
        - 笔记本电脑、台式机：PO号必填，且必须为纯数字
        """
        # 1. 序列号必填校验
        if self.category in self.SN_REQUIRED_CATEGORIES:
            if not self.serial_number or not self.serial_number.strip():
                raise ValueError(f"品类为「{self.category}」时，序列号（serial_number）为必填项")

        # 2. PO号必填 + 纯数字格式校验
        if self.category in self.PO_REQUIRED_CATEGORIES:
            if not self.po_number or not self.po_number.strip():
                raise ValueError(f"当资产分类为「{self.category}」时，PO号为必填项")
            if not self.po_number.strip().isdigit():
                raise ValueError("PO号格式错误，必须为纯数字（例如：12000327）")
        elif self.po_number and self.po_number.strip():
            # 非必填品类若填写了 PO号，也校验格式
            if not self.po_number.strip().isdigit():
                raise ValueError("PO号格式错误，必须为纯数字（例如：12000327）")

        return self

class AssetUpdate(BaseModel):
    asset_tag: Optional[str] = None
    category: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    status: Optional[str] = None
    purchase_date: Optional[datetime] = None
    notes: Optional[str] = None
    
    # 计算机专用字段
    employee_ref_id: Optional[int] = Field(default=None, gt=0)
    employee_id: Optional[str] = None
    employee_name: Optional[str] = None
    department: Optional[str] = None
    hostname: Optional[str] = None
    mac_address: Optional[str] = None
    ip_address: Optional[str] = None
    fixed_asset_number: Optional[str] = None
    system_version: Optional[str] = None
    antivirus_software: Optional[str] = None
    issue_date: Optional[datetime] = None
    lock_number: Optional[str] = None
    supervisor: Optional[str] = None
    bios_password: Optional[bool] = None
    tpm_status: Optional[bool] = None
    has_desktop: Optional[bool] = None
    po_number: str | None = None
    condition: Optional[str] = None  # 资产状况：可用 / 损坏 / 待报废
    
    location: Optional[str] = None
    quantity: Optional[int] = None

    # 扩展字段
    additional_info: Optional[dict] = None

class Asset(AssetBase):
    id: int
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class AssetLogBase(BaseModel):
    action: str
    description: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    operator: Optional[str] = None

class AssetLog(AssetLogBase):
    id: int
    asset_id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

class HostnameHistoryBase(BaseModel):
    old_hostname: Optional[str] = None
    new_hostname: Optional[str] = None
    change_reason: Optional[str] = None

class HostnameHistory(HostnameHistoryBase):
    id: int
    asset_id: int
    changed_at: datetime
    
    class Config:
        from_attributes = True

class AssetWithLogs(Asset):
    logs: List[AssetLog] = []
    hostname_history: List[HostnameHistory] = []

class WarehouseAssetBase(BaseModel):
    name: str
    category: str
    subcategory: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    receiver_name: Optional[str] = None
    total_quantity: int = 0
    available_quantity: int = 0
    allocated_quantity: int = 0
    minimum_stock: int = 5
    location: Optional[str] = None
    notes: Optional[str] = None

class WarehouseAssetCreate(WarehouseAssetBase):
    pass

class WarehouseAssetUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    receiver_name: Optional[str] = None
    total_quantity: Optional[int] = None
    available_quantity: Optional[int] = None
    allocated_quantity: Optional[int] = None
    minimum_stock: Optional[int] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    dispatch_note: Optional[str] = None  # 消耗品分配备注，用于操作日志描述，不存入资产字段

class WarehouseAsset(WarehouseAssetBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class WarehouseAssetLogResponse(BaseModel):
    id: int
    asset_id: int
    action: str
    description: Optional[str] = None
    operator: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class ReturnRecordBase(BaseModel):
    asset_name: str
    employee_id: str
    employee_name: str
    department: Optional[str] = None
    return_reason: str
    is_returned: bool = False
    return_date: Optional[datetime] = None
    notes: Optional[str] = None

class ReturnRecordCreate(ReturnRecordBase):
    pass

class ReturnRecordUpdate(BaseModel):
    return_reason: Optional[str] = None
    is_returned: Optional[bool] = None
    return_date: Optional[datetime] = None
    notes: Optional[str] = None

class ReturnRecord(ReturnRecordBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


# ========== 配件更换记录 Schemas ==========

class AssetPartLogCreate(BaseModel):
    warehouse_item_id: Optional[int] = None   # 关联库房配件 ID（可为空）
    warehouse_item_name: str                   # 配件名称
    action: str                                # "更换" 或 "新增"
    quantity: int = 1                          # 操作数量
    notes: Optional[str] = None               # 备注

class AssetPartLogResponse(BaseModel):
    id: int
    asset_id: int
    warehouse_item_id: Optional[int] = None
    warehouse_item_name: str
    action: str
    quantity: int
    notes: Optional[str] = None
    operator: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ========== 资产批量导入 Schemas ==========

class ImportError(BaseModel):
    """单条导入失败记录"""
    row_number: int                  # Excel 行号（从 2 开始，1 为列头）
    asset_tag: Optional[str] = None  # 该行的资产编号（如有）
    message: str                     # 失败原因描述

class ImportResult(BaseModel):
    """导入结果 JSON 报告（旧接口兼容模型，请勿破坏字段）"""
    total_rows: int              # Excel 中的数据总行数（不含列头）
    success_count: int           # 成功写入数据库的行数
    failed_count: int            # 验证失败的行数
    errors: List[ImportError]    # 失败日志列表
    message: str                 # 总结消息，如"成功导入 95 条，失败 5 条"


# ========== Wizard 资产导入 Schemas（Phase 4）==========

class ImportPreviewSummary(BaseModel):
    total: int
    valid: int
    mapping_required: int
    duplicate: int
    error: int


class ImportValidationErrorPreview(BaseModel):
    field: str
    message: str


class ImportResolverIssuePreview(BaseModel):
    field: str
    raw_value: str
    issue_type: str
    candidates: List[str] = []


class ImportDuplicatePreview(BaseModel):
    asset_id: Optional[int] = None
    asset_tag: Optional[str] = None
    serial_number: Optional[str] = None
    status: Optional[str] = None
    conflict_field: str
    conflict_scope: Literal["DATABASE", "FILE"] = "DATABASE"
    first_row_number: Optional[int] = None


class ImportRecordPreview(BaseModel):
    row_number: int
    asset_tag: Optional[str] = None
    classification: str
    validation_errors: List[ImportValidationErrorPreview] = []
    resolver_issues: List[ImportResolverIssuePreview] = []
    duplicate_info: Optional[ImportDuplicatePreview] = None


class ImportWarningPreview(BaseModel):
    row_number: int
    asset_tag: Optional[str] = None
    warning_type: str
    message: str


class ImportParseResponse(BaseModel):
    session_id: str
    request_id: str
    preview_summary: ImportPreviewSummary
    records: List[ImportRecordPreview]
    warnings: List[ImportWarningPreview]
    inferred_category: Optional[str] = None


class ImportMappingEntryRequest(BaseModel):
    raw_value: str
    field_type: Literal["DEPARTMENT", "BRAND", "LOCATION"]
    resolved_id: Optional[int] = None
    resolved_name: Optional[str] = None
    action: Literal["map_existing", "skip"] = "map_existing"

    @field_validator("field_type", mode="before")
    @classmethod
    def normalize_field_type(cls, value):
        return value.upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_mapping_target(self):
        if self.action == "map_existing" and self.resolved_id is None:
            raise ValueError("action 为 map_existing 时 resolved_id 为必填项")
        return self


class ImportApplyMappingRequest(BaseModel):
    session_id: str
    mapping_entries: List[ImportMappingEntryRequest] = []
    duplicate_policy: Literal[
        "INSERT_ONLY", "UPDATE_EXISTING", "REPLACE_EXISTING"
    ] = "INSERT_ONLY"


class ImportMappingResponse(BaseModel):
    request_id: str
    preview_summary: ImportPreviewSummary
    ready_to_execute: bool


class ImportExecuteRequest(BaseModel):
    session_id: str
    dry_run: bool = False


class ImportExecuteRecordResult(BaseModel):
    row_number: int
    asset_tag: Optional[str] = None
    decision: str
    status: Literal["SUCCESS", "SKIPPED", "FAILED"]
    message: str
    category: Optional[str] = None
    asset_status: Optional[str] = None
    error_type: Optional[str] = None


class ImportExecutionErrorItem(BaseModel):
    """Wizard 执行结果中的逐行不可执行原因。"""

    row_number: int
    asset_tag: Optional[str] = None
    error_type: str
    message: str
    field: Optional[str] = None
    request_id: str = ""


class ImportExecutionWarningItem(BaseModel):
    """Wizard 执行结果中的非致命提示。"""

    row_number: int
    asset_tag: Optional[str] = None
    warning_type: str
    message: str


class ImportWarehouseSyncEntry(BaseModel):
    warehouse_asset_id: int
    warehouse_asset_name: str
    warehouse_category: str
    before_available: int
    after_available: int
    before_allocated: int = 0
    after_allocated: int = 0
    delta: int
    committed: bool = False
    dry_run: bool = False
    rolled_back: bool = False


class ImportExecutionStatistics(BaseModel):
    total_rows: int = 0
    decision_counts: dict[str, int] = Field(default_factory=dict)
    by_decision: dict[str, int] = Field(default_factory=dict)
    inserted_count: int = 0
    updated_count: int = 0
    replaced_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    by_category: dict[str, int] = Field(default_factory=dict)
    by_status: dict[str, int] = Field(default_factory=dict)
    by_error_type: dict[str, int] = Field(default_factory=dict)
    warehouse_synced: List[ImportWarehouseSyncEntry] = Field(default_factory=list)


class WizardImportResult(BaseModel):
    """Wizard 结果；Phase 4-6 字段保持不变，增强字段均有兼容默认值。"""

    success_count: int
    fail_count: int
    skip_count: int
    dry_run: bool
    records: List[ImportExecuteRecordResult]
    total_rows: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    replaced_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    message: str = ""
    request_id: str = ""
    session_id: Optional[str] = None
    strategy: str = ""
    source_filenames: List[str] = Field(default_factory=list)
    executed_at: str = ""
    errors: List[ImportExecutionErrorItem] = Field(default_factory=list)
    warnings: List[ImportExecutionWarningItem] = Field(default_factory=list)
    statistics: ImportExecutionStatistics = Field(
        default_factory=ImportExecutionStatistics
    )


class ImportExecuteResponse(BaseModel):
    request_id: str
    result: WizardImportResult

# ==========资产位置建表 Schemas ===========
class LocationCreate(BaseModel):
    name: str
    description: Optional[str] = None


# ========== 资产分类与两级仓储目录 Schemas ==========
# 该区契约独立于旧单层 WarehouseAsset 模型，供后续目录、迁移和发放接口复用。
from category_policy import (
    AssetCategoryCode,
    FixedAssetStatus,
    IssuePolicy,
    PrimaryCategoryCode,
    require_fixed_asset_category,
    require_fixed_asset_status,
)


class ChineseErrorResponse(BaseModel):
    """统一的中文业务错误响应体。"""

    detail: str
    code: Optional[str] = None
    field: Optional[str] = None


class FixedAssetCategoryOption(BaseModel):
    code: AssetCategoryCode
    name: str


class FixedAssetInboundRequest(BaseModel):
    """受控固定资产入库的最小契约，仅接受 PC、NB、PD。"""

    source: Literal["SCAN", "MANUAL"]
    asset_category_code: AssetCategoryCode
    fixed_asset_number: str = Field(min_length=1, max_length=100)
    serial_number: str = Field(min_length=1, max_length=255)
    brand: Optional[str] = None
    model: Optional[str] = None
    purchase_date: Optional[datetime] = None
    notes: Optional[str] = None

    @field_validator("asset_category_code", mode="before")
    @classmethod
    def validate_fixed_asset_category(cls, value):
        return require_fixed_asset_category(value).value

    @field_validator("fixed_asset_number", "serial_number")
    @classmethod
    def reject_blank_identifiers(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("资产编号和序列号不能为空")
        return normalized


class FixedAssetStatusChangeRequest(BaseModel):
    status: FixedAssetStatus

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, value):
        return require_fixed_asset_status(value).value


class FixedAssetInboundCommand(FixedAssetInboundRequest):
    """受控入库命令，明确指定要同步的终端设备库存。"""

    terminal_inventory_id: int = Field(gt=0)


class FixedAssetInboundBatchRequest(BaseModel):
    """批量受控入库：每一项由服务层在独立事务内处理。"""

    items: List[FixedAssetInboundCommand] = Field(min_length=1, max_length=500)


class FixedAssetBindingRequest(BaseModel):
    recipient_id: Optional[int] = Field(default=None, gt=0)
    recipient_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    recipient_employee_id: Optional[str] = Field(default=None, min_length=1, max_length=100)
    recipient_department: Optional[str] = Field(default=None, min_length=1, max_length=100)
    issued_at: datetime

    @field_validator("recipient_name", "recipient_employee_id", "recipient_department")
    @classmethod
    def normalize_optional_binding_values(
        cls, value: Optional[str]
    ) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("领用人、工号和部门不能为空")
        return normalized

    @model_validator(mode="after")
    def require_employee_or_legacy_binding(self):
        legacy = (
            self.recipient_name,
            self.recipient_employee_id,
            self.recipient_department,
        )
        if any(value is not None for value in legacy) and not all(
            value is not None for value in legacy
        ):
            raise ValueError("旧版领用信息必须同时包含领用人、工号和部门")
        if self.recipient_id is None and not all(value is not None for value in legacy):
            raise ValueError("必须提供员工引用或完整的旧版领用信息")
        return self


class FixedAssetReturnRequest(BaseModel):
    recipient_id: Optional[int] = Field(default=None, gt=0)
    recipient_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    recipient_employee_id: Optional[str] = Field(default=None, min_length=1, max_length=100)
    recipient_department: Optional[str] = Field(default=None, min_length=1, max_length=100)

    @field_validator("recipient_name", "recipient_employee_id", "recipient_department")
    @classmethod
    def normalize_optional_return_values(
        cls, value: Optional[str]
    ) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("领用人、工号和部门不能为空")
        return normalized

    @model_validator(mode="after")
    def require_employee_or_legacy_return_binding(self):
        legacy = (
            self.recipient_name,
            self.recipient_employee_id,
            self.recipient_department,
        )
        if any(value is not None for value in legacy) and not all(
            value is not None for value in legacy
        ):
            raise ValueError("旧版领用信息必须同时包含领用人、工号和部门")
        if self.recipient_id is None and not all(value is not None for value in legacy):
            raise ValueError("必须提供员工引用或完整的旧版领用信息")
        return self


class FixedAssetRepairCompletionRequest(BaseModel):
    recipient_id: Optional[int] = Field(default=None, gt=0)
    recipient_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    recipient_employee_id: Optional[str] = Field(default=None, min_length=1, max_length=100)
    recipient_department: Optional[str] = Field(default=None, min_length=1, max_length=100)
    issued_at: Optional[datetime] = None

    @field_validator("recipient_name", "recipient_employee_id", "recipient_department")
    @classmethod
    def normalize_optional_repair_binding_values(
        cls, value: Optional[str]
    ) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("领用人、工号和部门不能为空")
        return normalized

    @model_validator(mode="after")
    def reject_partial_repair_binding(self):
        legacy = (
            self.recipient_name,
            self.recipient_employee_id,
            self.recipient_department,
        )
        if any(value is not None for value in legacy) and not all(
            value is not None for value in legacy
        ):
            raise ValueError("旧版领用信息必须同时包含领用人、工号和部门")
        return self


class WarehousePrimaryCategoryCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=100)
    sort_order: int = Field(default=0, ge=0)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("一级分类代码不能为空")
        return normalized

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("一级分类名称不能为空")
        return normalized


class WarehousePrimaryCategoryUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=1, max_length=64)
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    is_active: Optional[bool] = None
    sort_order: Optional[int] = Field(default=None, ge=0)

    @field_validator("code")
    @classmethod
    def normalize_optional_code(cls, value: Optional[str]) -> Optional[str]:
        return value.strip().upper() if value is not None else None

    @field_validator("name")
    @classmethod
    def normalize_optional_name(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value is not None else None


class WarehousePrimaryCategoryResponse(BaseModel):
    id: int
    code: str
    name: str
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WarehouseSecondaryCategoryCreate(BaseModel):
    primary_category_id: int = Field(gt=0)
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=100)
    sort_order: int = Field(default=0, ge=0)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("二级分类代码不能为空")
        return normalized

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("二级分类名称不能为空")
        return normalized


class WarehouseSecondaryCategoryUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=1, max_length=64)
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    is_active: Optional[bool] = None
    sort_order: Optional[int] = Field(default=None, ge=0)

    @field_validator("code")
    @classmethod
    def normalize_optional_code(cls, value: Optional[str]) -> Optional[str]:
        return value.strip().upper() if value is not None else None

    @field_validator("name")
    @classmethod
    def normalize_optional_name(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value is not None else None


class WarehouseSecondaryCategoryResponse(BaseModel):
    id: int
    primary_category_id: int
    code: str
    name: str
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WarehousePrimaryCategoryTreeResponse(WarehousePrimaryCategoryResponse):
    secondary_categories: List[WarehouseSecondaryCategoryResponse] = Field(
        default_factory=list
    )


class WarehouseCategoryTreeResponse(BaseModel):
    categories: List[WarehousePrimaryCategoryTreeResponse] = Field(default_factory=list)


class WarehouseMaterialCreate(BaseModel):
    """活动仓储物料必须提交且仅提交一个有效一级/二级分类组合。"""

    name: str = Field(min_length=1, max_length=255)
    primary_category_id: int = Field(gt=0)
    secondary_category_id: int = Field(gt=0)
    available_quantity: int = Field(default=0, ge=0)
    allocated_quantity: int = Field(default=0, ge=0)
    location: Optional[str] = Field(default=None, max_length=255)
    low_stock_threshold: int = Field(default=0, ge=0)
    issue_policy: IssuePolicy
    brand: Optional[str] = None
    model: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("name")
    @classmethod
    def normalize_material_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("物料名称不能为空")
        return normalized


class WarehouseMaterialUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    primary_category_id: Optional[int] = Field(default=None, gt=0)
    secondary_category_id: Optional[int] = Field(default=None, gt=0)
    available_quantity: Optional[int] = Field(default=None, ge=0)
    allocated_quantity: Optional[int] = Field(default=None, ge=0)
    location: Optional[str] = Field(default=None, max_length=255)
    low_stock_threshold: Optional[int] = Field(default=None, ge=0)
    issue_policy: Optional[IssuePolicy] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def require_complete_category_pair(self):
        category_ids = (self.primary_category_id, self.secondary_category_id)
        if (category_ids[0] is None) != (category_ids[1] is None):
            raise ValueError("一级分类和二级分类必须同时提交")
        return self


class WarehouseMaterialResponse(BaseModel):
    id: int
    name: str
    primary_category_id: int
    primary_category_code: str
    primary_category_name: str
    secondary_category_id: int
    secondary_category_code: str
    secondary_category_name: str
    available_quantity: int
    allocated_quantity: int
    location: Optional[str] = None
    low_stock_threshold: int
    low_stock: bool
    low_stock_message: Optional[str] = None
    issue_policy: IssuePolicy
    classification_status: Literal["ACTIVE", "PENDING_MIGRATION"] = "ACTIVE"
    legacy_category: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WarehouseMaterialFilter(BaseModel):
    name: Optional[str] = None
    primary_category_id: Optional[int] = Field(default=None, gt=0)
    secondary_category_id: Optional[int] = Field(default=None, gt=0)
    available_quantity: Optional[int] = Field(default=None, ge=0)
    allocated_quantity: Optional[int] = Field(default=None, ge=0)
    location: Optional[str] = None
    low_stock_threshold: Optional[int] = Field(default=None, ge=0)
    low_stock: Optional[bool] = None


class WarehouseCategoryMigrationResolutionRequest(BaseModel):
    primary_category_id: int = Field(gt=0)
    secondary_category_id: int = Field(gt=0)
    resolution_note: Optional[str] = Field(default=None, max_length=1000)


class WarehouseCategoryMigrationIssueResponse(BaseModel):
    id: int
    warehouse_asset_id: int
    material_name: Optional[str] = None
    original_category: str
    normalized_category: Optional[str] = None
    reason_code: Literal[
        "UNMAPPED", "AMBIGUOUS", "INACTIVE_TARGET", "INVALID_PAIR"
    ]
    reason_detail: str
    status: Literal["OPEN", "RESOLVED"]
    created_at: datetime
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WarehouseCategoryMigrationResolutionResponse(BaseModel):
    warehouse_asset_id: int
    primary_category_id: int
    secondary_category_id: int
    issue_id: int
    audit_log_id: int


class PrimaryCategorySeedResponse(BaseModel):
    code: PrimaryCategoryCode
    name: str


# ========== 普通低值物料发放与归还 Schemas ==========

class MaterialIssueCreateRequest(BaseModel):
    warehouse_asset_id: int = Field(gt=0)
    quantity: int = Field(gt=0)
    issued_at: datetime
    recipient_name: Optional[str] = Field(default=None, max_length=100)
    recipient_employee_id: Optional[str] = Field(default=None, max_length=100)
    recipient_department: Optional[str] = Field(default=None, max_length=100)
    purpose: Optional[str] = Field(default=None, max_length=5000)


class MaterialReturnCreateRequest(BaseModel):
    quantity: int = Field(gt=0)
    returned_at: datetime


# ========== 专业物料发放与工具借还 Schemas ==========

class RepairPartIssueRequest(BaseModel):
    warehouse_asset_id: int = Field(gt=0)
    quantity: int = Field(gt=0)
    issued_at: datetime
    target_asset_id: Optional[int] = Field(default=None, gt=0)
    repair_order_ref: Optional[str] = Field(default=None, max_length=100)
    disk_serial_number: Optional[str] = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def require_repair_association(self):
        if self.target_asset_id is None and not _has_text(self.repair_order_ref):
            raise ValueError("维修备件必须关联有效资产或维修单")
        return self


class NetworkConsumableIssueRequest(BaseModel):
    warehouse_asset_id: int = Field(gt=0)
    quantity: int = Field(gt=0)
    issued_at: datetime
    department_id: Optional[int] = Field(default=None, gt=0)
    project_ref: Optional[str] = Field(default=None, max_length=100)
    server_room_ref: Optional[str] = Field(default=None, max_length=100)
    work_order_ref: Optional[str] = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def reject_blank_network_references(self):
        for label, value in (
            ("项目", self.project_ref),
            ("机房", self.server_room_ref),
            ("工单", self.work_order_ref),
        ):
            if value is not None and not _has_text(value):
                raise ValueError(f"{label}用途关联不能为空")
        return self


class ToolLoanCreateRequest(BaseModel):
    warehouse_asset_id: int = Field(gt=0)
    borrower_id: Optional[int] = Field(default=None, gt=0)
    borrower_ref: Optional[str] = Field(default=None, max_length=255)
    quantity: int = Field(gt=0)
    borrowed_at: datetime
    expected_return_at: datetime
    tool_identifier: Optional[str] = Field(default=None, max_length=255)

    @field_validator("borrower_ref")
    @classmethod
    def normalize_borrower_ref(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_borrower_and_expected_return_at(self):
        if self.borrower_id is None and not _has_text(self.borrower_ref):
            raise ValueError("必须提供员工借用人或借用人文本")
        if self.expected_return_at < self.borrowed_at:
            raise ValueError("预计归还日期不能早于借出日期")
        return self


class ToolLoanReturnRequest(BaseModel):
    quantity: int = Field(gt=0)
    returned_at: datetime


class OfficeConsumableIssueRequest(BaseModel):
    warehouse_asset_id: int = Field(gt=0)
    quantity: int = Field(gt=0)
    issued_at: datetime


def _has_text(value: Optional[str]) -> bool:
    return isinstance(value, str) and bool(value.strip())
