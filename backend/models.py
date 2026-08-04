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

class Asset(Base):
    __tablename__ = "assets"
    
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
    
    # 计算机专用字段
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
    location = Column(String, nullable=True) #资产位置，允许为空
    po_number = Column(String, nullable=True) #PO号，允许为空
    condition = Column(String, nullable=True, default='可用')  # 闲置资产状况：可用 / 损坏 / 待报废
    
    # 笔记本专用字段
    bios_password = Column(Boolean, default=False)  # BIOS密码（开/关）
    tpm_status = Column(Boolean, default=False)  # TPM状态（开/关）
    has_desktop = Column(Boolean, default=False)  # 是否有台式机
    
    # 库房资产专用字段
    location = Column(String, index=True)  # 位置
    quantity = Column(Integer, default=1)  # 数量（库房资产可能有多个）

    # 扩展字段：存储导入时 Excel 中未映射到固定列的额外数据（JSON）
    additional_info = Column(JSON, nullable=True)

    # 标记该资产是否由库房发放创建（True 时归还不触发库房数量自动同步，因为库存由库房模块独立管理）
    from_warehouse = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=china_now)
    updated_at = Column(DateTime, default=china_now, onupdate=china_now)
    is_deleted = Column(Boolean, default=False, nullable=False)  # 软删除标记
    deleted_at = Column(DateTime, nullable=True)  # 软删除时间
    
    logs = relationship("AssetLog", back_populates="asset")
    hostname_history = relationship("HostnameHistory", back_populates="asset", cascade="all, delete-orphan")

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
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    category = Column(String, index=True, nullable=False)
    subcategory = Column(String, index=True)
    brand = Column(String, index=True)
    model = Column(String, index=True)
    receiver_name = Column(String)
    total_quantity = Column(Integer, default=0)
    available_quantity = Column(Integer, default=0)
    allocated_quantity = Column(Integer, default=0)
    minimum_stock = Column(Integer, default=5)
    location = Column(String)
    notes = Column(Text)
    created_at = Column(DateTime, default=china_now)
    updated_at = Column(DateTime, default=china_now, onupdate=china_now)
    
    logs = relationship("WarehouseAssetLog", back_populates="asset", cascade="all, delete-orphan")


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
