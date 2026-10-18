"""Review, stage, container-test, then optionally apply a single Python patch.

No repository code executes on the host. A successful Docker test is required
before the on-disk source can be changed through this module.
"""
from __future__ import annotations

import ast
import difflib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

from app.agent.patches import PatchProposal
from app.tools.repo_tools import RepositoryExplorer

MAX_MANIFEST_BYTES = 150_000
MAX_COPY_FILES = 1000
MAX_COPY_BYTES = 12_000_000
MAX_SOURCE_BYTES = 64_000
IMAGE = "devpilot-test-runner:local"
KEEP_EXTENSIONS = {".py", ".toml", ".ini", ".cfg", ".json", ".yaml", ".yml", ".txt"}


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SavedPatch:
    path: str
    explanation: str
    original_hash: str
    proposed_source: str


def save_proposal(proposal: PatchProposal, destination: Path) -> None:
    """Persist an already validated proposal for a separate approval process."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ValueError("Refusing to overwrite a symlinked proposal")
    if destination.exists():
        raise FileExistsError(f"Proposal already exists: {destination}")
    data = {
        "format_version": 1,
        "path": proposal.path,
        "explanation": proposal.explanation,
        "original_sha256": fingerprint(proposal.original),
        "proposed_source": proposal.proposed,
    }
    content = json.dumps(data, ensure_ascii=False, indent=2)
    if len(content.encode("utf-8")) > MAX_MANIFEST_BYTES:
        raise ValueError("Proposal manifest exceeds allowed size")
    with destination.open("x", encoding="utf-8") as f:
        f.write(content)


def load_proposal(repo: Path, location: Path) -> tuple[SavedPatch, Path, str]:
    """Re-check the manifest against the *current* original source."""
    if location.is_symlink() or not location.is_file():
        raise ValueError("Manifest not found or is a symlink")
    if location.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError("Manifest too large")
    data = json.loads(location.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("format_version") != 1:
        raise ValueError("Unsupported proposal format")
    path = data.get("path")
    if not isinstance(path, str) or not path or "\\" in path or ":" in path:
        raise ValueError("Invalid target path")
    parts = PurePosixPath(path).parts
    if PurePosixPath(path).is_absolute() or any(p in ("", ".", "..") for p in parts) or path.endswith("/"):
        raise ValueError("Invalid target path")
    if PurePosixPath(path).suffix != ".py":
        raise ValueError("Only Python source files can be applied")
    proposed = data.get("proposed_source")
    digest = data.get("original_sha256")
    reason = data.get("explanation")
    if not isinstance(proposed, str) or len(proposed.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise ValueError("Invalid proposed source")
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("Invalid baseline fingerprint")
    if not isinstance(reason, str):
        raise ValueError("Missing patch explanation")
    explorer = RepositoryExplorer(repo)
    # Deny symlinks in every component even on platforms that resolve links.
    candidate = explorer.root
    for part in parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise ValueError("Symlink targets are not allowed")
    source = explorer._safe_file(path)
    if source.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("Target exceeds max source size")
    original = source.read_text(encoding="utf-8")
    if fingerprint(original) != digest:
        raise ValueError("Source changed since proposal was created: regenerate proposal")
    if proposed == original:
        raise ValueError("Proposal does not modify the source")
    ast.parse(proposed, filename=path)
    return SavedPatch(path, reason[:500], digest, proposed), source, original


def diff_for(original: str, proposal: SavedPatch) -> str:
    return "".join(difflib.unified_diff(
        original.splitlines(keepends=True), proposal.proposed_source.splitlines(keepends=True),
        fromfile="a/" + proposal.path, tofile="b/" + proposal.path, n=3,
    ))


def stage_repository(repo: Path, stage: Path, proposal: SavedPatch) -> int:
    """Copy only bounded, inspectable text inputs into a disposable test directory."""
    explorer = RepositoryExplorer(repo)
    stage.mkdir(parents=True, exist_ok=False)
    count = total = 0
    for source in explorer._files():
        relative = source.relative_to(explorer.root)
        # Only files needed for Python tests; no .env, git, venv, executables.
        if source.suffix.lower() not in KEEP_EXTENSIONS:
            continue
        if any(part.startswith(".") for part in relative.parts):
            continue
        # Reject symlinked directory components as well as symlinked files.
        current = explorer.root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("Symlink encountered during staging")
        size = source.stat().st_size
        count += 1
        total += size
        if count > MAX_COPY_FILES or total > MAX_COPY_BYTES:
            raise ValueError("Repository exceeds bounded staging limits")
        dst = stage / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dst)
    target = stage / PurePosixPath(proposal.path)
    if not target.is_file():
        raise ValueError("Target missing from staged repository")
    target.write_text(proposal.proposed_source, encoding="utf-8", newline="")
    return count


def docker_test(stage: Path, *, timeout: int = 180, image: str = IMAGE):
    """Execute pytest only inside a constrained local Docker container."""
    if shutil.which("docker") is None:
        raise RuntimeError("Docker executable not found; install/start Docker Desktop")
    cmd = [
        "docker", "run", "--rm", "--network", "none",
        "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--pids-limit", "128", "--memory", "1g", "--memory-swap", "1g", "--cpus", "1",
        "--user", "65534:65534", "--tmpfs", "/tmp:rw,nosuid,nodev,size=128m,mode=1777",
        "--env", "TMPDIR=/tmp", "--env", "PYTHONDONTWRITEBYTECODE=1",
        "--env", "PYTHONPATH=/work", "--mount", f"type=bind,source={stage.resolve()},target=/work,readonly",
        "--workdir", "/work", image,
        "-q", "tests", "-p", "no:cacheprovider", "--basetemp=/tmp/pytest_temp",
    ]
    try:
        return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Docker test execution exceeded {timeout}s") from exc


def apply_tested_patch(repo: Path, proposal: SavedPatch, original: str, *, tests_passed: bool) -> Path:
    """Atomically replace source only after test success and fingerprint check."""
    if not tests_passed:
        raise ValueError("Refusing to apply an untested or failing patch")
    # Resolve and recheck all safety guards immediately before modification.
    manifest = RepositoryExplorer(repo)
    rel = PurePosixPath(proposal.path)
    file = manifest.root
    for part in rel.parts:
        file = file / part
        if file.is_symlink():
            raise ValueError("Symlink was inserted into target path")
    file = manifest._safe_file(proposal.path)
    current = file.read_text(encoding="utf-8")
    if fingerprint(current) != proposal.original_hash or current != original:
        raise ValueError("Source changed since verification; refusing to overwrite")
    # Keep a local backup under the excluded .venv directory (never stage/commit it).
    backup_root = manifest.root / ".venv" / "devpilot_backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    backup = backup_root / (proposal.path.replace("/", "__") + ".bak")
    if backup.is_symlink() or backup.exists():
        raise FileExistsError("A backup already exists; move it before applying another patch")
    backup.write_bytes(file.read_bytes())
    fd, temp_name = tempfile.mkstemp(prefix=".devpilot-", suffix=".tmp", dir=file.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(proposal.proposed_source)
            stream.flush()
            os.fsync(stream.fileno())
        shutil.copymode(file, temp_name)
        os.replace(temp_name, file)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return backup
