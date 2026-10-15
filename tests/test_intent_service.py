from services.intent_service import classify


def test_courses_extract_semester_and_academic_year():
    intent = classify("Quelles sont mes matières du semestre 2 pour l'année 2024/2025 ?")

    assert intent.name == "courses"
    assert intent.entities == {"semester": "2", "academic_year": "2024-2025"}


def test_semester_alone_is_not_misclassified_as_validation():
    intent = classify("Donne-moi mes matières du semestre 1")

    assert intent.name == "courses"
    assert intent.entities["semester"] == "1"


def test_grades_extract_period_and_year():
    intent = classify("Liste mes notes du semestre 1 de l'année 2023-2024")

    assert intent.name == "grades"
    assert intent.entities == {"semester": "1", "academic_year": "2023-2024"}


def test_average_and_unvalidated_subjects_have_distinct_intents():
    assert classify("Quelle est ma moyenne du semestre 2").name == "semester_average"
    assert classify("Quelles sont les matières à rattraper ?").name == "failed_courses"
    assert classify("Ai-je validé le semestre 1 ?").name == "semester_validation"
    assert classify("Combien d'enseignants travaille à l'institut ?").name == "institution_stats"


def test_teacher_questions_capture_course_or_return_all_teachers():
    course_teacher = classify("Qui enseigne la matière comptabilité ?")
    all_teachers = classify("Qui sont mes enseignants ?")
    teacher_courses = classify("Quelles matières enseigne le professeur Jean Dupont ?")

    assert course_teacher.name == "teacher_lookup"
    assert course_teacher.entities["teacher_fragment"] == "comptabilité"
    assert all_teachers.name == "teacher_lookup"
    assert all_teachers.entities["teacher_fragment"] == ""
    assert teacher_courses.name == "teacher_lookup"
    assert teacher_courses.entities["teacher_fragment"] == "Jean Dupont"
