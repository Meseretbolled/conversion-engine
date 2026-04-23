"""
eval/tau2_runner.py
Runs tau2-bench and automatically saves results to eval/score_log.json
and eval/trace_log.jsonl — no manual copying needed.

Usage (from repo root):
    python eval/tau2_runner.py --tag baseline --trials 5 --num-tasks 30
    python eval/tau2_runner.py --tag tenacious_method --agent tenacious_agent --trials 5 --num-tasks 30

Structure assumed:
    conversion-engine/
    ├── eval/
    │   ├── tau2_runner.py      ← this file
    │   ├── score_log.json      ← auto-updated after every run
    │   └── trace_log.jsonl     ← auto-updated after every run
    └── harness/
        └── tau2-bench/         ← gitignored, cloned here
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

# ── Paths ───────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent
EVAL_DIR  = REPO_ROOT / "eval"
TAU2_DIR  = REPO_ROOT / "harness" / "tau2-bench"
SCORE_LOG = EVAL_DIR / "score_log.json"
TRACE_LOG = EVAL_DIR / "trace_log.jsonl"

PUBLISHED_REFERENCE = 0.42  # τ²-Bench retail pass@1, GPT-5 class, Feb 2026


# ── Stats ────────────────────────────────────────────────────────────────
def wilson_ci(successes, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    spread = (z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))) / denom
    return (max(0.0, round(centre - spread, 4)), min(1.0, round(centre + spread, 4)))


# ── Score log ────────────────────────────────────────────────────────────
def load_score_log():
    if SCORE_LOG.exists():
        return json.loads(SCORE_LOG.read_text())
    return []

def save_score_log(entries):
    SCORE_LOG.write_text(json.dumps(entries, indent=2))

def append_trace(record):
    with open(TRACE_LOG, "a") as f:
        f.write(json.dumps(record) + "\n")


# ── Parse results.json ───────────────────────────────────────────────────
def parse_results(results_path):
    data = json.loads(results_path.read_text())
    trajectories = data.get("trajectories", [])

    # Count from trajectories directly — most reliable
    if trajectories:
        passed = sum(1 for t in trajectories if t.get("reward", 0) == 1.0)
        total  = len(trajectories)
    else:
        # Fall back to reward_metrics
        rm = data.get("reward_metrics", {})
        pass_1 = rm.get("pass_1") or rm.get("average_reward") or 0.0
        if pass_1 > 1.0:
            pass_1 /= 100.0
        total  = data.get("num_tasks", 30) * data.get("num_trials", 5)
        passed = round(pass_1 * total)

    pass_at_1     = round(passed / max(total, 1), 4)
    infra_errors  = data.get("infra_errors", 0)

    return {
        "pass_at_1":     pass_at_1,
        "successes":     passed,
        "total_trials":  total,
        "infra_errors":  infra_errors,
        "trajectories":  trajectories,
        "raw":           data,
    }


# ── Run tau2 ─────────────────────────────────────────────────────────────
def run_tau2(agent, agent_model, user_model, num_trials, num_tasks, save_to):
    if not TAU2_DIR.exists():
        raise FileNotFoundError(
            f"tau2-bench not found at {TAU2_DIR}\n"
            f"Clone it: git clone https://github.com/sierra-research/tau2-bench {TAU2_DIR}"
        )

    results_path = TAU2_DIR / "data" / "simulations" / save_to / "results.json"
    if results_path.exists():
        results_path.unlink()

    cmd = [
        "/home/meseret/Documents/conversion-engine/harness/tau2-bench/.venv/bin/tau2", "run",
        "--domain",     "retail",
        "--agent",      agent,
        "--agent-llm",  agent_model,
        "--user-llm",   user_model,
        "--num-trials", str(num_trials),
        "--num-tasks",  str(num_tasks),
        "--save-to",    save_to,
    ]

    env = {**os.environ}
    if "OPENROUTER_API_KEY" in env:
        env.setdefault("OPENAI_API_KEY",  env["OPENROUTER_API_KEY"])
        env.setdefault("OPENAI_API_BASE", "https://openrouter.ai/api/v1")

    print(f"\n{'='*60}")
    print(f"Agent:   {agent} → {agent_model}")
    print(f"Tasks:   {num_tasks} × {num_trials} trials = {num_tasks * num_trials} total")
    print(f"{'='*60}\n")

    t0 = time.monotonic()
    result = subprocess.run(cmd, cwd=str(TAU2_DIR), env=env)
    wall_seconds = time.monotonic() - t0

    if result.returncode != 0:
        raise RuntimeError(f"tau2 run failed (exit {result.returncode})")

    if not results_path.exists():
        candidates = sorted(
            (TAU2_DIR / "data" / "simulations").glob(f"{save_to}*/results.json"),
            key=os.path.getmtime, reverse=True
        )
        if not candidates:
            raise FileNotFoundError("No results.json found after run.")
        results_path = candidates[0]

    return results_path, wall_seconds


# ── Main ─────────────────────────────────────────────────────────────────
def run(args):
    # Load .env
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    run_id    = str(uuid.uuid4())[:8]
    timestamp = datetime.utcnow().isoformat()
    save_to   = f"{args.tag}_{run_id}"

    results_path, wall_seconds = run_tau2(
        agent=args.agent,
        agent_model=args.agent_model,
        user_model=args.user_model,
        num_trials=args.trials,
        num_tasks=args.num_tasks,
        save_to=save_to,
    )

    parsed    = parse_results(results_path)
    pass_at_1 = parsed["pass_at_1"]
    successes = parsed["successes"]
    total     = parsed["total_trials"]
    ci_lo, ci_hi = wilson_ci(successes, total)

    entry = {
        "run_id":              run_id,
        "tag":                 args.tag,
        "timestamp":           timestamp,
        "domain":              "retail",
        "agent":               args.agent,
        "agent_model":         args.agent_model,
        "user_model":          args.user_model,
        "num_tasks":           args.num_tasks,
        "num_trials":          args.trials,
        "pass_at_1":           pass_at_1,
        "successes":           successes,
        "total_trials":        total,
        "infra_errors":        parsed["infra_errors"],
        "ci_95_low":           ci_lo,
        "ci_95_high":          ci_hi,
        "ci_width":            round(ci_hi - ci_lo, 4),
        "published_reference": PUBLISHED_REFERENCE,
        "delta_vs_published":  round(pass_at_1 - PUBLISHED_REFERENCE, 4),
        "wall_seconds":        round(wall_seconds, 1),
        "results_path":        str(results_path),
    }

    # Auto-save to score_log.json
    score_log = load_score_log()
    score_log.append(entry)
    save_score_log(score_log)
    print(f"✅ score_log.json updated: {SCORE_LOG}")

    # Auto-save trajectories to trace_log.jsonl
    for traj in parsed["trajectories"]:
        append_trace({
            "run_id":    run_id,
            "tag":       args.tag,
            "agent":     args.agent,
            "task_id":   traj.get("task_id"),
            "trial":     traj.get("trial"),
            "reward":    traj.get("reward"),
            "num_turns": len(traj.get("messages", [])),
            "messages":  traj.get("messages", []),
            "timestamp": timestamp,
        })
    print(f"✅ trace_log.jsonl updated: {TRACE_LOG}")

    # Auto-save raw results
    raw_dest = EVAL_DIR / f"tau2_raw_{args.tag}.json"
    raw_dest.write_text(json.dumps(parsed["raw"], indent=2))
    print(f"✅ Raw results saved: {raw_dest}")

    print(f"\n{'='*60}")
    print(f"RESULTS — {args.tag}")
    print(f"  Agent:     {args.agent}")
    print(f"  Pass@1:    {pass_at_1:.1%}  ({successes}/{total} passed)")
    print(f"  95% CI:    [{ci_lo:.1%}, {ci_hi:.1%}]")
    print(f"  Published: {PUBLISHED_REFERENCE:.1%}  (delta: {pass_at_1 - PUBLISHED_REFERENCE:+.1%})")
    print(f"  Time:      {wall_seconds:.0f}s")
    print(f"{'='*60}\n")

    return entry


# ── CLI ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="τ²-Bench runner for Tenacious CE")
    parser.add_argument("--tag",         default="baseline")
    parser.add_argument("--agent",       default="llm_agent",
        help="Agent name: llm_agent (default baseline) or tenacious_agent")
    parser.add_argument("--agent-model", default="openrouter/deepseek/deepseek-chat")
    parser.add_argument("--user-model",  default="openrouter/deepseek/deepseek-chat")
    parser.add_argument("--trials",      type=int, default=5)
    parser.add_argument("--num-tasks",   type=int, default=30)
    args = parser.parse_args()
    run(args)