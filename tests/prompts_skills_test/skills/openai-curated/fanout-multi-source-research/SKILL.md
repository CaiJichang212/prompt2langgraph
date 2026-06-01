---
name: "fanout-multi-source-research"
description: "Research a topic from multiple sources simultaneously and synthesize results. Demonstrates fanout with join."
---

## Description

This skill performs parallel research across multiple sources:
1. Spawn parallel searches for web, academic, news sources
2. Collect results from each source
3. Join and synthesize into unified report

## When to Use

Use this skill when comprehensive research requires checking multiple independent sources.

## Workflow

1. **Prepare Queries**: Formulate search queries for the topic.
2. **Fanout Search**:
   - Branch A: Web search (general information)
   - Branch B: Academic search (papers, citations)
   - Branch C: News search (recent developments)
3. **Collect Results**: Each branch returns top 5 relevant items.
4. **Join**: Merge all results, remove duplicates, rank by relevance.
5. **Synthesize**: Generate summary report combining all perspectives.

## Inputs

- `research_topic`: The subject to research
- `depth`: How deep to search (quick/comprehensive)

## Outputs

- `synthesis_report`: Combined research summary
- `source_count`: Number of unique sources used
- `key_findings`: List of most important discoveries