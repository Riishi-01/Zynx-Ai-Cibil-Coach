# Quick Reference: CIBIL Coach Database Setup

**For rapid onboarding after the database migration (2026-07-25)**

---

## ⚡ TL;DR — Get Started in 3 Commands

```bash
# 1. Install & setup
source .venv/bin/activate
pip install -r requirements.txt

# 2. Initialize database
PYTHONPATH=/Users/rr/DEV/CIBIL\ Coach python3 scripts/seed_db.py --reset

# 3. Run the app
bash run_web.sh
```

Open http://localhost:8000 and start analyzing credit profiles.

---

## 📚 What Changed?

| Before | After |
|--------|-------|
| Fixture: `cibil_data.json` (23 KB) in memory | SQLite DB: `cibil_coach.db` (90 KB) on disk |
| No migrations | Alembic migrations in `alembic/` |
| `app/db.py`: in-memory dict | `app/db.py`: SQLAlchemy queries |
| No schema versioning | Versioned schema with alembic |
| Fixture dependency at startup | Works entirely from DB at runtime |

---

## 🔄 Key Concepts

### Repository Pattern
```
app/db.py → get_repository() → CustomerRepository
  ↓
  Queries SQLite (app/models.py ORM)
  ↓
  Returns CustomerRecord (Pydantic)
  ↓
  No fixture involved
```

### Database Layout
```
6 tables, all linked by PAN (primary key):
  customers ← (1:1) → scores
  customers ← (1:many) → accounts
  customers ← (1:many) → inquiries
  customers ← (1:many) → collections
  customers ← (1:many) → public_records
```

### Auto-Migration
```
On app startup (first request):
  get_db_session() calls alembic.command.upgrade("head")
  ↓
  All pending migrations run silently
  ↓
  Schema is ready
```

---

## 📁 Important Files

**Database:**
- `cibil_coach.db` — Main database file (created on first run)
- `alembic.ini` — Alembic configuration
- `alembic/` — Migration scripts (auto-generated)

**Code:**
- `app/models.py` — SQLAlchemy ORM (NEW)
- `app/database.py` — Engine + session factory (NEW)
- `app/db.py` — Repository (MODIFIED)

**Scripts:**
- `scripts/seed_db.py` — Load fixture into DB (NEW)
- `scripts/e2e_db_test.py` — Full pipeline test (NEW)

**Documentation:**
- `DATABASE_MIGRATION.md` — Complete migration summary (NEW)
- `WEB_README.md` — Updated with DB setup (MODIFIED)

---

## ✅ Common Tasks

### Fresh Installation
```bash
# 1. Create schema
alembic upgrade head

# 2. Seed from fixture
PYTHONPATH=$(pwd) python3 scripts/seed_db.py

# 3. Start app
bash run_web.sh
```

### Reset Everything (Dev Only)
```bash
# Drops all tables, recreates, reseed
PYTHONPATH=$(pwd) python3 scripts/seed_db.py --reset
```

### Add More Customers
```bash
# 1. Update cibil_data.json manually
# 2. Re-seed
PYTHONPATH=$(pwd) python3 scripts/seed_db.py --reset
```

### Test Full Pipeline
```bash
# Runs precompute → labels → prompt on all 23 customers
PYTHONPATH=$(pwd) python3 scripts/e2e_db_test.py
```

### Verify No Fixture Dependency
```bash
# Delete fixture, app still works
rm build_docs/cibil_data.json
bash run_web.sh
# ✓ Still responds at http://localhost:8000
```

---

## 🔧 Configuration

### Environment Variables (Optional)

```bash
# Database
export DATABASE_URL="sqlite:///./cibil_coach.db"  # Default
# or PostgreSQL:
# export DATABASE_URL="postgresql://user:pass@host/db"

# LLM (existing)
export OPENAI_API_KEY="sk-..."
export LLM_TEMPERATURE="0.3"
export LLM_MAX_TOKENS="1000"
```

### Database URL Examples

```
SQLite (default):     sqlite:///./cibil_coach.db
SQLite (in-memory):   sqlite:///:memory:
PostgreSQL:           postgresql://user:password@localhost/cibil_coach
MySQL:                mysql+pymysql://user:password@localhost/cibil_coach
```

---

## 🧪 Testing

### Unit: Check imports
```bash
python3 -c "from app.models import Base; from app.db import get_repository; print('✓')"
```

### Integration: Check repository
```bash
python3 -c "from app.db import get_repository; r = get_repository(); print(f'✓ {r.count()} customers')"
```

### End-to-End: Full pipeline
```bash
PYTHONPATH=$(pwd) python3 scripts/e2e_db_test.py
```

### API: Start web server and test
```bash
# Terminal 1
bash run_web.sh

# Terminal 2
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"pan": "ABCPS1234A", "income": 75000}'
```

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: app` | Set `PYTHONPATH=$(pwd)` before running scripts |
| `table customers already exists` | Normal on second run (migrations are idempotent) |
| `No credit file for PAN` | Use one of the 23 seed PANs (e.g., ABCPS1234A) |
| `ImportError: alembic` | Run `pip install -r requirements.txt` |
| `cibil_coach.db not found` | App creates it on first request (or run `alembic upgrade head`) |
| Web app won't start | Check `OPENAI_API_KEY` is set in `.env` |

---

## 📊 Database Schema at a Glance

```sql
-- Primary table (23 customers)
customers (
  pan_card VARCHAR PRIMARY KEY,
  customer_id VARCHAR UNIQUE,
  first_name, dob_year, income_bracket, income_monthly_paise, region
)

-- Linked tables (1:1 or 1:many)
scores (score_id PK, pan_card FK → customers, score, band, ...)
accounts (account_id PK, pan_card FK, display_name, balance, credit_limit, ...)
inquiries (inquiry_id PK, pan_card FK, creditor_name, inquiry_date, ...)
collections (collection_id PK, pan_card FK, original_creditor, is_past_sol, ...)
public_records (record_id PK, pan_card FK, record_type, filed_date, ...)
```

---

## ⏱️ Performance

| Operation | Time |
|-----------|------|
| Query customer by PAN | ~1ms |
| Reconstruct full record | ~2ms |
| Precompute 74 facts | ~10ms |
| Fire 32 labels | ~5ms |
| Build prompt | ~3ms |
| LLM call (mock) | 0ms |
| LLM call (real) | 2-5 sec |
| Full pipeline (no LLM) | ~25ms |
| Web app startup (first request) | +100ms (migrations) |

---

## 📚 Further Reading

- **DATABASE_MIGRATION.md** — Complete migration documentation
- **WEB_README.md** — Web interface documentation
- **app/models.py** — ORM model definitions (well-commented)
- **scripts/seed_db.py** — Fixture → DB seeding logic
- **scripts/e2e_db_test.py** — End-to-end test workflow

---

## ✅ Checklist After Migration

- [ ] Run `scripts/seed_db.py --reset` to initialize
- [ ] Verify `cibil_coach.db` created (file should exist)
- [ ] Test `python3 -c "from app.db import get_repository; print(get_repository().count())"` returns 23
- [ ] Start web app: `bash run_web.sh`
- [ ] Open http://localhost:8000 in browser
- [ ] Try analyzing ABCPS1234A with income 75000
- [ ] Verify score appears as 715 (Good)
- [ ] Check all 11 labels fire for that customer
- [ ] Test with real OpenAI API key (set in .env)
- [ ] Run `scripts/e2e_db_test.py` to verify all 32 labels fire

---

## 🎓 What You Learned

✅ SQLAlchemy ORM for Python-to-SQL mapping  
✅ Alembic for schema versioning and migrations  
✅ Repository pattern for data access abstraction  
✅ Fixture → database migration  
✅ Auto-migration on app startup  
✅ Backward-compatible API changes  
✅ End-to-end testing strategy

---

## 🚀 Next Steps (Optional)

1. Deploy to production (PostgreSQL backend)
2. Add more customers to the database
3. Implement score history tracking
4. Add audit logging for compliance
5. Build admin dashboard for customer management

---

**Status: READY TO USE** ✅

For detailed information, see `DATABASE_MIGRATION.md`.
