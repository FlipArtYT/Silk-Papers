import ollama
import os
import asyncio
from ollama import AsyncClient

async def chat():
    message = {'role': 'user', 'content': 'How does a graphics card work?'}
    response = await AsyncClient().chat(model='lfm2.5-thinking:1.2b', messages=[message], stream=True)

    print("=== THINKING PROCESS ===")
    async for chunk in response:
        message = chunk.get('message', {})
        
        # Print the thinking process as it generates
        if 'thinking' in message and message['thinking']:
            print(message['thinking'], end='', flush=True)
            
        # Print the final response text as it generates
        elif 'content' in message and message['content']:
            # Visual separator when switching from thinking to content
            if '=== ANSWER ===' not in locals():
                print("\n\n=== ANSWER ===")
                locals()['=== ANSWER ==='] = True
            print(message['content'], end='', flush=True)

asyncio.run(chat())
print("Wait.")