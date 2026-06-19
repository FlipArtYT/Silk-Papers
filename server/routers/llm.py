from fastapi import HTTPException, status, APIRouter
import re
import ollama
import sqlalchemy as sqla
from services.db_models import Notebooks, ChatMessage
from services.database import db_session
from services.chroma_database import query_request
from services.llm import generate_response, generate_chat_response
from pydantic_schemas.chat_mgr import GenerateLLMResponseRequest, LLMChatRequest

router = APIRouter()

@router.get("/list")
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

@router.post("/chat")
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

@router.post("/generate")
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

async def notebook_id_exists(notebook_id:int):
    async with db_session() as session:
        query = sqla.select(Notebooks)
        results = await session.execute(query)
        notebooks: list[Notebooks] = results.scalars().all()

        notebook_ids: list[str] = [notebook.id for notebook in notebooks]
    
    return notebook_id in notebook_ids
    
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