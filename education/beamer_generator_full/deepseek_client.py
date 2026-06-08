"""OpenAI-compatible streaming client for GPT 5.5 generation."""

from typing import AsyncIterator

import httpx
from openai import AsyncOpenAI


class DeepSeekClient:
    """Legacy class name kept for existing imports."""

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        base_url = base_url.rstrip("/")
        for suffix in ["/v1/chat/completions", "/v1", "/chat/completions"]:
            if base_url.endswith(suffix):
                base_url = base_url[: -len(suffix)]
        if not base_url.endswith("/v1"):
            base_url = base_url + "/v1"

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=httpx.Timeout(120.0, connect=20.0),
        )

    async def stream_generate(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = "gpt-5.5",
        max_tokens: int = 8192,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        stream = await self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
