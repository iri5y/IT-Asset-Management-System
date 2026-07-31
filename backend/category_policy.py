"""资产分类、领用策略与中文业务校验的唯一规则来源。"""

from enum import Enum
from typing import Final, Iterable


class CategoryPolicyError(ValueError):
    """分类、策略或状态不符合业务规则时抛出的中文错误。"""


class AssetCategoryCode(str, Enum):
    PC = "PC"
    NB = "NB"
    PD = "PD"


class IssuePolicy(str, Enum):
    RETURNABLE = "RETURNABLE"
    CONSUMABLE = "CONSUMABLE"


class FixedAssetStatus(str, Enum):
    IDLE = "闲置"
    IN_USE = "使用中"
    IN_REPAIR = "维修中"
    RETIRED = "报废"


class PrimaryCategoryCode(str, Enum):
    TERMINAL_EQUIPMENT = "TERMINAL_EQUIPMENT"
    DISPLAY_AUDIO_VIDEO = "DISPLAY_AUDIO_VIDEO"
    INPUT_OFFICE_PERIPHERALS = "INPUT_OFFICE_PERIPHERALS"
    STORAGE_REPAIR_PARTS = "STORAGE_REPAIR_PARTS"
    CABLES_CONNECTORS = "CABLES_CONNECTORS"
    NETWORK_SERVER_ROOM_CONSUMABLES = "NETWORK_SERVER_ROOM_CONSUMABLES"
    IT_TOOLS_LOAN_ITEMS = "IT_TOOLS_LOAN_ITEMS"
    OFFICE_GENERAL_CONSUMABLES = "OFFICE_GENERAL_CONSUMABLES"


ASSET_CATEGORY_NAMES: Final[dict[AssetCategoryCode, str]] = {
    AssetCategoryCode.PC: "台式机",
    AssetCategoryCode.NB: "笔记本电脑",
    AssetCategoryCode.PD: "平板电脑",
}
LEGACY_ASSET_CATEGORY_ALIASES: Final[dict[str, str]] = {"移动设备": "平板电脑"}
NON_FIXED_ASSET_CARD_ERROR: Final[str] = "请改入低值领用或仓储物料"
INVALID_ISSUE_POLICY_ERROR: Final[str] = "领用策略仅支持“待归还”或“一次性消耗品”"
INVALID_FIXED_ASSET_STATUS_ERROR: Final[str] = "固定资产状态仅支持“闲置、使用中、维修中、报废”"

PRIMARY_CATEGORY_NAMES: Final[dict[PrimaryCategoryCode, str]] = {
    PrimaryCategoryCode.TERMINAL_EQUIPMENT: "终端设备库存",
    PrimaryCategoryCode.DISPLAY_AUDIO_VIDEO: "显示与音视频设备",
    PrimaryCategoryCode.INPUT_OFFICE_PERIPHERALS: "输入与办公外设",
    PrimaryCategoryCode.STORAGE_REPAIR_PARTS: "存储与维修备件",
    PrimaryCategoryCode.CABLES_CONNECTORS: "线缆与连接配件",
    PrimaryCategoryCode.NETWORK_SERVER_ROOM_CONSUMABLES: "网络与机房耗材",
    PrimaryCategoryCode.IT_TOOLS_LOAN_ITEMS: "IT工具与借用物品",
    PrimaryCategoryCode.OFFICE_GENERAL_CONSUMABLES: "办公与通用耗材",
}
ISSUE_POLICY_NAMES: Final[dict[IssuePolicy, str]] = {
    IssuePolicy.RETURNABLE: "待归还",
    IssuePolicy.CONSUMABLE: "一次性消耗品",
}
FIXED_ASSET_CATEGORY_OPTIONS: Final[tuple[AssetCategoryCode, ...]] = tuple(
    AssetCategoryCode
)
FIXED_ASSET_STATUSES: Final[tuple[FixedAssetStatus, ...]] = tuple(
    FixedAssetStatus
)
PRIMARY_CATEGORY_SEEDS: Final[tuple[tuple[str, str], ...]] = tuple(
    (category.value, PRIMARY_CATEGORY_NAMES[category])
    for category in PrimaryCategoryCode
)

# 这些低值物品在保存目录项时只能选择待归还策略。
RETURNABLE_ONLY_MATERIALS: Final[frozenset[str]] = frozenset(
    {"显示器", "扬声器", "扩展坞", "摄像头"}
)
# 这些低值物品必须可选一次性消耗品；目录可按业务需要保留待归还策略。
CONSUMABLE_OPTION_MATERIALS: Final[frozenset[str]] = frozenset(
    {"鼠标", "键盘", "鼠标垫", "线材", "小配件"}
)


def _clean(value: str) -> str:
    return value.strip()


def normalize_asset_category(value: str | AssetCategoryCode) -> str:
    """规范化历史分类；未知分类保留原值，由调用方决定是否允许。"""
    if isinstance(value, AssetCategoryCode):
        return ASSET_CATEGORY_NAMES[value]
    normalized = _clean(value)
    return LEGACY_ASSET_CATEGORY_ALIASES.get(normalized, normalized)


def asset_category_code(value: str | AssetCategoryCode) -> AssetCategoryCode | None:
    """将固定资产代码、中文名称或历史名称解析为固定资产代码。"""
    if isinstance(value, AssetCategoryCode):
        return value
    category_name = normalize_asset_category(value)
    for code, name in ASSET_CATEGORY_NAMES.items():
        if category_name == name or category_name.upper() == code.value:
            return code
    return None


def is_fixed_asset_category(value: str | AssetCategoryCode) -> bool:
    return asset_category_code(value) is not None


def require_fixed_asset_category(value: str | AssetCategoryCode) -> AssetCategoryCode:
    category = asset_category_code(value)
    if category is None:
        raise CategoryPolicyError(NON_FIXED_ASSET_CARD_ERROR)
    return category


def require_fixed_asset_status(value: str | FixedAssetStatus) -> FixedAssetStatus:
    if isinstance(value, FixedAssetStatus):
        return value
    try:
        return FixedAssetStatus(_clean(value))
    except ValueError as error:
        raise CategoryPolicyError(INVALID_FIXED_ASSET_STATUS_ERROR) from error


def _primary_category_code(
    value: str | PrimaryCategoryCode,
) -> PrimaryCategoryCode | None:
    if isinstance(value, PrimaryCategoryCode):
        return value
    normalized = _clean(value)
    for code, name in PRIMARY_CATEGORY_NAMES.items():
        if normalized == name or normalized.upper() == code.value:
            return code
    return None


def allowed_issue_policies(
    primary_category: str | PrimaryCategoryCode | None,
    material_name: str | None = None,
) -> frozenset[IssuePolicy]:
    """根据一级分类与受限低值物品返回可保存的领用策略。"""
    primary_code = (
        _primary_category_code(primary_category)
        if primary_category is not None
        else None
    )
    if primary_code == PrimaryCategoryCode.OFFICE_GENERAL_CONSUMABLES:
        return frozenset({IssuePolicy.CONSUMABLE})

    normalized_name = _clean(material_name) if material_name else ""
    if normalized_name in RETURNABLE_ONLY_MATERIALS:
        return frozenset({IssuePolicy.RETURNABLE})
    if normalized_name in CONSUMABLE_OPTION_MATERIALS:
        return frozenset({IssuePolicy.CONSUMABLE})
    return frozenset(IssuePolicy)


def require_issue_policy(
    value: str | IssuePolicy,
    *,
    primary_category: str | PrimaryCategoryCode | None = None,
    material_name: str | None = None,
) -> IssuePolicy:
    try:
        policy = value if isinstance(value, IssuePolicy) else IssuePolicy(_clean(value).upper())
    except ValueError as error:
        raise CategoryPolicyError(INVALID_ISSUE_POLICY_ERROR) from error

    if policy not in allowed_issue_policies(primary_category, material_name):
        if _primary_category_code(primary_category or "") == (
            PrimaryCategoryCode.OFFICE_GENERAL_CONSUMABLES
        ):
            raise CategoryPolicyError("办公与通用耗材仅支持“一次性消耗品”领用策略")
        raise CategoryPolicyError("该低值物品不支持所选领用策略")
    return policy


def category_options(
    categories: Iterable[AssetCategoryCode] = FIXED_ASSET_CATEGORY_OPTIONS,
) -> list[dict[str, str]]:
    """生成供中文界面直接使用的固定资产分类选项。"""
    return [{"code": item.value, "name": ASSET_CATEGORY_NAMES[item]} for item in categories]
