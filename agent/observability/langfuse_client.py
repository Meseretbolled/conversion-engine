
import os
import time
import uuid
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_client = None

def get_client():
    global _client
    if _client is None:
        try:
            from langfuse import get_client as _get_client
            _client = _get_client()
            logger.info("Langfuse client initialized successfully")
        except Exception as e:
            logger.warning(f"Langfuse client init failed: {e}")
            _client = None
    return _client


def flush():
    """Force flush all pending spans to Langfuse. Call after every pipeline run."""
    lf = get_client()
    if lf:
        try:
            time.sleep(0.5)  # give spans time to close
            lf.flush()
            logger.info("Langfuse flush completed")
        except Exception as e:
            logger.warning(f"Langfuse flush failed: {e}")


class Tracer:
    """
    Context manager for tracing an outreach pipeline run.

    Usage:
        with Tracer("outreach_pipeline", prospect_id="abc") as t:
            t.log_span("step_name", input=..., output=...)
            t.set_output(final_result)
    """

    def __init__(self, name: str, **metadata):
        self.trace_id = str(uuid.uuid4()).replace("-", "")[:32]
        self.name = name
        self.metadata = metadata
        self._start = time.monotonic()
        self._span_ctx = None
        self._span = None

    def __enter__(self):
        lf = get_client()
        if lf:
            try:
                self._span_ctx = lf.start_as_current_observation(
                    as_type="span",
                    name=self.name,
                    input=str(self.metadata)[:500],
                )
                self._span = self._span_ctx.__enter__()
            except Exception as e:
                logger.warning(f"Langfuse span start failed: {e}")
                self._span_ctx = None
                self._span = None
        return self

    def set_output(self, output: Any):
        if self._span:
            try:
                self._span.update(output=str(output)[:2000])
            except Exception as e:
                logger.warning(f"Langfuse set_output failed: {e}")

    def log_span(self, name: str, input: Any = None, output: Any = None, cost_usd: float = 0):
        lf = get_client()
        if lf:
            try:
                with lf.start_as_current_observation(
                    as_type="span",
                    name=name,
                    input=str(input)[:1000] if input else None,
                ) as span:
                    if output:
                        span.update(
                            output=str(output)[:1000],
                            metadata={"cost_usd": cost_usd}
                        )
            except Exception as e:
                logger.warning(f"Langfuse log_span failed: {e}")

    def log_llm_call(self, model: str, prompt_tokens: int,
                     completion_tokens: int, cost_usd: float,
                     input_text: str, output_text: str):
        """Log an LLM generation span inside this trace."""
        lf = get_client()
        if lf:
            try:
                with lf.start_as_current_observation(
                    as_type="generation",
                    name="llm_call",
                    model=model,
                    input=input_text[:2000],
                ) as gen:
                    gen.update(
                        output=output_text[:2000],
                        usage={
                            "input": prompt_tokens,
                            "output": completion_tokens,
                            "total": prompt_tokens + completion_tokens,
                        },
                        metadata={"cost_usd": cost_usd},
                    )
            except Exception as e:
                logger.warning(f"Langfuse log_llm_call failed: {e}")

    def __exit__(self, exc_type, exc_val, exc_tb):
        latency_ms = int((time.monotonic() - self._start) * 1000)
        if self._span:
            try:
                self._span.update(
                    metadata={
                        **self.metadata,
                        "latency_ms": latency_ms,
                        "error": str(exc_val) if exc_val else None,
                    }
                )
            except Exception:
                pass
        if self._span_ctx:
            try:
                self._span_ctx.__exit__(exc_type, exc_val, exc_tb)
            except Exception:
                pass
        # Flush with delay to ensure spans are sent
        flush()
        return False


def log_llm_call(
    trace_id: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float,
    input_text: str,
    output_text: str,
):
    """Standalone LLM call logger outside a Tracer context."""
    lf = get_client()
    if lf:
        try:
            with lf.start_as_current_observation(
                as_type="generation",
                name="llm_call",
                model=model,
                input=input_text[:2000],
            ) as gen:
                gen.update(
                    output=output_text[:2000],
                    usage={
                        "input": prompt_tokens,
                        "output": completion_tokens,
                        "total": prompt_tokens + completion_tokens,
                    },
                    metadata={"cost_usd": cost_usd},
                )
            flush()
        except Exception as e:
            logger.warning(f"Langfuse log_llm_call failed: {e}")