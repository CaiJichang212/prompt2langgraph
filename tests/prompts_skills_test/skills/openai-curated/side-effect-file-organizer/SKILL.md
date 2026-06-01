---
name: "side-effect-file-organizer"
description: "Organize files by moving, renaming, and deleting. Demonstrates side_effect nodes with idempotency."
---

## Description

This skill organizes a directory of files:
1. Scan directory structure
2. Classify files by type
3. Move files to appropriate subdirectories
4. Rename files to follow conventions
5. Remove duplicate or temp files

## When to Use

Use this skill when cleaning up messy file directories.

## Security Considerations

This skill performs file system modifications. Each operation is logged and can be rolled back.

## Workflow

1. **Scan**: List all files in target directory.
2. **Classify**: Determine file type (document, image, code, data, temp).
3. **Plan Moves**: Generate list of source→destination mappings.
4. **Execute Moves**: Move files to type-specific subdirectories.
5. **Rename**: Apply naming convention (lowercase, no spaces).
6. **Cleanup**: Remove temp files and duplicates.
7. **Report**: Output summary of changes made.

## Inputs

- `target_directory`: Path to directory to organize
- `naming_convention`: Rule for renaming (default: lowercase-underscore)

## Outputs

- `files_moved`: Count of files relocated
- `files_renamed`: Count of files renamed
- `files_removed`: Count of files deleted
- `operations_log`: Detailed list of all changes