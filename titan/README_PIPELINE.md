## Pending research reading order

Run `python -m titan.pending_triage < checkpoint-input.json`. Supply a JSON object with
`pending_research` (records), `event_metadata` (a mapping keyed by event ID), and an
offset-aware ISO 8601 `cutoff`. Each combined record requires an event ID, unanswered
question, reason it matters, and next checkpoint. Optional fields include `event_type`,
`size_vs_annual_sales` (a nonnegative ratio on a consistent scale), offset-aware
`public_time`, and boolean `body_read`. Event classes include results, guidance,
orders/awards, regulatory actions, and transactions.

The output orders up to 12 items for deeper reading and discloses every remaining
item under `carry_pending`. Items published after cutoff stay in that list for the
next checkpoint. Both lists are pending. The cap applies only to reading order.
Publish both lists and their counts alongside the checkpoint. Original records,
research coverage, and forecast ranking are preserved.
