"""本地认证模块"""
from datetime import datetime, timedelta, timezone
from typing import Optional
import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import os

from database import get_db
import models

# 中国时区 UTC+8
CHINA_TZ = timezone(timedelta(hours=8))

def china_now():
    """返回中国时区的当前时间，但以naive datetime存储（数据库会按本地时区处理）"""
    # 获取当前UTC时间，然后转换为中国时区，最后移除时区信息
    utc_now = datetime.now(timezone.utc)
    china_time = utc_now.astimezone(CHINA_TZ)
    return china_time.replace(tzinfo=None)  # 移除时区信息，让数据库按本地时区处理

# JWT配置
SECRET_KEY = os.getenv("SECRET_KEY", "87b39aa0fa213676472d10c58aaef433243331cc57dd542730ce849ddfeae31b")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 30
PASSWORD_EXPIRE_DAYS = 90

security = HTTPBearer()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def get_password_hash(password: str) -> str:
    """生成密码哈希"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建访问令牌"""
    to_encode = data.copy()
    expire = china_now() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(data: dict) -> str:
    """创建刷新令牌"""
    to_encode = data.copy()
    expire = china_now() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> Optional[dict]:
    """解码令牌"""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None

def is_password_expired(user: models.User) -> bool:
    """检查密码是否过期（admin不过期）"""
    if user.role == "admin":
        return False
    if not user.password_changed_at:
        return True
    # 假设数据库中的时间是中国时区的naive datetime
    password_changed_china = user.password_changed_at
    current_china = china_now()
    
    days_since_change = (current_china - password_changed_china).days
    return days_since_change >= PASSWORD_EXPIRE_DAYS

def should_remind_password_change(user: models.User) -> bool:
    """检查是否应该提醒修改密码（admin超过90天提醒但不强制）"""
    if not user.password_changed_at:
        return True
    # 假设数据库中的时间是中国时区的naive datetime
    password_changed_china = user.password_changed_at
    current_china = china_now()
    
    days_since_change = (current_china - password_changed_china).days
    return days_since_change >= PASSWORD_EXPIRE_DAYS

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> models.User:
    """获取当前用户"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的认证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    token = credentials.credentials
    payload = decode_token(token)
    
    if payload is None:
        raise credentials_exception
    
    if payload.get("type") != "access":
        raise credentials_exception
    
    username: str = payload.get("sub")
    if username is None:
        raise credentials_exception
    
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None:
        raise credentials_exception
    
    return user

async def get_current_active_user(current_user: models.User = Depends(get_current_user)) -> models.User:
    """获取当前活跃用户"""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="用户已被禁用")
    return current_user

def require_role(allowed_roles: list):
    """角色验证装饰器"""
    async def role_checker(current_user: models.User = Depends(get_current_active_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足"
            )
        return current_user
    return role_checker

def require_admin():
    """管理员权限验证"""
    return require_role(["admin"])
