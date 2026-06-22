from fastapi import FastAPI, HTTPException, staticfiles, Depends, UploadFile, File, status, Form, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from contextlib import asynccontextmanager
from services.db_models import Base
from services.database import db_engine
from services.notebook_mgr import notebook_id_exists, get_notebooks, get_notebook_doclen
from services.db_models import Notebooks, Documents, ChatMessage
from services.database import get_db, db_session
from routers import notebooks, llm
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)
import sqlalchemy as sqla

APP_VERSION = "0.0.0 ALPHA"

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    await db_engine.dispose()

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.include_router(notebooks.router, prefix="/api/notebooks", tags=["notebooks"])
app.include_router(llm.router, prefix="/api/llm", tags=["llm"])

@app.get("/api/status")
def server_status():
    return {
        "message": "Active"
    }

@app.get("/", include_in_schema=False)
async def home(request: Request):
    notebooks = await get_notebooks()

    response_format = []

    for notebook in notebooks:
        try:
            doclen = await get_notebook_doclen(notebook_id=notebook.id)
        except Exception as e:
            print(f"Failed to get doclen of Notebook: {e}")
            doclen = 0

        response_format.append({
            "id": notebook.id,
            "name": notebook.name,
            "description": notebook.description,
            "doclen": doclen
        })

    return templates.TemplateResponse(
        request,
        "index.html",
        context={"notebooks": response_format}
    )

@app.get("/about", include_in_schema=False)
async def home(request: Request):
    return templates.TemplateResponse(
        request,
        "about.html",
        context={"version": APP_VERSION}
    )

@app.get("/notebooks/{requested_notebook}", name="notebook_view", include_in_schema=False)
async def notebook_view(request: Request, requested_notebook: str, db: AsyncSession = Depends(get_db)):
    notebook_exists = await notebook_id_exists(requested_notebook)

    if notebook_exists:
        # Get notebook info
        async with db_session() as session:
            query = sqla.select(Notebooks).where(Notebooks.id == requested_notebook)
            result = await session.execute(query)
            notebook_metadata: Notebooks = result.scalars().one()

        # Get documents
        async with db_session() as session:
            query = sqla.select(Documents).where(Documents.notebooks_id == requested_notebook)
            result = await session.execute(query)
            documents: list[Documents] = result.scalars().all()

            documents_list = []

            for document in documents:
                documents_list.append({
                    "id": document.id,
                    "display_name": document.display_name,
                    "filename": document.filename,
                    "content_type": document.content_type,
                })

        return templates.TemplateResponse(
            request,
            "notebook_view.html",
            context={
                "notebook_id": requested_notebook,
                "notebook_metadata": notebook_metadata,
                "document_metdata": documents_list
            }
        )
    
    else:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notebook was not found")

@app.exception_handler(StarletteHTTPException)
def general_http_exception_handler(request: Request, exception: StarletteHTTPException):
    message = (
        exception.detail
        if exception.detail
        else "An error occurred. Please check your request and try again."
    )

    if request.url.path.startswith("/api"):
        return JSONResponse(
            status_code=exception.status_code,
            content={"detail": message},
        )

    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "status_code": exception.status_code,
            "title": exception.status_code,
            "message": message,
        },
        status_code=exception.status_code,
    )


@app.exception_handler(RequestValidationError)
def validation_exception_handler(request: Request, exception: RequestValidationError):
    if request.url.path.startswith("/api"):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": exception.errors()},
        )

    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "status_code": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "title": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "message": "Invalid request. Please check your input and try again.",
        },
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )