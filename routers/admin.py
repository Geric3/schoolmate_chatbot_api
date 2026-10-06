from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form

from security import AuthContext, get_auth_context, require_role
from db import get_connection
from models import FaqIn, FaqOut, DocumentOut, AnnouncementIn, UnansweredOut
from services import faq_service, rag_service, context_builder as cb

router = APIRouter(prefix="/admin")


def _admin_only(ctx: AuthContext) -> AuthContext:
    require_role(ctx, "admin", "university")
    return ctx


# --- FAQs ---------------------------------------------------------------

@router.get("/faqs", response_model=List[FaqOut])
def get_faqs(ctx: AuthContext = Depends(_admin_only)):
    with get_connection(ctx.db_name) as conn:
        return faq_service.list_faqs(conn)


@router.post("/faqs", response_model=dict)
def add_faq(payload: FaqIn, ctx: AuthContext = Depends(_admin_only)):
    with get_connection(ctx.db_name) as conn:
        new_id = faq_service.create_faq(conn, payload.question_key, payload.answer, payload.lang)
    return {"id": new_id}


@router.put("/faqs/{faq_id}")
def edit_faq(faq_id: int, payload: FaqIn, ctx: AuthContext = Depends(_admin_only)):
    with get_connection(ctx.db_name) as conn:
        faq_service.update_faq(conn, faq_id, payload.question_key, payload.answer, payload.lang)
    return {"ok": True}


@router.delete("/faqs/{faq_id}")
def remove_faq(faq_id: int, ctx: AuthContext = Depends(_admin_only)):
    with get_connection(ctx.db_name) as conn:
        faq_service.delete_faq(conn, faq_id)
    return {"ok": True}


# --- Unanswered questions review queue -----------------------------------

@router.get("/unanswered", response_model=List[UnansweredOut])
def get_unanswered(ctx: AuthContext = Depends(_admin_only)):
    with get_connection(ctx.db_name) as conn:
        return faq_service.list_unanswered(conn)


@router.delete("/unanswered/{entry_id}")
def dismiss_unanswered(entry_id: int, ctx: AuthContext = Depends(_admin_only)):
    with get_connection(ctx.db_name) as conn:
        faq_service.delete_unanswered(conn, entry_id)
    return {"ok": True}


# --- Documents (RAG) ------------------------------------------------------

@router.get("/documents", response_model=List[DocumentOut])
def get_documents(ctx: AuthContext = Depends(_admin_only)):
    with get_connection(ctx.db_name) as conn:
        docs = rag_service.list_documents(conn)
    return [
        DocumentOut(
            id=d["id"], title=d["title"], chunk_count=d["chunk_count"],
            created_at=str(d["created_at"]) if d.get("created_at") else None,
        )
        for d in docs
    ]


@router.post("/documents/text")
def add_document_text(title: str = Form(...), content: str = Form(...),
                       ctx: AuthContext = Depends(_admin_only)):
    if not content.strip():
        raise HTTPException(status_code=400, detail="Empty content.")
    with get_connection(ctx.db_name) as conn:
        doc_id = rag_service.create_document(conn, title, content, uploaded_by=ctx.user_id)
    return {"id": doc_id}


@router.post("/documents/file")
async def add_document_file(title: Optional[str] = Form(None), file: UploadFile = File(...),
                             ctx: AuthContext = Depends(_admin_only)):
    raw = await file.read()
    filename = file.filename or "document"
    doc_title = title or filename

    if filename.lower().endswith(".pdf"):
        text = _extract_pdf_text(raw)
    else:
        text = raw.decode("utf-8", errors="ignore")

    if not text.strip():
        raise HTTPException(status_code=400, detail="Could not extract any text from the file.")

    with get_connection(ctx.db_name) as conn:
        doc_id = rag_service.create_document(conn, doc_title, text, uploaded_by=ctx.user_id)
    return {"id": doc_id}


@router.delete("/documents/{document_id}")
def remove_document(document_id: int, ctx: AuthContext = Depends(_admin_only)):
    with get_connection(ctx.db_name) as conn:
        rag_service.delete_document(conn, document_id)
    return {"ok": True}


def _extract_pdf_text(raw: bytes) -> str:
    from io import BytesIO
    try:
        from pypdf import PdfReader
    except ImportError:
        raise HTTPException(status_code=500, detail="PDF support not installed (pypdf).")
    reader = PdfReader(BytesIO(raw))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


# --- Announcements ---------------------------------------------------------

@router.post("/announcements")
def add_announcement(payload: AnnouncementIn, ctx: AuthContext = Depends(_admin_only)):
    with get_connection(ctx.db_name) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO announcements (title, content, audience, is_active, created_at) "
                "VALUES (%s, %s, %s, 1, NOW())",
                (payload.title, payload.content, payload.audience),
            )
            new_id = cur.lastrowid
    return {"id": new_id}


@router.get("/announcements")
def get_announcements(ctx: AuthContext = Depends(_admin_only)):
    with get_connection(ctx.db_name) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, title, content, audience, is_active, created_at FROM announcements ORDER BY created_at DESC")
            return cur.fetchall()


@router.delete("/announcements/{announcement_id}")
def remove_announcement(announcement_id: int, ctx: AuthContext = Depends(_admin_only)):
    with get_connection(ctx.db_name) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM announcements WHERE id = %s", (announcement_id,))
    return {"ok": True}
