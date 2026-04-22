import os, time
from typing import Optional
from openai import OpenAI
from observability.langfuse_client import log_llm_call

MODEL_COSTS = {
    "deepseek/deepseek-chat":       {"input": 0.14,  "output": 0.28},
    "qwen/qwen-2.5-72b-instruct":   {"input": 0.35,  "output": 0.40},
    "anthropic/claude-sonnet-4-6":  {"input": 3.00,  "output": 15.00},
}

_client: Optional[OpenAI] = None

def get_llm_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ["OPENROUTER_API_KEY"],
        )
    return _client


def chat(messages, system="", model=None, temperature=0.3, max_tokens=1024, trace_id=None):
    model = model or os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat")
    full_messages = []
    if system:
        full_messages.append({"role": "system", "content": system})
    full_messages.extend(messages)

    client = get_llm_client()
    t0 = time.monotonic()
    response = client.chat.completions.create(
        model=model,
        messages=full_messages,
        temperature=temperature,
        max_tokens=max_tokens,
        extra_headers={"HTTP-Referer": "https://tenacious-ce.local", "X-Title": "Tenacious CE"},
    )
    latency_ms = int((time.monotonic() - t0) * 1000)
    text = response.choices[0].message.content or ""
    pt = response.usage.prompt_tokens
    ct = response.usage.completion_tokens
    rates = MODEL_COSTS.get(model, {"input": 1.0, "output": 1.0})
    cost_usd = (pt * rates["input"] + ct * rates["output"]) / 1_000_000
    usage = {"model": model, "prompt_tokens": pt, "completion_tokens": ct, "cost_usd": round(cost_usd, 6), "latency_ms": latency_ms}
    if trace_id:
        log_llm_call(trace_id, model, pt, ct, cost_usd, str(full_messages), text)
    return text, usage
