from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from routers import chat, admin

app = FastAPI(
    title="Schoolmate Chatbot API",
    description="Intent -> MySQL -> FAQ -> Documents (RAG) -> LLM fallback, "
                "scoped per-tenant via signed JWTs minted by the PHP app.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS or [],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(chat.router)
app.include_router(admin.router)


@app.get("/health")
def health():
    return {"status": "ok"}
