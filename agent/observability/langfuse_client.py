import os, time, uuid
from typing import Any, Optional
from langfuse import Langfuse

_client: Optional[Langfuse] = None

def get_client() -> Langfuse:
    global _client
    if _client is None:
        _client = Langfuse(
            public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
            secret_key=os.environ["LANGFUSE_SECRET_KEY"],
            host=os.getenv("LANGFUSE_HOST", "https://eu.cloud.langfuse.com"),
        )
    return _client


class Tracer:
    def __init__(self, name: str, **metadata):
        self.trace_id = str(uuid.uuid4())
        self.name = name
        self.metadata = metadata
        self._start = time.monotonic()
        self._trace = None

    def __enter__(self):
        lf = get_client()
        self._trace = lf.trace(id=self.trace_id, name=self.name, metadata=self.metadata)
        return self

    def set_output(self, output: Any):
        if self._trace:
            self._trace.update(output=str(output)[:2000])

    def log_span(self, name: str, input: Any = None, output: Any = None, cost_usd: float = 0):
        if self._trace:
            self._trace.span(
                name=name,
                input=str(input)[:1000] if input else None,
                output=str(output)[:1000] if output else None,
                metadata={"cost_usd": cost_usd},
            )

    def __exit__(self, exc_type, exc_val, exc_tb):
        latency_ms = int((time.monotonic() - self._start) * 1000)
        if self._trace:
            self._trace.update(metadata={**self.metadata, "latency_ms": latency_ms, "error": str(exc_val) if exc_val else None})
        get_client().flush()
        return False


def log_llm_call(trace_id, model, prompt_tokens, completion_tokens, cost_usd, input_text, output_text):
    lf = get_client()
    lf.generation(
        trace_id=trace_id,
        name="llm_call",
        model=model,
        usage={"input": prompt_tokens, "output": completion_tokens},
        metadata={"cost_usd": cost_usd},
        input=input_text[:2000],
        output=output_text[:2000],
    )
    lf.flush()
