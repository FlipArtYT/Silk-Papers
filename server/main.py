from fastapi import FastAPI, HTTPException, staticfiles, Depends, UploadFile, File, status, Form
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool
from typing import Annotated
from pathlib import Path
import os
import json
import aioshutil
import secrets
import ollama
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
import sqlalchemy as sqla
from sqlalchemy import text
import datetime
from contextlib import asynccontextmanager
from services.db_models import Notebooks, Documents, ChatMessage, Base
from services.database import db_engine, get_db, db_session
import services.better_text_splitter as better_text_splitter
from services.chroma_database import insert_pages, query_request
from services.llm import generate_response
from pydantic_schemas.notebook_mgr import UploadDocumentMetadata
from pydantic_schemas.chat_mgr import GenerateLLMResponseRequest
from dataclasses import dataclass

ALLOWED_DOCUMENT_MIMETYPES = {"text/plain", "application/pdf"}
DOCUMENTS_DIR = Path("documents/")
DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DOCUMENTS_DIR = Path("temp/")
TEMP_DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    await db_engine.dispose()

app = FastAPI(lifespan=lifespan)

@app.get("/api/status")
def server_status():
    return {
        "message": "Active"
    }

@app.post("/api/notebooks/new", status_code=201)
async def new_notebook(db: AsyncSession = Depends(get_db)):
    async with db_session() as session:
        time_now = datetime.datetime.now()
        formatted_time = time_now.strftime("%a, %d. %m. %Y")
        notebook_name = f"New Notebook {formatted_time}"
        notebook_id = secrets.token_hex(8)

        query = sqla.insert(Notebooks).values(id=notebook_id, name=notebook_name, description="")

        try:
            await session.execute(query)
            await session.commit()
            return {
                "message": "Successfully created new notebook",
                "notebook_id": notebook_id,
            }
        
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error when trying to create new notebook: {str(e)}"
            )

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

@app.delete("/api/notebooks/delete")
async def delete_notebook(db: AsyncSession = Depends(get_db)):
    pass

@app.post("/api/llm/generate")
async def generate_llm_response(request_data: GenerateLLMResponseRequest):
    requested_notebook = request_data.notebook_id
    prompt = request_data.prompt.strip()
    model = request_data.model

    # Check if prompt isn't blank
    if prompt == "":
        raise HTTPException(
            status_code=400, 
            detail=f"No prompt was provided"
        )
    
    # Check if model exists
    local_models = ollama.list()
    model_exists = any(m['model'] == model for m in local_models.get('models', []))

    if not model_exists:
        raise HTTPException(
            status_code=404, 
            detail=f"AI Model does not exist"
        )
    
    # Check if notebook exists
    try:
        async with db_session() as session:
            query = sqla.select(Notebooks)
            results = await session.execute(query)
            notebooks: list[Notebooks] = results.scalars().all()

            notebook_ids: list[str] = [notebook.id for notebook in notebooks]
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error when trying to search for the requested notebook: {str(e)}"
        )
    
    if not requested_notebook in notebook_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notebook was not found"
        )
    
    # Get querying results from ChromaDB
    try:
        rag_results = await query_request(collection_id=requested_notebook, query=prompt, max_results=4)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error when trying to get RAG results: {str(e)}"
        )
    
    context_list = []

    for result in rag_results:
        formatted_result = ""
        page_content = result.page_content.strip()
        meatadata = result.metadata

        if meatadata:
            title = meatadata.get("title", "No title")
            source = meatadata.get("source", "No source")
            page_num = meatadata.get("page", "No page number")

            formatted_result = f"[Document]\nTitle: {title}\nSource: {source}\nPage number: {page_num}\nPage Content: {page_content}"""

        else:
            formatted_result = f"[Document]\nPage Content: {page_content}\nMetadata: Not provided"
        
        context_list.append(formatted_result)
    
    formatted_context = "\n\n".join(context_list)

    try:
        response = await generate_response(prompt=prompt, model=model, context=formatted_context)
        
        return {
            "response": response
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error when trying to generate a LLM response: {str(e)}"
        )

    
@app.post("/api/notebooks/upload", status_code=201)
async def add_file_to_notebook(file: UploadFile = File(...), metadata: str = Form(...), db: AsyncSession = Depends(get_db)):
    if not file.content_type in ALLOWED_DOCUMENT_MIMETYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File type is not supported for documents")
    
    try:
        # Manually parse the JSON string into our Pydantic model
        metadata_dict = json.loads(metadata)
        item_data = UploadDocumentMetadata(**metadata_dict)

        requested_notebook = item_data.notebook_id

    except (json.JSONDecodeError, TypeError, ValueError) as e:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid JSON provided in metadata field: {str(e)}"
        )
    
    # Check if notebook exists
    try:
        async with db_session() as session:
            query = sqla.select(Notebooks)
            results = await session.execute(query)
            notebooks: list[Notebooks] = results.scalars().all()

            notebook_ids: list[str] = [notebook.id for notebook in notebooks]
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error when trying to search for the requested notebook: {str(e)}"
        )
    
    if not requested_notebook in notebook_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notebook was not found"
        )
    
    document_id = secrets.token_hex(8)
    
    # Insert document
    try:
        # Save file to the temp directory
        file_name = f"{document_id}.pdf" if file.content_type in "application/pdf" else f"{document_id}.txt"
        temp_path = TEMP_DOCUMENTS_DIR / file_name

        with open(temp_path, "wb") as buffer:
                while chunk := await file.read(1024 * 1024):
                    buffer.write(chunk)
        
        await file.close()
        
        # Add file metadata to database
        async with db_session() as session:
            query = sqla.insert(Documents).values(
                                                id=document_id,
                                                notebooks_id=requested_notebook, 
                                                filename=file_name, 
                                                file_type=file.content_type,
                                                status="pending",
                                                chroma_collection_id=requested_notebook)
            await session.execute(query)
            await session.commit()
        
        async with db_session() as session:
            query = sqla.update(Documents).where(Documents.id == document_id).values(status="success")
            await session.execute(query)
            await session.commit()

        # Split document
        splitted_text = await better_text_splitter.split_text(temp_path, file.content_type)
        
        try:
            await insert_pages(collection_id=requested_notebook, chunks=splitted_text)

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error when trying to insert documents into the Chroma collection: {str(e)}"
            )

        # Move from temp to documents
        documents_path = DOCUMENTS_DIR / file_name
        await aioshutil.move(temp_path, documents_path)

        return {
            "message": "Successfully uploaded document",
            "document_id": document_id,
        }
    
    except Exception as MainException:
        # Update notebook status
        print(f"Notebook upload failed: {MainException}")
        try:
            async with db_session() as session:
                query = sqla.update(Documents).where(Documents.id == document_id).values(status="failed")
                await session.execute(query)
                await session.commit()
        
        except Exception as e:
            print(f"An error occured when trying to update the notebook status: {e}")
        
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occured when trying to upload the document: {str(MainException)}"
        )
    
    finally:
        await clean_up_failed_documents()
    
def sync_delete_file(path: str):
    if os.path.exists(path):
        os.remove(path)
    else:
        raise FileNotFoundError

async def clean_up_failed_documents() -> None:
    async with db_session() as session:
        # Get failed documents
        query = sqla.select(Documents).where(Documents.status == "failed")
        results = await session.execute(query)
        documents: list[Documents] = results.scalars().all()
        
        for document in documents:
            file_path = TEMP_DOCUMENTS_DIR / document.filename
            print(file_path)

            if os.path.exists(file_path):
                try:
                    await run_in_threadpool(sync_delete_file, file_path)

                except Exception as e:
                    print(f"Error when trying to delete {document}")