import os

import pytest
from dotenv import load_dotenv
from google import genai
from google.genai import types


load_dotenv()


@pytest.mark.asyncio
async def test_gemini_function_response_schema_streams():
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY or GOOGLE_API_KEY is required for this live Gemini schema test.")

    client = genai.Client(api_key=api_key)

    raw_parts = [
        types.Part.from_function_call(name="write_file", args={"path": "foo"})
    ]

    tool_response_parts = [{
        "function_response": {
            "name": "write_file",
            "response": {"result": "success"},
        }
    }]

    contents = [
        {"role": "user", "parts": ["hello"]},
        {"role": "model", "parts": raw_parts},
        {"role": "user", "parts": tool_response_parts},
    ]

    stream = await client.aio.models.generate_content_stream(
        model="gemini-3-flash-preview",
        contents=contents,
        config=types.GenerateContentConfig(
            tools=[types.Tool(function_declarations=[
                types.FunctionDeclaration(
                    name="write_file",
                    description="x",
                    parameters={"type": "object"},
                )
            ])]
        ),
    )

    stream_iter = stream.__aiter__()
    chunk = await stream_iter.__anext__()
    assert chunk is not None
