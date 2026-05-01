from __future__ import annotations

import json

import requests

from app.config import settings
from app.services.ticker_universe import validate_symbol_candidates


def _build_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "symbols": {
                "type": "array",
                "items": {"type": "string"},
            }
        },
        "required": ["symbols"],
    }


def _extract_output_text(payload: dict) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    for item in payload.get("output", []) or []:
        if item.get("type") != "message":
            continue
        for content in item.get("content", []) or []:
            if content.get("type") == "output_text":
                text = content.get("text")
                if isinstance(text, str) and text.strip():
                    return text

    raise RuntimeError("OpenAI did not return a readable structured response.")


def extract_symbols_from_image_data(image_data_url: str) -> list[str]:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured on the server.")

    if not image_data_url.strip().startswith("data:image/"):
        raise RuntimeError("Expected an image data URL for screenshot extraction.")

    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.openai_vision_model,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Read this screenshot and return only valid US stock ticker symbols visible in it. "
                                "Ignore prices, ranks, percentages, dates, RSI values, labels, Chinese text, and company names. "
                                "Prefer the actual ticker text shown in the image. Return JSON only."
                            ),
                        },
                        {
                            "type": "input_image",
                            "image_url": image_data_url,
                            "detail": "high",
                        },
                    ],
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "ticker_symbols",
                    "strict": True,
                    "schema": _build_schema(),
                }
            },
        },
        timeout=settings.openai_vision_timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    structured_text = _extract_output_text(payload)

    try:
        decoded = json.loads(structured_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("OpenAI returned invalid JSON for screenshot extraction.") from exc

    candidates = decoded.get("symbols", [])
    if not isinstance(candidates, list):
        raise RuntimeError("OpenAI returned an unexpected symbol payload.")

    normalized = [str(item).strip().upper() for item in candidates if str(item).strip()]
    return validate_symbol_candidates(normalized)
