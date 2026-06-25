# Pipeline workflow (Bedrock + human adjudication)

## Configs

Each review is a JSON file in `configs/`:

- `configs/adults.json` — adults review
- `configs/children.json` — under-18 companion review (carries forward under-18 papers from adults + adds children-specific DB exports)

Both now use:

| Role | Model | Bedrock ID | Region |
|---|---|---|---|
| Rater A | Nova 2 Lite | `us.amazon.nova-2-lite-v1:0` | us-east-1 |
| Rater B | Claude Sonnet 4.6 | `us.anthropic.claude-sonnet-4-6` | us-east-1 |
| Adjudicator | **Human** | — | — |

AWS auth: profile `phd` (override with `AWS_PROFILE`). The model IDs above are best-guess
us-east-1 inference profiles — **verify them after SSO login** (see step 0).

## End-to-end run

```bash
# 0. Log in + verify the model IDs are correct for us-east-1
aws sso login --profile phd
poetry run python scripts/verify_bedrock.py adults     # patches nothing; tells you exact IDs

# 1. (optional) tune prompts for the two models on a small sample first
poetry run python scripts/prompt_opt.py adults 40
#    → read /tmp/prompt_opt_disagreements.csv
#    → edit configs/adults.json raters.a.prompt_suffix / raters.b.prompt_suffix
#    → re-run until agreement is acceptable

# 2. full pipeline: combine → dedupe → fill_abstracts → classify (2 raters) → adjudicate (agreement pass only)
poetry run python pipeline.py adults

# 3. human adjudication of the disagreements the two raters couldn't agree on
poetry run python adjudicate_ui.py adults
#    → open http://localhost:8000
```

## Human adjudication UI

`adjudicate_ui.py` is a self-contained local web app (standard library only).

- **Auto-resolves** rows where both raters agree on every consensus field (no human needed).
- **Queues only decision-relevant disagreements** by default: a disagreement is skipped if the
  raters already *agree* on a criterion that excludes the paper (e.g. both say "not adults",
  "no intervention", "telecoaching"). This shrinks the queue from ~1000 to ~170 on the adults set.
  Set `ADJ_UI_ALL=1` to review every disagreement instead.
- Writes `Final_<field>` + `Human_<field>` and marks `Adjudicated = human`. Resumable.
- Works on existing data too: if the configured rater columns (e.g. `Nova_*`) aren't present
  but legacy `OpenAI_*` / `Gemini_*` columns are, it falls back to those.

Keyboard: `a`/`b` pick a rater's value · `1`-`9` pick an allowed value · `Tab` next field ·
`Enter` save + next · `[` / `]` navigate.

## Switching the adjudicator back to an LLM

Set the `adjudicator` rater's `provider` back to `"bedrock"` with a `model_id` and `region`
in the config. The `adjudicate` step will then resolve disagreements by majority vote
automatically (no UI needed).

## Notes on the SCP

RMIT's Service Control Policy currently allows direct model invocation and `au.*` (Australia)
inference profiles, but blocks `apac.*` and `global.*` cross-region profiles. us-east-1 uses
`us.*` profiles — if those are also blocked, ask the AWS admin to allow `bedrock:InvokeModel`
+ `bedrock:Converse` on the `us.*` inference-profile ARNs (or run in `au.*` and accept the
older model line). `scripts/verify_bedrock.py` reports exactly what's reachable.
