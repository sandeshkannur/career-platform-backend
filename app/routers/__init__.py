# Routers package initializer
# Ensures all routers are discoverable by FastAPI

from . import admin
from . import questions
from . import questions_random
from . import students
from . import assessments

# B11: Student assessment history (read-only)
from . import student_assessment_history
