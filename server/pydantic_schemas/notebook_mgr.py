from pydantic import BaseModel, Field

# Document specific
class UploadDocumentMetadata(BaseModel):
    notebook_id: str

class RenameDocumentRequest(BaseModel):
    document_id: str
    new_name: str

class DeleteDocumentRequest(BaseModel):
    document_id: str

# Notebook specific
class DeleteNotebookRequest(BaseModel):
    notebook_id: str

class NotebookRenameRequest(BaseModel):
    notebook_id: str
    new_name: str
    new_description: str

class NotebookDocumentsRequest(BaseModel):
    notebook_id: str