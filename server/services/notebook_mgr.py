import sqlalchemy as sqla
from services.database import db_session
from services.db_models import Notebooks, Documents, ChatMessage

async def get_notebook_doclen(notebook_id:int) -> int:
    async with db_session() as session:
        query = sqla.select(Documents).where(Documents.notebooks_id == notebook_id)
        result = await session.execute(query)
        documents: list[Documents] = result.scalars().all()
    
    return len(documents)

async def get_notebooks() -> list[Notebooks]:
    async with db_session() as session:
        query = sqla.select(Notebooks)
        result = await session.execute(query)
        notebooks: list[Notebooks] = result.scalars().all()
    
    return notebooks

async def notebook_id_exists(notebook_id:int) -> bool:
    async with db_session() as session:
        query = sqla.select(Notebooks)
        results = await session.execute(query)
        notebooks: list[Notebooks] = results.scalars().all()

        notebook_ids: list[str] = [notebook.id for notebook in notebooks]
    
    return notebook_id in notebook_ids

async def document_id_exists(document_id:int) -> bool:
    async with db_session() as session:
        query = sqla.select(Documents)
        results = await session.execute(query)
        documents: list[Documents] = results.scalars().all()

        document_ids: list[str] = [document.id for document in documents]
    
    return document_id in document_ids