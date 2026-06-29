# Pending plans

Plans land here **after** implementation is validated, committed on the plan branch, and merged into the long-running batch feature branch.

They are **not** finished — they await your review before sign-off.

## When moving a plan from `unfinished/`

Only on the **success path** (all validation / test-plan items passed):

1. Confirm every validation / test-plan item passed (UI: headless Playwright when applicable).
2. Move the file: `unfinished/<name>.md` → `pending/<name>.md`
3. Update frontmatter: `status: done`, all todos `status: completed`
4. Add at the top of the body:

   ```markdown
   **Completed:** YYYY-MM-DD — branch `feature/batch-.../<plan-slug>` (commit `abc1234`)
   ```

5. Remove the row from the unfinished queue in [`../README.md`](../README.md).
6. **Commit** on the plan branch, then **merge** into the long-running batch branch.

Do not move plans here on the failure path — leave them in `unfinished/` with `status: blocked` and a **Blocked** note.

## When moving a plan to `finished/`

After you review merged work on the long-running batch branch:

1. Confirm the implementation meets your expectations.
2. Move the file: `pending/<name>.md` → `finished/<name>.md`
3. Add a **Signed off:** note with the review date.

See [`../finished/README.md`](../finished/README.md) for details.
