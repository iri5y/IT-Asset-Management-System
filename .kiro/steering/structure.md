# Project Structure

```
├── backend/                     # FastAPI backend
│   ├── main.py                  # App entry, all REST route handlers
│   ├── models.py                # SQLAlchemy ORM models
│   ├── schemas.py               # Pydantic request/response schemas
│   ├── database.py              # DB engine, session, Base
│   ├── auth.py                  # JWT helpers, password utils, dependency injectors
│   ├── auth_routes.py           # /auth/* endpoints (login, users, password, logs)
│   ├── import_service.py        # Bulk import logic (Excel parsing, validation, template)
│   ├── init_admin.py            # Seed default admin user
│   ├── init_brands.py           # Seed default brands
│   ├── init_departments.py      # Seed default departments
│   ├── init_locations.py        # Seed default warehouse locations
│   ├── create_database.py       # DB creation utility (PostgreSQL)
│   ├── reconcile_inventory.py   # Ops tool: cross-check asset vs warehouse quantities
│   ├── migrate_fix_data_consistency.py  # Data repair: clear stale employee bindings
│   ├── migrate_asset_condition.py       # Add assets.condition column
│   ├── migrate_asset_part_logs.py       # Create asset_part_logs table
│   ├── migrate_location_description.py  # Add description to location tables
│   ├── requirements.txt         # Python dependencies
│   └── .env                     # Environment config (not committed)
│
├── frontend/                    # React SPA
│   ├── src/
│   │   ├── App.jsx              # Root component, routing, top-level state
│   │   ├── main.jsx             # ReactDOM entry point
│   │   ├── index.css            # Global + component styles
│   │   ├── contexts/
│   │   │   └── AuthContext.jsx  # Auth state provider (login, logout, token mgmt)
│   │   └── components/
│   │       ├── Dashboard.jsx          # Asset statistics dashboard
│   │       ├── Sidebar.jsx            # Asset list sidebar with search/filter panel
│   │       ├── AssetDetail.jsx        # Single asset detail view
│   │       ├── AssetModal.jsx         # Add/edit asset modal
│   │       ├── IdleAssets.jsx         # Idle assets in warehouse view
│   │       ├── RetiredAssets.jsx      # Retired assets list view
│   │       ├── Warehouse.jsx          # Warehouse inventory management
│   │       ├── WarehouseDashboard.jsx # Warehouse statistics dashboard
│   │       ├── WarehouseAssetDetail.jsx # Warehouse asset detail
│   │       ├── WarehouseSidebar.jsx   # Warehouse asset list sidebar
│   │       ├── ReturnManagement.jsx   # Employee asset return tracking
│   │       ├── ReturnHistory.jsx      # Return history table view
│   │       ├── ScanWorkstation.jsx    # Barcode scan workstation + bulk inbound
│   │       ├── ImportModal.jsx        # Bulk Excel import modal
│   │       ├── LocationManagement.jsx # Warehouse/office location CRUD
│   │       ├── BrandManagement.jsx    # Brand CRUD
│   │       ├── DepartmentManagement.jsx # Department tree CRUD
│   │       ├── Login.jsx              # Login form
│   │       ├── ChangePassword.jsx     # Password change form
│   │       ├── UserMenu.jsx           # User dropdown menu
│   │       └── UserManagement.jsx     # Admin user CRUD
│   ├── package.json
│   └── vite.config.js
│
├── *.bat                        # Windows convenience scripts (start, setup)
└── *.md                         # Documentation (README, DEPLOYMENT_GUIDE, etc.)
```

## Architecture Notes

- **Monorepo** with separate `backend/` and `frontend/` directories. No shared workspace tooling.
- Backend is a single FastAPI app — all routes live in `main.py` (assets, warehouse, returns) and `auth_routes.py` (auth/users). No blueprint/router splitting beyond auth.
- Frontend is a single-page app. `App.jsx` owns top-level state and renders all views based on route. There is no dedicated state management library; state flows via props and React Context (`AuthContext`).
- Components are flat in `frontend/src/components/` — no nested folders.
- API communication uses Axios with a base URL from `VITE_API_URL`. Auth tokens are injected via Axios interceptors configured in `AuthContext`.
- No monorepo build orchestration (no Turborepo, Nx, etc.). Backend and frontend are started independently.

## Asset Tag Format

- Format: `ZS-{PREFIX}{YY}-{NNNNNN}` (e.g. `ZS-PC26-000001`)
- Category prefix mapping: PC=台式机, NB=笔记本电脑, MR=显示器, PD=移动设备, PH=手机, PR=打印机, NW=网络设备, MS=无线鼠标, OT=其他设备, SV=服务器
- YY = last two digits of current year

## Migration Scripts (active)

Only the following migration scripts need to be run on a fresh database after `models.Base.metadata.create_all()`:

| Script | Purpose |
|--------|---------|
| `migrate_asset_condition.py` | Add `assets.condition` column |
| `migrate_asset_part_logs.py` | Create `asset_part_logs` table |
| `migrate_location_description.py` | Add `description` to location tables |
| `migrate_fix_data_consistency.py` | On-demand data repair tool |
| `reconcile_inventory.py` | On-demand inventory audit tool |
