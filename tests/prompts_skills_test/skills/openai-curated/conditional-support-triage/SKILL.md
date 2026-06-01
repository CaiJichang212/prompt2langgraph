---
name: "conditional-support-triage"
description: "Classify support tickets by severity and route to appropriate handling workflow. Demonstrates conditional branching."
---

## Description

This skill triages incoming support tickets:
1. Analyze ticket content
2. Classify severity (low, medium, high, critical)
3. Route to appropriate team based on severity

## When to Use

Use this skill when processing support tickets that need different handling based on urgency.

## Workflow

1. **Parse Ticket**: Extract subject, body, and metadata from the ticket.
2. **Analyze Content**: Identify keywords indicating severity (e.g., "urgent", "down", "critical").
3. **Classify**: 
   - If contains "critical" or "down" → severity = "critical"
   - If contains "urgent" or "asap" → severity = "high"
   - If contains "when" or "how to" → severity = "low"
   - Otherwise → severity = "medium"
4. **Route**: Assign to the team matching the severity level.

## Inputs

- `ticket_id`: Unique identifier
- `ticket_subject`: Subject line
- `ticket_body`: Full message content

## Outputs

- `severity`: Classification result (low/medium/high/critical)
- `assigned_team`: Team identifier
- `routing_reason`: Explanation of routing decision