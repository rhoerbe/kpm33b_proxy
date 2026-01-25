**Agent-specific Policies and Directives**

This file provides policies, requirements and guidance to Claude Code Agent (claude.ai/code) when working with this project repository.

# Contents
<!-- TOC -->
* [ToC](#toc)
* [Critical Rules](#critical-rules)
* [Project Context](#project-context)
* [Implementation Guidelines](#implementation-guidelines)
  * [Architecture Patterns](#architecture-patterns)
  * [Development Patterns](#development-patterns)
  * [Code Conventions](#code-conventions)
  * [Project Setup Conventions](#project-setup-conventions)
  * [Environment configuration and Python Path Policy](#environment-configuration-and-python-path-policy)
  * [Refactoring Guidelines](#refactoring-guidelines)
* [Debugging and Troubleshooting](#debugging-and-troubleshooting)
* [Security](#security)
* [Chat Interaction](#chat-interaction)
<!-- TOC -->


# Included Files
Read all files in AGENTS_POLICY/ and follow the instructions as a project policy.

# Implementation Guidelines
- Simple beats complicated.
- However, do not skip a clean architecture and professional deployment.

## Development Patterns
- **Testing Philosophy**: Classical unit testing.
- **Error Handling**: Implement retry logic with exponential backoff for API calls.
- **Configuration**: Use environment variables for API keys and model configuration. No secrets or private data may be checked into git.

## Code Conventions
- Use python unless agreed otherwise with the human
- Follow existing Python conventions and patterns in the codebase
- Use descriptive variable names that reflect domain concepts
- Use pydantic for data validation and serialization where appropriate
- Code should be self-explaining with clear variable names and function signatures
- Add short docstrings where additional information is required on top of self-explaining code - do not duplicate in comments what the code already expresses in clarity.
- Sort the functions and classes top-down by their usage in the file, with imports at the top
- Avoid imports relative to the current package. Import always based on the project root.
- Define a single initialization script (init_env.sh) that will prepare the environment for the rest of the code to run.
- Prefer pathlib over os.path for file operations.
- Use 120-char page width in markdown, python, and YAML
- SSH keys used by the project are by default ED25519, not RSA.
- It is bad practice to add suffices for version control. There should be only one persistent name for a file, versions are in git.
  If you need to stash in between commits, copy to temp dir.

## Refactoring Guidelines
- **MANDATORY**: Always search the complete codebase for references to the code, keywords etc. that are affected
- **MANDATORY**: Always run all tests after refactoring
- **Refactoring Steps**:
  1. Identify the component to refactor
  2. Understand its role and dependencies
  3. Write unit tests for existing behavior
  4. Refactor code while maintaining functionality
  5. Run all tests to ensure no regressions
- Ensure after renames that the old string is not found anymore in anything but logs, migrations or commit comments.

# Chat Interaction and Communication Style
- Use sober, precise language. Report facts as achieved/not achieved, not "excellent" or "perfect"
- Show actual command output, not interpretations
- Challenge assumptions when evidence suggests alternatives
- Use probability-based assessments ("likely to work because X") rather than certainties
- Act as technical team member providing analysis, not a servant seeking approval
- 
# Clean File System Structure
- The project root may contain only directories and files that must reside there! Think of a proper directory when creating files initially. 
  If you are not sure, create a scratch/ directory and put temporary files there. Consider what goes into git and what not.

# Communication Standards
- Report objective status: "Service running on test/prod" not "Everything is perfect"
- Show actual output, not summaries
- Challenge user assumptions when evidence suggests alternatives  
- Use probability language: "This likely works because..." not "This will definitely work"
- Ask for clarification when requirements are ambiguous
- Focus on Definition of Done - verify before claiming completion
