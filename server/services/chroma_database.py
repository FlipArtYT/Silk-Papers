import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter

DATA_PATH = "data"
CHROMA_PATH = "chroma_db"

chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)


async def insert_pages(collection_id:str, pages:list):
    collection = chroma_client.get_or_create_collection(name="collection_id")
    chunk_data = []
    documents = []
    metadata = []
    ids = []
    
    for i, page in enumerate(pages):
        print(f"Splitting page: {i+1}/{len(pages)}")
        chunks = await split_text(page.page_text)
        
        for chunk in chunks:
            chunk_data.append({"url":page.url, "title":page.title, "page_content":chunk})

    for i, chunk in enumerate(chunk_data):
        documents.append(chunk["page_content"])
        ids.append(f"ID{i}")
        metadata.append({"url":chunk["url"], "title":chunk["title"]})

    collection.upsert(
        documents=documents,
        metadatas=metadata,
        ids=ids,
    )

    print("Success!")

async def split_text(document):
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=300,
        chunk_overlap=100,
        length_function=len,
        is_separator_regex=False
    )

    chunks = await text_splitter.atransform_documents(document)
    
    return chunks