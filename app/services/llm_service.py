"""LLM calls with structured JSON outputs (Groq or OpenAI)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    BadRequestError,
)
from openai import AuthenticationError as ProviderAuthenticationError
from openai import RateLimitError as ProviderRateLimitError
from pydantic import BaseModel, ValidationError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.core.config import PROJECT_ROOT, get_settings
from app.models.schemas import EmailAnalysisResult, ReplyGenerationResult
from app.utils.json_extract import extract_json_object
from app.utils.reply_format import prepare_reply_text

TModel = TypeVar("TModel", bound=BaseModel)

_PROMPTS_DIR = PROJECT_ROOT / "app" / "prompts"
_GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class LLMServiceError(RuntimeError):
    """Business error while calling the LLM."""


def _is_insufficient_quota(exc: ProviderRateLimitError) -> bool:
    """Detect billing / insufficient_quota (mostly OpenAI)."""

    response = getattr(exc, "response", None)
    if response is None:
        return False
    try:
        payload = response.json()
    except Exception:
        return False
    err = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(err, dict):
        return False
    return (
        err.get("code") == "insufficient_quota"
        or err.get("type") == "insufficient_quota"
    )


def _rate_limit_user_message(exc: ProviderRateLimitError, *, provider: str) -> str:
    """User-facing message for HTTP 429 / quota issues."""

    label = "Groq" if provider == "groq" else "OpenAI"
    if _is_insufficient_quota(exc):
        if provider == "openai":
            return (
                "OpenAI billing or quota insufficient (insufficient_quota). "
                "See https://platform.openai.com/account/billing"
            )
        return (
            "Groq rate limit or quota reached. Check "
            "https://console.groq.com/settings/limits and your plan."
        )
    return (
        f"Rate limit reached ({label}, HTTP 429). "
        "Retry shortly or review your account limits."
    )


def _auth_failure_message(*, provider: str) -> str:
    """Message when the API key is rejected."""

    if provider == "groq":
        return "Groq API key rejected. Check GROQ_API_KEY (console.groq.com/keys)."
    return "OpenAI API key rejected. Check OPENAI_API_KEY."


def _read_prompt(filename: str) -> str:
    """Load a prompt file from `app/prompts`."""

    path = _PROMPTS_DIR / filename
    if not path.is_file():
        raise LLMServiceError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


def _schema_contract(schema: type[BaseModel]) -> str:
    """JSON Schema contract passed to the model (Groq / fallback)."""

    return json.dumps(schema.model_json_schema(), ensure_ascii=False, indent=2)


class LLMService:
    """Async facade for structured analysis and replies."""

    def __init__(self, client: AsyncOpenAI | None = None) -> None:
        settings = get_settings()
        self._settings = settings
        if client is not None:
            self._client = client
        elif settings.llm_provider == "groq":
            self._client = AsyncOpenAI(
                api_key=settings.groq_api_key or None,
                base_url=_GROQ_BASE_URL,
            )
        else:
            self._client = AsyncOpenAI(api_key=settings.openai_api_key or None)

    @property
    def _provider(self) -> str:
        """Short name of the active provider."""

        return self._settings.llm_provider

    @property
    def _model(self) -> str:
        """Model id for the active provider."""

        if self._settings.llm_provider == "groq":
            return self._settings.groq_model
        return self._settings.openai_model

    def _ensure_api_key(self) -> None:
        """Ensure an API key is configured for the selected provider."""

        if self._settings.llm_provider == "groq":
            if not self._settings.groq_api_key.strip():
                raise LLMServiceError(
                    "GROQ_API_KEY is missing. Add it to `.env` "
                    "(https://console.groq.com/keys).",
                )
            return
        if not self._settings.openai_api_key.strip():
            raise LLMServiceError(
                "OPENAI_API_KEY is missing while LLM_PROVIDER=openai.",
            )

    def _analysis_instructions(self) -> str:
        """Build system instructions for full analysis."""

        classification = _read_prompt("classification_prompt.txt")
        extraction = _read_prompt("extraction_prompt.txt")
        return (
            "You are an enterprise inbox assistant. Follow ALL instructions below.\n\n"
            f"{classification.strip()}\n\n---\n\n{extraction.strip()}\n\n"
            "Return ONLY structured data matching the provided schema."
        )

    def _reply_instructions(self) -> str:
        """Instructions for a standalone reply."""

        return _read_prompt("reply_prompt.txt").strip()

    async def _groq_structured_completion(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: type[TModel],
    ) -> TModel:
        """Groq: completion + JSON extraction + Pydantic validation."""

        contract = _schema_contract(schema)
        augmented_system = (
            f"{system_prompt}\n\n"
            "Respond with a single JSON object ONLY (no markdown fences, no prose). "
            "The JSON must validate against this JSON Schema "
            "(respect enums and required fields):\n"
            f"{contract}"
        )
        messages = [
            {"role": "system", "content": augmented_system},
            {"role": "user", "content": user_prompt},
        ]
        base_kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.55 if schema is ReplyGenerationResult else 0.1,
            "timeout": self._settings.llm_timeout_seconds,
        }
        try:
            try:
                completion = await self._client.chat.completions.create(
                    **base_kwargs,
                    response_format={"type": "json_object"},
                )
            except BadRequestError:
                completion = await self._client.chat.completions.create(
                    **base_kwargs,
                )
        except ProviderAuthenticationError as exc:
            raise LLMServiceError(_auth_failure_message(provider="groq")) from exc
        except ProviderRateLimitError:
            raise
        except (APIConnectionError, APITimeoutError) as exc:
            raise LLMServiceError(
                "Could not reach Groq (network error or timeout).",
            ) from exc

        content = completion.choices[0].message.content or ""
        try:
            payload = extract_json_object(content)
        except (ValueError, json.JSONDecodeError) as exc:
            raise LLMServiceError(
                "Invalid or unreadable JSON returned by Groq.",
            ) from exc
        try:
            return schema.model_validate(payload)
        except ValidationError as exc:
            raise LLMServiceError(
                "Model output does not match the expected schema.",
            ) from exc

    async def _openai_structured_completion(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: type[TModel],
    ) -> TModel:
        """OpenAI: parse() or strict json_schema."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        temp = 0.55 if schema is ReplyGenerationResult else 0.1
        try:
            parser = getattr(self._client.chat.completions, "parse", None)
            if callable(parser):
                completion = await parser(
                    model=self._model,
                    messages=messages,
                    response_format=schema,
                    timeout=self._settings.llm_timeout_seconds,
                    temperature=temp,
                )
                parsed_obj = completion.choices[0].message.parsed
                if parsed_obj is None:
                    raise LLMServiceError("Empty LLM response after parsing.")
                return parsed_obj

            json_schema: dict[str, Any] = {
                "name": schema.__name__,
                "schema": schema.model_json_schema(),
                "strict": True,
            }
            completion = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                response_format={
                    "type": "json_schema",
                    "json_schema": json_schema,
                },
                timeout=self._settings.llm_timeout_seconds,
                temperature=temp,
            )
            raw_content = completion.choices[0].message.content or ""
            payload = json.loads(raw_content)
            return schema.model_validate(payload)
        except ProviderAuthenticationError as exc:
            raise LLMServiceError(_auth_failure_message(provider="openai")) from exc
        except ProviderRateLimitError as exc:
            if _is_insufficient_quota(exc):
                raise LLMServiceError(
                    _rate_limit_user_message(exc, provider="openai"),
                ) from exc
            raise
        except (APIConnectionError, APITimeoutError) as exc:
            raise LLMServiceError(
                "Could not reach OpenAI (network error or timeout).",
            ) from exc
        except json.JSONDecodeError as exc:
            raise LLMServiceError(
                "Invalid JSON returned by the model.",
            ) from exc
        except ValidationError as exc:
            raise LLMServiceError(
                "Model output does not match the expected schema.",
            ) from exc

    @retry(
        reraise=True,
        stop=stop_after_attempt(max(1, get_settings().llm_max_retries)),
        wait=wait_exponential_jitter(initial=1, max=20),
        retry=retry_if_exception_type(ProviderRateLimitError),
    )
    async def _parse_response(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: type[TModel],
    ) -> TModel:
        """Dispatch to the configured provider and validate output."""

        if self._settings.llm_provider == "groq":
            return await self._groq_structured_completion(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema=schema,
            )
        return await self._openai_structured_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema=schema,
        )

    async def analyze_email(self, *, sender: str, subject: str, body: str) -> EmailAnalysisResult:
        """Produce the full structured analysis."""

        self._ensure_api_key()
        user_prompt = (
            "Analyze the following email.\n"
            f"FROM: {sender}\n"
            f"SUBJECT: {subject}\n"
            "BODY:\n"
            f"{body.strip()}"
        )
        try:
            result = await self._parse_response(
                system_prompt=self._analysis_instructions(),
                user_prompt=user_prompt,
                schema=EmailAnalysisResult,
            )
        except ProviderRateLimitError as exc:
            raise LLMServiceError(
                _rate_limit_user_message(exc, provider=self._provider),
            ) from exc
        return result.model_copy(
            update={"suggested_reply": prepare_reply_text(result.suggested_reply)},
        )

    async def generate_reply(
        self,
        *,
        sender: str,
        subject: str,
        body: str,
        tone: str,
    ) -> str:
        """Generate only a professional reply body."""

        self._ensure_api_key()
        system_prompt = (
            f"{self._reply_instructions()}\n"
            f"Desired tone: {tone}."
        )
        user_prompt = (
            "Compose a reply to this email.\n"
            f"FROM: {sender}\n"
            f"SUBJECT: {subject}\n"
            "BODY:\n"
            f"{body.strip()}"
        )
        try:
            result = await self._parse_response(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema=ReplyGenerationResult,
            )
        except ProviderRateLimitError as exc:
            raise LLMServiceError(
                _rate_limit_user_message(exc, provider=self._provider),
            ) from exc
        return prepare_reply_text(result.suggested_reply.strip())


_llm_singleton: LLMService | None = None


def get_llm_service() -> LLMService:
    """Return the shared LLM service instance."""

    global _llm_singleton
    if _llm_singleton is None:
        _llm_singleton = LLMService()
    return _llm_singleton
