-- PR-08 corrected explainability validation queries
-- Uses actual view columns: question_code, facet_code, aq_code, assessment_version

SELECT table_schema, table_name, table_type
FROM information_schema.tables
WHERE table_name IN (
    'associated_qualities_v',
    'aq_facets_v',
    'question_facet_tags_v',
    'questions'
)
ORDER BY table_name;

SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name IN (
    'associated_qualities_v',
    'aq_facets_v',
    'question_facet_tags_v',
    'questions'
)
ORDER BY table_name, ordinal_position;

SELECT 'associated_qualities_v' AS object_name, COUNT(*) AS row_count FROM associated_qualities_v
UNION ALL
SELECT 'aq_facets_v', COUNT(*) FROM aq_facets_v
UNION ALL
SELECT 'question_facet_tags_v', COUNT(*) FROM question_facet_tags_v
UNION ALL
SELECT 'questions', COUNT(*) FROM questions;

SELECT COUNT(*) AS questions_without_facet_mapping
FROM questions q
LEFT JOIN question_facet_tags_v qft
  ON q.assessment_version = qft.assessment_version
 AND q.question_code = qft.question_code
WHERE qft.question_code IS NULL;

SELECT qft.*
FROM question_facet_tags_v qft
LEFT JOIN questions q
  ON q.assessment_version = qft.assessment_version
 AND q.question_code = qft.question_code
WHERE q.question_code IS NULL
LIMIT 100;

SELECT qft.*
FROM question_facet_tags_v qft
LEFT JOIN aq_facets_v af
  ON qft.assessment_version = af.assessment_version
 AND qft.facet_code = af.facet_code
WHERE af.facet_code IS NULL
LIMIT 100;

SELECT af.*
FROM aq_facets_v af
LEFT JOIN associated_qualities_v aq
  ON af.assessment_version = aq.assessment_version
 AND af.aq_code = aq.aq_code
WHERE aq.aq_code IS NULL
LIMIT 100;

SELECT assessment_version, question_code, facet_code, COUNT(*) AS duplicate_count
FROM question_facet_tags_v
GROUP BY assessment_version, question_code, facet_code
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC, assessment_version, question_code, facet_code;

SELECT
    q.assessment_version,
    q.question_code,
    qft.facet_code,
    af.aq_code,
    af.name_en AS facet_name_en,
    aq.name_en AS aq_name_en
FROM questions q
LEFT JOIN question_facet_tags_v qft
  ON q.assessment_version = qft.assessment_version
 AND q.question_code = qft.question_code
LEFT JOIN aq_facets_v af
  ON qft.assessment_version = af.assessment_version
 AND qft.facet_code = af.facet_code
LEFT JOIN associated_qualities_v aq
  ON af.assessment_version = aq.assessment_version
 AND af.aq_code = aq.aq_code
ORDER BY q.question_code
LIMIT 50;

SELECT
    COUNT(*) AS total_questions,
    COUNT(qft.question_code) AS mapped_questions,
    COUNT(af.facet_code) AS mapped_facets,
    COUNT(aq.aq_code) AS mapped_aqs
FROM questions q
LEFT JOIN question_facet_tags_v qft
  ON q.assessment_version = qft.assessment_version
 AND q.question_code = qft.question_code
LEFT JOIN aq_facets_v af
  ON qft.assessment_version = af.assessment_version
 AND qft.facet_code = af.facet_code
LEFT JOIN associated_qualities_v aq
  ON af.assessment_version = aq.assessment_version
 AND af.aq_code = aq.aq_code;
