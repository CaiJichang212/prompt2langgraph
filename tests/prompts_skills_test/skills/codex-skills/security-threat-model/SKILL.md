---
name: "security-threat-model"
description: "Analyzes code repository for security risks, trust boundaries, and attack paths."
---

## Description

This skill performs threat modeling:
1. Identify trust boundaries
2. Map data flows
3. Find potential attack vectors
4. Assess risk severity
5. Recommend mitigations

## When to Use

Use this skill for security review of new features or entire codebases.

## Workflow

1. **Scan Architecture**: Identify components, APIs, data stores.
2. **Map Boundaries**: Find where trust levels change (auth, external input).
3. **Trace Data Flow**: Follow sensitive data through the system.
4. **Identify Threats**: For each boundary, list potential attacks.
5. **Assess Severity**: Rate each threat (low/medium/high/critical).
6. **Recommend Mitigations**: Suggest fixes for each threat.
7. **Generate Report**: Output structured threat model document.

## Inputs

- `repo_path`: Repository to analyze
- `focus_area`: Specific feature or module (optional)
- `depth`: Quick scan vs comprehensive

## Outputs

- `trust_boundaries`: Identified boundary list
- `threats`: Potential attack vectors
- `risk_matrix`: Severity assessments
- `mitigations`: Recommended fixes