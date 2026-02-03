# PR16 – CMS-backed explanation copy (using explanation_key)

## Goal
Move all human-readable explanation text out of code and into a CMS-backed store so:
- Explanations can be updated without redeploying
- Student-safe vs counsellor/admin copy can be controlled centrally
- Future exports (PR18) and versioning (PR19) can reference stable keys

## Approach (architecture)
- Introduce an `explanations` table keyed by `explanation_key`
- API exposes read endpoints:
  - Public/student-safe explanation content (role-aware)
  - Admin endpoints for CRUD / bulk upload
- Existing endpoints return `explanation_key` references (not long text blobs)

## Definition of Done
- Table + model + schema created
- Admin can bulk upload explanation records
- Student endpoints return explanation_key references
- Admin/counsellor can fetch resolved explanation text (role-gated)
- No breaking changes to existing analytics payload shapes unless explicitly planned
