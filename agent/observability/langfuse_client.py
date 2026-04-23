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
        self._span = None

    def __enter__(self):
        lf = get_client()
        self._span = lf.start_as_current_span(
            name=self.name,
            input=str(self.metadata)[:500],
        )
        self._span.__enter__()
        return self

    def set_output(self, output: Any):
        if self._span:
            try:
                self._span.update(output=str(output)[:2000])
            except Exception:
                pass

    def log_span(self, name: str, input: Any = None, output: Any = None, cost_usd: float = 0):
        lf = get_client()
        try:
            with lf.start_as_current_span(name=name) as span:
                if input:
                    span.update(input=str(input)[:1000])
                if output:
                    span.update(output=str(output)[:1000])
        except Exception:
            pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self._span:
                self._span.__exit__(exc_type, exc_val, exc_tb)
            get_client().flush()
        except Exception:
            pass
        return False

def log_llm_call(trace_id, model, prompt_tokens, completion_tokens, cost_usd, input_text, output_text):
    try:
        lf = get_client()
        lf.flush()
    except Exception:
        pass
