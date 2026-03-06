from __future__ import annotations

import asyncio
import logging
from typing import Any

from google import genai
from google.genai import types

from config import (
    GEMINI_API_KEY,
    MODEL_FLASH_LITE,
    MODEL_FLASH,
    MODEL_PRO,
    API_RETRY_ATTEMPTS,
    API_RETRY_DELAYS,
)

logger = logging.getLogger(__name__)

_client: genai.Client | None = None

SAFETY_OFF = [
    types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
    types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
    types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF"),
    types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
]


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def _build_config(
    model_key: str,
    system_prompt: str,
) -> tuple[str, types.GenerateContentConfig]:
    base = dict(
        system_instruction=system_prompt,
        safety_settings=SAFETY_OFF,
    )

    if model_key == "flash_lite":
        return MODEL_FLASH_LITE, types.GenerateContentConfig(
            **base, temperature=0.3,
        )

    if model_key == "flash":
        return MODEL_FLASH, types.GenerateContentConfig(
            **base, temperature=0.7,
        )

    if model_key.startswith("flash_thinking_"):
        budget = int(model_key.split("_")[-1])
        return MODEL_FLASH, types.GenerateContentConfig(
            **base,
            temperature=0.7,
            thinking_config=types.ThinkingConfig(thinking_budget=budget),
        )

    if model_key == "pro":
        return MODEL_PRO, types.GenerateContentConfig(
            **base, temperature=0.7,
        )

    return MODEL_FLASH, types.GenerateContentConfig(
        **base,
        temperature=0.7,
        thinking_config=types.ThinkingConfig(thinking_budget=2000),
    )


async def generate(
    system_prompt: str,
    user_message: str,
    model_key: str = "flash_thinking_2000",
    images: list[Any] | None = None,
) -> str:
    client = _get_client()
    model_name, config = _build_config(model_key, system_prompt)

    contents: list[Any] = []
    if images:
        contents.extend(images)
    contents.append(user_message)

    last_error = None
    delays = API_RETRY_DELAYS + [0]

    for attempt in range(API_RETRY_ATTEMPTS):
        try:
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            )
            if response.text:
                return response.text.strip()
            logger.warning("Empty response from Gemini on attempt %d", attempt + 1)
            return ""
        except Exception as e:
            last_error = e
            logger.error(
                "Gemini API error (attempt %d/%d, model=%s): %s",
                attempt + 1, API_RETRY_ATTEMPTS, model_name, e,
            )
            if attempt < API_RETRY_ATTEMPTS - 1:
                await asyncio.sleep(delays[attempt])

    raise last_error or RuntimeError("Gemini API failed after retries")


async def generate_json(
    system_prompt: str,
    user_message: str,
    model_key: str = "flash_lite",
) -> str:
    return await generate(system_prompt, user_message, model_key)


async def transcribe_voice(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    client = _get_client()
    audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)

    response = await client.aio.models.generate_content(
        model=MODEL_FLASH,
        contents=[
            audio_part,
            "Транскрибируй это голосовое сообщение. Верни только текст, без комментариев.",
        ],
        config=types.GenerateContentConfig(temperature=0.1),
    )
    return response.text.strip() if response.text else ""
