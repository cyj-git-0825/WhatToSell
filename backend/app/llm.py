"""Provider-agnostic LLM access via LiteLLM.

Callers name a task, not a model; the model per task comes from settings, so switching
Claude <-> DeepSeek is an env change. Structured output is requested as JSON and
validated against a pydantic model, which works the same across providers.
"""

import json
import logging
from dataclasses import dataclass
from enum import StrEnum

import litellm
from pydantic import BaseModel, ValidationError

from app.config import get_settings

log = logging.getLogger(__name__)


class LLMTask(StrEnum):
    CLUSTER_NAMING = "cluster_naming"
    OPPORTUNITY = "opportunity"
    VERDICT = "verdict"


def model_for(task: LLMTask) -> str:
    return getattr(get_settings(), f"llm_model_{task.value}")


@dataclass
class LLMUsage:
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


class LLMOutputError(Exception):
    pass


async def structured[T: BaseModel](
    task: LLMTask,
    system: str,
    user: str,
    schema: type[T],
    *,
    max_tokens: int = 4096,
    retries: int = 1,
) -> tuple[T, LLMUsage]:
    """Return `schema` parsed from the model's JSON reply, retrying once with the validation error."""
    model = model_for(task)
    system_full = (
        f"{system}\n\nRespond with a single JSON object matching this JSON Schema, and nothing else:\n"
        f"{json.dumps(schema.model_json_schema(), ensure_ascii=False)}"
    )
    messages = [{"role": "system", "content": system_full}, {"role": "user", "content": user}]
    usage = LLMUsage(model=model, input_tokens=0, output_tokens=0, cost_usd=0.0)

    for attempt in range(retries + 1):
        resp = await litellm.acompletion(model=model, messages=messages, max_tokens=max_tokens)
        usage.input_tokens += resp.usage.prompt_tokens
        usage.output_tokens += resp.usage.completion_tokens
        try:
            usage.cost_usd += litellm.completion_cost(completion_response=resp)
        except Exception:  # unknown pricing for a model is not fatal
            pass

        text = resp.choices[0].message.content or ""
        try:
            return schema.model_validate_json(_strip_fences(text)), usage
        except ValidationError as e:
            log.warning("LLM output failed validation (task=%s, attempt=%d): %s", task, attempt, e)
            messages += [
                {"role": "assistant", "content": text},
                {"role": "user", "content": f"That JSON did not validate:\n{e}\nReturn corrected JSON only."},
            ]
    raise LLMOutputError(f"{task}: model {model} did not return valid {schema.__name__}")


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    return text.strip()
