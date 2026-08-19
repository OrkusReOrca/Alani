"""Cross-repo bridge: lets Alani trigger/inspect GitHub Actions workflows in
another repo (Alani-Bot by default) via the already-authenticated `gh` CLI
on this machine. No new infrastructure — reuses the `gh auth login` set up
for Alani-Bot's own development.
"""

import shutil
import subprocess

from .config import GITHUB_BOT_REPO

# On Windows, `gh` may not be on PATH for every shell (seen previously with
# GitHub CLI installed via winget) — fall back to the known install path.
_GH_CANDIDATES = ["gh", r"C:\Program Files\GitHub CLI\gh.exe"]


def _gh_path():
    for candidate in _GH_CANDIDATES:
        if shutil.which(candidate) or candidate.endswith(".exe"):
            return candidate
    return "gh"


GH = _gh_path()


def trigger_workflow(workflow_name: str, repo: str = GITHUB_BOT_REPO) -> str:
    """Triggers a GitHub Actions workflow via workflow_dispatch. Returns a
    short human-readable result string (never raises to the caller — tool
    calls should always produce something speakable back to the user)."""
    try:
        result = subprocess.run(
            [GH, "workflow", "run", workflow_name, "-R", repo],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return f"Triggered the '{workflow_name}' workflow in {repo}."
        return f"Couldn't trigger '{workflow_name}': {result.stderr.strip() or result.stdout.strip()}"
    except Exception as e:
        return f"Couldn't trigger '{workflow_name}': {e}"


def list_workflows(repo: str = GITHUB_BOT_REPO) -> str:
    """Lists available workflow names in the target repo."""
    try:
        result = subprocess.run(
            [GH, "workflow", "list", "-R", repo],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return result.stdout.strip() or "No workflows found."
        return f"Couldn't list workflows: {result.stderr.strip()}"
    except Exception as e:
        return f"Couldn't list workflows: {e}"
