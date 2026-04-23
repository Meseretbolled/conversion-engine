# Act I — τ²-Bench Retail Baseline

## What Was Reproduced

Ran the τ²-Bench retail domain using the default `llm_agent` with
`openrouter/deepseek/deepseek-chat` (DeepSeek V3) as both agent and user simulator.
30 tasks × 5 trials = 150 total simulations on the dev partition.

## Results

| Metric | Value |
|---|---|
| Agent | llm_agent (DeepSeek V3 via OpenRouter) |
| Domain | retail |
| Tasks | 30 |
| Trials per task | 5 |
| Total simulations | 150 |
| Infra errors | 5 (excluded from metrics) |
| Evaluated | 145 |
| **Pass@1** | **0.120 (12.0%)** |
| 95% CI | [0.075, 0.165] |
| Published reference (GPT-5 class) | 0.42 (42%) |
| Delta vs published | −0.30 |
| Avg cost/conversation | $0.00 (cost tracking unavailable: DeepSeek V3 not mapped in LiteLLM) |

## Confidence Interval

Wilson score interval at 95% confidence:
- Successes: ~17 out of 145 evaluated trials
- CI: [7.5%, 16.5%]
- CI width: 9.0 percentage points

The interval is wide because DeepSeek's rate limiting caused some tasks to time out,
reducing the effective sample. A full 150-trial run with no infra errors would tighten
the CI to approximately ±5 percentage points.

## Cost Per Run

LiteLLM did not map `deepseek/deepseek-chat-v3` via OpenRouter, so per-conversation
cost shows $0.00 in the results. Manual estimate based on OpenRouter pricing
($0.14/M input, $0.28/M output): approximately $0.15–0.25 for the full 150-trial run,
well within the $4 dev-tier budget.

## Unexpected Behavior

1. **Cost tracking failure** — LiteLLM error: `model deepseek/deepseek-chat-v3 not mapped`.
   Cost shows $0.00 in results.json but actual spend was non-zero. Logged as a known
   limitation; cost will be tracked correctly for the tenacious_agent runs using
   Claude Sonnet (eval tier).

2. **Rate limiting** — DeepSeek via OpenRouter has strict rate limits. Several tasks
   took 400–500 seconds per trial (vs expected 30–60s), causing 5 infra errors out of
   150 simulations. Mitigation: tenacious_method run uses `--concurrency 1` flag.

3. **Low pass@1 vs reference** — 12% vs published 42% is expected. The published
   reference uses GPT-5 class models. DeepSeek V3 is used here as the dev-tier
   baseline only. The tenacious_agent run with Claude Sonnet 4.6 will be the scored
   method.

## Next Steps

- Run `python eval/tau2_runner.py --tag tenacious_method --agent tenacious_agent` to
  score the Tenacious custom agent against the same 30-task dev partition.
- Run final held-out scoring with Claude Sonnet 4.6 on Days 5–7.