# import_v2.resolvers — Resolver Layer
# 每个 Resolver 负责解析一种主数据，返回强类型 Ref 对象（含 DB id）
from .department_resolver import DepartmentResolver
from .brand_resolver import BrandResolver
from .location_resolver import LocationResolver

__all__ = ["DepartmentResolver", "BrandResolver", "LocationResolver"]
