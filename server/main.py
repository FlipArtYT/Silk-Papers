from fastapi import FastAPI, HTTPException, staticfiles, Depends, UploadFile, File, status, Form
from fastapi.responses import HTMLResponse
from typing import Annotated
from pathlib import Path
import json
import secrets
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
import sqlalchemy as sqla
from sqlalchemy import text
from contextlib import asynccontextmanager
from services.db_models import Notebooks, Documents, ChatMessage, Base
from services.database import db_engine, get_db, db_session
from pydantic_schemas.notebook_mgr import UploadDocumentMetadata
from dataclasses import dataclass

ALLOWED_DOCUMENT_MIMETYPES = {"text/plain", "application/pdf"}
DOCUMENTS_DIR = Path("documents/")
DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DOCUMENTS_DIR = Path("temp/")
TEMP_DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI()

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    await db_engine.dispose()

@app.get("/api/status")
def server_status():
    return {
        "message": "Success"
    }

@app.get("/api/notebooks/new")
async def new_notebook(db: AsyncSession = Depends(get_db)):
    async with db_session() as session:
        query = sqla.insert(Notebooks).values(name="New Notebook", description="")
        result = await session.execute(query)

        try:
            await session.commit()
            return {"res": "Success"}
        
        except:
            return {"res": "Failed to commit"}

@app.get("/api/notebooks/get_list")
async def get_notebook_list(db: AsyncSession = Depends(get_db)):
    async with db_session() as session:
        query = sqla.select(Notebooks)
        result = await session.execute(query)
        notebooks: list[Notebooks] = result.scalars().all()

        response_format = []

        for notebook in notebooks:
            response_format.append({
                "id": notebook.id,
                "name": notebook.name,
                "description": notebook.description
            })
        
        return {"notebooks": response_format}
    
@app.post("/api/notebooks/upload")
async def add_file_to_notebook(file: UploadFile = File(...), metadata: str = Form(...), db: AsyncSession = Depends(get_db)):
    if not file.content_type in ALLOWED_DOCUMENT_MIMETYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File type is not supported for documents")
    
    try:
        # Manually parse the JSON string into our Pydantic model
        metadata_dict = json.loads(metadata)
        item_data = UploadDocumentMetadata(**metadata_dict)
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid JSON provided in metadata field: {str(e)}"
        )
    
    try:
        # Save file to the temp directory
        file_name = f"{secrets.token_hex(8)}.pdf"
        temp_path = TEMP_DOCUMENTS_DIR / file_name

        with open(temp_path, "wb") as buffer:
                while chunk := await file.read(1024 * 1024):
                    buffer.write(chunk)
        
        await file.close()     
        
        # Add file metadata to database
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fatal error when trying to upload document: {str(e)}"
        )