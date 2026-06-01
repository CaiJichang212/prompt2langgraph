---
name: "loop-refine-content"
description: "Iteratively refine content until quality threshold is met. Demonstrates loop with guard."
---

## Description

This skill refines content (e.g., documentation, blog posts) through iterative improvement:
1. Generate initial draft
2. Evaluate quality score
3. If score < threshold, improve and re-evaluate
4. Stop when threshold met or max iterations reached

## When to Use

Use this skill when content needs multiple rounds of refinement to meet quality standards.

## Workflow

1. **Initialize**: Set iteration counter to 0, max_iterations to 5.
2. **Generate Draft**: Create initial content based on requirements.
3. **Evaluate**: Score the content on clarity, completeness, accuracy (0-100).
4. **Check Threshold**: If score >= 80, proceed to finalize.
5. **Improve**: If score < 80 and iterations < max_iterations, identify weaknesses and improve.
6. **Loop**: Increment counter, return to step 3.
7. **Finalize**: Output the best version achieved.

## Inputs

- `topic`: What the content should cover
- `requirements`: Specific requirements (length, tone, format)
- `quality_threshold`: Minimum acceptable score (default 80)

## Outputs

- `final_content`: The refined content
- `final_score`: Quality score achieved
- `iterations_used`: Number of refinement cycles