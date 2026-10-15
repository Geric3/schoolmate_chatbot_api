from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from security import AuthContext, get_auth_context
from db import get_connection
from models import ChatRequest, ChatResponse
from services import moderation, intent_service, context_builder as cb
from services import faq_service, rag_service, llm_service, continuation_service

router = APIRouter()

# Intentions liées aux données propres à l'utilisateur : elles passent avant le RAG/FAQ.
PERSONAL_INTENTS = {
    "grades", "failed_courses", "semester_average", "semester_validation", "payment",
    "courses", "teacher_lookup", "notifications", "teacher_hours", "teacher_subjects",
}
BATCH_SIZE = 4               # passages de document affichés par réponse
MAX_RELEVANT_CHUNKS = 12     # passages pertinents conservés (le reste alimente « la suite »)


def _reading_order(chunks: list[dict]) -> list[dict]:
    """Remet les passages dans l'ordre du document pour que la réponse se lise naturellement."""
    return sorted(chunks, key=lambda c: (c.get("doc_id") or 0, c.get("chunk_index") or 0))


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

        # --- 1b. L'utilisateur répond « oui / non » à « voulez-vous la suite ? » ---
        pending = continuation_service.get_pending(conn, ctx.role, ctx.user_id)
        if pending:
            if continuation_service.is_affirmative(message):
                reply = _continue_document_answer(conn, ctx, lang, pending)
                faq_service.log_interaction(conn, ctx.user_id, message, reply)
                return ChatResponse(response=reply, source="documents")
            continuation_service.clear_pending(conn, ctx.role, ctx.user_id)
            if continuation_service.is_negative(message):
                reply = continuation_service.DECLINED[lang]
                faq_service.log_interaction(conn, ctx.user_id, message, reply)
                return ChatResponse(response=reply, source="documents")
            # sinon : c'est une nouvelle question, on poursuit normalement

        # --- 2. Resolve authenticated, live user data before general knowledge ---
        intent = intent_service.classify(message)
        answer, source = None, None
        personal = bool(intent and intent.name in PERSONAL_INTENTS)
        if personal and ctx.role == "student" and student:
            answer, source = _handle_student_intent(conn, intent, message, lang, student)
        elif personal and ctx.role == "teacher":
            answer, source = _handle_teacher_intent(conn, intent, message, lang, ctx)
        elif intent and ctx.role in ("admin", "university"):
            answer, source = _handle_admin_intent(conn, intent, message, lang)

        # --- 3. Institution documents are searched before FAQ/general Groq answers ---
        if not answer and not personal:
            ranked = rag_service.search_documents(
                conn, message, top_k=MAX_RELEVANT_CHUNKS, min_score=0.15, relative_min=0.6,
            )
            if ranked:
                first, rest = ranked[:BATCH_SIZE], ranked[BATCH_SIZE:]
                doc_answer = llm_service.answer_with_documents(lang, message, _reading_order(first))
                if doc_answer:
                    answer, source = doc_answer, "documents"
                    if rest:
                        continuation_service.save_pending(
                            conn, ctx.role, ctx.user_id, message, [c["id"] for c in rest], doc_answer)
                        answer = f"{doc_answer}\n\n{continuation_service.FOLLOWUP[lang]}"

        # Announcements are live database records; use them only when no matching
        # document passage answered the question, rather than returning unrelated latest items.
        if not answer and intent and intent.name == "announcements":
            answer, source = _handle_announcements(conn, ctx, message, lang)

        if not answer and intent and ctx.role == "teacher" and not personal:
            answer, source = _handle_teacher_intent(conn, intent, message, lang, ctx)

        # --- 4. Local FAQ table ---
        if not answer:
            faq_hit = faq_service.find_best_faq(conn, message, lang)
            if faq_hit:
                answer, source = faq_hit["answer"], "faq"

        # --- 5. General LLM fallback (out-of-scope or nothing matched) ---
        if not answer:
            answer = llm_service.answer_general(lang, message)
            source = "llm_general"
            # Keep a record so admin can review and turn recurring gaps into FAQs
            faq_service.log_unanswered(conn, message, answer)

        faq_service.log_interaction(conn, ctx.user_id, message, answer)
        return ChatResponse(response=answer, source=source)


# ---------------------------------------------------------------------------
# Suite d'une réponse tirée des documents
# ---------------------------------------------------------------------------

def _continue_document_answer(conn, ctx, lang, pending) -> str:
    ids = pending["chunk_ids"]
    batch_ids, remaining = ids[:BATCH_SIZE], ids[BATCH_SIZE:]
    chunks = rag_service.get_chunks_by_ids(conn, batch_ids)

    answer = None
    if chunks:
        answer = llm_service.answer_with_documents(
            lang, pending["question"], _reading_order(chunks), previous_answer=pending["last_answer"])

    if not answer:
        continuation_service.clear_pending(conn, ctx.role, ctx.user_id)
        return continuation_service.NO_MORE[lang]

    if remaining:
        shown = (pending["last_answer"] + "\n" + answer)[-1500:]
        continuation_service.save_pending(conn, ctx.role, ctx.user_id, pending["question"], remaining, shown)
        return f"{answer}\n\n{continuation_service.FOLLOWUP[lang]}"

    continuation_service.clear_pending(conn, ctx.role, ctx.user_id)
    return answer


# ---------------------------------------------------------------------------
# Intent handlers
# ---------------------------------------------------------------------------

def _handle_student_intent(conn, intent, message, lang, student):
    name = intent.name

    if name == "grades":
        grades = cb.get_student_grades(
            conn, student["id"], intent.entities.get("semester"),
            intent.entities.get("academic_year"),
        )
        if not grades:
            msg = ("Aucune note n'est encore enregistrée pour vous." if lang == "fr"
                   else "No grades are recorded for you yet.")
            return msg, "structured_data"
        return llm_service.polish_structured_answer(lang, message, {"grades": grades}), "structured_data"

    if name in ("semester_average", "semester_validation"):
        year = intent.entities.get("academic_year") or student["academic_year"]
        summaries = cb.get_semester_summaries(
            conn, student["id"], year, intent.entities.get("semester"),
        )
        if not summaries:
            msg = ("Aucune note n'est encore enregistrée pour cette période."
                   if lang == "fr" else "No grades are recorded for this period yet.")
            return msg, "structured_data"
        key = "semester_averages" if name == "semester_average" else "semester_validation"
        return llm_service.polish_structured_answer(lang, message, {key: summaries}), "structured_data"

    if name == "failed_courses":
        grades = cb.get_student_grades(
            conn, student["id"], intent.entities.get("semester"),
            intent.entities.get("academic_year"),
        )
        failed = [grade for grade in grades
                  if grade["total_on_100"] is not None and not grade["passed"]]
        if not failed:
            msg = ("Vous n'avez aucune matière à rattraper parmi les notes enregistrées."
                   if lang == "fr" else "You have no subjects to retake among the recorded grades.")
            return msg, "structured_data"
        return llm_service.polish_structured_answer(
            lang, message, {"subjects_to_retake": failed},
        ), "structured_data"

    if name == "semester_validation":
        semester = intent.entities.get("semester") or "1"
        result = cb.get_semester_validation(conn, student["id"], semester, student["academic_year"])
        return llm_service.polish_structured_answer(lang, message, result), "structured_data"

    if name == "payment":
        summary = cb.get_payment_summary(conn, student)
        return llm_service.polish_structured_answer(lang, message, summary), "structured_data"

    if name == "courses":
        courses = cb.get_student_courses(
            conn, student, intent.entities.get("semester"), intent.entities.get("academic_year"),
        )
        if not courses:
            msg = ("Aucune matière n'a été trouvée pour cette période."
                   if lang == "fr" else "No subjects were found for this period.")
            return msg, "structured_data"
        return llm_service.polish_structured_answer(lang, message, {"courses": courses}), "structured_data"

    if name == "teacher_lookup":
        details = cb.get_student_teacher_subjects(
            conn, student, intent.entities.get("teacher_fragment"),
            intent.entities.get("semester"), intent.entities.get("academic_year"),
        )
        if not details:
            msg = ("Je n'ai trouvé aucun enseignant ou cours correspondant dans votre programme."
                   if lang == "fr" else
                   "I couldn't find a matching teacher or subject in your programme.")
            return msg, "structured_data"
        return llm_service.polish_structured_answer(
            lang, message, {"teachers_and_subjects": details},
        ), "structured_data"

    if name == "notifications":
        notifs = cb.get_notifications(conn, student["id"])
        return llm_service.polish_structured_answer(lang, message, {"notifications": notifs}), "structured_data"

    return None, None


def _handle_teacher_intent(conn, intent, message, lang, ctx: AuthContext):
    name = intent.name
    teacher = cb.get_teacher_profile(conn, ctx.user_id)
    if not teacher:
        return None, None

    if name in ("teacher_subjects", "courses"):
        subjects = cb.get_teacher_subjects(
            conn, ctx.user_id, intent.entities.get("academic_year"),
            intent.entities.get("semester"),
        )
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


def _handle_announcements(conn, ctx, message, lang):
    audience = "students" if ctx.role == "student" else ("teachers" if ctx.role == "teacher" else "all")
    items = cb.get_announcements(conn, audience=audience)
    if items:
        return llm_service.polish_structured_answer(lang, message, {"announcements": items}), "structured_data"
    chunks = rag_service.search_documents(conn, message)
    if chunks:
        ans = llm_service.answer_with_documents(lang, message, _reading_order(chunks))
        if ans:
            return ans, "documents"
    return None, None