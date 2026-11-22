import pytest
from pydantic import BaseModel
from backend.services.llm_client import LLMClient, MockProvider

class SampleSchema(BaseModel):
    status: str
    message: str

@pytest.mark.asyncio
async def test_mock_provider_generation():
    client = LLMClient(provider_name="mock")
    res = await client.generate_json(
        system_prompt="Generate interview questions for company",
        user_prompt="Company: Nova Logistics",
    )
    assert "questions" in res
    assert len(res["questions"]) > 0
    assert any(q["category"] == "competitors" for q in res["questions"])

@pytest.mark.asyncio
async def test_provider_switch():
    client = LLMClient(provider_name="mock")
    assert client.provider_name == "mock"
    
    client.set_provider("groq")
    assert client.provider_name == "groq"

    client.set_provider("gemini")
    assert client.provider_name == "gemini"

    with pytest.raises(ValueError):
        client.set_provider("unsupported_provider")

@pytest.mark.asyncio
async def test_schema_validation_in_client():
    client = LLMClient(provider_name="mock")
    res = await client.generate_json(
        system_prompt="Return status check",
        user_prompt="Check ping",
        schema_class=SampleSchema
    )
    assert res["status"] == "ok"
    assert "Mock response generated" in res["message"]
