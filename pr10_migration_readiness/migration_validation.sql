-- PR-10 Migration Readiness Validation
-- Purpose:
-- Validate whether PR-09 tables already exist physically,
-- inspect their structure, and compare with Alembic version state.
-- Read-only only. No schema changes.

\echo '=================================================='
\echo 'PR-10 :: ALEMBIC VERSION'
\echo '=================================================='
SELECT * FROM alembic_version;

\echo '=================================================='
\echo 'PR-10 :: TARGET TABLE EXISTENCE'
\echo '=================================================='
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
    'question_student_skill_weights',
    'skill_keyskill_map'
  )
ORDER BY table_name;

\echo '=================================================='
\echo 'PR-10 :: TARGET TABLE COLUMNS'
\echo '=================================================='
SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN (
    'question_student_skill_weights',
    'skill_keyskill_map'
  )
ORDER BY table_name, ordinal_position;

\echo '=================================================='
\echo 'PR-10 :: TARGET TABLE CONSTRAINTS'
\echo '=================================================='
SELECT
    tc.table_name,
    tc.constraint_name,
    tc.constraint_type
FROM information_schema.table_constraints tc
WHERE tc.table_schema = 'public'
  AND tc.table_name IN (
    'question_student_skill_weights',
    'skill_keyskill_map'
  )
ORDER BY tc.table_name, tc.constraint_type, tc.constraint_name;

\echo '=================================================='
\echo 'PR-10 :: TARGET FK DETAILS'
\echo '=================================================='
SELECT
    tc.table_name,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name,
    tc.constraint_name
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
    ON tc.constraint_name = kcu.constraint_name
   AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage AS ccu
    ON ccu.constraint_name = tc.constraint_name
   AND ccu.table_schema = tc.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_schema = 'public'
  AND tc.table_name IN (
    'question_student_skill_weights',
    'skill_keyskill_map'
  )
ORDER BY tc.table_name, kcu.column_name;

\echo '=================================================='
\echo 'PR-10 :: TARGET INDEXES'
\echo '=================================================='
SELECT
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN (
    'question_student_skill_weights',
    'skill_keyskill_map'
  )
ORDER BY tablename, indexname;

\echo '=================================================='
\echo 'PR-10 :: REFERENCE TABLE EXISTENCE'
\echo '=================================================='
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
    'questions',
    'skills',
    'keyskills'
  )
ORDER BY table_name;

\echo '=================================================='
\echo 'PR-10 :: DUPLICATE UNIQUE INDEX DEEP CHECK'
\echo '=================================================='
SELECT
    c.relname AS index_name,
    i.indisunique AS is_unique,
    pg_get_indexdef(i.indexrelid) AS index_definition,
    con.conname AS attached_constraint_name,
    contype AS constraint_type
FROM pg_index i
JOIN pg_class c
    ON c.oid = i.indexrelid
JOIN pg_class t
    ON t.oid = i.indrelid
JOIN pg_namespace n
    ON n.oid = t.relnamespace
LEFT JOIN pg_constraint con
    ON con.conindid = i.indexrelid
WHERE n.nspname = 'public'
  AND t.relname = 'skill_keyskill_map'
  AND c.relname IN ('uq_skill_keyskill', 'ux_skill_keyskill')
ORDER BY c.relname;