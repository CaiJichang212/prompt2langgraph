---
name: "linear-data-pipeline"
description: "A linear workflow that fetches data, processes it, and stores results. Demonstrates basic linear flow with transform nodes."
---

## Description

This skill implements a simple data pipeline:
1. Fetch data from a source
2. Clean and normalize the data
3. Validate the schema
4. Store to destination

## When to Use

Use this skill when you need to process data through a sequence of transformation steps without branching.

## Workflow

1. **Fetch Data**: Retrieve raw data from the configured source (API, file, or database).
2. **Clean Data**: Remove nulls, fix encoding issues, standardize formats.
3. **Validate**: Check that all required fields exist and types are correct.
4. **Store**: Write the processed data to the destination.

## Inputs

- `source_url`: The URL or path to fetch data from
- `destination_path`: Where to store the processed data

## Outputs

- `processed_records`: Count of successfully processed records
- `errors`: List of validation errors encountered