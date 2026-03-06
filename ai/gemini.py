from __future__ import annotations
import asyncio
import logging
from typing import Any

import google.generativeai as genai
from google.generativeai.types import GenerationConfig

from config import (
    GEMINI_API_KEY,
    MODEL_FLASH_LITE,
    MODEL_FLASH,
    MODEL_PRO,
    API_RETRY_ATTEMPTS,
    API_RETRY_DELAYS,
)

logger = logging.getLogger(__name__)

_configured = False


def _ensure_configured():
    global _configured
    if not _configured:
        genai.configure(api_key=GEMINI_API_KEY)
        _configured = True


def _resolve_model_and_config(
    model_key: str,
) -> tuple[str, GenerationConfig]:
    """Map ТЗ model keys to actual Gemini model names and generation configs."""
    _ensure_configured()

    if model_key == "flash_lite":
        return MODEL_FLASH_LITE, GenerationConfig(temperature=0.3)

    if model_key == "flash":
        return MODEL_FLASH, GenerationConfig(temperature=0.7)

    if model_key.startswith("flash_thinking_"):
        budget = int(model_key.split("_")[-1])
        return MODEL_FLASH, GenerationConfig(
            temperature=0.7,
            thinking_config={"thinking_budget": budget},
        )

    if model_key == "pro":
        return MODEL_PRO, GenerationConfig(temperature=0.7)

    return MODEL_FLASH, GenerationConfig(
        temperature=0.7,
        thinking_config={"thinking_budget": 2000},
    )


async def generate(
    system_prompt: str,
    user_message: str,
    model_key: str = "flash_thinking_2000",
    images: list[Any] | None = None,
) -> str:
    model_name, gen_config = _resolve_model_and_config(model_key)
    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=system_prompt,
        generation_config=gen_config,
        safety_settings={
            "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
            "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
            "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
            "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
        },
    )

    contents = []
    if images:
        contents.extend(images)
    contents.append(user_message)

    last_error = None
    delays = API_RETRY_DELAYS + [0]

    for attempt in range(API_RETRY_ATTEMPTS):
        try:
            response = await asyncio.to_thread(
                model.generate_content, contents
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
    """Transcribe voice message using Gemini's multimodal input."""
    _ensure_configured()
    model = genai.GenerativeModel(
        model_name=MODEL_FLASH,
        generation_config=GenerationConfig(temperature=0.1),
    )

    audio_part = {"mime_type": mime_type, "data": audio_bytes}
    prompt = "Транскрибируй это голосовое сообщение. Верни только текст, без комментариев."

    response = await asyncio.to_thread(
        model.generate_content, [audio_part, prompt]
    )
    return response.text.strip() if response.text else ""
