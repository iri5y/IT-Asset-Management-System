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
