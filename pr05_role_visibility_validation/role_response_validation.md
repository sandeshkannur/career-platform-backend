
Confirmed finding for scorecard endpoint:
- Route tested: GET /v1/analytics/scorecard/{student_id}
- Caller role: student
- Own student_id=2 -> 500 Internal Server Error
- Other student_id=3 -> 403 Forbidden

Interpretation:
- Ownership enforcement works correctly for cross-student access.
- Self-access path is broken due to backend/schema mismatch.
- This is not yet a role-visibility leak; it is an implementation defect on a valid student path.

Backend log root cause:
- scorecard.py calls services.scoring.get_student_keyskill_scores(...)
- query expects column: student_keyskill_map.score
- live production DB error:
  psycopg2.errors.UndefinedColumn: column student_keyskill_map.score does not exist

PR-05 classification for this finding:
- PASS on authorization boundary
- FAIL on self-access functional path
- No schema change should be made yet under PR-05
- This should be documented and routed as a backend gap / schema-alignment defect for later corrective PR

Confirmed finding for assessment history endpoint:
- Route tested: GET /v1/students/{student_id}/assessments
- Caller role: student
- Own student_id=2 -> 200 OK
- Other student_id=3 -> 403 with message:
  Not authorized to access this student's assessments

Interpretation:
- Ownership enforcement works correctly.
- Valid self-access works correctly.
- No role-visibility leakage observed on this endpoint.
- Endpoint is behaving in line with PR-05 expectations for student-safe access.

PR-05 classification for this finding:
- PASS on authorization boundary
- PASS on self-access functional path
- No backend change indicated from this endpoint

Confirmed finding for results history endpoint:
- Route tested: GET /v1/students/{student_id}/results
- Caller role: student
- Own student_id=2 -> 200 OK
- Returned payload summary:
  - student_id = 2
  - total_results = 0
  - message = No stored or computed results found yet.
- Other student_id=3 -> 403 with message:
  Not authorized to access this student's results

Interpretation:
- Ownership enforcement works correctly.
- Valid self-access works correctly even when no stored results exist.
- No role-visibility leakage observed on this endpoint.
- Empty-state response is handled safely for student role.

PR-05 classification for this finding:
- PASS on authorization boundary
- PASS on self-access functional path
- No backend change indicated from this endpoint

Confirmed finding for dashboard endpoint:
- Route tested: GET /v1/students/{student_id}/dashboard
- Caller role: student
- Own student_id=2 -> 500 Internal Server Error
- Other student_id=3 -> 403 with message:
  Not authorized to access this student's dashboard

Interpretation:
- Ownership enforcement works correctly for cross-student access.
- Self-access path is broken on dashboard endpoint.
- This is not yet evidence of role-visibility leakage; it is a functional defect on a valid student path.
- Earlier assessment-history response showed student_id=2 has assessment records, so this failure is unlikely to be caused simply by no assessments existing.

PR-05 classification for this finding:
- PASS on authorization boundary
- FAIL on self-access functional path
- Backend log inspection required to identify root cause

Backend log root cause for dashboard endpoint:
- student_dashboard.py queries student_analytics_summary
- live production DB error:
  psycopg2.errors.UndefinedTable: relation "student_analytics_summary" does not exist

PR-05 interpretation update:
- Dashboard cross-student authorization works.
- Dashboard self-access is broken due to missing live DB object dependency.
- This is a production schema/code alignment defect, not a visibility-leak defect.
- No direct schema or API change should be made under PR-05; this should be routed to a corrective backend/schema-alignment PR.

Confirmed finding for recommendations endpoint:
- Route tested: GET /v1/recommendations/{student_id}
- Caller role: student
- Own student_id=2 -> controlled error response:
  No keyskills found for this student
- Other student_id=3 -> forbidden with message:
  Operation forbidden

Interpretation:
- Ownership enforcement works correctly for cross-student access.
- Self-access does not leak data and does not crash; it returns a controlled business/data-state response.
- This suggests recommendation authorization behavior is functioning correctly for student role.
- Follow-up on missing keyskills belongs to data/scoring completeness validation, not PR-05 visibility redesign.

PR-05 classification for this finding:
- PASS on authorization boundary
- PASS on controlled self-access behavior
- No role-visibility leakage observed
- No backend change indicated under PR-05 for visibility control

Confirmed provisional finding for student-safe paid analytics endpoint:
- Route tested: GET /v1/paid-analytics/{student_id}/student
- Caller role: student
- Own student_id=2 -> 500 Internal Server Error
- Other student_id=3 -> 500 Internal Server Error

Interpretation:
- Authorization conclusion cannot yet be finalized because both self-access and cross-student access failed before a clean allow/deny outcome was observed.
- This suggests a backend functional defect occurs before or during route processing.
- Backend log inspection is required before classifying visibility control behavior.

PR-05 classification for this finding:
- Authorization status: inconclusive pending traceback
- Self-access functional path: FAIL
- Cross-student behavior: inconclusive

Backend log root cause for student-safe paid analytics endpoint:
- paid_analytics.py calls services.scoring.get_student_keyskill_scores(...)
- query expects column: student_keyskill_map.score
- live production DB error:
  psycopg2.errors.UndefinedColumn: column student_keyskill_map.score does not exist

PR-05 interpretation update:
- Student-safe paid analytics route is currently blocked by backend/schema mismatch.
- Because both own-student and cross-student requests fail at the same broken dependency, authorization behavior cannot be conclusively validated from runtime response alone.
- This is a functional/schema-alignment defect, not evidence of a role-visibility leak.
- No schema/API change should be made under PR-05; this should be routed to a corrective backend/schema-alignment PR.

Confirmed finding for reports endpoint:
- Route tested: GET /v1/reports/{student_id}
- Caller role: student
- Own student_id=2 -> 500 Internal Server Error
- Other student_id=3 -> 403 with message:
  Not authorized to access this student's report

Interpretation:
- Ownership enforcement works correctly for cross-student access.
- Self-access path is broken on reports endpoint.
- This is not yet evidence of role-visibility leakage; it is a functional defect on a valid student path.

PR-05 classification for this finding:
- PASS on authorization boundary
- FAIL on self-access functional path
- Backend log inspection required to identify root cause

Backend log root cause for reports endpoint:
- reports.py queries student_analytics_summary
- live production DB error:
  psycopg2.errors.UndefinedTable: relation "student_analytics_summary" does not exist

PR-05 interpretation update:
- Reports cross-student authorization works.
- Reports self-access is broken due to missing live DB object dependency.
- This is a production schema/code alignment defect, not a visibility-leak defect.
- No direct schema or API change should be made under PR-05; this should be routed to a corrective backend/schema-alignment PR.

==================================================
PR-05 INTERIM CONCLUSION
==================================================

Validation scope completed so far:
- Student-role runtime validation executed against selected in-scope endpoints using a live student token and both own-student and cross-student IDs.

Summary of observed behavior:
1. Authorization / ownership enforcement
- Cross-student access blocking is working on the endpoints successfully exercised to an authorization outcome.
- Confirmed 403 / forbidden-style behavior was observed for:
  - /v1/analytics/scorecard/{student_id}
  - /v1/students/{student_id}/assessments
  - /v1/students/{student_id}/results
  - /v1/students/{student_id}/dashboard
  - /v1/recommendations/{student_id}
  - /v1/reports/{student_id}

2. Valid student self-access behavior
- PASS:
  - /v1/students/{student_id}/assessments
  - /v1/students/{student_id}/results
  - /v1/recommendations/{student_id} returned a controlled business/data-state response rather than leaking data or crashing
- FAIL:
  - /v1/analytics/scorecard/{student_id}
  - /v1/students/{student_id}/dashboard
  - /v1/paid-analytics/{student_id}/student
  - /v1/reports/{student_id}

3. Nature of failures observed
- The failing self-access paths do not currently indicate role-visibility leakage.
- They indicate backend/live-schema misalignment:
  - Missing column: student_keyskill_map.score
  - Missing table: student_analytics_summary

4. PR-05 visibility conclusion at this stage
- No evidence has been found so far that student users are being overexposed to privileged/admin-only response content.
- The larger current risk is functional breakage on valid student self-access routes caused by backend expectations that do not match live production schema objects.

5. Production-safety conclusion
- PR-05 should remain validation-only.
- No schema or API change should be made directly under PR-05.
- The confirmed runtime defects should be routed into a later corrective PR focused on schema/code alignment and safe remediation.

6. Remaining gap
- Privileged-route validation is still pending because a working admin login has not yet been completed for runtime testing.
- Therefore PR-05 is not fully closed yet, but the student-tier validation evidence is already substantial.
