"""
eval/tau2_runner.py
Wrapper around τ²-Bench retail domain for Tenacious Conversion Engine.
Writes results to eval/score_log.json and eval/trace_log.jsonl.
Langfuse tracing optional (skipped if LANGFUSE keys not set).

Usage:
    # From repo root — tau2-bench must be cloned at ../tau2-bench/
    python eval/tau2_runner.py --tasks dev --trials 5 --tag baseline
    python eval/tau2_runner.py --tasks dev --trials 1 --tag repro_check --num-tasks 3

Requirements (install once):
    cd ../tau2-bench && uv sync   # or: pip install -e .
    # Set OPENROUTER_API_KEY (or any LiteLLM-supported key) in your .env
"""

import argparse
import json
import math
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

# ── paths ──────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent
EVAL_DIR = REPO_ROOT / "eval"
TAU2_DIR = Path(os.getenv("TAU2_DIR", str(REPO_ROOT.parent / "tau2-bench")))
SCORE_LOG = EVAL_DIR / "score_log.json"
TRACE_LOG = EVAL_DIR / "trace_log.jsonl"

# Dev partition: first 30 tasks (indices 0–29).
# Held-out partition: provided by program staff (indices 30–49 by default).
DEV_TASK_RANGE = (0, 29)
HELD_OUT_TASK_RANGE = (30, 49)

# Published τ²-Bench retail pass@1 reference (Feb 2026 leaderboard, GPT-5 class)
PUBLISHED_REFERENCE = 0.42


# ── 95% CI helper (Wilson score interval) ──────────────────────────────
def wilson_ci(successes: int, n: int, z: float = 1.96):
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    spread = (z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))) / denom
    return (max(0.0, round(centre - spread, 4)), min(1.0, round(centre + spread, 4)))


# ── load / save score log ───────────────────────────────────────────────
def load_score_log():
    if SCORE_LOG.exists():
        return json.loads(SCORE_LOG.read_text())
    return []


def save_score_log(entries):
    SCORE_LOG.write_text(json.dumps(entries, indent=2))


def append_trace(trace: dict):
    with open(TRACE_LOG, "a") as f:
        f.write(json.dumps(trace) + "\n")


# ── LLM model resolution (LiteLLM / OpenRouter naming) ─────────────────
MODEL_ALIASES = {
    # dev-tier defaults (cheap)
    "deepseek":  "openrouter/deepseek/deepseek-chat",
    "qwen3":     "openrouter/qwen/qwen-2.5-72b-instruct",
    "qwen3-80b": "openrouter/qwen/qwq-32b",   # closest available via OpenRouter
    # eval-tier
    "claude-sonnet": "openrouter/anthropic/claude-sonnet-4-6",
    "gpt-4.1":  "gpt-4.1",  # direct via OpenAI key
}


def resolve_model(alias: str) -> str:
    return MODEL_ALIASES.get(alias, alias)


# ── run τ²-Bench via subprocess ─────────────────────────────────────────
def run_tau2(
    domain: str,
    agent_model: str,
    user_model: str,
    num_trials: int,
    task_ids: list[int] | None,
    num_tasks: int | None,
    save_to: str,
) -> dict:
    """
    Calls `tau2 run` as a subprocess.
    Returns parsed results dict from the saved JSON file, or raises on failure.
    """
    if not TAU2_DIR.exists():
        raise FileNotFoundError(
            f"tau2-bench not found at {TAU2_DIR}. "
            f"Clone it: git clone https://github.com/sierra-research/tau2-bench {TAU2_DIR}"
        )

    cmd = [
        sys.executable, "-m", "tau2", "run",   # use 'tau2' if installed in PATH
        "--domain", domain,
        "--agent-llm", agent_model,
        "--user-llm", user_model,
        "--num-trials", str(num_trials),
        "--save-to", save_to,
    ]
    if task_ids:
        cmd += ["--task-ids"] + [str(t) for t in task_ids]
    elif num_tasks:
        cmd += ["--num-tasks", str(num_tasks)]

    # Try `tau2` CLI first; fall back to python -m tau2
    env = {**os.environ}
    # Ensure OPENROUTER_API_KEY is forwarded as OPENAI_API_KEY for LiteLLM
    if "OPENROUTER_API_KEY" in env and "OPENAI_API_KEY" not in env:
        env["OPENAI_API_KEY"] = env["OPENROUTER_API_KEY"]
        env["OPENAI_API_BASE"] = "https://openrouter.ai/api/v1"

    print(f"\n▶ Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=str(TAU2_DIR),
        env=env,
        capture_output=False,  # stream output so progress is visible
    )
    if result.returncode != 0:
        # Try alternate invocation
        cmd[0:2] = ["tau2"]
        result = subprocess.run(cmd, cwd=str(TAU2_DIR), env=env)
        if result.returncode != 0:
            raise RuntimeError(f"tau2 run failed with exit code {result.returncode}")

    # Find the results file tau2 saved
    sim_dir = TAU2_DIR / "data" / "simulations"
    candidates = sorted(sim_dir.glob(f"{save_to}*.json"), key=os.path.getmtime, reverse=True)
    if not candidates:
        # tau2 may save with timestamp suffix
        candidates = sorted(sim_dir.glob("*.json"), key=os.path.getmtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No results JSON found in {sim_dir} after run.")
    return json.loads(candidates[0].read_text())


# ── parse pass@1 from tau2 results ─────────────────────────────────────
def extract_pass_at_1(results_data: dict) -> tuple[float, int, int]:
    """Returns (pass_at_1, successes, total_trials)."""
    # tau2 results format: results_data["results"][domain]["pass_1"]
    # or flat structure with per-task records
    try:
        for domain_key in results_data.get("results", {}):
            v = results_data["results"][domain_key].get("pass_1")
            if v is not None:
                # pass_1 is expressed as percentage 0–100 or fraction 0–1
                frac = v / 100.0 if v > 1.0 else v
                # Approximate successes from fraction and task count
                tasks = results_data.get("num_tasks", 30)
                trials = results_data.get("num_trials", 5)
                total = tasks * trials
                successes = round(frac * total)
                return (round(frac, 4), successes, total)
    except Exception:
        pass

    # Fallback: count per-task pass arrays directly
    trajectories = results_data.get("trajectories", [])
    if trajectories:
        passed = sum(1 for t in trajectories if t.get("reward", 0) == 1.0)
        total = len(trajectories)
        return (round(passed / max(total, 1), 4), passed, total)

    return (0.0, 0, 0)


# ── main runner ─────────────────────────────────────────────────────────
def run_baseline(args):
    run_id = str(uuid.uuid4())[:8]
    timestamp = datetime.utcnow().isoformat()

    # Resolve task range
    partition = args.tasks
    if partition == "dev":
        task_ids = list(range(DEV_TASK_RANGE[0], DEV_TASK_RANGE[1] + 1))
    elif partition == "held_out":
        task_ids = list(range(HELD_OUT_TASK_RANGE[0], HELD_OUT_TASK_RANGE[1] + 1))
    else:
        task_ids = None  # all tasks

    # Limit for quick tests
    if args.num_tasks and task_ids:
        task_ids = task_ids[: args.num_tasks]
    elif args.num_tasks:
        task_ids = list(range(args.num_tasks))

    agent_model = resolve_model(args.agent_model)
    user_model = resolve_model(args.user_model)
    save_to = f"{args.tag}_{run_id}"

    print(f"\n{'='*60}")
    print(f"τ²-Bench Retail Baseline Run")
    print(f"  Run ID:       {run_id}")
    print(f"  Tag:          {args.tag}")
    print(f"  Partition:    {partition} ({len(task_ids) if task_ids else 'all'} tasks)")
    print(f"  Trials:       {args.trials}")
    print(f"  Agent model:  {agent_model}")
    print(f"  User model:   {user_model}")
    print(f"{'='*60}\n")

    t0 = time.monotonic()
    raw_results = run_tau2(
        domain="retail",
        agent_model=agent_model,
        user_model=user_model,
        num_trials=args.trials,
        task_ids=task_ids,
        num_tasks=None,  # already sliced into task_ids
        save_to=save_to,
    )
    wall_seconds = time.monotonic() - t0

    pass_at_1, successes, total = extract_pass_at_1(raw_results)
    ci_lo, ci_hi = wilson_ci(successes, total)
    delta_vs_published = round(pass_at_1 - PUBLISHED_REFERENCE, 4)

    entry = {
        "run_id": run_id,
        "tag": args.tag,
        "timestamp": timestamp,
        "domain": "retail",
        "partition": partition,
        "num_tasks": len(task_ids) if task_ids else "all",
        "num_trials": args.trials,
        "agent_model": agent_model,
        "user_model": user_model,
        "pass_at_1": pass_at_1,
        "successes": successes,
        "total_trials": total,
        "ci_95_low": ci_lo,
        "ci_95_high": ci_hi,
        "ci_width": round(ci_hi - ci_lo, 4),
        "published_reference": PUBLISHED_REFERENCE,
        "delta_vs_published": delta_vs_published,
        "wall_seconds": round(wall_seconds, 1),
        "p50_latency_ms": None,  # populated from traces if available
        "p95_latency_ms": None,
        "raw_results_path": str(save_to),
    }

    # Write to score_log
    score_log = load_score_log()
    score_log.append(entry)
    save_score_log(score_log)

    # Write traces to trace_log.jsonl
    trajectories = raw_results.get("trajectories", [])
    for traj in trajectories:
        trace_record = {
            "run_id": run_id,
            "tag": args.tag,
            "task_id": traj.get("task_id"),
            "trial": traj.get("trial"),
            "reward": traj.get("reward"),
            "num_turns": len(traj.get("messages", [])),
            "messages": traj.get("messages", []),
            "tool_calls": traj.get("tool_calls", []),
            "timestamp": timestamp,
        }
        append_trace(trace_record)

    # Print summary
    print(f"\n{'='*60}")
    print(f"RESULTS — {args.tag}")
    print(f"  Pass@1:    {pass_at_1:.1%}  ({successes}/{total} trials passed)")
    print(f"  95% CI:    [{ci_lo:.1%}, {ci_hi:.1%}]  (width: {round(ci_hi-ci_lo, 3):.1%})")
    print(f"  Published: {PUBLISHED_REFERENCE:.1%}  (delta: {delta_vs_published:+.1%})")
    print(f"  Wall time: {wall_seconds:.0f}s")
    print(f"  Scores written to: {SCORE_LOG}")
    print(f"  Traces written to: {TRACE_LOG}")
    print(f"{'='*60}\n")

    # Warn if CI is too wide (not enough trials for the interim report)
    if (ci_hi - ci_lo) > 0.25:
        print(
            "⚠  CI width > 0.25 — run more trials or tasks for a tighter interval.\n"
            "   Interim submission needs at least a recognizable baseline number.\n"
            "   Try: --trials 5 --tasks dev (30 tasks × 5 = 150 trials)\n"
        )

    return entry


# ── CLI ─────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="τ²-Bench runner for Tenacious CE")
    parser.add_argument(
        "--tasks",
        choices=["dev", "held_out", "all"],
        default="dev",
        help="Which task partition to run (default: dev = tasks 0–29)",
    )
    parser.add_argument(
        "--trials", type=int, default=5,
        help="Number of trials per task (default: 5 for pass@1 with CI)",
    )
    parser.add_argument(
        "--tag", default="baseline",
        help="Label for this run in score_log.json (e.g. baseline, repro_check, method_v1)",
    )
    parser.add_argument(
        "--agent-model", default="deepseek",
        help="Agent LLM alias or full LiteLLM model string (default: deepseek = dev tier)",
    )
    parser.add_argument(
        "--user-model", default="deepseek",
        help="User simulator LLM alias (default: deepseek)",
    )
    parser.add_argument(
        "--num-tasks", type=int, default=None,
        help="Limit to N tasks (useful for quick smoke tests, e.g. --num-tasks 3)",
    )
    parser.add_argument(
        "--tau2-dir", default=None,
        help=f"Path to tau2-bench repo (default: {TAU2_DIR})",
    )
    args = parser.parse_args()

    if args.tau2_dir:
        global TAU2_DIR
        TAU2_DIR = Path(args.tau2_dir)

    # Load .env from repo root
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    run_baseline(args)


if __name__ == "__main__":
    main()