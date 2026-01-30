\# PR17 – Role-Based Access Control (RBAC)



\## Goal

Introduce robust, future-proof RBAC to prevent accidental data exposure, preserve PR15 scorecard governance, and make future PRs safe by default.



---



\## Role Model

\- Role stored in DB: `users.role`

\- Roles supported:

&nbsp; - `admin`

&nbsp; - `counsellor`

&nbsp; - `student`

\- Storage is flat; permissions are hierarchical in code.



\### Permissions

\- \*\*Admin\*\*

&nbsp; - Full system control

&nbsp; - Ingestion, validation, role management

\- \*\*Counsellor\*\*

&nbsp; - Read-only access to numeric analytics

&nbsp; - Scorecards, paid analytics

\- \*\*Student\*\*

&nbsp; - Access only to own student-safe views

&nbsp; - No numeric analytics



---



\## What Changed

\- RBAC enforced via JWT role claims

\- Endpoint-level role checks added

\- Ownership checks enforced for students

\- `RoleChange` schema updated to support `counsellor`

\- Backward compatibility preserved (`editor` retained)



---



\## Verification Evidence Pack



\### Admin

\- Admin JWT contains `role=admin` ✅



\### Counsellor Provisioning

\- Admin promoted counsellor via:

&nbsp; - `POST /v1/admin/change-role/6`

\- Counsellor re-login → JWT contains `role=counsellor` ✅



\### Counsellor Access

\- `GET /v1/analytics/scorecard/admin/4` → \*\*200 OK\*\* ✅

\- `GET /v1/paid-analytics/4` → \*\*200 OK\*\* ✅

\- `GET /v1/admin/list-users` → \*\*403 Forbidden\*\* ✅



\### Student Safety (PR15 preserved)

\- Student JWT contains `role=student` ✅

\- Student → own scorecard → \*\*200 OK\*\*

\- Student → other student → \*\*403 Forbidden\*\*

\- Student → admin scorecard → \*\*403 Forbidden\*\*

\- Student-safe payload contains \*\*no numeric analytics\*\*



---



\## Security Guarantees

\- No token → \*\*401 Unauthorized\*\*

\- Wrong role → \*\*403 Forbidden\*\*

\- No silent fallbacks

\- No data leakage



---



\## Outcome

PR17 establishes a secure foundation for:

\- PR16 – CMS-backed explanations

\- PR18 – Reports / exports

\- PR19 – Versioned assessments



PR17 is complete and production-credible.



