#!/usr/bin/env python3
"""
GitHub MCP Server

An MCP server that wraps the GitHub CLI (gh) to provide 40 GitHub operations
directly from Claude Desktop/Code/Web.

Prerequisites:
    1. Install GitHub CLI: https://cli.github.com/
    2. Authenticate: gh auth login

Usage:
    # Local (Claude Desktop/Code)
    python server.py

    # Remote (Claude.ai via tunnel)
    MCP_TRANSPORT=sse MCP_PORT=9000 MCP_SERVER_URL=https://your-tunnel.ngrok-free.dev python server.py
"""

import base64
import json
import os
import re
import tempfile
from typing import Optional

from mcp_shared import (
    create_server,
    run_server,
    run_cli,
    log_tool_call,
    require_write_access,
    validate_path,
    WORK_DIR,
)

# Create the MCP server (transport configured via MCP_TRANSPORT env var)
mcp = create_server("github")


# =============================================================================
# GITHUB-SPECIFIC HELPERS
# =============================================================================

def run_gh(args: list[str], cwd: Optional[str] = None) -> dict:
    """Run a gh CLI command. Thin wrapper around run_cli."""
    return run_cli("gh", args, cwd=cwd or str(WORK_DIR), timeout=60)


def run_git(args: list[str], cwd: Optional[str] = None) -> dict:
    """Run a git command. Thin wrapper around run_cli."""
    return run_cli("git", args, cwd=cwd or str(WORK_DIR), timeout=120)


# =============================================================================
# GITHUB-SPECIFIC VALIDATORS
# =============================================================================

def validate_repo_name(repo: str) -> str:
    """Validate repo format is 'owner/repo' or just 'repo-name'."""
    if not re.match(r'^[a-zA-Z0-9._-]+(/[a-zA-Z0-9._-]+)?$', repo):
        raise ValueError(f"Invalid repository name: '{repo}'")
    return repo


def validate_branch_name(branch: str) -> str:
    """Validate branch name contains only safe characters."""
    if not re.match(r'^[a-zA-Z0-9._/-]+$', branch):
        raise ValueError(f"Invalid branch name: '{branch}'")
    return branch


def validate_username(username: str) -> str:
    """Validate GitHub username contains only safe characters."""
    if not re.match(r'^[a-zA-Z0-9._-]+$', username):
        raise ValueError(f"Invalid username: '{username}'")
    return username


def validate_file_path(path: str) -> str:
    """Validate file path for GitHub API operations (no query injection)."""
    if re.search(r'[?&=#]', path):
        raise ValueError(f"Invalid file path: '{path}'")
    return path


# =============================================================================
# AUTHENTICATION & STATUS
# =============================================================================

@mcp.tool()
def auth_status() -> str:
    """
    Check GitHub CLI authentication status.
    Shows which account is logged in and what scopes are available.
    """
    log_tool_call("auth_status")
    result = run_gh(["auth", "status"])
    
    if result["success"]:
        return f"✅ Authenticated\n\n{result['output']}"
    else:
        return f"❌ Not authenticated\n\n{result['error']}\n\nRun: gh auth login"


@mcp.tool()
def whoami() -> str:
    """Get the currently authenticated GitHub username."""
    log_tool_call("whoami")
    result = run_gh(["api", "user", "--jq", ".login"])
    
    if result["success"]:
        return f"Logged in as: {result['output']}"
    else:
        return f"Error: {result['error']}"


@mcp.tool()
def switch_account(username: str) -> str:
    """
    Switch the active GitHub CLI account.

    Args:
        username: GitHub username to switch to (must already be authenticated via gh auth login)

    Returns:
        Confirmation of the switch with current auth status
    """
    log_tool_call("switch_account", username=username)
    try:
        require_write_access("switch_account")
        username = validate_username(username)
    except (PermissionError, ValueError) as e:
        return str(e)
    result = run_gh(["auth", "switch", "--user", username])

    if result["success"]:
        status = run_gh(["auth", "status"])
        return f"✅ Switched to {username}\n\n{status['output']}"
    else:
        return f"❌ Failed to switch account: {result['error']}"


# =============================================================================
# REPOSITORY OPERATIONS
# =============================================================================

@mcp.tool()
def create_repo(
    name: str,
    description: str = "",
    public: bool = True,
    clone: bool = True,
) -> str:
    """
    Create a new GitHub repository.
    
    Args:
        name: Repository name (e.g., 'my-project')
        description: Repository description
        public: Whether the repo should be public (default: True)
        clone: Whether to clone the repo locally after creation (default: True)
        
    Returns:
        Success message with repo URL or error
    """
    log_tool_call("create_repo", name=name, description=description, public=public, clone=clone)
    try:
        require_write_access("create_repo")
        name = validate_repo_name(name)
    except (PermissionError, ValueError) as e:
        return str(e)
    args = ["repo", "create", name]
    
    if description:
        args.extend(["--description", description])
    
    if public:
        args.append("--public")
    else:
        args.append("--private")
    
    if clone:
        args.append("--clone")
    
    result = run_gh(args)
    
    if result["success"]:
        return f"✅ Repository created!\n\n{result['output']}"
    else:
        return f"❌ Failed to create repository\n\n{result['error']}"


@mcp.tool()
def create_repo_with_files(
    repo_name: str,
    files: list[dict],
    description: str = "",
    public: bool = True,
) -> str:
    """
    Create a new GitHub repo and populate it with files in a single operation.
    Uses the GitHub REST API directly — works from Claude.ai without local filesystem.

    Args:
        repo_name: Repository name (e.g., 'my-project')
        files: List of files, each a dict with 'path' and 'content' keys.
               Example: [{"path": "README.md", "content": "# My Project"}, {"path": "src/main.py", "content": "print('hello')"}]
        description: Repository description
        public: Whether the repo should be public (default: True)

    Returns:
        Repo URL on success, or error message
    """
    log_tool_call("create_repo_with_files", repo_name=repo_name, files=f"[{len(files)} files]", description=description, public=public)
    try:
        require_write_access("create_repo_with_files")
        repo_name = validate_repo_name(repo_name)
    except (PermissionError, ValueError) as e:
        return str(e)

    if not files:
        return "❌ No files provided. Pass at least one file with 'path' and 'content'."

    for f in files:
        if not isinstance(f, dict) or "path" not in f or "content" not in f:
            return "❌ Each file must be a dict with 'path' and 'content' keys."

    # Step 1: Get authenticated username
    user_result = run_gh(["api", "user", "--jq", ".login"])
    if not user_result["success"]:
        return f"❌ Failed to get username: {user_result['error']}"
    owner = user_result["output"].strip()

    # Step 2: Create the repository with auto_init to get an initial commit
    create_args = [
        "api", "user/repos", "-X", "POST",
        "-f", f"name={repo_name}",
        "-f", f"description={description}",
        "-F", f"private={str(not public).lower()}",
        "-F", "auto_init=true",
    ]
    create_result = run_gh(create_args)
    if not create_result["success"]:
        if "already exists" in (create_result["error"] or ""):
            return f"❌ Repository '{repo_name}' already exists."
        return f"❌ Failed to create repo: {create_result['error']}"

    repo_full = f"{owner}/{repo_name}"

    # Brief pause for GitHub to initialize the repo
    import time as _time
    _time.sleep(2)

    # Step 3: Get the current commit SHA on main (from auto_init)
    ref_result = run_gh([
        "api", f"repos/{repo_full}/git/ref/heads/main",
        "--jq", ".object.sha",
    ])
    if not ref_result["success"]:
        return f"❌ Repo created but failed to get initial commit: {ref_result['error']}\n\n🔗 https://github.com/{repo_full}"
    parent_sha = ref_result["output"].strip()

    # Step 4: Create blobs for each file
    tree_entries = []
    for f in files:
        encoded = base64.b64encode(f["content"].encode("utf-8")).decode("utf-8")
        blob_result = run_gh([
            "api", f"repos/{repo_full}/git/blobs", "-X", "POST",
            "-f", f"content={encoded}",
            "-f", "encoding=base64",
            "--jq", ".sha",
        ])
        if not blob_result["success"]:
            return f"❌ Failed to create blob for '{f['path']}': {blob_result['error']}"
        tree_entries.append({
            "path": f["path"],
            "mode": "100644",
            "type": "blob",
            "sha": blob_result["output"].strip(),
        })

    # Step 5: Create a tree (with base_tree from parent to keep README from auto_init)
    import tempfile
    tree_json = json.dumps({"base_tree": parent_sha, "tree": tree_entries})
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tf:
        tf.write(tree_json)
        tf_path = tf.name
    try:
        tree_result = run_gh([
            "api", f"repos/{repo_full}/git/trees", "-X", "POST",
            "--input", tf_path,
            "--jq", ".sha",
        ])
    finally:
        os.unlink(tf_path)

    if not tree_result["success"]:
        return f"❌ Failed to create tree: {tree_result['error']}"
    tree_sha = tree_result["output"].strip()

    # Step 6: Create a commit with the parent
    commit_json = json.dumps({
        "message": "Initial commit — files added via MCP",
        "tree": tree_sha,
        "parents": [parent_sha],
    })
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tf:
        tf.write(commit_json)
        tf_path = tf.name
    try:
        commit_result = run_gh([
            "api", f"repos/{repo_full}/git/commits", "-X", "POST",
            "--input", tf_path,
            "--jq", ".sha",
        ])
    finally:
        os.unlink(tf_path)

    if not commit_result["success"]:
        return f"❌ Failed to create commit: {commit_result['error']}"
    commit_sha = commit_result["output"].strip()

    # Step 7: Update refs/heads/main to point to new commit
    update_ref = run_gh([
        "api", f"repos/{repo_full}/git/refs/heads/main", "-X", "PATCH",
        "-f", f"sha={commit_sha}",
    ])
    if not update_ref["success"]:
        return f"❌ Failed to update ref: {update_ref['error']}"

    file_list = "\n".join(f"  - {f['path']}" for f in files)
    return f"✅ Repository created with {len(files)} files!\n\nFiles:\n{file_list}\n\n🔗 https://github.com/{repo_full}"


@mcp.tool()
def list_repos(
    owner: Optional[str] = None,
    limit: int = 10,
    visibility: str = "all",
) -> str:
    """
    List repositories for a user or organization.
    
    Args:
        owner: GitHub username or org (default: authenticated user)
        limit: Maximum number of repos to list (default: 10)
        visibility: Filter by visibility - 'all', 'public', 'private' (default: 'all')
        
    Returns:
        List of repositories
    """
    log_tool_call("list_repos", owner=owner, limit=limit, visibility=visibility)
    args = ["repo", "list"]

    if owner:
        args.append(owner)

    args.extend(["--limit", str(limit)])

    if visibility != "all":
        args.extend(["--visibility", visibility])

    args.extend(["--json", "name,description,visibility,updatedAt"])

    result = run_gh(args)

    if result["success"]:
        try:
            repos = json.loads(result["output"])
            lines = []
            for r in repos:
                desc = r.get("description") or "No description"
                vis = r.get("visibility", "").upper()
                updated = r.get("updatedAt", "")[:10]
                lines.append(f"  {r['name']} ({vis}) - {desc} [updated: {updated}]")
            formatted = "\n".join(lines) if lines else "No repositories found."
            return f"📁 Repositories:\n\n{formatted}"
        except (json.JSONDecodeError, KeyError):
            return f"📁 Repositories:\n\n{result['output']}"
    else:
        return f"Error: {result['error']}"


@mcp.tool()
def repo_view(repo: str) -> str:
    """
    View details of a GitHub repository.
    
    Args:
        repo: Repository in 'owner/repo' format (e.g., 'prateekaryann/freelance-job-mcp')
        
    Returns:
        Repository details including description, stars, forks, etc.
    """
    log_tool_call("repo_view", repo=repo)
    try:
        repo = validate_repo_name(repo)
    except ValueError as e:
        return str(e)
    result = run_gh(["repo", "view", repo])
    
    if result["success"]:
        return result["output"]
    else:
        return f"Error: {result['error']}"


@mcp.tool()
def clone_repo(repo: str, directory: Optional[str] = None) -> str:
    """
    Clone a GitHub repository.
    
    Args:
        repo: Repository in 'owner/repo' format
        directory: Local directory name (default: repo name)
        
    Returns:
        Success message or error
    """
    log_tool_call("clone_repo", repo=repo, directory=directory)
    try:
        require_write_access("clone_repo")
        repo = validate_repo_name(repo)
    except (PermissionError, ValueError) as e:
        return str(e)
    args = ["repo", "clone", repo]
    
    if directory:
        args.append(directory)
    
    result = run_gh(args)
    
    if result["success"]:
        clone_path = directory or repo.split("/")[-1]
        return f"✅ Cloned to {WORK_DIR / clone_path}"
    else:
        return f"❌ Clone failed\n\n{result['error']}"


@mcp.tool()
def delete_repo(repo: str, confirm: bool = False) -> str:
    """
    Delete a GitHub repository. USE WITH CAUTION!
    
    Args:
        repo: Repository in 'owner/repo' format
        confirm: Must be True to actually delete (safety check)
        
    Returns:
        Confirmation or error
    """
    log_tool_call("delete_repo", repo=repo, confirm=confirm)
    try:
        require_write_access("delete_repo")
    except PermissionError as e:
        return str(e)
    try:
        repo = validate_repo_name(repo)
    except ValueError as e:
        return str(e)
    if not confirm:
        return "⚠️ Safety check: Set confirm=True to actually delete the repository. This cannot be undone!"
    
    result = run_gh(["repo", "delete", repo, "--yes"])
    
    if result["success"]:
        return f"✅ Repository {repo} deleted"
    else:
        return f"❌ Failed to delete\n\n{result['error']}"


# =============================================================================
# GIT OPERATIONS (Push, Pull, Commit)
# =============================================================================

@mcp.tool()
def git_status(repo_path: str) -> str:
    """
    Get git status for a local repository.
    
    Args:
        repo_path: Path to the local repository
        
    Returns:
        Git status output
    """
    log_tool_call("git_status", repo_path=repo_path)
    try:
        repo_path = validate_path(repo_path)
    except ValueError as e:
        return str(e)
    result = run_git(["status"], cwd=repo_path)
    
    if result["success"]:
        return result["output"]
    else:
        return f"Error: {result['error']}"


@mcp.tool()
def git_add_commit_push(
    repo_path: str,
    message: str,
    add_all: bool = True,
    branch: str = "main",
) -> str:
    """
    Add, commit, and push changes in one operation.
    
    Args:
        repo_path: Path to the local repository
        message: Commit message
        add_all: Whether to add all changes (default: True)
        branch: Branch to push to (default: 'main')
        
    Returns:
        Success message or error
    """
    log_tool_call("git_add_commit_push", repo_path=repo_path, message=message, add_all=add_all, branch=branch)
    try:
        require_write_access("git_add_commit_push")
    except PermissionError as e:
        return str(e)
    try:
        repo_path = validate_path(repo_path)
    except ValueError as e:
        return str(e)
    try:
        branch = validate_branch_name(branch)
    except ValueError as e:
        return str(e)
    results = []

    # Add
    if add_all:
        add_result = run_git(["add", "."], cwd=repo_path)
        if not add_result["success"]:
            return f"❌ Git add failed: {add_result['error']}"
        results.append("✅ Added changes")
    
    # Commit
    commit_result = run_git(["commit", "-m", message], cwd=repo_path)
    if not commit_result["success"]:
        if "nothing to commit" in commit_result["error"]:
            return "ℹ️ Nothing to commit - working tree clean"
        return f"❌ Git commit failed: {commit_result['error']}"
    results.append(f"✅ Committed: {message}")
    
    # Push
    push_result = run_git(["push", "-u", "origin", branch], cwd=repo_path)
    if not push_result["success"]:
        return f"❌ Git push failed: {push_result['error']}"
    results.append(f"✅ Pushed to origin/{branch}")
    
    return "\n".join(results)


@mcp.tool()
def git_init_and_push(
    repo_path: str,
    repo_name: str,
    description: str = "",
    public: bool = True,
    commit_message: str = "Initial commit",
) -> str:
    """
    Initialize a local directory as a git repo, create GitHub repo, and push.
    Perfect for pushing an existing project to GitHub.
    
    Args:
        repo_path: Path to the local project directory
        repo_name: Name for the GitHub repository
        description: Repository description
        public: Whether the repo should be public
        commit_message: Initial commit message
        
    Returns:
        Success message with repo URL or error
    """
    log_tool_call("git_init_and_push", repo_path=repo_path, repo_name=repo_name, description=description, public=public, commit_message=commit_message)
    try:
        require_write_access("git_init_and_push")
    except PermissionError as e:
        return str(e)
    try:
        repo_path = validate_path(repo_path)
    except ValueError as e:
        return str(e)
    path = Path(repo_path).expanduser().resolve()
    
    if not path.exists():
        return f"❌ Directory not found: {path}"
    
    results = []
    
    # Check if already a git repo
    git_dir = path / ".git"
    if not git_dir.exists():
        # Init
        init_result = run_git(["init"], cwd=str(path))
        if not init_result["success"]:
            return f"❌ Git init failed: {init_result['error']}"
        results.append("✅ Initialized git repository")
        
        # Set branch to main
        run_git(["branch", "-M", "main"], cwd=str(path))
    else:
        results.append("ℹ️ Already a git repository")
    
    # Add and commit if needed
    status_result = run_git(["status", "--porcelain"], cwd=str(path))
    if status_result["output"]:  # Has changes
        run_git(["add", "."], cwd=str(path))
        commit_result = run_git(["commit", "-m", commit_message], cwd=str(path))
        if commit_result["success"]:
            results.append(f"✅ Committed: {commit_message}")
    
    # Create GitHub repo
    visibility = "--public" if public else "--private"
    create_args = ["repo", "create", repo_name, visibility, "--source", str(path), "--push"]
    
    if description:
        create_args.extend(["--description", description])
    
    create_result = run_gh(create_args)
    
    if create_result["success"]:
        results.append(f"✅ Created and pushed to GitHub!")
        results.append(f"\n🔗 https://github.com/{repo_name}")
        return "\n".join(results)
    else:
        # Maybe repo already exists, try just adding remote and pushing
        if "already exists" in create_result["error"]:
            results.append("ℹ️ Repository already exists, trying to push...")
            
            # Get username
            user_result = run_gh(["api", "user", "--jq", ".login"])
            if user_result["success"]:
                username = user_result["output"]
                remote_url = f"git@github.com:{username}/{repo_name}.git"
                
                # Add remote if not exists
                run_git(["remote", "add", "origin", remote_url], cwd=str(path))
                
                # Push
                push_result = run_git(["push", "-u", "origin", "main"], cwd=str(path))
                if push_result["success"]:
                    results.append(f"✅ Pushed to existing repo!")
                    results.append(f"\n🔗 https://github.com/{username}/{repo_name}")
                    return "\n".join(results)
                else:
                    return f"❌ Push failed: {push_result['error']}"
        
        return f"❌ Failed to create repo: {create_result['error']}"


@mcp.tool()
def git_pull(repo_path: str, branch: str = "main") -> str:
    """
    Pull latest changes from remote.
    
    Args:
        repo_path: Path to the local repository
        branch: Branch to pull (default: 'main')
    """
    log_tool_call("git_pull", repo_path=repo_path, branch=branch)
    try:
        require_write_access("git_pull")
    except PermissionError as e:
        return str(e)
    try:
        repo_path = validate_path(repo_path)
        branch = validate_branch_name(branch)
    except ValueError as e:
        return str(e)
    result = run_git(["pull", "origin", branch], cwd=repo_path)

    if result["success"]:
        return f"✅ Pulled latest from origin/{branch}\n\n{result['output']}"
    else:
        return f"❌ Pull failed: {result['error']}"


# =============================================================================
# BRANCH OPERATIONS
# =============================================================================

@mcp.tool()
def create_branch(
    repo_path: str,
    branch_name: str,
    from_branch: str = "main",
) -> str:
    """
    Create a new git branch.

    Args:
        repo_path: Path to the local repository
        branch_name: Name for the new branch
        from_branch: Branch to create from (default: 'main')

    Returns:
        Success message or error
    """
    log_tool_call("create_branch", repo_path=repo_path, branch_name=branch_name, from_branch=from_branch)
    try:
        require_write_access("create_branch")
    except PermissionError as e:
        return str(e)
    try:
        repo_path = validate_path(repo_path)
    except ValueError as e:
        return str(e)
    try:
        branch_name = validate_branch_name(branch_name)
    except ValueError as e:
        return str(e)
    try:
        from_branch = validate_branch_name(from_branch)
    except ValueError as e:
        return str(e)
    result = run_git(["checkout", "-b", branch_name, from_branch], cwd=repo_path)

    if result["success"]:
        return f"✅ Created and switched to branch '{branch_name}' (from '{from_branch}')"
    else:
        return f"❌ Failed to create branch: {result['error']}"


@mcp.tool()
def list_branches(repo_path: str) -> str:
    """
    List all local branches, marking the current one.

    Args:
        repo_path: Path to the local repository

    Returns:
        List of branches with current branch marked
    """
    log_tool_call("list_branches", repo_path=repo_path)
    try:
        repo_path = validate_path(repo_path)
    except ValueError as e:
        return str(e)
    result = run_git(["branch"], cwd=repo_path)

    if result["success"]:
        return f"🔀 Branches:\n\n{result['output']}"
    else:
        return f"❌ Failed to list branches: {result['error']}"


@mcp.tool()
def switch_branch(repo_path: str, branch_name: str) -> str:
    """
    Switch to (checkout) a branch.

    Args:
        repo_path: Path to the local repository
        branch_name: Branch to switch to

    Returns:
        Success message or error
    """
    log_tool_call("switch_branch", repo_path=repo_path, branch_name=branch_name)
    try:
        require_write_access("switch_branch")
        repo_path = validate_path(repo_path)
        branch_name = validate_branch_name(branch_name)
    except (PermissionError, ValueError) as e:
        return str(e)
    result = run_git(["checkout", branch_name], cwd=repo_path)

    if result["success"]:
        return f"✅ Switched to branch '{branch_name}'"
    else:
        return f"❌ Failed to switch branch: {result['error']}"


@mcp.tool()
def delete_branch(
    repo_path: str,
    branch_name: str,
    force: bool = False,
) -> str:
    """
    Delete a local branch.

    Args:
        repo_path: Path to the local repository
        branch_name: Branch to delete
        force: Force delete even if not fully merged (default: False)

    Returns:
        Success message or error
    """
    log_tool_call("delete_branch", repo_path=repo_path, branch_name=branch_name, force=force)
    try:
        require_write_access("delete_branch")
    except PermissionError as e:
        return str(e)
    try:
        repo_path = validate_path(repo_path)
    except ValueError as e:
        return str(e)
    try:
        branch_name = validate_branch_name(branch_name)
    except ValueError as e:
        return str(e)
    flag = "-D" if force else "-d"
    result = run_git(["branch", flag, branch_name], cwd=repo_path)

    if result["success"]:
        return f"✅ Deleted branch '{branch_name}'"
    else:
        return f"❌ Failed to delete branch: {result['error']}"


# =============================================================================
# FORK OPERATIONS
# =============================================================================

@mcp.tool()
def fork_repo(repo: str, clone: bool = False) -> str:
    """
    Fork a GitHub repository to your account.

    Args:
        repo: Repository in 'owner/repo' format (e.g., 'facebook/react')
        clone: Whether to clone the fork locally after creation (default: False)

    Returns:
        Success message with fork info or error
    """
    log_tool_call("fork_repo", repo=repo, clone=clone)
    try:
        require_write_access("fork_repo")
    except PermissionError as e:
        return str(e)
    try:
        repo = validate_repo_name(repo)
    except ValueError as e:
        return str(e)
    args = ["repo", "fork", repo]

    if clone:
        args.append("--clone")
    else:
        args.append("--clone=false")

    result = run_gh(args)

    if result["success"]:
        return f"✅ Forked {repo}!\n\n{result['output']}"
    else:
        return f"❌ Failed to fork repository\n\n{result['error']}"


@mcp.tool()
def sync_fork(repo_path: str) -> str:
    """
    Sync a forked repository with its upstream (parent) repository.

    Args:
        repo_path: Path to the local fork repository

    Returns:
        Success message or error
    """
    log_tool_call("sync_fork", repo_path=repo_path)
    try:
        require_write_access("sync_fork")
        repo_path = validate_path(repo_path)
    except (PermissionError, ValueError) as e:
        return str(e)
    result = run_gh(["repo", "sync"], cwd=repo_path)

    if result["success"]:
        return f"✅ Fork synced with upstream!\n\n{result['output']}"
    else:
        return f"❌ Failed to sync fork\n\n{result['error']}"


# =============================================================================
# ISSUES
# =============================================================================

@mcp.tool()
def create_issue(
    repo: str,
    title: str,
    body: str = "",
    labels: Optional[str] = None,
) -> str:
    """
    Create a new GitHub issue.
    
    Args:
        repo: Repository in 'owner/repo' format
        title: Issue title
        body: Issue body/description
        labels: Comma-separated labels (e.g., 'bug,help wanted')
        
    Returns:
        Issue URL or error
    """
    log_tool_call("create_issue", repo=repo, title=title, body=body, labels=labels)
    try:
        require_write_access("create_issue")
    except PermissionError as e:
        return str(e)
    try:
        repo = validate_repo_name(repo)
    except ValueError as e:
        return str(e)
    args = ["issue", "create", "--repo", repo, "--title", title]
    
    if body:
        args.extend(["--body", body])
    
    if labels:
        args.extend(["--label", labels])
    
    result = run_gh(args)
    
    if result["success"]:
        return f"✅ Issue created!\n\n{result['output']}"
    else:
        return f"❌ Failed to create issue: {result['error']}"


@mcp.tool()
def list_issues(
    repo: str,
    state: str = "open",
    limit: int = 10,
) -> str:
    """
    List issues for a repository.
    
    Args:
        repo: Repository in 'owner/repo' format
        state: Filter by state - 'open', 'closed', 'all' (default: 'open')
        limit: Maximum number of issues to list
        
    Returns:
        List of issues
    """
    log_tool_call("list_issues", repo=repo, state=state, limit=limit)
    try:
        repo = validate_repo_name(repo)
    except ValueError as e:
        return str(e)
    args = ["issue", "list", "--repo", repo, "--state", state, "--limit", str(limit)]
    args.extend(["--json", "number,title,state,author,createdAt"])

    result = run_gh(args)

    if result["success"]:
        try:
            issues = json.loads(result["output"])
            lines = []
            for i in issues:
                author = i.get("author", {}).get("login", "unknown") if isinstance(i.get("author"), dict) else "unknown"
                created = i.get("createdAt", "")[:10]
                lines.append(f"  #{i['number']} [{i['state']}] {i['title']} (by {author}, {created})")
            formatted = "\n".join(lines) if lines else "No issues found."
            return f"📋 Issues ({state}):\n\n{formatted}"
        except (json.JSONDecodeError, KeyError):
            return f"📋 Issues ({state}):\n\n{result['output']}"
    else:
        return f"Error: {result['error']}"


@mcp.tool()
def comment_on_issue(
    repo: str,
    issue_number: int,
    body: str,
) -> str:
    """
    Add a comment to an issue.

    Args:
        repo: Repository in 'owner/repo' format
        issue_number: Issue number to comment on
        body: Comment text

    Returns:
        Success message or error
    """
    log_tool_call("comment_on_issue", repo=repo, issue_number=issue_number, body=body)
    try:
        require_write_access("comment_on_issue")
    except PermissionError as e:
        return str(e)
    try:
        repo = validate_repo_name(repo)
    except ValueError as e:
        return str(e)
    args = ["issue", "comment", str(issue_number), "--repo", repo, "--body", body]

    result = run_gh(args)

    if result["success"]:
        return f"✅ Comment added to issue #{issue_number}\n\n{result['output']}"
    else:
        return f"❌ Failed to comment on issue: {result['error']}"


# =============================================================================
# PULL REQUESTS
# =============================================================================

@mcp.tool()
def create_pr(
    repo: str,
    title: str,
    body: str = "",
    base: str = "main",
    head: Optional[str] = None,
    draft: bool = False,
) -> str:
    """
    Create a pull request.
    
    Args:
        repo: Repository in 'owner/repo' format
        title: PR title
        body: PR description
        base: Base branch (default: 'main')
        head: Head branch (default: current branch)
        draft: Create as draft PR
        
    Returns:
        PR URL or error
    """
    log_tool_call("create_pr", repo=repo, title=title, body=body, base=base, head=head, draft=draft)
    try:
        require_write_access("create_pr")
        repo = validate_repo_name(repo)
        base = validate_branch_name(base)
        if head:
            head = validate_branch_name(head)
    except (PermissionError, ValueError) as e:
        return str(e)
    args = ["pr", "create", "--repo", repo, "--title", title, "--base", base]
    
    if body:
        args.extend(["--body", body])
    
    if head:
        args.extend(["--head", head])
    
    if draft:
        args.append("--draft")
    
    result = run_gh(args)
    
    if result["success"]:
        return f"✅ Pull request created!\n\n{result['output']}"
    else:
        return f"❌ Failed to create PR: {result['error']}"


@mcp.tool()
def list_prs(
    repo: str,
    state: str = "open",
    limit: int = 10,
) -> str:
    """
    List pull requests for a repository.
    
    Args:
        repo: Repository in 'owner/repo' format
        state: Filter by state - 'open', 'closed', 'merged', 'all'
        limit: Maximum number of PRs to list
    """
    log_tool_call("list_prs", repo=repo, state=state, limit=limit)
    try:
        repo = validate_repo_name(repo)
    except ValueError as e:
        return str(e)
    args = ["pr", "list", "--repo", repo, "--state", state, "--limit", str(limit)]
    args.extend(["--json", "number,title,state,author,createdAt"])

    result = run_gh(args)

    if result["success"]:
        try:
            prs = json.loads(result["output"])
            lines = []
            for p in prs:
                author = p.get("author", {}).get("login", "unknown") if isinstance(p.get("author"), dict) else "unknown"
                created = p.get("createdAt", "")[:10]
                lines.append(f"  #{p['number']} [{p['state']}] {p['title']} (by {author}, {created})")
            formatted = "\n".join(lines) if lines else "No pull requests found."
            return f"🔀 Pull Requests ({state}):\n\n{formatted}"
        except (json.JSONDecodeError, KeyError):
            return f"🔀 Pull Requests ({state}):\n\n{result['output']}"
    else:
        return f"Error: {result['error']}"


@mcp.tool()
def comment_on_pr(
    repo: str,
    pr_number: int,
    body: str,
) -> str:
    """
    Add a comment to a pull request.

    Args:
        repo: Repository in 'owner/repo' format
        pr_number: Pull request number to comment on
        body: Comment text

    Returns:
        Success message or error
    """
    log_tool_call("comment_on_pr", repo=repo, pr_number=pr_number, body=body)
    try:
        require_write_access("comment_on_pr")
    except PermissionError as e:
        return str(e)
    try:
        repo = validate_repo_name(repo)
    except ValueError as e:
        return str(e)
    args = ["pr", "comment", str(pr_number), "--repo", repo, "--body", body]

    result = run_gh(args)

    if result["success"]:
        return f"✅ Comment added to PR #{pr_number}\n\n{result['output']}"
    else:
        return f"❌ Failed to comment on PR: {result['error']}"


# =============================================================================
# COLLABORATORS
# =============================================================================

@mcp.tool()
def list_collaborators(repo: str) -> str:
    """
    List collaborators for a GitHub repository.

    Args:
        repo: Repository in 'owner/repo' format (e.g., 'prateekaryann/github-mcp')

    Returns:
        List of collaborator usernames
    """
    log_tool_call("list_collaborators", repo=repo)
    try:
        repo = validate_repo_name(repo)
    except ValueError as e:
        return str(e)
    result = run_gh(["api", f"repos/{repo}/collaborators", "--jq", ".[].login"])

    if result["success"]:
        return f"👥 Collaborators for {repo}:\n\n{result['output']}"
    else:
        return f"❌ Failed to list collaborators: {result['error']}"


@mcp.tool()
def add_collaborator(
    repo: str,
    username: str,
    permission: str = "push",
) -> str:
    """
    Add a collaborator to a GitHub repository.

    Args:
        repo: Repository in 'owner/repo' format (e.g., 'prateekaryann/github-mcp')
        username: GitHub username to add as collaborator
        permission: Permission level - 'pull', 'push', 'admin' (default: 'push')

    Returns:
        Success message or error
    """
    log_tool_call("add_collaborator", repo=repo, username=username, permission=permission)
    try:
        require_write_access("add_collaborator")
        repo = validate_repo_name(repo)
        username = validate_username(username)
        if permission not in ("pull", "push", "admin"):
            raise ValueError(f"⛔ Invalid permission: '{permission}'. Must be 'pull', 'push', or 'admin'.")
    except (PermissionError, ValueError) as e:
        return str(e)
    result = run_gh([
        "api", "-X", "PUT",
        f"repos/{repo}/collaborators/{username}",
        "-f", f"permission={permission}",
    ])

    if result["success"]:
        return f"✅ Added {username} as collaborator to {repo} with '{permission}' permission"
    else:
        return f"❌ Failed to add collaborator: {result['error']}"


# =============================================================================
# FILE OPERATIONS
# =============================================================================

@mcp.tool()
def get_file_contents(repo: str, path: str, ref: str = "main") -> str:
    """
    Get the contents of a file from a GitHub repository.

    Args:
        repo: Repository in 'owner/repo' format (e.g., 'prateekaryann/github-mcp')
        path: Path to the file in the repo (e.g., 'src/main.py')
        ref: Branch, tag, or commit SHA (default: 'main')

    Returns:
        File contents or error
    """
    log_tool_call("get_file_contents", repo=repo, path=path, ref=ref)
    try:
        repo = validate_repo_name(repo)
        path = validate_file_path(path)
        ref = validate_branch_name(ref)
    except ValueError as e:
        return str(e)
    result = run_gh(["api", f"repos/{repo}/contents/{path}?ref={ref}", "--jq", ".content"])

    if result["success"]:
        try:
            decoded = base64.b64decode(result["output"]).decode("utf-8")
            return f"📄 {path} (from {repo}@{ref}):\n\n{decoded}"
        except Exception:
            return result["output"]
    else:
        return f"❌ Failed to get file contents: {result['error']}"


@mcp.tool()
def create_or_update_file(
    repo: str,
    path: str,
    content: str,
    message: str,
    branch: str = "main",
) -> str:
    """
    Create or update a file in a GitHub repository via the API.

    Args:
        repo: Repository in 'owner/repo' format (e.g., 'prateekaryann/github-mcp')
        path: Path to the file in the repo (e.g., 'docs/README.md')
        content: The file content to write
        message: Commit message for the change
        branch: Branch to commit to (default: 'main')

    Returns:
        Success message with commit info or error
    """
    log_tool_call("create_or_update_file", repo=repo, path=path, content=content, message=message, branch=branch)
    try:
        require_write_access("create_or_update_file")
        repo = validate_repo_name(repo)
        path = validate_file_path(path)
        branch = validate_branch_name(branch)
    except (PermissionError, ValueError) as e:
        return str(e)
    encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")

    # Try to get existing file SHA (needed for updates)
    sha_result = run_gh(["api", f"repos/{repo}/contents/{path}?ref={branch}", "--jq", ".sha"])
    sha = sha_result["output"] if sha_result["success"] else None

    # Build the API request
    args = [
        "api", "-X", "PUT",
        f"repos/{repo}/contents/{path}",
        "-f", f"message={message}",
        "-f", f"content={encoded_content}",
        "-f", f"branch={branch}",
    ]

    if sha:
        args.extend(["-f", f"sha={sha}"])

    result = run_gh(args)

    if result["success"]:
        action = "Updated" if sha else "Created"
        return f"✅ {action} {path} in {repo} ({branch})\n\nCommit message: {message}"
    else:
        return f"❌ Failed to create/update file: {result['error']}"


# =============================================================================
# PR MERGE, REVIEW & DIFF
# =============================================================================

@mcp.tool()
def merge_pr(
    repo: str,
    pr_number: int,
    method: str = "merge",
    delete_branch: bool = True,
) -> str:
    """
    Merge a pull request.

    Args:
        repo: Repository in 'owner/repo' format
        pr_number: Pull request number
        method: Merge method - 'merge', 'squash', or 'rebase' (default: 'merge')
        delete_branch: Whether to delete the branch after merging (default: True)

    Returns:
        Success message or error
    """
    log_tool_call("merge_pr", repo=repo, pr_number=pr_number, method=method, delete_branch=delete_branch)
    try:
        require_write_access("merge_pr")
    except PermissionError as e:
        return str(e)
    try:
        repo = validate_repo_name(repo)
    except ValueError as e:
        return str(e)
    args = ["pr", "merge", str(pr_number), "--repo", repo, f"--{method}"]

    if delete_branch:
        args.append("--delete-branch")

    result = run_gh(args)

    if result["success"]:
        return f"✅ PR #{pr_number} merged ({method})!\n\n{result['output']}"
    else:
        return f"❌ Failed to merge PR: {result['error']}"


@mcp.tool()
def review_pr(
    repo: str,
    pr_number: int,
    action: str = "approve",
    body: str = "",
) -> str:
    """
    Review a pull request.

    Args:
        repo: Repository in 'owner/repo' format
        pr_number: Pull request number
        action: Review action - 'approve', 'comment', or 'request-changes' (default: 'approve')
        body: Review comment body (required for 'comment' and 'request-changes')

    Returns:
        Success message or error
    """
    log_tool_call("review_pr", repo=repo, pr_number=pr_number, action=action, body=body)
    try:
        require_write_access("review_pr")
    except PermissionError as e:
        return str(e)
    try:
        repo = validate_repo_name(repo)
    except ValueError as e:
        return str(e)
    args = ["pr", "review", str(pr_number), "--repo", repo, f"--{action}"]

    if body:
        args.extend(["--body", body])

    result = run_gh(args)

    if result["success"]:
        return f"✅ PR #{pr_number} reviewed ({action})!\n\n{result['output']}"
    else:
        return f"❌ Failed to review PR: {result['error']}"


@mcp.tool()
def pr_diff(
    repo: str,
    pr_number: int,
) -> str:
    """
    View the diff of a pull request.

    Args:
        repo: Repository in 'owner/repo' format
        pr_number: Pull request number

    Returns:
        PR diff output or error
    """
    log_tool_call("pr_diff", repo=repo, pr_number=pr_number)
    try:
        repo = validate_repo_name(repo)
    except ValueError as e:
        return str(e)
    result = run_gh(["pr", "diff", str(pr_number), "--repo", repo])

    if result["success"]:
        return f"📋 Diff for PR #{pr_number}:\n\n{result['output']}"
    else:
        return f"❌ Failed to get PR diff: {result['error']}"


# =============================================================================
# GISTS
# =============================================================================

@mcp.tool()
def create_gist(
    filename: str,
    content: str,
    description: str = "",
    public: bool = False,
) -> str:
    """
    Create a GitHub Gist.
    
    Args:
        filename: Name for the gist file (e.g., 'script.py')
        content: File content
        description: Gist description
        public: Whether the gist should be public
        
    Returns:
        Gist URL or error
    """
    log_tool_call("create_gist", filename=filename, content=content, description=description, public=public)
    try:
        require_write_access("create_gist")
    except PermissionError as e:
        return str(e)
    import tempfile
    
    # Write content to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix=f"_{filename}", delete=False) as f:
        f.write(content)
        temp_path = f.name
    
    try:
        args = ["gist", "create", temp_path]
        
        if description:
            args.extend(["--desc", description])
        
        if public:
            args.append("--public")
        
        result = run_gh(args)
        
        if result["success"]:
            return f"✅ Gist created!\n\n{result['output']}"
        else:
            return f"❌ Failed to create gist: {result['error']}"
    finally:
        os.unlink(temp_path)


# =============================================================================
# WORKFLOWS (GitHub Actions)
# =============================================================================

@mcp.tool()
def list_workflows(repo: str) -> str:
    """
    List workflows in a GitHub repository.

    Args:
        repo: Repository in 'owner/repo' format

    Returns:
        List of workflows in the repository
    """
    log_tool_call("list_workflows", repo=repo)
    try:
        repo = validate_repo_name(repo)
    except ValueError as e:
        return str(e)
    result = run_gh(["workflow", "list", "--repo", repo])

    if result["success"]:
        return f"⚙️ Workflows for {repo}:\n\n{result['output']}"
    else:
        return f"❌ Failed to list workflows: {result['error']}"


@mcp.tool()
def run_workflow(repo: str, workflow: str, ref: str = "main") -> str:
    """
    Trigger a GitHub Actions workflow run.

    Args:
        repo: Repository in 'owner/repo' format
        workflow: Workflow filename or ID (e.g., 'build.yml')
        ref: Branch or tag to run the workflow on

    Returns:
        Confirmation of workflow trigger
    """
    log_tool_call("run_workflow", repo=repo, workflow=workflow, ref=ref)
    try:
        require_write_access("run_workflow")
        repo = validate_repo_name(repo)
        ref = validate_branch_name(ref)
        if not re.match(r'^[a-zA-Z0-9._/-]+$', workflow):
            raise ValueError(f"⛔ Invalid workflow name: '{workflow}'")
    except (PermissionError, ValueError) as e:
        return str(e)
    result = run_gh(["workflow", "run", workflow, "--repo", repo, "--ref", ref])

    if result["success"]:
        return f"✅ Workflow '{workflow}' triggered on {ref} in {repo}\n\n{result['output']}"
    else:
        return f"❌ Failed to trigger workflow: {result['error']}"


@mcp.tool()
def list_workflow_runs(repo: str, limit: int = 10) -> str:
    """
    List recent GitHub Actions workflow runs.

    Args:
        repo: Repository in 'owner/repo' format
        limit: Maximum number of runs to show

    Returns:
        List of recent workflow runs
    """
    log_tool_call("list_workflow_runs", repo=repo, limit=limit)
    try:
        repo = validate_repo_name(repo)
    except ValueError as e:
        return str(e)
    result = run_gh(["run", "list", "--repo", repo, "--limit", str(limit)])

    if result["success"]:
        return f"🔄 Recent workflow runs for {repo}:\n\n{result['output']}"
    else:
        return f"❌ Failed to list workflow runs: {result['error']}"


@mcp.tool()
def view_workflow_run(repo: str, run_id: str) -> str:
    """
    View details of a specific GitHub Actions workflow run.

    Args:
        repo: Repository in 'owner/repo' format
        run_id: The ID of the workflow run

    Returns:
        Details of the workflow run
    """
    log_tool_call("view_workflow_run", repo=repo, run_id=run_id)
    try:
        repo = validate_repo_name(repo)
        if not re.match(r'^\d+$', run_id):
            raise ValueError(f"⛔ Invalid run ID: '{run_id}'. Must be numeric.")
    except ValueError as e:
        return str(e)
    result = run_gh(["run", "view", run_id, "--repo", repo])

    if result["success"]:
        return f"📋 Workflow run {run_id}:\n\n{result['output']}"
    else:
        return f"❌ Failed to view workflow run: {result['error']}"


# =============================================================================
# SEARCH
# =============================================================================

@mcp.tool()
def search_repos(
    query: str,
    limit: int = 10,
) -> str:
    """
    Search GitHub repositories.
    
    Args:
        query: Search query (e.g., 'fastapi language:python stars:>100')
        limit: Maximum number of results
        
    Returns:
        List of matching repositories
    """
    log_tool_call("search_repos", query=query, limit=limit)
    args = ["search", "repos", query, "--limit", str(limit)]
    
    result = run_gh(args)
    
    if result["success"]:
        return f"🔍 Search results:\n\n{result['output']}"
    else:
        return f"Error: {result['error']}"


# =============================================================================
# RELEASES
# =============================================================================

@mcp.tool()
def create_release(
    repo: str,
    tag: str,
    title: str,
    notes: str = "",
    draft: bool = False,
    prerelease: bool = False,
) -> str:
    """
    Create a GitHub release.
    
    Args:
        repo: Repository in 'owner/repo' format
        tag: Tag name (e.g., 'v1.0.0')
        title: Release title
        notes: Release notes
        draft: Create as draft
        prerelease: Mark as prerelease
        
    Returns:
        Release URL or error
    """
    log_tool_call("create_release", repo=repo, tag=tag, title=title, notes=notes, draft=draft, prerelease=prerelease)
    try:
        require_write_access("create_release")
    except PermissionError as e:
        return str(e)
    try:
        repo = validate_repo_name(repo)
    except ValueError as e:
        return str(e)
    args = ["release", "create", tag, "--repo", repo, "--title", title]
    
    if notes:
        args.extend(["--notes", notes])
    
    if draft:
        args.append("--draft")
    
    if prerelease:
        args.append("--prerelease")
    
    result = run_gh(args)
    
    if result["success"]:
        return f"✅ Release created!\n\n{result['output']}"
    else:
        return f"❌ Failed to create release: {result['error']}"


@mcp.tool()
def list_releases(repo: str, limit: int = 10) -> str:
    """
    List releases for a GitHub repository.

    Args:
        repo: Repository in 'owner/repo' format
        limit: Maximum number of releases to list (default: 10)

    Returns:
        List of releases or error
    """
    log_tool_call("list_releases", repo=repo, limit=limit)
    try:
        repo = validate_repo_name(repo)
    except ValueError as e:
        return str(e)
    result = run_gh(["release", "list", "--repo", repo, "--limit", str(limit)])

    if result["success"]:
        output = result["output"].strip()
        if not output:
            return f"ℹ️ No releases found for {repo}"
        return f"📋 Releases for {repo}:\n\n{output}"
    else:
        return f"❌ Failed to list releases: {result['error']}"


# =============================================================================
# RUN SERVER
# =============================================================================

if __name__ == "__main__":
    import shutil

    WORK_DIR.mkdir(parents=True, exist_ok=True)

    if not shutil.which("gh"):
        print("GitHub CLI (gh) not found! Install from: https://cli.github.com/")
        print("Then run: gh auth login")

    run_server(mcp)
