# Finished plans

Plans land here **only after** implementation is validated and tested per the plan checklist.

## When moving a plan from `unfinished/`

1. Confirm every validation / test-plan item passed (UI: headless Playwright when applicable).
2. Move the file: `unfinished/<name>.md` → `finished/<name>.md`
3. Update frontmatter: `status: done`, all todos `status: completed`
4. Add at the top of the body:

   ```markdown
   **Completed:** YYYY-MM-DD — branch `feature/...` (commit `abc1234` if committed)
   ```

5. Remove the row from the unfinished queue in [`../README.md`](../README.md) or mark it done.
6. **Commit** the feature branch (code + moved plan file). Wait for explicit user approval to commit or push.

Do not move plans here to "mark progress" — use `status: in_progress` in `unfinished/` instead.
