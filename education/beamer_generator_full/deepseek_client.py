"""DeepSeek API 灏佽 鈥?浣跨敤 openai SDK 鍏煎鎺ュ彛锛堝紓姝ユ祦寮忚皟鐢級"""
import httpx
from typing import AsyncIterator
from openai import AsyncOpenAI


class DeepSeekClient:
    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com"):
        # 鑷姩淇 base_url锛氬幓鎺夋湯灏剧殑 /v1/chat/completions 绛夎矾寰?        base_url = base_url.rstrip("/")
        for suffix in ["/v1/chat/completions", "/v1", "/chat/completions"]:
            if base_url.endswith(suffix):
                base_url = base_url[: -len(suffix)]
        # openai SDK 闇€瑕?/v1 鍚庣紑
        if not base_url.endswith("/v1"):
            base_url = base_url + "/v1"

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=httpx.Timeout(120.0, connect=20.0),  # 杩炴帴瓒呮椂30s锛屾€昏秴鏃?00s
        )

    async def stream_generate(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = "deepseek-chat",
        max_tokens: int = 8192,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        """娴佸紡璋冪敤 DeepSeek API锛岄€愬潡 yield 鏂囨湰"""
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
