from services.context_builder import get_semester_summaries, get_student_courses, get_student_grades


class FakeCursor:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.query = ""
        self.params = ()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, query, params):
        self.query = query
        self.params = params

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows=None):
        self.fake_cursor = FakeCursor(rows)

    def cursor(self):
        return self.fake_cursor


def test_grades_filter_by_semester_and_academic_year():
    conn = FakeConnection()

    get_student_grades(conn, student_id=42, semester="2", academic_year="2024-2025")

    assert "r.semester = %s" in conn.fake_cursor.query
    assert "r.academic_year = %s" in conn.fake_cursor.query
    assert conn.fake_cursor.params == [42, "2", "2024-2025"]


def test_courses_filter_by_semester_and_academic_year():
    conn = FakeConnection()
    student = {"level": "2", "field_of_study": "Accounting", "status": "Day"}

    get_student_courses(conn, student, semester="1", academic_year="2024-2025")

    assert "sub.semester = %s" in conn.fake_cursor.query
    assert "sub.academic_year = %s" in conn.fake_cursor.query
    assert conn.fake_cursor.params == ["2", "Accounting", "Day", "1", "2024-2025"]


def test_semester_average_is_coefficient_weighted():
    conn = FakeConnection([
        {
            "subject_name": "Accounting", "subject_code": "ACC1", "coefficient": 2,
            "continuous_score": 20, "exam_score": 30, "retake_score": None,
            "is_retake_passed": 0, "semester": "1", "academic_year": "2024-2025",
        },
        {
            "subject_name": "Management", "subject_code": "MGT1", "coefficient": 1,
            "continuous_score": 30, "exam_score": 50, "retake_score": None,
            "is_retake_passed": 0, "semester": "1", "academic_year": "2024-2025",
        },
    ])

    summaries = get_semester_summaries(conn, student_id=42, academic_year="2024-2025")

    assert summaries == [{
        "academic_year": "2024-2025",
        "semester": "1",
        "subjects_graded": 2,
        "average": 60.0,
        "validated": True,
    }]
