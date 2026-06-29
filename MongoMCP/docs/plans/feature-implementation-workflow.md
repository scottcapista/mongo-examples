# Feature implementation workflow

Org-wide strategy for planning and shipping features in this repo.  
**Memory:** `feature_implementation_workflow` (`scope=0`) in cluster  
**Cursor rule:** [`.cursor/rules/plan-workflow.mdc`](../../.cursor/rules/plan-workflow.mdc) (`alwaysApply: true`)

## New plans

- **Always** create new plans in [`unfinished/`](unfinished/) — never only in `~/.cursor/plans/`.
- Include frontmatter: `name`, `status`, `order`, `overview`, `todos`.
- Register in the queue table in [`README.md`](README.md).

## Folder lifecycle

| Folder | Meaning |
|--------|---------|
| `unfinished/` | Not started, in progress, or blocked after a failed batch attempt |
| `pending/` | Validated, committed, merged into long-running branch — awaiting human review |
| `finished/` | User reviewed and signed off |

## Batch session (headless or walk-away)

### Step 0 — Start

1. Branch from `main`: create **one long-running feature branch** (e.g. `feature/batch-2026-06-28` or `feature/batch-<theme>`).
2. Work from [`unfinished/`](unfinished/) in `order` (ties: alphabetical filename).

### Step 1 — Per plan (repeat until `unfinished/` is empty)

| Step | Action |
|------|--------|
| 1. Branch | `feature/batch-<date>-<plan-slug>` from the long-running branch |
| 2. Implement | Complete todos; minimal diff; UI → headless Playwright (`.cursor/rules/ui-playwright-validation.mdc`) |
| 3. Validate | Run every item in the plan's Validation / Test plan section |
| 4a. Success | Move to `pending/`, update frontmatter + README queue, commit on plan branch, merge into long-running branch |
| 4b. Failure | After reasonable retries: commit plan branch with failure notes, **do not merge**, leave plan in `unfinished/` as `blocked`, continue from long-running branch only |

### Step 2 — After batch

- Long-running branch holds all successfully merged work.
- `pending/` holds plans awaiting your review.
- Move `pending/` → `finished/` after sign-off.

## Archive gates

- Do **not** move a plan to `pending/` until validation passes.
- Do **not** move a plan to `finished/` until you have reviewed merged work.
- Use `status: in_progress` in `unfinished/` while work is ongoing.
- Use `status: blocked` in `unfinished/` when a batch attempt failed and the plan branch was left unmerged.

## Git conventions

- Long-running: `feature/batch-YYYY-MM-DD` or `feature/batch-<theme>`
- Per-plan: `feature/batch-YYYY-MM-DD-<plan-slug>` (hyphenated slug; not nested slashes)
- Headless batch sessions: **auto-commit and auto-merge pre-authorized** when validation passes (overrides default commit-only-when-asked for this workflow).
- Do not push unless the user asks.
- Leave failed plan branches on disk for inspection.

## Sequential execution

Finish validate → archive → commit → merge for plan N before starting plan N+1. Never branch the next plan from a failed, unmerged plan branch.

## Walk-away batch mode (no continue prompts)

When the user starts a batch from `unfinished/` (or says **long-running session**, **walk-away batch**, **implement all unfinished plans**):

- Run plans sequentially until `unfinished/` is empty or all remaining plans are `blocked`.
- After merging plan N, **immediately** start plan N+1 in the **same agent session**.
- **Do not** ask the user to continue between plans or end with “say continue” prompts.
- Auto-commit and auto-merge remain pre-authorized when validation passes.

**Stop only for:** human-only blockers (service restart, secrets, OIDC, push), a plan left `blocked` after retries (then skip to next), or explicit user interrupt.

**Resume:** new chat — “Resume batch on `feature/batch-…`”; read queue and continue without asking to continue.

**Per-plan branches:** `feature/batch-YYYY-MM-DD-<plan-slug>` (hyphens, not nested slashes).
