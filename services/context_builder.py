"""
All queries here are parameterised and explicitly select only the columns
they need — passwords and payment secrets are never in a SELECT list in
this file. Every function is scoped by the caller's own id (student_id /
teacher_id) taken from the verified JWT, never from user-supplied text.
"""
from typing import Optional
from services.moderation import strip_sensitive_columns


# ---------------------------------------------------------------------------
# Student-facing
# ---------------------------------------------------------------------------

def get_student_profile(conn, student_id: int) -> Optional[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, student_number, firstname, lastname, level, type,
                      field_of_study, specialty_id, status, academic_year
               FROM students WHERE id = %s""",
            (student_id,),
        )
        row = cur.fetchone()
        return strip_sensitive_columns(row) if row else None


def get_student_grades(conn, student_id: int, semester: Optional[str] = None) -> list[dict]:
    sql = """SELECT sub.subject_name, sub.subject_code, sub.coefficient,
                     r.continuous_score, r.exam_score, r.retake_score,
                     r.is_retake_passed, r.semester, r.academic_year
              FROM results r
              JOIN subjects sub ON r.subject_id = sub.id
              WHERE r.student_id = %s"""
    params = [student_id]
    if semester:
        sql += " AND r.semester = %s"
        params.append(semester)
    sql += " ORDER BY r.academic_year DESC, r.semester, sub.subject_name"

    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    graded = []
    for r in rows:
        exam = r["retake_score"] if r["is_retake_passed"] and r["retake_score"] is not None else r["exam_score"]
        total = None
        if r["continuous_score"] is not None and exam is not None:
            total = float(r["continuous_score"]) + float(exam)
        graded.append({
            "subject": r["subject_name"],
            "code": r["subject_code"],
            "coefficient": r["coefficient"],
            "continuous_score": r["continuous_score"],
            "exam_score": exam,
            "retaken": bool(r["is_retake_passed"]),
            "total_on_100": total,
            "passed": (total is not None and total >= 50),
            "semester": r["semester"],
            "academic_year": r["academic_year"],
        })
    return graded


def get_semester_validation(conn, student_id: int, semester: str, academic_year: str) -> dict:
    grades = get_student_grades(conn, student_id, semester=semester)
    grades = [g for g in grades if g["academic_year"] == academic_year]
    weighted_sum, coef_sum = 0.0, 0
    for g in grades:
        if g["total_on_100"] is not None:
            weighted_sum += g["total_on_100"] * g["coefficient"]
            coef_sum += g["coefficient"]
    average = round(weighted_sum / coef_sum, 2) if coef_sum else None
    return {
        "semester": semester,
        "academic_year": academic_year,
        "subjects_graded": len(grades),
        "average": average,
        "validated": (average is not None and average >= 50),
    }


def get_student_courses(conn, student: dict) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT sub.subject_name, sub.subject_code, sub.coefficient, sub.semester,
                      t.firstname AS teacher_firstname, t.lastname AS teacher_lastname
               FROM subjects sub
               LEFT JOIN teachers t ON sub.teacher_id = t.id
               WHERE sub.level = %s AND sub.field_of_study = %s
                 AND sub.status = %s AND sub.academic_year = %s
               ORDER BY sub.semester, sub.subject_name""",
            (student["level"], student["field_of_study"], student["status"], student["academic_year"]),
        )
        return cur.fetchall()


def get_teacher_for_subject(conn, student: dict, subject_name_fragment: str) -> Optional[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT sub.subject_name, t.firstname, t.lastname, t.title, t.grade
               FROM subjects sub
               JOIN teachers t ON sub.teacher_id = t.id
               WHERE sub.level = %s AND sub.field_of_study = %s
                 AND sub.status = %s AND sub.academic_year = %s
                 AND sub.subject_name LIKE %s
               LIMIT 1""",
            (student["level"], student["field_of_study"], student["status"],
             student["academic_year"], f"%{subject_name_fragment}%"),
        )
        return cur.fetchone()


def get_payment_summary(conn, student: dict) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT tf.registration_fee, tf.tuition_total
               FROM tuition_fees tf
               JOIN specialties sp ON sp.field_id = tf.field_id
               WHERE sp.id = %s AND tf.degree_type = %s AND tf.academic_year = %s
               LIMIT 1""",
            (student.get("specialty_id"), student["type"], student["academic_year"]),
        )
        fees = cur.fetchone() or {"registration_fee": 0, "tuition_total": 0}

        cur.execute(
            """SELECT payment_type, COALESCE(SUM(amount), 0) AS paid
               FROM student_payments
               WHERE student_id = %s AND academic_year = %s
               GROUP BY payment_type""",
            (student["id"], student["academic_year"]),
        )
        paid = {r["payment_type"]: float(r["paid"]) for r in cur.fetchall()}

    registration_fee = float(fees["registration_fee"] or 0)
    tuition_total = float(fees["tuition_total"] or 0)
    registration_paid = paid.get("registration", 0.0)
    tuition_paid = paid.get("tuition", 0.0)

    return {
        "academic_year": student["academic_year"],
        "registration_fee": registration_fee,
        "registration_paid": registration_paid,
        "registration_balance": max(registration_fee - registration_paid, 0.0),
        "tuition_total": tuition_total,
        "tuition_paid": tuition_paid,
        "tuition_balance": max(tuition_total - tuition_paid, 0.0),
        "total_balance": max((registration_fee + tuition_total) - (registration_paid + tuition_paid), 0.0),
    }


def get_notifications(conn, student_id: int, limit: int = 5) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT message, created_at, is_read FROM student_notifications
               WHERE student_id = %s ORDER BY created_at DESC LIMIT %s""",
            (student_id, limit),
        )
        return cur.fetchall()


# ---------------------------------------------------------------------------
# Teacher-facing
# ---------------------------------------------------------------------------

def get_teacher_profile(conn, teacher_id: int) -> Optional[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, firstname, lastname, title, grade, email, phone, specialty_id
               FROM teachers WHERE id = %s""",
            (teacher_id,),
        )
        row = cur.fetchone()
        return strip_sensitive_columns(row) if row else None


def get_teacher_subjects(conn, teacher_id: int, academic_year: Optional[str] = None) -> list[dict]:
    sql = """SELECT s.subject_name, s.subject_code, s.level, s.field_of_study,
                     s.status, s.academic_year
              FROM teacher_subject ts
              JOIN subjects s ON ts.subject_id = s.id
              WHERE ts.teacher_id = %s"""
    params = [teacher_id]
    if academic_year:
        sql += " AND ts.academic_year = %s"
        params.append(academic_year)
    sql += " ORDER BY s.academic_year DESC, s.subject_name"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def get_teacher_monthly_hours(conn, teacher_id: int, month: int, academic_year: str) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT session_date, start_time, end_time FROM course_sessions
               WHERE teacher_id = %s AND academic_year = %s AND MONTH(session_date) = %s
               ORDER BY session_date""",
            (teacher_id, academic_year, month),
        )
        rows = cur.fetchall()

    total_seconds = 0
    for r in rows:
        sh, sm, ss = [int(x) for x in str(r["start_time"]).split(":")]
        eh, em, es = [int(x) for x in str(r["end_time"]).split(":")]
        total_seconds += (eh * 3600 + em * 60 + es) - (sh * 3600 + sm * 60 + ss)

    return {
        "sessions_count": len(rows),
        "total_hours": round(total_seconds / 3600, 2),
    }


# ---------------------------------------------------------------------------
# Shared (admin, teacher, student where relevant)
# ---------------------------------------------------------------------------

def get_announcements(conn, audience: str = "all", limit: int = 5) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT title, content, created_at FROM announcements
               WHERE is_active = 1 AND (audience = 'all' OR audience = %s)
               ORDER BY created_at DESC LIMIT %s""",
            (audience, limit),
        )
        return cur.fetchall()


def get_institution_stats(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM students")
        students = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM teachers")
        teachers = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM subjects")
        subjects = cur.fetchone()["c"]
    return {"students": students, "teachers": teachers, "subjects": subjects}
