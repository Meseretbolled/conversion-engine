import os, time, uuid
from typing import Any, Optional

_client = None

def get_client():
    global _client
    if _client is None:
        try:
            from langfuse import Langfuse
            _client = Langfuse(
                public_key=os.environ.get("LANGFUSE_PUBLIC_KEY", ""),
                secret_key=os.environ.get("LANGFUSE_SECRET_KEY", ""),
                host=os.getenv("LANGFUSE_HOST", "https://eu.cloud.langfuse.com"),
            )
        except Exception:
            _client = None
    return _client

class Tracer:
    def __init__(self, name: str, **metadata):
        self.trace_id = str(uuid.uuid4())
        self.name = name
        self.metadata = metadata
        self._start = time.monotonic()

    def __enter__(self):
        return self

    def set_output(self, output: Any):
        pass

    def log_span(self, name: str, input: Any = None, output: Any = None, cost_usd: float = 0):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            lf = get_client()
            if lf:
                lf.flush()
        except Exception:
            pass
        return False

def log_llm_call(trace_id, model, prompt_tokens, completion_tokens, cost_usd, input_text, output_text):
    try:
        lf = get_client()
        if lf:
            lf.flush()
    except Exception:
        pass
