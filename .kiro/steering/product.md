# Product Overview

IT Asset Management System (IT资产管理系统) — an enterprise-grade web application for managing the full lifecycle of IT assets: procurement, allocation, repair, return, and retirement.

## Core Modules

- **Asset Management**: Track computers, laptops, monitors, printers, network devices, and phones. Supports assignment to employees, status transitions (Active → In Storage → In Repair → Retired), and full audit logging.
- **Warehouse Management**: Inventory control for IT supplies with stock-in/stock-out, low-stock alerts, and location-based categorization.
- **Return Management**: Handle asset returns from departing employees with tracking and confirmation workflows.
- **Dashboard & Reporting**: Statistical dashboards with distribution charts for asset status, category, brand, and location. Weekly report generation.
- **User & Auth**: JWT-based authentication with role-based access (admin / MIS). Password expiration policies, password history enforcement, and forced password change on first login.

## Key Business Rules

- Asset tags follow the format `IT-YYYY-NNNN`.
- Asset statuses: `Active`, `In Storage`, `In Repair`, `Retired`.
- Hostname changes are tracked in a dedicated history table.
- Asset deletions require admin role and a reason; deleted asset data is preserved in a deletion record.
- All mutations generate operation logs for audit.
- Passwords expire after 90 days for non-admin users; admins get a reminder but are not forced.
- The system must always retain at least one active admin account.

## Language & Locale

- The UI and all user-facing strings are in **Chinese (Simplified)**.
- Code comments, variable names, and API error messages are a mix of Chinese and English.
- When adding new user-facing text, use Chinese to stay consistent.
