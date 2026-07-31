from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone, timedelta
from database import Base
import os

# 中国时区 UTC+8
CHINA_TZ = timezone(timedelta(hours=8))

def china_now():
    """返回中国时区的当前时间，但以naive datetime存储（数据库会按本地时区处理）"""
    # 获取当前UTC时间，然后转换为中国时区，最后移除时区信息
    utc_now = datetime.now(timezone.utc)
    china_time = utc_now.astimezone(CHINA_TZ)
    return china_time.replace(tzinfo=None)  # 移除时区信息，让数据库按本地时区处理

# ========== 用户认证模型 ==========

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100))
    role = Column(String(20), nullable=False, default="MIS")  # admin 或 MIS 或 readonly角色
    is_active = Column(Boolean, default=True)
    must_change_password = Column(Boolean, default=True)  # 新用户首次登录必须修改密码
    password_changed_at = Column(DateTime, default=china_now)
    last_login = Column(DateTime)
    created_at = Column(DateTime, default=china_now)
    updated_at = Column(DateTime, default=china_now, onupdate=china_now)
    created_by = Column(Integer, ForeignKey("users.id"))
    
    # 关联操作日志
    operation_logs = relationship("OperationLog", back_populates="user", foreign_keys="OperationLog.user_id")
    # 关联密码历史
    password_history = relationship("PasswordHistory", back_populates="user", cascade="all, delete-orphan")

class PasswordHistory(Base):
    """密码历史记录 - 用于防止用户重复使用旧密码"""
    __tablename__ = "password_history"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=china_now)
    
    user = relationship("User", back_populates="password_history")

class OperationLog(Base):
    """操作日志 - 记录所有用户操作"""
    __tablename__ = "operation_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String(50), nullable=False)  # create, update, delete, login, logout等
    resource_type = Column(String(50), nullable=False)  # asset, warehouse_asset, user等
    resource_id = Column(Integer)
    description = Column(Text)
    old_value = Column(Text)
    new_value = Column(Text)
    ip_address = Column(String(50))
    created_at = Column(DateTime, default=china_now)
    
    user = relationship("User", back_populates="operation_logs", foreign_keys=[user_id])

class AssetDeletionRecord(Base):
    """资产删除记录 - 记录被删除的资产信息"""
    __tablename__ = "asset_deletion_records"
    
    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, nullable=False)
    asset_tag = Column(String, nullable=False)
    asset_data = Column(Text)  # JSON格式存储完整资产信息
    deletion_reason = Column(Text, nullable=False)
    deleted_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    deleted_at = Column(DateTime, default=china_now)
    
    deleter = relationship("User")

# ========== 资产管理模型 ==========

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    text,
)


class Employee(Base):
    """员工主数据；旧业务文本字段继续作为历史快照保留。"""

    __tablename__ = "employees"
    __table_args__ = (
        CheckConstraint(
            "TRIM(employee_no) <> '' AND TRIM(name) <> '' "
            "AND TRIM(department) <> ''",
            name="ck_employees_nonblank_identity",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'DEPARTED')",
            name="ck_employees_status",
        ),
        CheckConstraint(
            "(status = 'ACTIVE' AND departure_date IS NULL) OR "
            "(status = 'DEPARTED' AND departure_date IS NOT NULL)",
            name="ck_employees_status_departure_date",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    employee_no = Column(String(100), nullable=False, unique=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    department = Column(String(100), nullable=False, index=True)
    status = Column(
        String(16), nullable=False, default="ACTIVE", server_default=text("'ACTIVE'"), index=True
    )
    departure_date = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=china_now)
    updated_at = Column(DateTime, nullable=False, default=china_now, onupdate=china_now)

    current_assets = relationship("Asset", back_populates="current_employee")
    fixed_asset_issuances = relationship(
        "FixedAssetIssuance", back_populates="recipient"
    )
    tool_loans = relationship("ToolLoan", back_populates="borrower")


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        CheckConstraint(
            "asset_category_code IS NULL OR asset_category_code IN ('PC', 'NB', 'PD')",
            name="ck_assets_fixed_asset_category_code",
        ),
        CheckConstraint(
            "inbound_source IS NULL OR inbound_source IN ('SCAN', 'MANUAL')",
            name="ck_assets_inbound_source",
        ),
        CheckConstraint(
            "(asset_category_code IS NULL "
            "AND inbound_source IS NULL "
            "AND terminal_inventory_id IS NULL) "
            "OR "
            "(asset_category_code IS NOT NULL "
            "AND inbound_source IN ('SCAN', 'MANUAL') "
            "AND terminal_inventory_id IS NOT NULL "
            "AND fixed_asset_number IS NOT NULL "
            "AND TRIM(fixed_asset_number) <> '' "
            "AND serial_number IS NOT NULL "
            "AND TRIM(serial_number) <> '')",
            name="ck_assets_controlled_fixed_asset_identifiers",
        ),
        CheckConstraint(
            "asset_category_code IS NULL OR status IN ('闲置', '使用中', '维修中', '报废')",
            name="ck_assets_fixed_asset_status",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    asset_tag = Column(String, unique=True, index=True, nullable=False)
    category = Column(String, index=True, nullable=False)

    # 通用字段
    brand = Column(String, index=True)
    model = Column(String, index=True)
    serial_number = Column(String, unique=True)
    status = Column(String, index=True, nullable=False)
    purchase_date = Column(DateTime)
    notes = Column(Text)

    # 固定资产受控入库字段。历史资产保留 NULL，由迁移脚本和服务层逐步接入。
    asset_category_code = Column(String(2), index=True, nullable=True)
    inbound_source = Column(String(16), index=True, nullable=True)
    terminal_inventory_id = Column(
        Integer,
        ForeignKey("warehouse_assets.id", ondelete="RESTRICT"),
        index=True,
        nullable=True,
    )

    # 计算机专用字段
    # employee_ref_id 是员工主数据引用；下列旧文本字段仍保留为历史快照。
    employee_ref_id = Column(
        Integer,
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    employee_id = Column(String, index=True)  # 工号
    employee_name = Column(String, index=True)  # 姓名
    department = Column(String, index=True)  # 部门
    hostname = Column(String, index=True)  # 主机名
    mac_address = Column(String)  # MAC地址
    ip_address = Column(String)  # IP地址
    fixed_asset_number = Column(String, unique=True, index=True)  # 固定资产编号
    system_version = Column(String)  # 系统版本
    antivirus_software = Column(String)  # 杀毒软件
    issue_date = Column(DateTime)  # 领用日期
    lock_number = Column(String)  # 锁号（仅台式机）
    supervisor = Column(String)  # 直属领导
    location = Column(String, nullable=True)  # 资产位置，允许为空
    po_number = Column(String, nullable=True)  # PO号，允许为空
    condition = Column(String, nullable=True, default="可用")

    # 笔记本专用字段
    bios_password = Column(Boolean, default=False)
    tpm_status = Column(Boolean, default=False)
    has_desktop = Column(Boolean, default=False)

    # 库房资产专用字段
    location = Column(String, index=True)  # 位置
    quantity = Column(Integer, default=1)  # 数量（库房资产可能有多个）

    # 扩展字段：存储导入时 Excel 中未映射到固定列的额外数据（JSON）
    additional_info = Column(JSON, nullable=True)

    # 标记该资产是否由库房发放创建（True 时归还不触发库房数量自动同步）
    from_warehouse = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=china_now)
    updated_at = Column(DateTime, default=china_now, onupdate=china_now)
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime, nullable=True)

    logs = relationship("AssetLog", back_populates="asset")
    hostname_history = relationship(
        "HostnameHistory", back_populates="asset", cascade="all, delete-orphan"
    )
    fixed_asset_inbound = relationship(
        "FixedAssetInbound", back_populates="asset", uselist=False
    )
    fixed_asset_issuances = relationship(
        "FixedAssetIssuance", back_populates="asset"
    )
    lifecycle_events = relationship("AssetLifecycleEvent", back_populates="asset")
    terminal_inventory = relationship(
        "WarehouseAsset", foreign_keys=[terminal_inventory_id]
    )
    current_employee = relationship(
        "Employee", back_populates="current_assets", foreign_keys=[employee_ref_id]
    )


class AssetLog(Base):
    __tablename__ = "asset_logs"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id", ondelete="SET NULL"), nullable=True)
    action = Column(String, nullable=False)
    description = Column(Text)
    old_value = Column(Text)
    new_value = Column(Text)
    operator = Column(String)
    created_at = Column(DateTime, default=china_now)

    asset = relationship("Asset", back_populates="logs")


class HostnameHistory(Base):
    __tablename__ = "hostname_history"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    old_hostname = Column(String)
    new_hostname = Column(String)
    change_reason = Column(String)
    changed_at = Column(DateTime, default=china_now)

    asset = relationship("Asset", back_populates="hostname_history")


class WarehouseAsset(Base):
    __tablename__ = "warehouse_assets"
    __table_args__ = (
        ForeignKeyConstraint(
            ["primary_category_id", "secondary_category_id"],
            [
                "warehouse_secondary_categories.primary_category_id",
                "warehouse_secondary_categories.id",
            ],
            name="fk_warehouse_assets_secondary_category_pair",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "classification_status IN ('ACTIVE', 'PENDING_MIGRATION')",
            name="ck_warehouse_assets_classification_status",
        ),
        CheckConstraint(
            "(classification_status = 'ACTIVE' "
            "AND primary_category_id IS NOT NULL "
            "AND secondary_category_id IS NOT NULL "
            "AND issue_policy IN ('RETURNABLE', 'CONSUMABLE')) "
            "OR "
            "(classification_status = 'PENDING_MIGRATION' "
            "AND primary_category_id IS NULL "
            "AND secondary_category_id IS NULL "
            "AND COALESCE(NULLIF(TRIM(legacy_category), ''), "
            "NULLIF(TRIM(category), '')) IS NOT NULL)",
            name="ck_warehouse_assets_classification_pair",
        ),
        CheckConstraint(
            "total_quantity >= 0 AND available_quantity >= 0 "
            "AND allocated_quantity >= 0 "
            "AND total_quantity = available_quantity + allocated_quantity",
            name="ck_warehouse_assets_inventory_balance",
        ),
        CheckConstraint(
            "minimum_stock >= 0 AND low_stock_threshold >= 0",
            name="ck_warehouse_assets_stock_thresholds",
        ),
        Index(
            "ix_warehouse_assets_category_pair_status",
            "primary_category_id",
            "secondary_category_id",
            "classification_status",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    # 保留旧单层分类字段，供迁移前历史记录和旧接口读取。
    category = Column(String, index=True, nullable=False)
    subcategory = Column(String, index=True)
    brand = Column(String, index=True)
    model = Column(String, index=True)
    receiver_name = Column(String)
    total_quantity = Column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    available_quantity = Column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    allocated_quantity = Column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    minimum_stock = Column(
        Integer, nullable=False, default=5, server_default=text("5")
    )
    low_stock_threshold = Column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    location = Column(String, index=True)
    notes = Column(Text)

    primary_category_id = Column(
        Integer,
        ForeignKey("warehouse_primary_categories.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    secondary_category_id = Column(
        Integer,
        ForeignKey("warehouse_secondary_categories.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    classification_status = Column(
        String(32),
        nullable=False,
        default="PENDING_MIGRATION",
        server_default=text("'PENDING_MIGRATION'"),
        index=True,
    )
    legacy_category = Column(String, nullable=True, index=True)
    material_kind = Column(String(32), nullable=True, index=True)
    issue_policy = Column(String(16), nullable=True, index=True)

    created_at = Column(DateTime, default=china_now)
    updated_at = Column(DateTime, default=china_now, onupdate=china_now)

    logs = relationship(
        "WarehouseAssetLog", back_populates="asset", cascade="all, delete-orphan"
    )
    primary_category = relationship(
        "WarehousePrimaryCategory", foreign_keys=[primary_category_id]
    )
    # 单列外键用于 ORM 关联；复合外键仍由数据库校验一级/二级从属关系。
    secondary_category = relationship(
        "WarehouseSecondaryCategory", foreign_keys=[secondary_category_id]
    )
    material_issues = relationship("MaterialIssue", back_populates="warehouse_asset")
    tool_loans = relationship("ToolLoan", back_populates="warehouse_asset")
    migration_issues = relationship(
        "WarehouseCategoryMigrationIssue", back_populates="warehouse_asset"
    )


# ========== 受控仓储两级分类目录 ===========

class WarehousePrimaryCategory(Base):
    __tablename__ = "warehouse_primary_categories"
    __table_args__ = (
        UniqueConstraint("code", name="uq_warehouse_primary_categories_code"),
        UniqueConstraint("name", name="uq_warehouse_primary_categories_name"),
        CheckConstraint(
            "TRIM(code) <> '' AND TRIM(name) <> ''",
            name="ck_warehouse_primary_categories_nonblank_identity",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(64), nullable=False)
    name = Column(String(100), nullable=False)
    is_active = Column(
        Boolean, nullable=False, default=True, server_default=text("true"), index=True
    )
    sort_order = Column(Integer, nullable=False, default=0, server_default=text("0"), index=True)
    created_at = Column(DateTime, nullable=False, default=china_now)
    updated_at = Column(DateTime, nullable=False, default=china_now, onupdate=china_now)

    secondary_categories = relationship(
        "WarehouseSecondaryCategory", back_populates="primary_category"
    )


class WarehouseSecondaryCategory(Base):
    __tablename__ = "warehouse_secondary_categories"
    __table_args__ = (
        UniqueConstraint(
            "primary_category_id",
            "code",
            name="uq_warehouse_secondary_categories_parent_code",
        ),
        UniqueConstraint(
            "primary_category_id",
            "name",
            name="uq_warehouse_secondary_categories_parent_name",
        ),
        # 该候选键被仓储物料和单层分类映射的复合外键引用。
        UniqueConstraint(
            "primary_category_id",
            "id",
            name="uq_warehouse_secondary_categories_parent_id",
        ),
        CheckConstraint(
            "TRIM(code) <> '' AND TRIM(name) <> ''",
            name="ck_warehouse_secondary_categories_nonblank_identity",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    primary_category_id = Column(
        Integer,
        ForeignKey("warehouse_primary_categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    code = Column(String(64), nullable=False)
    name = Column(String(100), nullable=False)
    is_active = Column(
        Boolean, nullable=False, default=True, server_default=text("true"), index=True
    )
    sort_order = Column(Integer, nullable=False, default=0, server_default=text("0"), index=True)
    created_at = Column(DateTime, nullable=False, default=china_now)
    updated_at = Column(DateTime, nullable=False, default=china_now, onupdate=china_now)

    primary_category = relationship(
        "WarehousePrimaryCategory", back_populates="secondary_categories"
    )


class WarehouseCategoryMapping(Base):
    __tablename__ = "warehouse_category_mappings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["primary_category_id", "secondary_category_id"],
            [
                "warehouse_secondary_categories.primary_category_id",
                "warehouse_secondary_categories.id",
            ],
            name="fk_warehouse_category_mappings_secondary_category_pair",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "TRIM(normalized_legacy_category) <> ''",
            name="ck_warehouse_category_mappings_normalized_category",
        ),
        Index(
            "ix_warehouse_category_mappings_pair_active",
            "primary_category_id",
            "secondary_category_id",
            "is_active",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    normalized_legacy_category = Column(
        String(255), nullable=False, unique=True, index=True
    )
    primary_category_id = Column(
        Integer,
        ForeignKey("warehouse_primary_categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    secondary_category_id = Column(
        Integer,
        ForeignKey("warehouse_secondary_categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    is_active = Column(
        Boolean, nullable=False, default=True, server_default=text("true"), index=True
    )
    created_by = Column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    created_at = Column(DateTime, nullable=False, default=china_now)

    primary_category = relationship(
        "WarehousePrimaryCategory", foreign_keys=[primary_category_id]
    )
    # 避免单列及复合外键同时存在时 ORM 推断关联路径歧义。
    secondary_category = relationship(
        "WarehouseSecondaryCategory", foreign_keys=[secondary_category_id]
    )
    creator = relationship("User", foreign_keys=[created_by])


class WarehouseCategoryMigrationIssue(Base):
    __tablename__ = "warehouse_category_migration_issues"
    __table_args__ = (
        CheckConstraint(
            "reason_code IN ('UNMAPPED', 'AMBIGUOUS', 'INACTIVE_TARGET', 'INVALID_PAIR')",
            name="ck_warehouse_category_migration_issues_reason_code",
        ),
        CheckConstraint(
            "status IN ('OPEN', 'RESOLVED')",
            name="ck_warehouse_category_migration_issues_status",
        ),
        CheckConstraint(
            "(status = 'OPEN' AND resolved_by IS NULL AND resolved_at IS NULL) "
            "OR (status = 'RESOLVED' AND resolved_by IS NOT NULL AND resolved_at IS NOT NULL)",
            name="ck_warehouse_category_migration_issues_resolution_state",
        ),
        Index(
            "uq_warehouse_category_migration_issues_open_asset",
            "warehouse_asset_id",
            unique=True,
            sqlite_where=text("status = 'OPEN'"),
            postgresql_where=text("status = 'OPEN'"),
        ),
        Index(
            "ix_warehouse_category_migration_issues_status_created",
            "status",
            "created_at",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    warehouse_asset_id = Column(
        Integer,
        ForeignKey("warehouse_assets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    original_category = Column(String, nullable=False)
    normalized_category = Column(String, nullable=True, index=True)
    reason_code = Column(String(32), nullable=False, index=True)
    reason_detail = Column(Text, nullable=False)
    status = Column(
        String(16),
        nullable=False,
        default="OPEN",
        server_default=text("'OPEN'"),
        index=True,
    )
    resolved_by = Column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=china_now)

    warehouse_asset = relationship(
        "WarehouseAsset", back_populates="migration_issues"
    )
    resolver = relationship("User", foreign_keys=[resolved_by])


# ========== 固定资产受控入库、发放与生命周期 ===========

class FixedAssetInbound(Base):
    __tablename__ = "fixed_asset_inbounds"
    __table_args__ = (
        CheckConstraint(
            "source IN ('SCAN', 'MANUAL')",
            name="ck_fixed_asset_inbounds_source",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(
        Integer,
        ForeignKey("assets.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    terminal_inventory_id = Column(
        Integer,
        ForeignKey("warehouse_assets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    source = Column(String(16), nullable=False)
    operator_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    inbound_at = Column(DateTime, nullable=False, default=china_now, index=True)

    asset = relationship("Asset", back_populates="fixed_asset_inbound")
    terminal_inventory = relationship("WarehouseAsset", foreign_keys=[terminal_inventory_id])
    operator = relationship("User", foreign_keys=[operator_id])


class FixedAssetIssuance(Base):
    __tablename__ = "fixed_asset_issuances"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(
        Integer,
        ForeignKey("assets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    terminal_inventory_id = Column(
        Integer,
        ForeignKey("warehouse_assets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    recipient_name = Column(String(100), nullable=False, index=True)
    recipient_employee_id = Column(String(100), nullable=False, index=True)
    recipient_department = Column(String(100), nullable=False, index=True)
    recipient_id = Column(
        Integer,
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    issued_at = Column(DateTime, nullable=False, default=china_now, index=True)
    operator_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    asset = relationship("Asset", back_populates="fixed_asset_issuances")
    terminal_inventory = relationship("WarehouseAsset", foreign_keys=[terminal_inventory_id])
    operator = relationship("User", foreign_keys=[operator_id])
    recipient = relationship(
        "Employee", back_populates="fixed_asset_issuances", foreign_keys=[recipient_id]
    )


class AssetLifecycleEvent(Base):
    __tablename__ = "asset_lifecycle_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('ISSUE', 'RETURN', 'TRANSFER', 'REPAIR_SENT', "
            "'REPAIR_COMPLETED', 'RETIRED')",
            name="ck_asset_lifecycle_events_type",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(
        Integer,
        ForeignKey("assets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    event_type = Column(String(32), nullable=False, index=True)
    previous_binding = Column(JSON, nullable=True)
    new_binding = Column(JSON, nullable=True)
    operator_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    occurred_at = Column(DateTime, nullable=False, default=china_now, index=True)
    event_metadata = Column("metadata", JSON, nullable=True)

    asset = relationship("Asset", back_populates="lifecycle_events")
    operator = relationship("User", foreign_keys=[operator_id])


# ========== 低值物料及专业用途记录 ===========

class MaterialIssue(Base):
    __tablename__ = "material_issues"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_material_issues_quantity_positive"),
        CheckConstraint(
            "(record_type = 'RETURNABLE' "
            "AND issue_policy = 'RETURNABLE' "
            "AND unreturned_quantity >= 0 "
            "AND consumed_completed = false) "
            "OR "
            "(record_type = 'CONSUMABLE' "
            "AND issue_policy = 'CONSUMABLE' "
            "AND unreturned_quantity = 0 "
            "AND consumed_completed = true)",
            name="ck_material_issues_record_type_policy",
        ),
        CheckConstraint(
            "unreturned_quantity <= quantity",
            name="ck_material_issues_unreturned_quantity",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    warehouse_asset_id = Column(
        Integer,
        ForeignKey("warehouse_assets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    record_type = Column(String(16), nullable=False, index=True)
    issue_policy = Column(String(16), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    unreturned_quantity = Column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    consumed_completed = Column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    recipient_name = Column(String(100), nullable=True, index=True)
    recipient_employee_id = Column(String(100), nullable=True, index=True)
    recipient_department = Column(String(100), nullable=True, index=True)
    purpose = Column(Text, nullable=True)
    operator_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    issued_at = Column(DateTime, nullable=False, default=china_now, index=True)

    warehouse_asset = relationship("WarehouseAsset", back_populates="material_issues")
    operator = relationship("User", foreign_keys=[operator_id])
    returns = relationship("MaterialReturn", back_populates="material_issue")


class MaterialReturn(Base):
    __tablename__ = "material_returns"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_material_returns_quantity_positive"),
    )

    id = Column(Integer, primary_key=True, index=True)
    material_issue_id = Column(
        Integer,
        ForeignKey("material_issues.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantity = Column(Integer, nullable=False)
    returned_at = Column(DateTime, nullable=False, default=china_now, index=True)
    operator_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    material_issue = relationship("MaterialIssue", back_populates="returns")
    operator = relationship("User", foreign_keys=[operator_id])


class RepairPartIssue(Base):
    __tablename__ = "repair_part_issues"
    __table_args__ = (
        CheckConstraint(
            "target_asset_id IS NOT NULL OR repair_order_ref IS NOT NULL",
            name="ck_repair_part_issues_target",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    material_issue_id = Column(
        Integer,
        ForeignKey("material_issues.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    target_asset_id = Column(
        Integer,
        ForeignKey("assets.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    repair_order_ref = Column(String(100), nullable=True, index=True)
    disk_serial_number = Column(String(255), nullable=True, index=True)

    material_issue = relationship("MaterialIssue", foreign_keys=[material_issue_id])
    target_asset = relationship("Asset", foreign_keys=[target_asset_id])


class NetworkConsumableIssue(Base):
    __tablename__ = "network_consumable_issues"

    id = Column(Integer, primary_key=True, index=True)
    material_issue_id = Column(
        Integer,
        ForeignKey("material_issues.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    department_id = Column(
        Integer,
        ForeignKey("departments.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    project_ref = Column(String(100), nullable=True, index=True)
    server_room_ref = Column(String(100), nullable=True, index=True)
    work_order_ref = Column(String(100), nullable=True, index=True)

    material_issue = relationship("MaterialIssue", foreign_keys=[material_issue_id])
    department = relationship("Department", foreign_keys=[department_id])


class ToolLoan(Base):
    __tablename__ = "tool_loans"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_tool_loans_quantity_positive"),
        CheckConstraint(
            "unreturned_quantity >= 0 AND unreturned_quantity <= quantity",
            name="ck_tool_loans_unreturned_quantity",
        ),
        CheckConstraint(
            "(status = 'BORROWED' AND unreturned_quantity > 0) "
            "OR (status = 'RETURNED' AND unreturned_quantity = 0)",
            name="ck_tool_loans_status_balance",
        ),
        CheckConstraint(
            "borrower_id IS NOT NULL OR "
            "NULLIF(TRIM(borrower_ref), '') IS NOT NULL",
            name="ck_tool_loans_borrower_reference",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    warehouse_asset_id = Column(
        Integer,
        ForeignKey("warehouse_assets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # borrower_ref 保留旧自由文本；新记录可改用结构化员工引用。
    borrower_ref = Column(String(255), nullable=True, index=True)
    borrower_id = Column(
        Integer,
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    quantity = Column(Integer, nullable=False)
    unreturned_quantity = Column(Integer, nullable=False)
    status = Column(String(16), nullable=False, default="BORROWED", index=True)
    borrowed_at = Column(DateTime, nullable=False, default=china_now, index=True)
    expected_return_at = Column(DateTime, nullable=False, index=True)
    returned_at = Column(DateTime, nullable=True, index=True)
    tool_identifier = Column(String(255), nullable=True, index=True)
    operator_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    warehouse_asset = relationship("WarehouseAsset", back_populates="tool_loans")
    operator = relationship("User", foreign_keys=[operator_id])
    borrower = relationship(
        "Employee", back_populates="tool_loans", foreign_keys=[borrower_id]
    )
    return_events = relationship("ToolLoanReturnEvent", back_populates="tool_loan")


class ToolLoanReturnEvent(Base):
    __tablename__ = "tool_loan_return_events"
    __table_args__ = (
        CheckConstraint(
            "quantity > 0", name="ck_tool_loan_return_events_quantity_positive"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    tool_loan_id = Column(
        Integer,
        ForeignKey("tool_loans.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantity = Column(Integer, nullable=False)
    is_partial = Column(Boolean, nullable=False, default=False)
    returned_at = Column(DateTime, nullable=False, default=china_now, index=True)
    operator_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    tool_loan = relationship("ToolLoan", back_populates="return_events")
    operator = relationship("User", foreign_keys=[operator_id])


class WarehouseAssetLog(Base):
    """库房资产操作日志"""
    __tablename__ = "warehouse_asset_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("warehouse_assets.id"), nullable=False)
    action = Column(String, nullable=False)
    description = Column(Text)
    operator = Column(String)
    created_at = Column(DateTime, default=china_now)
    
    asset = relationship("WarehouseAsset", back_populates="logs")


class AssetPartLog(Base):
    """资产配件更换/新增记录"""
    __tablename__ = "asset_part_logs"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    # 关联的库房配件（可为空，允许记录非库房来源的配件）
    warehouse_item_id = Column(Integer, ForeignKey("warehouse_assets.id", ondelete="SET NULL"), nullable=True)
    warehouse_item_name = Column(String, nullable=False)   # 冗余存储名称，防止库房条目被删后丢失
    action = Column(String, nullable=False)                # "更换" 或 "新增"
    quantity = Column(Integer, default=1, nullable=False)  # 操作数量
    notes = Column(Text, nullable=True)                    # 备注（如损坏原因、旧配件去向）
    operator = Column(String, nullable=True)               # 操作人
    created_at = Column(DateTime, default=china_now)

class WarehouseLocation(Base):
    """库房存放位置"""
    __tablename__ = "warehouse_locations"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=True)  # 备注，例如"A区货架-第2排"
    created_at = Column(DateTime, default=china_now)

class OfficeLocation(Base):
    """使用中资产位置"""
    __tablename__="office_locations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True) #例如 “L1 3厂厂区电脑”，“L2 5厂厂区电脑”，“OA办公室电脑”
    description = Column(String(255), nullable=True)  # 备注


class Brand(Base):
    """品牌"""
    __tablename__ = "brands"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=china_now)


class Department(Base):
    """部门（支持主分类-子分类两级结构）"""
    __tablename__ = "departments"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    parent_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    created_at = Column(DateTime, default=china_now)


class ReturnRecord(Base):
    __tablename__ = "return_records"
    
    id = Column(Integer, primary_key=True, index=True)
    asset_name = Column(String, nullable=False, index=True)  # 资产名称
    employee_id = Column(String, nullable=False, index=True)
    employee_name = Column(String, nullable=False, index=True)
    department = Column(String, index=True)
    return_reason = Column(String, nullable=False)
    is_returned = Column(Boolean, default=False)
    return_date = Column(DateTime)
    notes = Column(Text)
    created_at = Column(DateTime, default=china_now)
