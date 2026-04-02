# GitHub MCP Server

An MCP server with **40 tools** wrapping the GitHub CLI (`gh`) for Claude integration.

## Prerequisites

- Python 3.10+
- [GitHub CLI](https://cli.github.com/) installed and authenticated (`gh auth login`)

## Quick Start

```bash
# From monorepo root
pip install -e ./shared

# Run
cd servers/github
python server.py
```

## Tools (40)

| Category | Tools |
|----------|-------|
| Auth | `auth_status`, `whoami`, `switch_account` |
| Repos | `create_repo`, `create_repo_with_files`, `list_repos`, `repo_view`, `clone_repo`, `delete_repo` |
| Git | `git_status`, `git_add_commit_push`, `git_init_and_push`, `git_pull` |
| Branches | `create_branch`, `list_branches`, `switch_branch`, `delete_branch` |
| Forks | `fork_repo`, `sync_fork` |
| Issues | `create_issue`, `list_issues`, `comment_on_issue` |
| PRs | `create_pr`, `list_prs`, `comment_on_pr`, `merge_pr`, `review_pr`, `pr_diff` |
| Collaborators | `list_collaborators`, `add_collaborator` |
| Files | `get_file_contents`, `create_or_update_file` |
| Gists | `create_gist` |
| Workflows | `list_workflows`, `run_workflow`, `list_workflow_runs`, `view_workflow_run` |
| Search | `search_repos` |
| Releases | `create_release`, `list_releases` |

## Remote Access

```bash
MCP_TRANSPORT=sse MCP_PORT=9000 MCP_SERVER_URL=https://your-tunnel.ngrok-free.dev python server.py
```
