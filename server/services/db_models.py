from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase

class Base(DeclarativeBase):
    pass

class Notebooks(Base):
    __tablename__ = "notebooks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, unique=True)
    name: Mapped[str] = mapped_column(index=True)
    description: Mapped[str] = mapped_column(index=True)

class Documents(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(index=True, primary_key=True, autoincrement=True, unique=True)
    notebooks_id: Mapped[int] = mapped_column(index=True)
    filename: Mapped[str] = mapped_column(index=True)
    file_type: Mapped[str] = mapped_column(index=True)
    status: Mapped[bool]
    chroma_collection_id: Mapped[str] = mapped_column(index=True)

class ChatMessage(Base):
    __tablename__ = "chat_message"

    id: Mapped[int] = mapped_column(index=True, primary_key=True, autoincrement=True, unique=True)
    notebooks_id: Mapped[int] = mapped_column(index=True)
    role: Mapped[str] = mapped_column(index=True)
    content: Mapped[str] = mapped_column(index=True)
    model_used: Mapped[str] = mapped_column(index=True)