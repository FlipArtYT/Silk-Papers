from langchain_chroma import Chroma
from langchain_core.documents import Document
import chromadb

CHROMA_PATH = "./chroma"

async def insert_pages(collection_id:str, chunks:list[Document]) -> None:
    vector_store = Chroma(
        collection_name=collection_id,
        persist_directory=CHROMA_PATH
    )

    await vector_store.aadd_documents(
        documents=chunks
    )

    print(f"Inserted {len(chunks)} document chunks into {collection_id}")

async def query_request(collection_id:str, query:str, max_results:int=4) -> list:
    vector_store = Chroma(
        collection_name=collection_id,
        persist_directory=CHROMA_PATH
    )

    results = await vector_store.asimilarity_search(query=query, k=max_results)

    return results