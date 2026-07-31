# import_v2 — 企业级导入模块 v2
# Phase 1: Domain Model + Source + Normalizer + Resolvers
# Phase 2: Validator + Classifier + ImportPolicy + Pipeline

from .domain_models import (
    AssetRecord,
    ImportContext,
    ResolvedRefs,
    DepartmentRef,
    BrandRef,
    LocationRef,
    RecordClassification,
    PolicyDecision,
    IssueType,
    LocationType,
    ErrorType,
    WarningType,
)
from .normalizer import Normalizer
from .validator import Validator
from .classifier import Classifier
from .import_policy import ImportPolicy, ImportPolicyType
from .pipeline import ImportPipeline, PipelineResult, PreviewSummary
from .executor import Executor, ImportExecutionError
from .sources.excel_source import ExcelSource, generate_import_template
from .resolvers import DepartmentResolver, BrandResolver, LocationResolver
from .import_session import (
    ImportSession,
    SessionStatus,
    MappingEntry,
    MappingFieldType,
    InMemorySessionStore,
    AbstractSessionStore,
    get_session_store,
    make_mapping_key,
)

__all__ = [
    # Domain Models
    "AssetRecord", "ImportContext", "ResolvedRefs",
    "DepartmentRef", "BrandRef", "LocationRef",
    "RecordClassification", "PolicyDecision",
    "IssueType", "LocationType", "ErrorType", "WarningType",
    # Processing Layers
    "Normalizer", "Validator", "Classifier",
    "ImportPolicy", "ImportPolicyType",
    # Pipeline
    "ImportPipeline", "PipelineResult", "PreviewSummary",
    # Executor
    "Executor", "ImportExecutionError",
    # Source & Resolvers
    "ExcelSource", "generate_import_template",
    "DepartmentResolver", "BrandResolver", "LocationResolver",
    # Session
    "ImportSession", "SessionStatus",
    "MappingEntry", "MappingFieldType",
    "InMemorySessionStore", "AbstractSessionStore",
    "get_session_store", "make_mapping_key",
]
