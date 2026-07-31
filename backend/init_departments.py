"""从现有资产数据中提取部门并初始化"""
from database import SessionLocal
import models

def init():
    db = SessionLocal()
    depts = db.query(models.Asset.department).distinct().filter(
        models.Asset.department.isnot(None), models.Asset.department != ''
    ).all()
    all_depts = set()
    for (d,) in depts:
        if d and d.strip():
            all_depts.add(d.strip())
    for name in sorted(all_depts):
        if not db.query(models.Department).filter(models.Department.name == name).first():
            db.add(models.Department(name=name))
            print(f"✅ 添加部门: {name}")
        else:
            print(f"⏭ 已存在: {name}")
    db.commit()
    db.close()

if __name__ == "__main__":
    init()
