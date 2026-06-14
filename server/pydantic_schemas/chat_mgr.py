from pydantic import BaseModel, Field

class GenerateLLMResponseRequest(BaseModel):
    notebook_id: str
    model: str
    prompt: str