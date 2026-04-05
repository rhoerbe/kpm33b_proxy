## Github Policy
- Tasks are passed as Github issues as #nn, like "do #5" or "plan #14".
- Post a plan as a comment to the issue if asked to provide a plan.
- When asked to change or improve aspects of the plan, overwrite the original comment - do not add another comment.
- When asked to "do #nn", perform the task and report results as a comment in issue #nn.
- Prepare a report as a comment in the issue once the task is done.
- For all files on git, always use Unix line endings (LF) and UTF-8 encoding.
- Changes related to an issue are written to a issue-specific branch and submitted as PR. Do not commit anything to main.
- Avoid breaking git history of files (e.g. copying a file for a new version).
- Release Versioning: Use semantic versioning for releases. All changes must be documented in the git commit log.

## Formatting YAML
1. Multi-line strings use the vertical bar option
2. Each record is separated by a single blank line, followed by a comment line with 3 dashes (---).
4. Lists are indented with 2 spaces.
5. No tabs, only spaces.
6. No line wrapping.
7. In multi-line text blocks avoid blank lines within the block.
8. Always remove blank lines at the end of a multi-line text block.

## Remote access and SSH
- All ssh connections use pubkey-based authentication
- All ssh connections are defined in ~/.ssh/config
- SSH key creation: prefer ED25519 over RSA.



** Coding
- Python is the preferred language
- Deploy using venv. Even within containers, use a virtual environment to keep consistence between dev and prod.
- Follow PEP 8 for code style, line width 120.
- Use pytest
- No imports relative to the current package. Import always based on the project root.
Define a single initialization script (init_env.sh) that will prepare the environment for the rest of the code to run.
- Prefer pathlib over os.path for file operations.
- Prever uv over pip
