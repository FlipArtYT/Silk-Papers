from langchain_chroma import Chroma
from langchain_core.documents import Document

async def insert_pages(collection_id:str, chunks:list[Document]):
    vector_store = Chroma(
        collection_name=collection_id,
        persist_directory="./chroma"
    )

    await vector_store.aadd_documents(
        documents=chunks
    )

    print(f"Inserted {len(chunks)} document chunks into {collection_id}")