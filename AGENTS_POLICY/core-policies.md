# Core Policies

## Version Control
- By default, all files need to be version-managed by git, except:
  - Secrets (such as tokens, passwords, keys, seeds)
  - Files listed in .gitignore
- Git-managed files MUST be transferred between staging environments via github (i.e., no file transfer)
- Git is there to avoid the need to duplicate files to make versions. 
  Do not copy files and append suffices like "_new" or "test"
- If something is experimental, consider creating a git branch.
- Release Versioning: Use semantic versioning for releases. All changes must be documented in the git commit log.

## Clean State
- Your mother does not work here, clean up yourself you must.
- If something is created/copied/restarted to replace something existing, remove or archive the existing something.
  <example>
    Container switched from rootful to rootless; a systemd unit after a system has been renamed/deprecated/etc,
    a database on a new location after fixing some issue, and so forth.
  </example>
- If a change is implemented, carefully analyze the impact on dependent code or documentation. 
  Make sure that all impacted
  

## Security
- **CRITICAL**: Never commit secrets or private data to git
- **Authentication**: All access must be properly authenticated
- **Container Security**: Use security-hardened container configurations
- **Access Control**: Proper file permissions and user management
- **Least Privilege**: Propose restriction and isolation where feasible,
  such as non-root service users, read-only access, granular network filters and file access privileges.

## Git Workflow  
- Files managed with git must not bypass github for file transfers (e.g., no scp)
- Ask for confirmation if this is unavoidable
- Use proper SSH key management and authentication
- If a test requires changes to be commited (e.g. when triggering a build on gh runner) always:
  - prefix the commit message with "UNTESTED:"
  - change the commit message to "TESTED: " with --amend after tests passed (agent or human)
- Version Tracking
  - relate commits to issues (e.g., "implements #123") where applicable


## File Handling
- For Linux files, always use Unix line endings (LF) and UTF-8 encoding

# Agent Setup, Behavior and Restrictions
- **Agent Working Directory**. As an agent you are bound to work with the current directory set to the root of the repository, 
  even though your privileges may allow you to access other parts of the filesystem.
  Reason: your environment has set CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR to <repo root>
- **Terminal Output**: Don't write files with more than 5 lines to terminal, use scratch/ instead (whitespace issues)
- **Feature additions**: ALWAYS wait for user feedback - no speculative features
- **File references**: If a file referenced in a prompt cannot be found, always ask to clarify
- **Approach changes**: If planned approach doesn't work, ask for confirmation before changing
- **Authentication failures**: If authentication fails unexpectedly, ask for clarification (don't guess the cause or try workarounds)
- **Code Changes** After changing code, ALWAYS run tests/unit/ (and other non-destructive tests if applicable)

## Remote access and SSH
- All ssh connections use pubkey-based authentication
- All connections are defined in ~/.ssh/config, with targe-specific keys and port settings