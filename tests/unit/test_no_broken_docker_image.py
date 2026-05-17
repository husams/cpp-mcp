"""Repo-grep test: assert the broken Docker image reference is absent.

ADR-16 (2026-05-17) replaced the broken Docker compose fixture with the
``cargo install indradb`` path.  This test ensures the broken image tag never
comes back in production/test code.

The image name is split across a variable to avoid this source file itself
triggering the grep.
"""

import os
import subprocess

# Split to prevent this source file from matching the grep below.
_BROKEN_IMAGE = "indradb/" + "indradb:5.0.0"


def test_no_broken_docker_image_reference() -> None:
    """Assert the broken Docker image tag is absent from src/tests/fixtures."""
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    result = subprocess.run(
        [
            "grep",
            "-rn",
            _BROKEN_IMAGE,
            ".",
            "--exclude-dir=.git",
            "--exclude-dir=.venv",
            "--exclude-dir=.claude",
            "--exclude-dir=__pycache__",
            "--include=*.py",
            "--include=*.yml",
            "--include=*.yaml",
            "--include=*.toml",
            "--include=*.md",
            "--include=*.txt",
        ],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    assert result.returncode != 0, (
        f"Found broken Docker image reference `{_BROKEN_IMAGE}` in the repo "
        "(ADR-16: use `cargo install indradb` instead). "
        f"Matches:\n{result.stdout}"
    )
