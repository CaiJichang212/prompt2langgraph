---
name: "gh-address-comments"
description: "Reads PR review comments and generates code fixes that address each comment."
---

## Description

This skill processes PR feedback:
1. Fetch PR review comments
2. Parse each comment for requested changes
3. Apply fixes to relevant code
4. Commit fixes as separate commits or batch

## When to Use

Use this skill when responding to PR review feedback.

## Workflow

1. **Fetch PR**: Get PR number and review comments using `gh pr view`.
2. **Parse Comments**: Extract each comment's file, line, and requested change.
3. **Prioritize**: Sort by severity (blocking vs suggestion).
4. **Address Blocking**: Fix critical issues first.
5. **Address Suggestions**: Implement non-blocking improvements.
6. **Commit**: Create commits referencing each addressed comment.
7. **Push**: Push fixes to PR branch.
8. **Respond**: Add comment acknowledging fixes.

## Inputs

- `pr_number`: PR to address
- `batch_mode`: Single commit vs per-comment commits

## Outputs

- `comments_addressed`: Count of fixed items
- `commits_created`: List of fix commits
- `remaining_items`: Unaddressed comments (if any)