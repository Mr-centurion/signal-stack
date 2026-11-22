import pytest
from unittest.mock import AsyncMock, patch
from backend.services.llm_client import LLMClient, LLMRateLimitError, BaseLLMProvider

class MockRateLimitingProvider(BaseLLMProvider):
    async def generate_json(self, system_prompt, user_prompt, schema_class=None):
        raise LLMRateLimitError("429 Too Many Requests: Quota exhausted on primary model")

class MockSuccessfulProvider(BaseLLMProvider):
    async def generate_json(self, system_prompt, user_prompt, schema_class=None):
        return {"status": "ok", "provider": "alternate", "fallback_success": True}

@pytest.mark.asyncio
async def test_automatic_llm_fallback_on_429():
    """
    User Requirement:
    Add automatic fallback between Gemini and Groq on 429/quota errors,
    with a logged event when it happens.
    """
    client = LLMClient(provider_name="gemini")
    client.providers["gemini"] = MockRateLimitingProvider()
    client.providers["groq"] = MockSuccessfulProvider()
    # Ensure groq provider has api_key set
    client.providers["groq"].api_key = "mock_groq_key"

    # Clear fallback events
    client.fallback_events.clear()

    # Generate JSON
    res = await client.generate_json("system prompt", "user prompt", use_cache=False)

    # 1. Verify alternate provider succeeded
    assert res.get("fallback_success") is True
    assert res.get("provider") == "alternate"

    # 2. Verify fallback event was logged
    assert len(client.fallback_events) >= 1
    event = client.fallback_events[0]
    assert event["from_provider"] == "gemini"
    assert event["to_provider"] == "groq"
    assert "429" in event["reason"]
