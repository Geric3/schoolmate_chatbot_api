from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from security import AuthContext, get_auth_context
from db import get_connection
from models import ChatRequest, ChatResponse
from services import moderation, intent_service, context_builder as cb
from services import faq_service, rag_service, llm_service

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, ctx: AuthContext = Depends(get_auth_context)):
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Empty message.")

    lang = ctx.lang if ctx.lang in ("fr", "en") else "fr"

    with get_connection(ctx.db_name) as conn:
        # --- 1. Hard safety checks, before touching anything else ---
        own_student_number = None
        student = None
        if ctx.role == "student":
            student = cb.get_student_profile(conn, ctx.user_id)
            own_student_number = student["student_number"] if student else None

        refusal = moderation.check_password_request(message, lang) or \
            moderation.check_cross_student_request(message, ctx.role, own_student_number, lang)
        if refusal:
            faq_service.log_interaction(conn, ctx.user_id, message, refusal)
            return ChatResponse(response=refusal, source="blocked")

        # --- 2. Structured intent -> live DB facts ---
        intent = intent_service.classify(message)
        answer, source = None, None

        if intent and ctx.role == "student" and student:
            answer, source = _handle_student_intent(conn, intent, message, lang, student)
        elif intent and ctx.role == "teacher":
            answer, source = _handle_teacher_intent(conn, intent, message, lang, ctx)
        elif intent and ctx.role in ("admin", "university"):
            answer, source = _handle_admin_intent(conn, intent, message, lang)
        elif intent and intent.name == "announcements":
            audience = "students" if ctx.role == "student" else ("teachers" if ctx.role == "teacher" else "all")
            items = cb.get_announcements(conn, audience=audience)
            if not items:
                # règlement intérieur / announcement text might live as an uploaded document instead
                doc = rag_service.get_document_by_title_fragment(conn, "reglement") or \
                      rag_service.get_document_by_title_fragment(conn, "règlement") or \
                      rag_service.get_document_by_title_fragment(conn, "annonce")
                if doc:
                    answer = llm_service.answer_with_documents(lang, message, doc)
                    source = "documents"
            else:
                answer = llm_service.polish_structured_answer(lang, message, {"announcements": items})
                source = "structured_data"

        # --- 3. Local FAQ table ---
        if not answer:
            faq_hit = faq_service.find_best_faq(conn, message, lang)
            if faq_hit:
                answer, source = faq_hit["answer"], "faq"

        # --- 4. Admin-uploaded documents (RAG) ---
        if not answer:
            chunks = rag_service.search_documents(conn, message)
            if chunks:
                doc_answer = llm_service.answer_with_documents(lang, message, chunks)
                if doc_answer:
                    answer, source = doc_answer, "documents"

        # --- 5. General LLM fallback (out-of-scope or nothing matched) ---
        if not answer:
            answer = llm_service.answer_general(lang, message)
            source = "llm_general"
            # Keep a record so admin can review and turn recurring gaps into FAQs
            faq_service.log_unanswered(conn, message, answer)

        faq_service.log_interaction(conn, ctx.user_id, message, answer)
        return ChatResponse(response=answer, source=source)


# ---------------------------------------------------------------------------
# Intent handlers
# ---------------------------------------------------------------------------

def _handle_student_intent(conn, intent, message, lang, student):
    name = intent.name

    if name == "grades":
        grades = cb.get_student_grades(conn, student["id"])
        if not grades:
            msg = ("Aucune note n'est encore enregistrée pour vous." if lang == "fr"
                   else "No grades are recorded for you yet.")
            return msg, "structured_data"
        return llm_service.polish_structured_answer(lang, message, {"grades": grades}), "structured_data"

    if name == "semester_validation":
        semester = intent.entities.get("semester") or "1"
        result = cb.get_semester_validation(conn, student["id"], semester, student["academic_year"])
        return llm_service.polish_structured_answer(lang, message, result), "structured_data"

    if name == "payment":
        summary = cb.get_payment_summary(conn, student)
        return llm_service.polish_structured_answer(lang, message, summary), "structured_data"

    if name == "courses":
        courses = cb.get_student_courses(conn, student)
        return llm_service.polish_structured_answer(lang, message, {"courses": courses}), "structured_data"

    if name == "teacher_lookup":
        fragment = intent.entities.get("subject_fragment", "")
        teacher = cb.get_teacher_for_subject(conn, student, fragment) if fragment else None
        if not teacher:
            msg = ("Je n'ai pas trouvé d'enseignant pour cette matière. Vérifiez le nom exact du cours."
                   if lang == "fr" else
                   "I couldn't find a teacher for that subject. Please check the exact course name.")
            return msg, "structured_data"
        return llm_service.polish_structured_answer(lang, message, teacher), "structured_data"

    if name == "notifications":
        notifs = cb.get_notifications(conn, student["id"])
        return llm_service.polish_structured_answer(lang, message, {"notifications": notifs}), "structured_data"

    return None, None


def _handle_teacher_intent(conn, intent, message, lang, ctx: AuthContext):
    name = intent.name
    teacher = cb.get_teacher_profile(conn, ctx.user_id)
    if not teacher:
        return None, None

    if name == "teacher_subjects":
        subjects = cb.get_teacher_subjects(conn, ctx.user_id)
        return llm_service.polish_structured_answer(lang, message, {"subjects": subjects}), "structured_data"

    if name == "teacher_hours":
        now = datetime.now()
        # best-effort academic year guess: adjust if your school year starts in a different month
        academic_year = f"{now.year}-{now.year + 1}" if now.month >= 8 else f"{now.year - 1}-{now.year}"
        hours = cb.get_teacher_monthly_hours(conn, ctx.user_id, now.month, academic_year)
        return llm_service.polish_structured_answer(lang, message, hours), "structured_data"

    return None, None


def _handle_admin_intent(conn, intent, message, lang):
    if intent.name == "institution_stats":
        stats = cb.get_institution_stats(conn)
        return llm_service.polish_structured_answer(lang, message, stats), "structured_data"
    return None, None
