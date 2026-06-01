from fastapi import FastAPI, HTTPException, status, staticfiles
from fastapi.responses import HTMLResponse
import services.database

app = FastAPI()

@app.get("/api/status")
def status():
    return {
        "message": "Success"
    }