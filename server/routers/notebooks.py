from fastapi import HTTPException, Depends, UploadFile, File, status, Form, APIRouter
from starlette.concurrency import run_in_threadpool
from pathlib import Path
import os
import json
import aioshutil
import secrets
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)
import sqlalchemy as sqla
import datetime
from services.db_models import Notebooks, Documents, ChatMessage
from services.database import get_db, db_session
import services.better_text_splitter as better_text_splitter
from services.chroma_database import insert_pages
from pydantic_schemas.notebook_mgr import (
    UploadDocumentMetadata,
    DeleteNotebookRequest, 
    NotebookRenameRequest,
    NotebookDocumentsRequest,
    DeleteDocumentRequest,
    RenameDocumentRequest,
    LLMChatClearRequest
)

ALLOWED_DOCUMENT_MIMETYPES = {"application/pdf"}
DOCUMENTS_DIR = Path("documents/")
DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DOCUMENTS_DIR = Path("temp/")
TEMP_DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter()

@router.get("/get_list")
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
    
@router.post("/get_documents_list")
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
    
@router.post("/new", status_code=201)
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

@router.post("/rename", status_code=201)
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

@router.post("/rename_document", status_code=201)
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
    
@router.post("/upload", status_code=201)
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

@router.delete("/clear_chat", status_code=204)
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

@router.delete("/delete_document", status_code=204)
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

@router.delete("/delete", status_code=204)
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