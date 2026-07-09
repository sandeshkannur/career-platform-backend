"""fix mojibake punctuation in explainability_content (en locale, 24 rows)

The original ingestion mangled UTF-8 typographic punctuation into literal
"???" sequences (each ??? is one 3-byte character whose bytes were replaced).
Restores, per surrounding context:
  - possessive/contraction apostrophes -> U+2019 (18 occurrences)
  - word-pair connectors (cause-effect etc.) -> U+2013 en dash (6 occurrences)
  - quotes around "why/how" in AQ01_F2 -> U+201C/U+201D (2 occurrences)

Data-only: no schema change. Idempotent: rows are matched on the exact
corrupted text, so a second run matches nothing. Downgrade restores the exact
corrupted text (recorded verbatim below). kn-locale rows are untouched.

Revision ID: b7c4e9a2d1f8
Revises: c8e2f4a6b9d3
Create Date: 2026-07-09

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b7c4e9a2d1f8"
down_revision = "c8e2f4a6b9d3"
branch_labels = None
depends_on = None

# (explanation_key, corrupted_text, corrected_text) for version=v1, locale=en
FIXES = [
    ('AQ_20',
     'Emotional Insight: Ability to recognize and name one???s own emotions to guide decisions and behavior.',
     'Emotional Insight: Ability to recognize and name one’s own emotions to guide decisions and behavior.'),
    ('AQ_22',
     'Perspective Taking: Ability to consider others??? viewpoints and understand differing perspectives.',
     'Perspective Taking: Ability to consider others’ viewpoints and understand differing perspectives.'),
    ('AQ01_F2',
     'Question-Seeking Habit: Natural tendency to ask ???why/how??? and generate questions when encountering something new.',
     'Question-Seeking Habit: Natural tendency to ask “why/how” and generate questions when encountering something new.'),
    ('AQ02_F2',
     'Logical Structuring: Ability to organise questions logically (step-by-step, cause???effect, sequence).',
     'Logical Structuring: Ability to organise questions logically (step-by-step, cause–effect, sequence).'),
    ('AQ03_F2',
     'Cause???Effect Analysis: Ability to reason about how actions or factors lead to outcomes.',
     'Cause–Effect Analysis: Ability to reason about how actions or factors lead to outcomes.'),
    ('AQ04_F3',
     'Conceptual Flexibility: Ability to shift thinking frameworks when one approach doesn???t work.',
     'Conceptual Flexibility: Ability to shift thinking frameworks when one approach doesn’t work.'),
    ('AQ06_F5',
     'Self-Awareness of Attention: Awareness of one???s own focus levels and attention limits.',
     'Self-Awareness of Attention: Awareness of one’s own focus levels and attention limits.'),
    ('AQ07_F1',
     'Emotional Awareness: Ability to recognise and label one???s own emotions.',
     'Emotional Awareness: Ability to recognise and label one’s own emotions.'),
    ('AQ07_F5',
     'Emotion???Action Alignment: Ability to act thoughtfully despite emotional states.',
     'Emotion–Action Alignment: Ability to act thoughtfully despite emotional states.'),
    ('AQ10_F1',
     'Strength Awareness: Awareness of one???s own strengths or areas of competence.',
     'Strength Awareness: Awareness of one’s own strengths or areas of competence.'),
    ('AQ10_F2',
     'Limitation Awareness: Awareness of one???s own difficulties or areas for improvement.',
     'Limitation Awareness: Awareness of one’s own difficulties or areas for improvement.'),
    ('AQ10_F3',
     'Behaviour???Outcome Insight: Ability to link one???s actions with resulting outcomes.',
     'Behaviour–Outcome Insight: Ability to link one’s actions with resulting outcomes.'),
    ('AQ12_F5',
     'Supportive Responsiveness: Ability to respond helpfully to teammates??? needs or inputs.',
     'Supportive Responsiveness: Ability to respond helpfully to teammates’ needs or inputs.'),
    ('AQ13_F2',
     'Perspective Taking: Ability to understand situations from another person???s point of view.',
     'Perspective Taking: Ability to understand situations from another person’s point of view.'),
    ('AQ13_F4',
     'Impact Awareness: Awareness of how one???s actions or words affect others.',
     'Impact Awareness: Awareness of how one’s actions or words affect others.'),
    ('AQ14_F5',
     'Supportive Leadership: Ability to lead while considering others??? inputs and needs.',
     'Supportive Leadership: Ability to lead while considering others’ inputs and needs.'),
    ('AQ15_F2',
     'Responsibility for Impact: Willingness to take responsibility for the effects of one???s actions.',
     'Responsibility for Impact: Willingness to take responsibility for the effects of one’s actions.'),
    ('AQ15_F3',
     'Integrity in Choices: Tendency to act honestly even when it???s inconvenient.',
     'Integrity in Choices: Tendency to act honestly even when it’s inconvenient.'),
    ('AQ20_F2',
     'Action???Value Consistency: Tendency to act in ways that align with personal values.',
     'Action–Value Consistency: Tendency to act in ways that align with personal values.'),
    ('AQ21_F3',
     'Balanced Risk???Benefit View: Ability to weigh risks against potential benefits.',
     'Balanced Risk–Benefit View: Ability to weigh risks against potential benefits.'),
    ('AQ22_F3',
     'Outcome Accountability: Willingness to acknowledge outcomes linked to one???s actions.',
     'Outcome Accountability: Willingness to acknowledge outcomes linked to one’s actions.'),
    ('AQ23_F3',
     'Judgement Confidence: Confidence in one???s own judgement in everyday situations.',
     'Judgement Confidence: Confidence in one’s own judgement in everyday situations.'),
    ('AQ23_F5',
     'Responsibility for Own Work: Willingness to take responsibility for one???s own work without deflection.',
     'Responsibility for Own Work: Willingness to take responsibility for one’s own work without deflection.'),
    ('AQ25_F1',
     'Self-Exploration Interest: Interest in understanding one???s own interests, strengths, and preferences.',
     'Self-Exploration Interest: Interest in understanding one’s own interests, strengths, and preferences.'),
]


_SQL = sa.text(
    "UPDATE explainability_content "
    "SET text = :new_text "
    "WHERE version = 'v1' AND locale = 'en' "
    "AND explanation_key = :key AND text = :old_text"
)


def upgrade():
    bind = op.get_bind()
    for key, corrupted, corrected in FIXES:
        bind.execute(_SQL, {"key": key, "old_text": corrupted, "new_text": corrected})


def downgrade():
    bind = op.get_bind()
    for key, corrupted, corrected in FIXES:
        bind.execute(_SQL, {"key": key, "old_text": corrected, "new_text": corrupted})
