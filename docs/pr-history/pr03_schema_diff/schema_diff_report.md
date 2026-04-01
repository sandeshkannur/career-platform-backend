\# PR-03 Schema Diff Report



\## 1. Objective



Validate schema alignment between:



Production database (PR-01 baseline snapshot)



and



Local repository SQLAlchemy models (PR-02 baseline snapshot)



The purpose is to detect potential schema drift before introducing any new backend features.



This PR performs analysis only.  

No schema changes, migrations, or code modifications are introduced.



\---



\## 2. Inputs Used



\### Production Baseline (PR-01)



\- live\_tables\_inventory.txt

\- live\_columns\_inventory.txt

\- live\_constraints\_inventory.txt

\- live\_indexes\_inventory.txt

\- alembic\_current.txt

\- alembic\_history.txt

\- alembic\_versions\_files.txt



\### Local Repository Baseline (PR-02)



\- pr02\_models\_inventory.txt

\- pr02\_routers\_inventory.txt

\- pr02\_local\_backend\_baseline\_summary.txt

\- pr02\_local\_vs\_pr01\_production\_comparison.txt



\---



\## 3. Production Migration State



Alembic current revision:



ec55ebc40479 (head)



Migration history inspected from:



\- alembic\_current.txt

\- alembic\_history.txt

\- alembic\_versions\_files.txt



Conclusion:



Production database snapshot was captured at Alembic head revision `ec55ebc40479`, indicating the live production schema was aligned with the deployed migration state at the time of PR-01 capture.



Migration history shows a continuous forward chain from the assessment baseline through later additions such as:

\- career key skill weighting

\- student/context support

\- consent logging

\- skill aliases

\- assessment response hardening

\- versioned assessment / knowledge pack support



At this stage, there is no evidence of production being behind its own migration chain.





\## 4. Table Presence Comparison



\### Tables Found in Production

public.alembic\_version

public.aq\_facets

public.aq\_facets\_v

public.assessment\_questions

public.assessment\_responses

public.assessment\_results

public.assessments

public.associated\_qualities\_v

public.career\_clusters

public.career\_keyskill\_association

public.careers

public.consent\_logs

public.context\_profile

public.explanation\_translations

public.facet\_translations

public.keyskills

public.languages

public.question\_facet\_tags\_v

public.question\_translations

public.questions

public.skill\_aliases

public.skills

public.student\_keyskill\_map

public.student\_skill\_map

public.student\_skill\_scores

public.students

public.users



\### Tables Found in Local Models



users  

students  

context\_profile  

skills  

skill\_aliases  

student\_skill\_map  

career\_clusters  

career\_keyskill\_association  

careers  

keyskills  

student\_keyskill\_map  

skill\_keyskill\_map  

languages  

question\_translations  

facet\_translations  

explanation\_translations  

questions  

assessment\_questions  

assessments  

assessment\_responses  

assessment\_results  

student\_skill\_scores  

student\_analytics\_summary  

consent\_logs  

associated\_qualities  

aq\_facets  

question\_facet\_tags  

question\_student\_skill\_weights  

explainability\_content  



\### Initial Observations



Production contains several tables/views that appear with `\_v` suffixes, while local models currently list some corresponding base names without `\_v`.



Likely naming or structure comparison candidates requiring validation:

\- associated\_qualities\_v (production) vs associated\_qualities (local)

\- aq\_facets\_v (production) vs aq\_facets (local)

\- question\_facet\_tags\_v (production) vs question\_facet\_tags (local)



Confirmed as present in local models but not found in production baseline artifacts (table/column/constraint snapshot):

\- skill\_keyskill\_map

\- question\_student\_skill\_weights

\- student\_analytics\_summary

\- explainability\_content



Present in production baseline but not represented as local business models:

\- alembic\_version



Interpretation note:

The above does not automatically indicate a defect in production. These may be:

\- future/local-only models not yet deployed

\- intentionally deferred schema

\- model definitions without deployed migration

\- alternative production implementation paths



Additional naming/structure findings from production column snapshot:



\- `associated\_qualities\_v` is present in production with full versioned structure including:

&#x20; `id, assessment\_version, aq\_code, name\_en, name\_hi, name\_ta, status, created\_at, updated\_at`



\- `question\_facet\_tags\_v` is present in production with full versioned structure including:

&#x20; `id, assessment\_version, question\_code, facet\_code, tag\_weight, created\_at, updated\_at`



\- `aq\_facets\_v` is present in production with full versioned structure including:

&#x20; `id, assessment\_version, facet\_code, aq\_code, name\_en, name\_hi, name\_ta, description\_en, description\_hi, description\_ta, status, created\_at, updated\_at`



\- Production snapshot also shows a separate `aq\_facets` presence, but only `facet\_id` was observed in the column inventory excerpt. This requires additional validation before drawing conclusions about whether `aq\_facets` is a separate legacy/base table, a partial object, or an artifact of the snapshot.



Interpretation:

Production appears to use versioned explainability knowledge-pack tables with `\_v` suffixes. Local models currently list some corresponding non-`\_v` names, which suggests a likely naming/model drift or an older/newer representation in local code.



Further production constraint validation confirms:



\- `aq\_facets` exists in production as a real constrained object with primary key `facet\_id`

\- `facet\_translations.facet\_id` references `aq\_facets.facet\_id`

\- `aq\_facets\_v` also exists in production as a separate versioned object with:

&#x20; - primary key on `id`

&#x20; - unique constraint on `(assessment\_version, facet\_code)`

&#x20; - foreign key relationship back to `associated\_qualities\_v`

\- `question\_facet\_tags\_v` references `aq\_facets\_v`



Interpretation:

Production currently contains both a base explainability structure (`aq\_facets`) and a versioned explainability structure (`aq\_facets\_v`). This suggests coexistence of legacy/base and versioned knowledge-pack schema rather than a simple naming mismatch.







\## 5. Critical Scoring Tables Validation



The intended scoring path is:



Question → Student Skill → KeySkill → Career → Career Cluster



Production table inventory confirms the following scoring-chain tables are present:



\- questions

\- skills

\- keyskills

\- student\_skill\_map

\- student\_keyskill\_map

\- student\_skill\_scores

\- careers

\- career\_clusters

\- career\_keyskill\_association



Production table inventory does not show the following local-model tables:



\- skill\_keyskill\_map

\- question\_student\_skill\_weights

\- student\_analytics\_summary

\- explainability\_content



Observations:



\- The downstream scoring/output tables and core career-mapping tables are present in production.

\- The local repository defines additional scoring-support / analytics-support tables that are not present in the production baseline snapshot.

\- Based on current evidence, production appears to implement the scoring pipeline using:



question → student\_skill\_map → student\_keyskill\_map → career\_keyskill\_association → careers → career\_clusters



while the local repository models define additional intermediate support tables (`skill\_keyskill\_map`, `question\_student\_skill\_weights`) that would enable a more explicit scoring graph.



PR-03 does not modify this behavior and records the difference as schema drift for future evaluation.



Status:



NEEDS\_VALIDATION



Reason:



The production baseline supports much of the core assessment and recommendation structure, but some local-model support tables required for a fuller explicit pipeline are not deployed in the production schema snapshot.



Migration cross-check:



A search of `alembic\_versions\_files.txt` did not show references to:

\- `skill\_keyskill\_map`

\- `question\_student\_skill\_weights`

\- `student\_analytics\_summary`

\- `explainability\_content`



Interpretation:

These objects appear to be present in the local model inventory but are not evidenced in the deployed production migration snapshot. This suggests local schema/model definitions may be ahead of deployed production rather than production being out of sync with its own migration chain.







\## 6. Constraint and Index Observations



Constraint and index snapshots were analyzed using:



\- live\_constraints\_inventory.txt

\- live\_indexes\_inventory.txt



Findings:



\- Core scoring chain tables (skills, keyskills, student\_skill\_map, student\_keyskill\_map, careers, career\_clusters, career\_keyskill\_association) contain expected primary key and foreign key relationships.

\- Explainability versioned tables (`associated\_qualities\_v`, `aq\_facets\_v`, `question\_facet\_tags\_v`) include appropriate foreign key relationships enforcing version alignment through `assessment\_version`.

\- The base table `aq\_facets` remains referenced by `facet\_translations`, indicating coexistence of legacy/base and versioned explainability schema.

\- No unexpected constraint anomalies were observed in the production snapshot.



Conclusion:



Production constraints and indexes appear internally consistent with the deployed schema and migration history.

This report should be treated as the authoritative schema comparison baseline for all subsequent backend PRs starting with PR-04.



\## 7. Schema Drift Classification



Possible categories:



MATCHED  

MISSING\_IN\_PRODUCTION  

MISSING\_IN\_LOCAL  

COLUMN\_DRIFT  

CONSTRAINT\_DRIFT  

INDEX\_DRIFT  

NEEDS\_VALIDATION  



Result:



\- MATCHED:

&#x20; - questions

&#x20; - skills

&#x20; - keyskills

&#x20; - student\_skill\_map

&#x20; - student\_keyskill\_map

&#x20; - student\_skill\_scores

&#x20; - careers

&#x20; - career\_clusters

&#x20; - career\_keyskill\_association

&#x20; - assessments

&#x20; - assessment\_questions

&#x20; - assessment\_responses

&#x20; - assessment\_results

&#x20; - consent\_logs

&#x20; - question\_translations

&#x20; - facet\_translations

&#x20; - explanation\_translations

&#x20; - skill\_aliases

&#x20; - students

&#x20; - users

&#x20; - context\_profile

&#x20; - languages



\- MISSING\_IN\_PRODUCTION (based on PR-01 baseline artifacts):

&#x20; - skill\_keyskill\_map

&#x20; - question\_student\_skill\_weights

&#x20; - student\_analytics\_summary

&#x20; - explainability\_content



\- NAMING / STRUCTURE DRIFT REQUIRING VALIDATION:

&#x20; - associated\_qualities\_v (production) vs associated\_qualities (local)

&#x20; - question\_facet\_tags\_v (production) vs question\_facet\_tags (local)

&#x20; - aq\_facets and aq\_facets\_v both exist in production, while local inventory lists aq\_facets only



\- EXPECTED PRODUCTION-ONLY TECHNICAL TABLE:

&#x20; - alembic\_version



Overall classification:



NEEDS\_VALIDATION





\## 8. Risk Assessment



Risk level: Medium



Reasoning:



\- Production appears internally consistent with its deployed Alembic head.

\- Core assessment and recommendation tables are present in production.

\- However, several local-model support tables for a fuller explicit scoring / explainability pipeline are not present in the production schema snapshot.

\- This introduces risk if future PRs assume those local-model tables already exist in production.

\- There is no evidence in PR-03 that production is broken today.

\- The primary risk is incorrect assumptions in future implementation work, not immediate runtime instability in the current deployed environment.





\## 9. Recommended Action



PR-03 is an analysis step.



Recommended next step:



\- Do not make schema changes as part of PR-03.

\- Treat PR-03 as a drift-detection and safety documentation PR only.

\- Use this report to inform the next additive PR.

\- Any future introduction of `skill\_keyskill\_map`, `question\_student\_skill\_weights`, `student\_analytics\_summary`, or `explainability\_content` into production must be handled through a separate additive migration PR with rollback and validation checks.

\- Future scoring logic PRs must not assume those tables already exist in production.





\## 10. Conclusion



PR-03 comparison shows that production is aligned with its deployed migration head and already contains the core assessment, student, skill, career, and recommendation-related schema required for the currently deployed platform.



At the same time, the local repository model inventory includes additional support tables that are not present in the PR-01 production schema baseline and are not evidenced in the deployed migration inventory.



Therefore:



\- production should be treated as internally consistent

\- local code should be treated as potentially ahead of deployed schema in selected areas

\- no schema change is justified inside PR-03

\- any future schema rollout must be handled as a separate additive PR



Final decision:



PR-03 completed as analysis-only schema drift validation. No direct production or local schema change should be made in this PR.

