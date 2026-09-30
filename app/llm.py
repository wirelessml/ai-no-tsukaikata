"""Gemini 呼び出しの薄いラッパー。

- 既定は Vertex AI モード（Cloud Run 上では ADC＝サービスアカウントで認証。キー不要）
- GEMINI_API_KEY があるときは Gemini API（ローカル確認用）
- LLM_MODE=mock のときは固定応答（テスト・画面確認用）
"""
from __future__ import annotations

import json
import re
from typing import Protocol, TypeVar

from pydantic import BaseModel

from . import config

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    pass


class LLM(Protocol):
    name: str

    def generate(self, schema: type[T], system: str, user: str, *, temperature: float = 0.4) -> tuple[T, dict]:
        """構造化出力を生成する。戻り値は (パース済みモデル, 使用量メタ情報)。"""
        ...


class GeminiLLM:
    def __init__(self) -> None:
        from google import genai  # 遅延import（mockモードでは不要）

        self._genai = genai
        if config.GEMINI_API_KEY:
            self.client = genai.Client(api_key=config.GEMINI_API_KEY)
            self.name = "gemini-api"
        else:
            kwargs = {"vertexai": True, "location": config.GOOGLE_CLOUD_LOCATION}
            if config.GOOGLE_CLOUD_PROJECT:
                kwargs["project"] = config.GOOGLE_CLOUD_PROJECT
            self.client = genai.Client(**kwargs)
            self.name = "vertex-ai"

    def _thinking(self):
        from google.genai import types

        lvl = config.THINKING_LEVEL
        model = config.GEMINI_MODEL
        if lvl == "OFF" or model.startswith("gemini-2.0"):
            return None
        if model.startswith("gemini-2.5"):
            return types.ThinkingConfig(thinking_budget=0 if "flash" in model else 512)
        if lvl in ("MINIMAL", "LOW", "MEDIUM", "HIGH"):
            return types.ThinkingConfig(thinking_level=getattr(types.ThinkingLevel, lvl))
        return None

    def generate(self, schema: type[T], system: str, user: str, *, temperature: float = 0.4) -> tuple[T, dict]:
        from google.genai import types

        cfg = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            max_output_tokens=config.MAX_OUTPUT_TOKENS,
            response_mime_type="application/json",
            response_schema=schema,
            thinking_config=self._thinking(),
            http_options=types.HttpOptions(timeout=config.LLM_TIMEOUT_MS),
        )
        try:
            resp = self.client.models.generate_content(model=config.GEMINI_MODEL, contents=user, config=cfg)
        except Exception as e:  # ネットワーク・権限・クォータなど
            raise LLMError(f"{type(e).__name__}") from e
        text = (resp.text or "").strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
        try:
            parsed = schema.model_validate(json.loads(text))
        except Exception as e:
            raise LLMError("invalid_json") from e
        um = getattr(resp, "usage_metadata", None)
        usage = {
            "prompt_tokens": getattr(um, "prompt_token_count", None),
            "output_tokens": getattr(um, "candidates_token_count", None),
        }
        return parsed, usage


def make_llm() -> LLM:
    if config.LLM_MODE == "mock":
        from .mock_llm import MockLLM

        return MockLLM()
    return GeminiLLM()
