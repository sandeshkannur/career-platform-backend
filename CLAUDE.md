# Career Platform Backend — Claude Cheat Sheet

## Stack
- FastAPI 0.115 + SQLAlchemy 2.0 + Pydantic 2.11 + PostgreSQL (AWS RDS)
- Auth: JWT via `python-jose`, role-based (`admin` / `student`)
- Migrations: Alembic 1.15

## Commands
```bash
python main.py                        # run server (prod-style)
uvicorn app.main:app --reload         # run server (dev, hot-reload)
pytest                                # run all tests
alembic upgrade head                  # apply all pending migrations
alembic revision --autogenerate -m "description"  # generate new migration
pip install -r requirements.txt       # install deps
```

## Project Layout
```
app/
  main.py          # FastAPI factory (create_app), CORS, router mounting
  database.py      # engine, SessionLocal, Base
  models.py        # ALL ORM models (40+ tables)
  deps.py          # get_db(), get_current_user() dependencies
  auth/auth.py     # JWT issue/verify, role guards
  core/
    config.py      # settings (env vars)
    startup.py     # startup task orchestration
  routers/         # one file per feature area, all mounted under /v1
    admin/         # admin-only endpoints (ingest, users, sme, fit_bands, compliance, …)
  services/        # business logic (scoring, recommendations, analytics, reports)
  schemas/         # Pydantic schemas (newer ones); legacy schemas_*.py at app root
  utils/           # helpers (normalization, consent tokens, result sanitizer)
  validators/      # validation logic (question ingestion)
alembic/           # migration scripts
scripts/           # one-off/backfill scripts (safe to re-run idempotently)
data/              # CSV seed data
tmp_*.py           # temporary diagnostic scripts at repo root (check before creating new ones)
```

## Key Env Vars (from .env)
```
DATABASE_URL=postgresql+psycopg2://...   # full connection string (takes priority)
POSTGRES_HOST / PORT / DB / USER / PASSWORD  # fallback construction
SKIP_DB_WAIT=1                           # skip DB readiness polling on startup
```

## Router → URL Prefix Map (all under /v1)
| File | Prefix |
|---|---|
| auth/auth.py | /auth |
| routers/admin/* | /admin |
| careers.py | /careers |
| career_clusters.py | /career-clusters |
| skills.py | /skills |
| key_skills.py | /key-skills |
| students.py | /students |
| assessments.py | /assessments |
| recommendations.py | /recommendations |
| analytics.py | /analytics |
| paid_analytics.py | /paid-analytics |
| admin_analytics.py | /admin-analytics |
| student_dashboard.py | /students (additional routes) |
| student_graph_analytics.py | /student-graph-analytics |
| consent.py | /consent |
| reports.py | /reports |
| content.py | /content |
| questions.py / questions_random.py | /questions |

## Core Models (app/models.py)
- **Auth/Identity**: `User`, `Student`, `ContextProfile`
- **Careers**: `Career`, `CareerCluster`, `CareerContent`, `KeySkill`
- **Skills**: `Skill`, `SkillAlias`, `StudentSkillScore`, `SkillKeySkillMap`
- **Assessment**: `Assessment`, `AssessmentQuestion`, `AssessmentResponse`, `AssessmentResult`, `Question`, `QuestionTranslation`
- **AQ/Facets**: `AssociatedQuality`, `AQFacet`, `QuestionFacetTag`, `FacetTranslation`
- **Mappings**: `career_keyskill_association`, `CareerAQWeight`, `AQStudentSkillWeight`, `QuestionStudentSkillWeight`
- **SME**: `SMEProfile`, `SMESubmissionToken`, `SMEAQRating`, `SMEKeySkillRating`
- **Analytics**: `StudentAnalyticsSummary`, `FitBandConfig`
- **Compliance/Audit**: `ConsentLog`, `InterestInventoryResponse`
- **i18n**: `Language`, `ExplainabilityContent`, `ExplanationTranslation`

## Coding Rules
- All new endpoints need Pydantic schemas and type hints.
- **Never modify DB schema without a corresponding Alembic migration.**
- Schema changes must be additive/backward-compatible (no breaking column renames/drops without migration).
- Check `tmp_*.py` at repo root before creating new diagnostic scripts; clean them up when done.
- CORS origins: `localhost:5173` (dev), `mapyourcareer.in` (prod).
- Scoring outputs: HSI (Holistic Skill Index, capped at 100) and CPS (Career Potential Score).
- Assessments are version-pinned at submission time for auditability — never mutate a submitted assessment.
- `get_db()` from `app/deps.py` is the standard session dependency for all routers.
