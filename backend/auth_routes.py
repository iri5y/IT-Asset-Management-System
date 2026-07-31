from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from typing import List
import json

from database import get_db
import models
import schemas
from auth import (
    verify_password, get_password_hash, create_access_token, 
    create_refresh_token, decode_token, is_password_expired,
    should_remind_password_change,
    get_current_user, get_current_active_user, require_admin,
    PASSWORD_EXPIRE_DAYS
)

router = APIRouter(prefix="/auth", tags=["认证"])

DEFAULT_ADMIN_EMAIL = "admin@example.com"

# 中国时区 UTC+8
CHINA_TZ = timezone(timedelta(hours=8))

def china_now():
    """返回中国时区的当前时间，但以naive datetime存储（数据库会按本地时区处理）"""
    # 获取当前UTC时间，然后转换为中国时区，最后移除时区信息
    utc_now = datetime.now(timezone.utc)
    china_time = utc_now.astimezone(CHINA_TZ)
    return china_time.replace(tzinfo=None)  # 移除时区信息，让数据库按本地时区处理

def create_operation_log(
    db: Session, 
    user_id: int, 
    action: str, 
    resource_type: str, 
    resource_id: int = None,
    description: str = None,
    old_value: str = None,
    new_value: str = None,
    ip_address: str = None
):
    """创建操作日志"""
    log = models.OperationLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        description=description,
        old_value=old_value,
        new_value=new_value,
        ip_address=ip_address
    )
    db.add(log)
    db.commit()

def get_active_admin_count(db: Session, exclude_default_admin: bool = False) -> int:
    """获取活跃的admin账号数量"""
    query = db.query(models.User).filter(
        models.User.role == "admin",
        models.User.is_active == True
    )
    if exclude_default_admin:
        query = query.filter(models.User.email != DEFAULT_ADMIN_EMAIL)
    return query.count()

def check_and_disable_default_admin(db: Session, current_user_id: int):
    """检查是否有其他admin，如果有则禁用默认admin账号"""
    other_admin_count = get_active_admin_count(db, exclude_default_admin=True)
    
    if other_admin_count > 0:
        default_admin = db.query(models.User).filter(
            models.User.email == DEFAULT_ADMIN_EMAIL,
            models.User.is_active == True
        ).first()
        
        if default_admin:
            default_admin.is_active = False
            db.commit()
            create_operation_log(
                db, current_user_id, "auto_disable", "user", default_admin.id,
                f"系统自动禁用默认管理员账号（已有其他管理员）"
            )

@router.post("/login", response_model=schemas.Token)
def login(user_login: schemas.UserLogin, request: Request, db: Session = Depends(get_db)):
    """用户登录"""
    user = db.query(models.User).filter(models.User.username.ilike(user_login.username)).first()
    
    if not user or not verify_password(user_login.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被禁用"
        )
    
    password_expired = is_password_expired(user)
    password_remind = should_remind_password_change(user)
    
    # 使用中国时区时间记录登录时间
    user.last_login = china_now()
    db.commit()
    
    client_ip = request.client.host if request.client else None
    create_operation_log(db, user.id, "login", "user", user.id, "用户登录", ip_address=client_ip)
    
    access_token = create_access_token(data={"sub": user.username, "role": user.role})
    refresh_token = create_refresh_token(data={"sub": user.username})
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": user,
        "password_expired": password_expired,
        "password_remind": password_remind,
        "must_change_password": user.must_change_password if hasattr(user, 'must_change_password') else False
    }

@router.post("/refresh", response_model=schemas.Token)
def refresh_token(token_data: schemas.TokenRefresh, db: Session = Depends(get_db)):
    """刷新访问令牌"""
    payload = decode_token(token_data.refresh_token)
    
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的刷新令牌"
        )
    
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请使用刷新令牌"
        )
    
    username = payload.get("sub")
    user = db.query(models.User).filter(models.User.username == username).first()
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被禁用"
        )
    
    access_token = create_access_token(data={"sub": user.username, "role": user.role})
    
    return {
        "access_token": access_token,
        "refresh_token": token_data.refresh_token,
        "token_type": "bearer",
        "user": user,
        "password_expired": is_password_expired(user),
        "password_remind": should_remind_password_change(user),
        "must_change_password": user.must_change_password if hasattr(user, 'must_change_password') else False
    }

@router.get("/me", response_model=schemas.UserResponse)
def get_current_user_info(current_user: models.User = Depends(get_current_active_user)):
    """获取当前用户信息"""
    return current_user

@router.put("/change-password")
def change_password(
    password_data: schemas.UserPasswordChange,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """修改密码"""
    if password_data.old_password:
        if not verify_password(password_data.old_password, current_user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="旧密码错误"
            )
    
    if current_user.role != "admin":
        password_history = db.query(models.PasswordHistory).filter(
            models.PasswordHistory.user_id == current_user.id
        ).all()
        
        for history in password_history:
            if verify_password(password_data.new_password, history.hashed_password):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="新密码不能与历史使用过的密码相同"
                )
        
        if verify_password(password_data.new_password, current_user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="新密码不能与当前密码相同"
            )
        
        password_history_record = models.PasswordHistory(
            user_id=current_user.id,
            hashed_password=current_user.hashed_password
        )
        db.add(password_history_record)
    
    current_user.hashed_password = get_password_hash(password_data.new_password)
    current_user.password_changed_at = china_now()
    if hasattr(current_user, 'must_change_password'):
        current_user.must_change_password = False
    db.commit()
    
    create_operation_log(db, current_user.id, "change_password", "user", current_user.id, "修改密码")
    
    return {"message": "密码修改成功"}

# ========== 用户管理（仅管理员） ==========

@router.post("/users", response_model=schemas.UserResponse)
def create_user(
    user_data: schemas.UserCreate,
    current_user: models.User = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """创建用户（仅管理员）"""
    if db.query(models.User).filter(models.User.username == user_data.username).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在"
        )
    
    if user_data.email and db.query(models.User).filter(models.User.email == user_data.email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邮箱已被使用"
        )
    
    new_user = models.User(
        username=user_data.username,
        email=user_data.email,
        full_name=user_data.full_name,
        hashed_password=get_password_hash(user_data.password),
        role=user_data.role,
        created_by=current_user.id,
        must_change_password=True,
        password_changed_at=datetime.now(CHINA_TZ)
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    create_operation_log(
        db, current_user.id, "create", "user", new_user.id, 
        f"创建用户: {new_user.username}"
    )
    
    if user_data.role == "admin":
        check_and_disable_default_admin(db, current_user.id)
    
    return new_user

@router.get("/users", response_model=List[schemas.UserResponse])
def list_users(
    current_user: models.User = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """获取所有用户（仅管理员）"""
    return db.query(models.User).all()


@router.get("/mis-users", response_model=List[schemas.UserResponse])
def list_mis_users(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取MIS用户列表（用于下拉选择，所有登录用户可访问）"""
    return db.query(models.User).filter(
        models.User.is_active == True,
        models.User.role == 'MIS'
    ).all()

@router.get("/users/{user_id}", response_model=schemas.UserResponse)
def get_user(
    user_id: int,
    current_user: models.User = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """获取用户详情（仅管理员）"""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user

@router.put("/users/{user_id}", response_model=schemas.UserResponse)
def update_user(
    user_id: int,
    user_data: schemas.UserUpdate,
    current_user: models.User = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """更新用户信息（仅管理员）"""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    update_data = user_data.dict(exclude_unset=True)
    old_values = {k: getattr(user, k) for k in update_data.keys()}
    
    if 'role' in update_data and update_data['role'] != user.role:
        old_role = user.role
        new_role = update_data['role']
        
        if old_role == 'admin' and new_role != 'admin':
            active_admin_count = get_active_admin_count(db, exclude_default_admin=True)
            default_admin = db.query(models.User).filter(
                models.User.email == DEFAULT_ADMIN_EMAIL
            ).first()
            is_default_admin_active = default_admin and default_admin.is_active if default_admin else False
            
            if not is_default_admin_active:
                if active_admin_count <= 1 and user.is_active:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="无法修改权限：系统需要至少保留一个活跃的管理员账号"
                    )
            else:
                total_active_admin = get_active_admin_count(db, exclude_default_admin=False)
                if total_active_admin <= 1 and user.is_active:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="无法修改权限：系统需要至少保留一个活跃的管理员账号"
                    )
    
    if 'is_active' in update_data and update_data['is_active'] == False and user.is_active:
        if user.role == 'admin':
            is_default_admin = user.email == DEFAULT_ADMIN_EMAIL
            
            if is_default_admin:
                other_admin_count = get_active_admin_count(db, exclude_default_admin=True)
                if other_admin_count == 0:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="无法禁用默认管理员：请先创建其他管理员账号"
                    )
            else:
                active_admin_count = get_active_admin_count(db, exclude_default_admin=True)
                default_admin = db.query(models.User).filter(
                    models.User.email == DEFAULT_ADMIN_EMAIL
                ).first()
                is_default_admin_active = default_admin and default_admin.is_active if default_admin else False
                
                if not is_default_admin_active and active_admin_count <= 1:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="无法禁用账号：系统需要至少保留一个活跃的管理员账号（默认管理员已被禁用）"
                    )
    
    for key, value in update_data.items():
        setattr(user, key, value)
    
    db.commit()
    db.refresh(user)
    
    create_operation_log(
        db, current_user.id, "update", "user", user.id,
        f"更新用户: {user.username}",
        json.dumps(old_values, default=str),
        json.dumps(update_data, default=str)
    )
    
    if 'role' in update_data and update_data['role'] == 'admin':
        check_and_disable_default_admin(db, current_user.id)
    
    return user

@router.put("/users/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    password_data: schemas.UserPasswordChange,
    current_user: models.User = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """重置用户密码（仅管理员）"""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    user.hashed_password = get_password_hash(password_data.new_password)
    user.password_changed_at = china_now()
    db.commit()
    
    create_operation_log(
        db, current_user.id, "reset_password", "user", user.id,
        f"重置用户密码: {user.username}"
    )
    
    return {"message": f"用户 {user.username} 的密码已重置"}

@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    current_user: models.User = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """禁用用户（仅管理员）— 不物理删除，仅标记为不活跃"""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 不能删除自己
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="不能删除当前登录的账号")

    # 保证至少保留一个管理员
    if user.role == 'admin' and user.is_active:
        active_admin_count = get_active_admin_count(db, exclude_default_admin=False)
        if active_admin_count <= 1:
            raise HTTPException(status_code=400, detail="无法删除：系统需要至少保留一个活跃的管理员账号")

    username = user.username

    # 软删除：仅禁用用户，保留所有关联数据（操作日志、密码历史等）
    user.is_active = False

    create_operation_log(
        db, current_user.id, "delete", "user", user.id,
        f"禁用用户: {username}"
    )
    db.commit()
    return {"message": f"用户 {username} 已禁用"}

@router.get("/logs", response_model=List[schemas.OperationLogResponse])
def get_operation_logs(
    skip: int = 0,
    limit: int = 100,
    user_id: int = None,
    action: str = None,
    resource_type: str = None,
    current_user: models.User = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """获取操作日志（仅管理员）"""
    query = db.query(models.OperationLog)
    
    if user_id:
        query = query.filter(models.OperationLog.user_id == user_id)
    if action:
        query = query.filter(models.OperationLog.action == action)
    if resource_type:
        query = query.filter(models.OperationLog.resource_type == resource_type)
    
    return query.order_by(models.OperationLog.created_at.desc()).offset(skip).limit(limit).all()
