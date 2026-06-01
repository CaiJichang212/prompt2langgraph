---
name: "human-gate-deployment"
description: "Deploy code changes with mandatory human approval before execution. Demonstrates human_gate node."
---

## Description

This skill manages safe deployment:
1. Prepare deployment package
2. Run pre-deployment checks
3. Request human approval
4. If approved, execute deployment
5. Verify and report results

## When to Use

Use this skill for production deployments that require explicit human sign-off.

## Workflow

1. **Prepare**: Bundle code changes, identify target environment.
2. **Pre-check**: Run tests, lint, security scan.
3. **Request Approval**: Present deployment summary and risks to human reviewer.
4. **Wait for Decision**: Pause until human provides approval or rejection.
5. **Execute**: If approved, run deployment commands.
6. **Verify**: Check that deployment succeeded, run smoke tests.
7. **Report**: Send notification with deployment status.

## Inputs

- `changes`: Description of what is being deployed
- `target_env`: Destination environment (staging/production)
- `approver`: Who should approve (optional)

## Outputs

- `deployment_status`: success/failed/rejected
- `approval_decision`: approved/rejected
- `verification_results`: Post-deployment check results