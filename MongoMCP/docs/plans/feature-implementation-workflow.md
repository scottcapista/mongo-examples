# Feature implementation workflow

Org-wide strategy for planning and shipping features in this repo.  
**Memory:** `feature_implementation_workflow` (`scope=0`) in cluster  
**Cursor rule (add when editing rules):** `.cursor/rules/plan-workflow.mdc` with `alwaysApply: true`

## New plans

- **Always** create new plans in [`unfinished/`](unfinished/) — never only in `~/.cursor/plans/`.
- Include frontmatter: `name`, `status`, `order`, `overview`, `todos`.
- Register in the queue table in [`README.md`](README.md).

## Lifecycle (per feature)

| Step | Action |
|------|--------|
| 1. Create | Write plan under `unfinished/` |
| 2. Branch | Feature branch off `main` |
| 3. Implement | Complete todos; minimal diff |
| 4. Validate | Run plan checklist; UI → headless Playwright (`.cursor/rules/ui-playwright-validation.mdc`) |
| 5. Archive | **Only after validation passes:** move to `finished/`, `status: done`, update README queue |
| 6. Commit | Git commit on feature branch (user must request; no push unless asked) |
| 7. Next | In batch sessions, finish steps 4–6 before starting the next `order` |

## Archive gate

Do **not** move a plan to `finished/` until validation and testing pass. Use `status: in_progress` in `unfinished/` while work is ongoing.

## Batch execution

When executing multiple unfinished plans in one session: sequential only — validate → archive → commit for plan N, then start plan N+1.
