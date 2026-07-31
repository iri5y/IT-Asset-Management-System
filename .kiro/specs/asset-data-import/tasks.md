# 实现任务：资产数据导入

## 任务列表

- [x] 1 后端依赖与 Schema 准备
  - [x] 1.1 在 `backend/requirements.txt` 中添加 `pandas>=2.0.0`、`openpyxl>=3.1.0`、`hypothesis>=6.0.0` 依赖
  - [x] 1.2 在 `backend/schemas.py` 中新增 `ImportError` 和 `ImportResult` Pydantic 模型（含 total_rows, success_count, failed_count, errors, message 字段）
- [x] 2 后端服务模块 `import_service.py`
  - [x] 2.1 创建 `backend/import_service.py`，定义 `COLUMN_MAPPING`、`REVERSE_MAPPING`、`REQUIRED_COLUMNS`、`VALID_STATUSES`、`ASSET_TAG_PATTERN` 常量，以及 `map_columns()` 映射函数
  - [x] 2.2 实现 `parse_excel(file_content: bytes)` 函数：使用 `pandas.read_excel(io.BytesIO(file_content), dtype=str)` 读取 Excel，检查必填列头，将中文列头映射为英文字段名，NaN 转 None，返回 `(headers, rows)`
  - [x] 2.3 实现 `validate_rows(rows, db)` 函数：逐行先用 `AssetCreate(**row_data)` 做 Pydantic 验证（捕获 ValidationError），再做自定义验证（asset_tag 格式/去重/DB唯一性、status 合法性、serial_number DB唯一性、使用中需 employee_name），返回 `(valid_rows, errors)`
  - [x] 2.4 实现 `bulk_insert_assets(valid_rows, db, current_user)` 函数：批量创建 Asset 记录、AssetLog（action="批量导入"）、闲置资产同步库房数量、创建 OperationLog
  - [x] 2.5 实现 `generate_template()` 函数：使用 openpyxl 生成包含中文列头和示例数据的 .xlsx 模板
- [x] 3 后端 API 路由
  - [x] 3.1 在 `backend/main.py` 中添加 `POST /assets/import` 路由：文件类型/大小校验 → 调用 parse_excel → validate_rows → bulk_insert_assets → 返回 ImportResult JSON 报告
  - [x] 3.2 在 `backend/main.py` 中添加 `GET /assets/import-template` 路由：调用 generate_template() 返回 StreamingResponse
- [x] 4 前端导入界面
  - [x] 4.1 创建 `frontend/src/components/ImportModal.jsx`：文件选择（仅 .xlsx）、下载模板链接、上传按钮、加载状态、结果表格（成功数/失败数/失败明细）
  - [x] 4.2 修改 `frontend/src/components/Sidebar.jsx`：添加"批量导入"按钮，新增 `onImport` prop
  - [x] 4.3 修改 `frontend/src/App.jsx`：添加 ImportModal 状态管理，将 `onImport` 回调传递给 Sidebar，导入成功后刷新资产列表
- [x] 5 测试
  - [x] 5.1 创建 `backend/tests/test_import_unit.py`：编写单元测试（文件类型拒绝、文件大小拒绝、认证检查、列头映射、pandas 字符串读取、Pydantic 错误捕获、事务回滚、JSON 报告格式、全失败场景、OperationLog 创建、模板示例行）
  - [x] 5.2 创建 `backend/tests/test_import_integration.py`：编写集成测试（端到端导入流程、闲置资产库房同步、AssetLog 创建、模板下载后重新导入）
