from fastapi import FastAPI, HTTPException, staticfiles, Depends, UploadFile, File, status, Form
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
from services.db_models import Base
from services.database import db_engine
from routers import notebooks, llm

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    await db_engine.dispose()

app = FastAPI(lifespan=lifespan)

app.include_router(notebooks.router, prefix="/api/notebooks", tags=["notebooks"])
app.include_router(llm.router, prefix="/api/llm", tags=["llm"])

@app.get("/api/status")
def server_status():
    return {
        "message": "Active"
    }