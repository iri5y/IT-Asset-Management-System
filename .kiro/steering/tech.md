# Tech Stack & Build

## Backend (Python)

- **Framework**: FastAPI
- **ORM**: SQLAlchemy 2.0+ with declarative models
- **Database**: PostgreSQL (via `psycopg2-binary`); SQLite supported for dev
- **Validation**: Pydantic v2 (BaseModel with `from_attributes = True`)
- **Auth**: JWT tokens via `python-jose`, password hashing via `bcrypt`
- **Config**: `python-dotenv` for `.env` loading
- **Server**: Uvicorn

### Backend Commands

```bash
# Install dependencies
cd backend && pip install -r requirements.txt

# Run dev server
cd backend && python -m uvicorn main:app --reload --port 8000

# Initialize database tables (auto-created on startup via SQLAlchemy metadata)
# Seed data
cd backend && python seed_updated_data.py

# Initialize admin user
cd backend && python init_admin.py

# Run migrations (manual scripts)
cd backend && python migrate_auth.py
```

## Frontend (JavaScript/JSX)

- **UI**: React 18 (functional components, hooks)
- **Routing**: React Router v7 (BrowserRouter, `<Routes>`)
- **HTTP Client**: Axios (with interceptors for JWT)
- **Icons**: lucide-react
- **Styling**: Tailwind CSS v4 (via `@tailwindcss/vite` plugin) + custom CSS in `index.css`
- **Build Tool**: Vite 5

### Frontend Commands

```bash
# Install dependencies
cd frontend && npm install

# Run dev server
cd frontend && npm run dev

# Production build
cd frontend && npm run build

# Preview production build
cd frontend && npm run preview
```

## Environment Variables

- Backend: `backend/.env` — `DATABASE_URL`, `SECRET_KEY`
- Frontend: `frontend/.env` — `VITE_API_URL` (defaults to ``)

## Conventions

- Backend follows PEP 8. No linter/formatter config is committed.
- Frontend uses JSX (not TSX). No ESLint or Prettier config is committed.
- No test framework is currently set up in either backend or frontend.
- Database migrations are handled via standalone Python scripts (`migrate_*.py`), not Alembic.
- All timestamps use China timezone (UTC+8) via a `china_now()` helper, stored as naive datetimes.
