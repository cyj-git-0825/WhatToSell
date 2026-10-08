from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app import llm


class Clusters(BaseModel):
    titles: list[str]


def _resp(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
    )


@pytest.fixture
def replies(monkeypatch):
    queue: list[str] = []
    calls: list[dict] = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs)
        return _resp(queue.pop(0))

    monkeypatch.setattr(llm.litellm, "acompletion", fake_acompletion)
    monkeypatch.setattr(llm.litellm, "completion_cost", lambda **_: 0.001)
    return queue, calls


async def test_parses_fenced_json_and_routes_model(replies, monkeypatch):
    queue, calls = replies
    monkeypatch.setenv("LLM_MODEL_CLUSTER_NAMING", "deepseek/deepseek-chat")
    llm.get_settings.cache_clear()
    queue.append('```json\n{"titles": ["breaks after a week"]}\n```')

    out, usage = await llm.structured(llm.LLMTask.CLUSTER_NAMING, "sys", "user", Clusters)

    llm.get_settings.cache_clear()
    assert out.titles == ["breaks after a week"]
    assert calls[0]["model"] == "deepseek/deepseek-chat"
    assert usage.input_tokens == 10 and usage.cost_usd == 0.001


async def test_retries_once_with_validation_error(replies):
    queue, calls = replies
    queue += ['{"titles": "not a list"}', '{"titles": ["ok"]}']

    out, usage = await llm.structured(llm.LLMTask.VERDICT, "sys", "user", Clusters)

    assert out.titles == ["ok"]
    assert len(calls) == 2
    assert "did not validate" in calls[1]["messages"][-1]["content"]
    assert usage.input_tokens == 20


async def test_gives_up_after_retries(replies):
    queue, _ = replies
    queue += ["nope", "still nope"]

    with pytest.raises(llm.LLMOutputError):
        await llm.structured(llm.LLMTask.VERDICT, "sys", "user", Clusters)
