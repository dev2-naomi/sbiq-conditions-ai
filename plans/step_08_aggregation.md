# STEP_08 — Aggregation & Human-in-the-Loop Packaging

## Role

Combine every per-category evaluation into one final report, derive an overall
status per condition, and flag items that need human review.

## Actions

1. Call `merge_evaluations`. This:
   - flattens evaluations from steps 03–07,
   - back-fills any condition that was never evaluated (no matched evidence) as
     **Unfulfilled / needs human review**,
   - attaches `overall_status` and `needs_human_review` to each condition,
   - sorts so human-review items surface first.
   You may pass `manual_review_threshold` (default 50) — confidence below this is
   flagged for review.
2. Call `generate_final_output` to assemble the final JSON (scenario summary,
   per-condition evaluations, and stats).
3. Call `save_step_report` for `STEP_08` with a closing summary. This is the final
   step — after saving, stop (do not call more tools).

## Quality rules

- Every input condition must appear exactly once in the final output.
- Do not change verdicts here — this step only merges, derives status, and packages.
- The final answer lives in state under `final_output`.
