from pydantic import BaseModel, Field

class UploadDocumentMetadata(BaseModel):
    notebook_id: str