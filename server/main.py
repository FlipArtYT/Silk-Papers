from fastapi import FastAPI, HTTPException, staticfiles, Depends, UploadFile, File, status, Form
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool
from typing import Annotated
from pathlib import Path
import os
import re
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
from services.llm import generate_response, generate_chat_response
from pydantic_schemas.notebook_mgr import (
    UploadDocumentMetadata,
    DeleteNotebookRequest, 
    NotebookRenameRequest,
    NotebookDocumentsRequest,
    DeleteDocumentRequest,
    RenameDocumentRequest,
    LLMChatClearRequest
)
from pydantic_schemas.chat_mgr import GenerateLLMResponseRequest, LLMChatRequest
from dataclasses import dataclass

ALLOWED_DOCUMENT_MIMETYPES = {"application/pdf"}
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
        
        return {"result": response_format}
    
@app.post("/api/notebooks/get_documents_list")
async def get_notebook_list(request_data: NotebookDocumentsRequest, db: AsyncSession = Depends(get_db)):
    requested_notebook = request_data.notebook_id

    # Check if notebook exists
    try:
        requested_notebook_exists = await notebook_id_exists(requested_notebook)
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error when trying to search for the requested notebook: {str(e)}"
        )
    
    if not requested_notebook_exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notebook was not found"
        )

    async with db_session() as session:
        query = sqla.select(Documents).where(Documents.notebooks_id == requested_notebook)
        result = await session.execute(query)
        documents: list[Documents] = result.scalars().all()

        response_format = []

        for document in documents:
            response_format.append({
                "id": document.id,
                "display_name": document.display_name,
                "filename": document.filename,
                "content_type": document.content_type,
            })
        
        return {"result": response_format}
    
@app.post("/api/notebooks/new", status_code=201)
async def create_new_notebook(db: AsyncSession = Depends(get_db)):
    async with db_session() as session:
        time_now = datetime.datetime.now()
        formatted_time = time_now.strftime("%a, %d. %m. %Y")
        notebook_name = f"New Notebook {formatted_time}"
        notebook_id = secrets.token_hex(8)

        query = sqla.insert(Notebooks).values(id=notebook_id, name=notebook_name, description="")

        try:
            await session.execute(query)
            await session.commit()
        
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error when trying to create new notebook: {str(e)}"
            )
        
        return {
            "message": "Successfully created new notebook",
            "notebook_id": notebook_id,
        }

@app.post("/api/notebooks/rename", status_code=201)
async def rename_notebook(request_data: NotebookRenameRequest, db: AsyncSession = Depends(get_db)):
    requested_notebook = request_data.notebook_id
    requested_new_name = request_data.new_name
    requested_new_desc = request_data.new_description

    # Check if notebook exists
    try:
        requested_notebook_exists = await notebook_id_exists(requested_notebook)
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error when trying to search for the requested notebook: {str(e)}"
        )
    
    if not requested_notebook_exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notebook was not found"
        )
    
    # Rename notebook
    try:
        async with db_session() as session:
            query = sqla.update(Notebooks).where(Notebooks.id == requested_notebook).values(
                name=requested_new_name,
                description=requested_new_desc
            )
            await session.execute(query)
            await session.commit()
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error when trying to rename the notebook: {str(e)}"
        )
    
    return {
        "message": "Successfully renamed the notebook"
    }

@app.post("/api/notebooks/rename_document", status_code=201)
async def new_notebook(request_data: RenameDocumentRequest, db: AsyncSession = Depends(get_db)):
    requested_document = request_data.document_id
    requested_new_name = request_data.new_name

    # Check if document exists
    try:
        requested_document_exists = await document_id_exists(requested_document)
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error when trying to search for the requested document: {str(e)}"
        )
    
    if not requested_document_exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document was not found"
        )
    
    # Rename document
    try:
        async with db_session() as session:
            query = sqla.update(Documents).where(Documents.id == requested_document).values(
                display_name=requested_new_name
            )
            await session.execute(query)
            await session.commit()
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error when trying to rename the document: {str(e)}"
        )
    
    return {
        "message": "Successfully renamed the document"
    }
    
@app.post("/api/notebooks/upload", status_code=201)
async def upload_file_to_notebook(file: UploadFile = File(...), metadata: str = Form(...), db: AsyncSession = Depends(get_db)):
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
        requested_notebook_exists = await notebook_id_exists(requested_notebook)
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error when trying to search for the requested notebook: {str(e)}"
        )
    
    if not requested_notebook_exists:
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
                                                display_name=file.filename,
                                                filename=file_name, 
                                                content_type=file.content_type,
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

        for chunk in splitted_text:
            chunk.metadata["title"] = file.filename
        
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

@app.delete("/api/notebooks/clear_chat", status_code=204)
async def delete_notebook(request_data: LLMChatClearRequest, db: AsyncSession = Depends(get_db)):
    requested_notebook = request_data.notebook_id

    # Check if notebook exists
    try:
        requested_notebook_exists = await notebook_id_exists(requested_notebook)
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error when trying to search for the requested notebook: {str(e)}"
        )
    
    if not requested_notebook_exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notebook was not found"
        )
    
    # Delete document's metadata
    try:
        async with db_session() as session:
            query = sqla.delete(ChatMessage).where(ChatMessage.notebooks_id == requested_notebook)
            await session.execute(query)
            await session.commit()
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error when trying to clear the chat: {str(e)}"
        )

@app.delete("/api/notebooks/delete_document", status_code=204)
async def delete_notebook(request_data: DeleteDocumentRequest, db: AsyncSession = Depends(get_db)):
    requested_document = request_data.document_id

    # Check if document exists
    try:
        requested_document_exists = await document_id_exists(requested_document)
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error when trying to search for the requested notebook: {str(e)}"
        )
    
    if not requested_document_exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document was not found"
        )
    
    # Get document's metadata
    try:
        async with db_session() as session:
            query = sqla.select(Documents).where(Documents.id == requested_document)
            result = await session.execute(query)
            document_metadata = result.scalars().one()
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error when trying to get the requested document: {str(e)}"
        )
    
    # Delete file from the documents folder
    doc_path = DOCUMENTS_DIR / document_metadata.filename

    try:
        if os.path.exists(doc_path):
            await run_in_threadpool(sync_delete_file, doc_path)
    
    except Exception as e:
        print(f"Deleting {document_metadata.filename} failed")
    
    # Delete document's metadata
    try:
        async with db_session() as session:
            query = sqla.delete(Documents).where(Documents.id == requested_document)
            await session.execute(query)
            await session.commit()
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error when trying to delete the document: {str(e)}"
        )
    
    return {
        "message": "Successfully deleted document",
        "notebook_id": requested_document,
    }

@app.delete("/api/notebooks/delete", status_code=204)
async def delete_notebook(request_data: DeleteNotebookRequest, db: AsyncSession = Depends(get_db)):
    requested_notebook = request_data.notebook_id

    # Check if notebook exists
    try:
        requested_notebook_exists = await notebook_id_exists(requested_notebook)
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error when trying to search for the requested notebook: {str(e)}"
        )
    
    if not requested_notebook_exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notebook was not found"
        )
    
    # Get all document metadata from the notebook
    try:
        async with db_session() as session:
            query = sqla.select(Documents).where(Documents.notebooks_id == requested_notebook)
            result = await session.execute(query)
            documents_metadata: list[Documents] = result.scalars().all()
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error when trying to get all documents from the requested notebook: {str(e)}"
        )
    
    print(f"Deleting Notebook {requested_notebook}")
    
    # Delete notebook's documents
    for doc_metadata in documents_metadata:
        doc_path = DOCUMENTS_DIR / doc_metadata.filename

        try:
            if os.path.exists(doc_path):
                print(f"Deleting file {doc_metadata.filename}")
                await run_in_threadpool(sync_delete_file, doc_path)
        
        except Exception as e:
            print(f"Failed to delete {doc_metadata.filename}: {e}")
    
    # Delete notebook's document metadata
    try:
        async with db_session() as session:
            query = sqla.delete(Documents).where(Documents.notebooks_id == requested_notebook)
            await session.execute(query)
            await session.commit()
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error when trying to delete the notebook: {str(e)}"
        )
    
    # Delete notebook metadata from database
    try:
        async with db_session() as session:
            query = sqla.delete(Notebooks).where(Notebooks.id == requested_notebook)
            await session.execute(query)
            await session.commit()
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error when trying to delete the notebook: {str(e)}"
        )
    
    return {
        "message": "Successfully deleted notebook",
        "notebook_id": requested_notebook,
    }

@app.get("/api/llm/list")
async def get_available_models():
    models: list = ollama.list()
    formatted_models = []

    for model in models["models"]:
        model_name = model.get("model")
        details = model.get("details")
        parameter_size = details.get("parameter_size")
        int_parameter_size = parse_parameter_size(parameter_size)

        formatted_models.append({
            "model": model_name,
            "parameter_size": int_parameter_size
        })

    return formatted_models

@app.post("/api/llm/chat")
async def chat_with_llm(request_data: LLMChatRequest):
    requested_notebook = request_data.notebook_id
    prompt = request_data.prompt.strip()
    model = request_data.model
    chat_messages_list = []

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
        requested_notebook_exists = await notebook_id_exists(requested_notebook)
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error when trying to search for the requested notebook: {str(e)}"
        )
    
    if not requested_notebook_exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notebook was not found"
        )
    
    # Get messages from chat
    try:
        async with db_session() as session:
            query = sqla.select(ChatMessage).where(ChatMessage.notebooks_id == requested_notebook)
            results = await session.execute(query)
            messages: list[ChatMessage] = results.scalars().all()

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error when trying to search for the messages from the requested notebook: {str(e)}"
        )
    
    for message in messages:
        chat_messages_list.append({"role": message.role, "content": message.content})
    
    # Get querying results from ChromaDB
    try:
        rag_results = await query_request(collection_id=requested_notebook, query=prompt, max_results=6)

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
        response = await generate_chat_response(prompt=prompt, model=model, context=formatted_context, messages=chat_messages_list)
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error when trying to generate a LLM response: {str(e)}"
        )
    
    # Create updated messages list
    new_chat_messages = [
        {"notebooks_id": requested_notebook, "role": "user", "content": prompt, "model_used": ""},
        {"notebooks_id": requested_notebook, "role": "assistant", "content": response, "model_used": model}
    ]
    
    # Insert messages into the database
    try:
        async with db_session() as session:
            query = sqla.insert(ChatMessage).values(new_chat_messages)
            await session.execute(query)
            await session.commit()

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error when trying to insert chat messages: {str(e)}"
        )
    
    return {
        "response": response
    }

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
        requested_notebook_exists = await notebook_id_exists(requested_notebook)
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error when trying to search for the requested notebook: {str(e)}"
        )
    
    if not requested_notebook_exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notebook was not found"
        )
    
    # Get querying results from ChromaDB
    try:
        rag_results = await query_request(collection_id=requested_notebook, query=prompt, max_results=6)

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

# Helper functions
async def notebook_id_exists(notebook_id:int):
    async with db_session() as session:
        query = sqla.select(Notebooks)
        results = await session.execute(query)
        notebooks: list[Notebooks] = results.scalars().all()

        notebook_ids: list[str] = [notebook.id for notebook in notebooks]
    
    return notebook_id in notebook_ids

async def document_id_exists(document_id:int):
    async with db_session() as session:
        query = sqla.select(Documents)
        results = await session.execute(query)
        documents: list[Documents] = results.scalars().all()

        document_ids: list[str] = [document.id for document in documents]
    
    return document_id in document_ids
    
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
                    # Delete file from temp folder
                    await run_in_threadpool(sync_delete_file, file_path)

                    # Delete metadata from database
                    del_query = sqla.delete(Documents).where(Documents.id == document.id)
                    await session.execute(del_query)
                    await session.commit()

                    print(f"Deleted {document.filename}; ID: {document.id}")


                except Exception as e:
                    print(f"Error when trying to delete {document.filename}; ID: {document.id}: {e}")

def parse_parameter_size(size_str: str) -> int:
    if not size_str:
        return 0
    
    clean_str = size_str.strip().upper()
    
    match = re.match(r"^([0-9.]+)\s*([M_B_T]?)$", clean_str)
    if not match:
        return 0
    
    value_str, suffix = match.groups()
    value = float(value_str)
    
    multipliers = {
        'M': 1_000_000,          # Million
        'B': 1_000_000_000,      # Billion
        'T': 1_000_000_000_000,  # Trillion
        '': 1                    # No suffix
    }
    
    return int(value * multipliers.get(suffix, 1))