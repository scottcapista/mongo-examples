# Finished plans

Plans land here **only after** you review and sign off on work that was validated, committed, and merged during a batch session.

## Lifecycle

```
unfinished/  →  pending/  →  finished/
(implement)     (merged)      (you signed off)
```

Plans no longer move directly from `unfinished/` to `finished/`. The agent archives to `pending/` after validation; you move to `finished/` after review.

## When moving a plan from `pending/`

1. Review the merged implementation on the long-running batch branch.
2. Move the file: `pending/<name>.md` → `finished/<name>.md`
3. Add at the top of the body:

   ```markdown
   **Signed off:** YYYY-MM-DD
   ```

4. Keep the existing **Completed:** note (branch + commit) from when the plan entered `pending/`.

Do not move plans here to "mark progress" — use `status: in_progress` in `unfinished/` or `status: done` in `pending/` instead.

## Reference: agent archive to `pending/`

When the batch agent succeeds, it moves `unfinished/<name>.md` → `pending/<name>.md` with:

- `status: done`, all todos `status: completed`
- **Completed:** note with plan branch and commit hash
- Unfinished queue row removed from [`../README.md`](../README.md)

See [`../pending/README.md`](../pending/README.md) for the full success-path checklist.
