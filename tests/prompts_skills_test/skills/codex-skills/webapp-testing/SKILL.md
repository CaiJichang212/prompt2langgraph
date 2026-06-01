---
name: "webapp-testing"
description: "Generates comprehensive test suites for web applications including unit, integration, and E2E tests."
---

## Description

This skill creates tests for web apps:
1. Analyze application structure
2. Identify testable components
3. Generate unit tests for functions
4. Generate integration tests for APIs
5. Generate E2E tests for user flows

## When to Use

Use this skill when adding test coverage to web applications.

## Workflow

1. **Scan Structure**: Identify pages, components, APIs, services.
2. **Detect Framework**: Determine test framework (Jest, Vitest, Playwright, etc.).
3. **Plan Tests**: List components needing tests, prioritize by criticality.
4. **Generate Unit Tests**: For pure functions and utilities.
5. **Generate Integration Tests**: For API endpoints and service interactions.
6. **Generate E2E Tests**: For critical user flows (login, checkout, etc.).
7. **Run Tests**: Execute generated tests, fix any failures.
8. **Report Coverage**: Output coverage summary.

## Inputs

- `app_path`: Path to web application
- `test_types`: Which test types to generate (unit/integration/e2e/all)
- `priority_flows`: Critical user flows to test first

## Outputs

- `tests_created`: Count of test files generated
- `coverage_report`: Coverage percentage by type
- `failing_tests`: List of tests that need fixes