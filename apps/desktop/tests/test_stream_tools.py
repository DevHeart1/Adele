import asyncio
import os
import sys

import pytest

if os.environ.get("ADELE_RUN_LIVE_GEMINI_TESTS") != "1" or not os.environ.get("GEMINI_API_KEY"):
    pytest.skip("Live Gemini stream-tools smoke test; set ADELE_RUN_LIVE_GEMINI_TESTS=1 and GEMINI_API_KEY to run.", allow_module_level=True)

sys.path.append(os.path.abspath('.'))

from providers import GeminiProvider
from google.genai import types

async def main():
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        with open('.env', 'r') as f:
            for line in f:
                if line.startswith('GEMINI_API_KEY='):
                    api_key = line.strip().split('=', 1)[1]
    
    print('Testing generate_content_stream...')
    provider = GeminiProvider(api_key=api_key, model='gemini-2.5-pro')
    
    try:
        response_stream = await provider._client.aio.models.generate_content_stream(
            model=provider._model,
            contents='You are a calculator. Tell me 5+3.',
            config=types.GenerateContentConfig(
                tools=[types.Tool(function_declarations=[
                    types.FunctionDeclaration(
                        name='add',
                        description='Add two numbers',
                        parameters={
                            'type': 'OBJECT',
                            'properties': {'a': {'type': 'NUMBER'}, 'b': {'type': 'NUMBER'}},
                            'required': ['a', 'b']
                        }
                    )
                ])]
            )
        )
        async for chunk in response_stream:
            if chunk.candidates and chunk.candidates[0].content and chunk.candidates[0].content.parts:
                for part in chunk.candidates[0].content.parts:
                    if part.function_call:
                        print(f'Function call streamed chunk! {part.function_call}')
                    if part.text:
                        print(f'Text chunk: {part.text}')
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f'Error: {e}')

asyncio.run(main())
