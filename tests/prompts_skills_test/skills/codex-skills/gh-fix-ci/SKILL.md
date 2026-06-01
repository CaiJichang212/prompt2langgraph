---
name: "gh-fix-ci"
description: "Reads CI failure logs from GitHub Actions, diagnoses the root cause, and applies targeted fixes to pass the pipeline."
---

## Description

This skill automates CI/CD failure diagnosis and repair:
1. Fetch latest CI run logs
2. Identify failing step and error
3. Analyze codebase for root cause
4. Apply minimal fix
5. Verify locally

## When to Use

Use this skill when GitHub Actions CI fails and you need quick diagnosis and fix.

## Workflow

1. **Fetch Logs**: Use `gh run view` to get the latest failed run logs.
2. **Identify Failure**: Parse logs to find the first failing step.
3. **Extract Error**: Capture error message, file, and line number.
4. **Analyze**: Read the failing file, understand the context.
5. **Diagnose**: Determine root cause (syntax error, missing import, test assertion, etc.).
6. **Fix**: Apply minimal change to resolve the issue.
7. **Verify**: Run the failing test locally to confirm fix.
8. **Commit**: If verified, commit the fix.

## Inputs

- `repo`: Repository name (optional, uses current)
- `branch`: Branch with failure (optional, uses current)

## Outputs

- `failure_step`: Which step failed
- `error_type`: Category of error
- `fix_applied`: Description of the fix
- `verification_result`: Local test result