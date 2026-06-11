import asyncio
import aiofiles
import pathlib
import os
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader

async def split_text(path, content_type) -> list:
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=300,
        chunk_overlap=100,
        length_function=len,
        is_separator_regex=False,
    )

    if not os.path.exists(path):
        raise FileNotFoundError

    if content_type in "application/pdf":
        loader = PyPDFLoader(path)
        document = loader.load_and_split()
        split_docs = await text_splitter.atransform_documents(document)

        return split_docs
    
    elif content_type in "text/plain":
        async with aiofiles.open(path, mode='r', encoding='utf-8') as f:
            content = f.read(path)

        document = [Document(page_content=content, metadata={"source": path})]
        
        split_docs = await text_splitter.atransform_documents(document)

        return split_docs
