import ollama
import os
import asyncio
from ollama import AsyncClient

SYSTEM_PROMPT = """
You are a 
"""

async def generate_response(prompt: str, model:str):
    response = await AsyncClient().generate(
        model='gemma3', 
        prompt='Erkläre kurz, was eine asynchrone Funktion in Python ist.'
    )

    return response['response']