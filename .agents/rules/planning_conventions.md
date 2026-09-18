# Project Conventions: Planning and Issues

## Implementation Plans
When asked to create an implementation plan for an issue, **DO NOT** use the internal `implementation_plan.md` artifact.

Instead, you **MUST** create a Markdown file in the `docs/` folder of the repository.

### File Naming Convention
The file should be named using the format `issue_XX_name.md`, where:
- `XX` is the zero-padded issue number (e.g., `04` for Issue 4).
- `name` is a short, descriptive name of the feature (e.g., `reddit_extractor`).

### File Format
The plan should be a standard Markdown document containing:
1. **Header**: Issue title, Branch name, Status, and PR link.
2. **Objective**: A brief summary of the goal.
3. **Acceptance Criteria**: A checklist of requirements.
4. **Implementation Tasks**: Step-by-step breakdown of the changes (grouped by files/components), including `make` commands for starting, testing, and finishing the issue.

Always adhere to these conventions to keep the repository's documentation organized.
