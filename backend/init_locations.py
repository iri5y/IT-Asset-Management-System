"""初始化默认库房位置"""
from database import SessionLocal
import models

def init():
    db = SessionLocal()
    defaults = ['IT库房', 'A区货架', 'B区货架', 'C区货架', '临时存放区', '办公区域']
    for name in defaults:
        existing = db.query(models.WarehouseLocation).filter(models.WarehouseLocation.name == name).first()
        if not existing:
            db.add(models.WarehouseLocation(name=name))
            print(f"✅ 添加位置: {name}")
        else:
            print(f"⏭ 已存在: {name}")
    db.commit()
    db.close()

if __name__ == "__main__":
    init()
