"""从现有资产数据中提取品牌并初始化"""
from database import SessionLocal
import models

def init():
    db = SessionLocal()
    # 从资产表提取所有不重复的品牌
    brands_from_assets = db.query(models.Asset.brand).distinct().filter(models.Asset.brand.isnot(None), models.Asset.brand != '').all()
    brands_from_warehouse = db.query(models.WarehouseAsset.brand).distinct().filter(models.WarehouseAsset.brand.isnot(None), models.WarehouseAsset.brand != '').all()
    
    all_brands = set()
    for (b,) in brands_from_assets:
        if b and b.strip():
            all_brands.add(b.strip())
    for (b,) in brands_from_warehouse:
        if b and b.strip():
            all_brands.add(b.strip())
    
    # 补充常见品牌
    common = ['Dell', 'HP', 'Lenovo', 'Apple', 'ASUS', 'Acer', 'Microsoft', 'Samsung', 'Huawei', 'Xiaomi', 'ThinkPad']
    all_brands.update(common)
    
    for name in sorted(all_brands):
        existing = db.query(models.Brand).filter(models.Brand.name == name).first()
        if not existing:
            db.add(models.Brand(name=name))
            print(f"✅ 添加品牌: {name}")
        else:
            print(f"⏭ 已存在: {name}")
    db.commit()
    db.close()

if __name__ == "__main__":
    init()
