import sqlite3
import sqlalchemy as sqla
import sqlalchemy.ext.asyncio as sqla_async
import sqlalchemy.orm as sqla_orm
from services.db_models import Notebooks, Documents, ChatMessage, Base
import os

DB_PATH = "sqlite+aiosqlite:///databases/database.db"
os.makedirs("./databases", exist_ok=True)
db_engine: sqla_async.AsyncEngine = sqla_async.create_async_engine(
    DB_PATH,
    echo=True,
)

db_session = sqla_async.async_sessionmaker(
    bind=db_engine,
    class_=sqla_async.AsyncSession,
    expire_on_commit=False,
)

metadata = sqla.MetaData()

async def get_db():
    async with db_session() as session:
        yield db_session

async def init_db():
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)