# 📝 Silk-Papers
![Papers logo](/assets/papers.png)
<br>
A local and private NotebookLM alternative. Currently very experimental.

## ⭐ Features
- Easily chat with an AI assistant about a stack of documents
- Manage notebooks easily using the WebUI (not implemented yet)

## ⚙️ Requirements
- `fastapi[standard]`
- `ollama` (pip and system-wide)
- `langchain`
- `langchain_community`
- `langchain_text_splitters`
- `langchain_chroma`
- `chromadb`
- `sqlalchemy[asyncio]`
- `aiosqlite`
- `python-dotenv`
- `aioshutil`
- `aiofiles`
- `bs4`
- `pypdf`

## 🚀 How to run
To use this web server, simply run it using this command:
```
fastapi run main.py
```

## 🗺️ API Endpoints
- `/api/status/`: Returns a message string
- `/api/notebooks/get_list`: Returns a list of notebooks
- `/api/notebooks/get_documents_list`: Returns a list of documents in a notebook
- `/api/notebooks/new`: Creates a new notebook
- `/api/notebooks/rename`: Renames an existing notebook
- `/api/notebooks/rename_document`: Renames an existing document
- `/api/notebooks/upload`: Uploads a PDF file and saves it to the server
- `/api/notebooks/clear_chat`: Clears chat within a notebook
- `/api/notebooks/delete_document`: Deletes a document
- `/api/notebooks/delete`: Deletes a notebook including their documents
- `/api/llm/list`: Lists locally available LLMs
- `/api/llm/chat`: Generates a response using Ollama and document chunks from RAG with previous chat messages in a notebook
- `/api/llm/generate`: Generates a response using Ollama and document chunks from RAG

## 📃 To-do
- [x] Database Setup (`sqlite3`)
- [x] Document upload
- [x] Setup LLM (`ollama`)
- [x] Setup chat and RAG (`chromadb` and `langchain`)
- [x] Multiple Notebook support
- [x] Finish base API endpoints
- [ ] Split main script into routers
- [ ] Multiple chats within a notebook
- [ ] WebUI
- [ ] Ollama Cloud integration
- [ ] Website upload and direct upload from other external sources
- [ ] Podcast feature inspired by NotebookLM

## 🔜 Transfer to the Silk Project Organisation
This project will likely be transferred to the Silk Project organisation after finishing the WebUI.
