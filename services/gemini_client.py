import json
import logging

from google import genai
from google.genai import types

from config import GEMINI_API_KEY

MODEL_NAME = "gemini-3.5-flash"
_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


def generate_json(prompt, system_instruction, temperature=0.2):
    if _client is None:
        return []

    try:
        response = _client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                temperature=temperature,
            ),
        )
        return json.loads(response.text or "[]")
    except Exception as error:
        logging.warning("Gemini request failed: %s", error)
        return []
