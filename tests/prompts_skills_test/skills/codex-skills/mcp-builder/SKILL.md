---
name: "mcp-builder"
description: "Builds MCP (Model Context Protocol) servers following best practices through a structured workflow."
---

## Description

This skill guides MCP server development:
1. Plan server capabilities
2. Implement tools and resources
3. Evaluate against MCP spec
4. Optimize and document

## When to Use

Use this skill when building new MCP servers for AI model integration.

## Workflow

1. **Plan**: Define what tools and resources the server will expose.
2. **Design Schema**: Create JSON schemas for tool inputs/outputs.
3. **Implement**: Write the server code following MCP protocol.
4. **Test Locally**: Run server, test tool invocations.
5. **Evaluate**: Check against MCP specification compliance.
6. **Optimize**: Improve error handling, add validation.
7. **Document**: Generate README with usage examples.
8. **Package**: Create distribution configuration.

## Inputs

- `server_name`: Name for the MCP server
- `capabilities`: List of tools/resources to implement
- `target_models`: Which AI models to support

## Outputs

- `server_code`: Implemented server files
- `schema_definitions`: Tool/resource schemas
- `compliance_report`: MCP spec compliance status
- `documentation`: Usage guide