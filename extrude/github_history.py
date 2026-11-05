"""Read-only GitHub history stored in bare Git repositories."""

import base64
import hashlib
import os
import re
import subprocess
import threading
from pathlib import Path

from extrude.project_map import KINDS
from extrude.runtime import data_dir

_SOURCE = re.compile(r"(?:https://github\.com/)?([a-z\d][a-z\d-]{0,38})/([a-z\d_.-]{1,100})/?", re.I | re.ASCII)
_SHA = re.compile(r"[0-9a-f]{40}")
_ID = re.compile(r"[0-9a-f]{32}")
_LOCK = threading.Lock()
_HEAD = "refs/atlas/head"
_PREVIOUS = "refs/atlas/previous"
_FETCHED = "refs/atlas/fetched"
_MAX_PREVIEW = 128_000


class GitHubError(RuntimeError):
    """A GitHub operation failed with a message safe to show in Atlas."""


def normalize(source: str) -> str:
    match = _SOURCE.fullmatch(source.strip())
    if not match:
        raise ValueError("Enter a GitHub repository URL or owner/repository.")
    owner, repo = match.groups()
    repo = repo.lower().removesuffix(".git")
    if repo in {"", ".", ".."}:
        raise ValueError("Enter a GitHub repository name.")
    return f"{owner.lower()}/{repo}"


def _root() -> Path:
    return data_dir() / "github"


def _git(repo: Path, *args: str, remote: bool = False, stdin: bytes | None = None) -> bytes:
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0",
               GIT_NO_REPLACE_OBJECTS="1")
    command = ["git", f"--git-dir={repo}", "-c", "core.hooksPath=" + os.devnull]
    if remote:
        command += ["-c", "http.followRedirects=false", "-c", "credential.helper=",
                    "-c", "protocol.allow=never", "-c", "protocol.https.allow=always"]
        token = os.environ.get("EXTRUDE_GITHUB_TOKEN", "").strip()
        if token:
            credential = base64.b64encode(f"x-access-token:{token}".encode()).decode("ascii")
            env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="http.https://github.com/.extraHeader",
                       GIT_CONFIG_VALUE_0=f"Authorization: Basic {credential}")
    try:
        result = subprocess.run([*command, *args], env=env, input=stdin or b"",
                                capture_output=True, timeout=90 if remote else 20, check=False)
    except FileNotFoundError as exc:
        raise GitHubError("Install Git on the computer running Extrude.") from exc
    except (OSError, subprocess.TimeoutExpired):
        # Avoid exception text containing remote output or Git arguments.
        raise GitHubError("Git did not finish. Try again.") from None
    if result.returncode:
        if remote:
            raise GitHubError("GitHub import failed. Check the repository URL and read access, then try again.")
        raise GitHubError("Git could not read the requested repository data.")
    return result.stdout


def _text(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def _ref(repo: Path, name: str) -> str | None:
    result = _text(_git(repo, "for-each-ref", "--format=%(objectname) %(refname)", name))
    for line in result.splitlines():
        sha, ref = line.split(" ", 1)
        if ref == name:
            return sha
    return None


def _repository(repo_id: str) -> Path:
    if not _ID.fullmatch(repo_id):
        raise KeyError(repo_id)
    repo = _root() / repo_id
    if not (repo / "atlas-source").is_file():
        raise KeyError(repo_id)
    return repo


def _describe(repo: Path) -> dict:
    source = (repo / "atlas-source").read_text(encoding="utf-8")
    saved_tips = _text(_git(repo, "for-each-ref", "--format=%(objectname)",
                           "--sort=-creatordate", "refs/atlas/snapshots/")).splitlines()
    return {"id": repo.name, "source": source, "url": f"https://github.com/{source}",
            "head": _ref(repo, _HEAD), "previous_head": _ref(repo, _PREVIOUS), "saved_tips": saved_tips}


def repositories() -> list[dict]:
    with _LOCK:
        if not _root().is_dir():
            return []
        return [_describe(repo) for repo in sorted(_root().iterdir())
                if _ID.fullmatch(repo.name) and (repo / "atlas-source").is_file()]


def _fetch(repo: Path, source: str) -> None:
    if os.environ.get("EXTRUDE_GITHUB_OFFLINE") == "1":
        raise GitHubError("Remote GitHub imports are disabled in this process.")
    _git(repo, "fetch", "--no-tags", "--no-recurse-submodules", "--no-auto-maintenance",
         f"https://github.com/{source}.git", f"+HEAD:{_FETCHED}", remote=True)


def _sync(repo: Path, source: str) -> None:
    before = _ref(repo, _HEAD)
    _fetch(repo, source)
    after = _ref(repo, _FETCHED)
    if not after or not _SHA.fullmatch(after):
        raise GitHubError("GitHub did not return a default branch commit.")
    if before == after:
        return
    # Publish the pair together and keep every imported tip reachable after a force push.
    changes = [f"update {_HEAD} {after} {before or '0' * 40}",
               f"update refs/atlas/snapshots/{after} {after}"]
    if before:
        changes.append(f"update {_PREVIOUS} {before}")
    _git(repo, "update-ref", "--stdin", stdin=("\n".join(changes) + "\n").encode("ascii"))


def connect(source: str) -> dict:
    source = normalize(source)
    repo = _root() / hashlib.sha256(source.encode("ascii")).hexdigest()[:32]
    with _LOCK:
        repo.mkdir(parents=True, exist_ok=True)
        if not (repo / "config").is_file():
            _git(repo, "init", "--bare", "--template=")
        _sync(repo, source)
        marker = repo / "atlas-source"
        if not marker.is_file():
            pending = repo / "atlas-source.tmp"
            pending.write_text(source, encoding="utf-8")
            pending.replace(marker)
        return _describe(repo)


def sync(repo_id: str) -> dict:
    with _LOCK:
        repo = _repository(repo_id)
        _sync(repo, (repo / "atlas-source").read_text(encoding="utf-8"))
        return _describe(repo)


def _commit(repo: Path, sha: str) -> str:
    if not _SHA.fullmatch(sha):
        raise ValueError("Choose a full commit SHA.")
    try:
        if _text(_git(repo, "cat-file", "-t", sha)).strip() == "commit":
            return sha
    except GitHubError:
        pass
    raise KeyError(sha)


def _kind(path: str) -> str:
    return KINDS.get(Path(path).suffix.lower(), "other")


def history(repo_id: str, revision: str | None = None, offset: int = 0, limit: int = 30) -> dict:
    repo = _repository(repo_id)
    head = _commit(repo, revision or _ref(repo, _HEAD) or "")
    raw = _git(repo, "log", "-z", "--format=%H%x00%P%x00%an%x00%aI%x00%s",
               f"--skip={offset}", f"--max-count={limit + 1}", head, "--")
    fields = _text(raw).split("\0")
    rows = [{"sha": sha, "parents": parents.split(), "author": author, "date": date, "subject": subject}
            for sha, parents, author, date, subject in zip(*(iter(fields),) * 5)]
    return {"revision": head, "commits": rows[:limit], "next_offset": offset + limit if len(rows) > limit else None}


def inventory(repo_id: str, revision: str, offset: int = 0, limit: int = 100) -> dict:
    repo = _repository(repo_id)
    sha = _commit(repo, revision)
    entries = []
    for row in _text(_git(repo, "ls-tree", "-rz", sha)).split("\0"):
        if not row:
            continue
        info, path = row.split("\t", 1)
        mode, kind, object_id = info.split()
        entries.append({"path": path, "kind": _kind(path), "object": object_id,
                        "type": "symlink" if mode == "120000" else kind})
    return {"files": entries[offset:offset + limit], "total": len(entries),
            "next_offset": offset + limit if offset + limit < len(entries) else None}


def changes(repo_id: str, revision: str, base: str | None = None, offset: int = 0, limit: int = 100) -> dict:
    repo = _repository(repo_id)
    sha, base = comparison_revisions(repo_id, revision, base)
    flags = ("--name-status", "-z", "-M", "--no-ext-diff", "--no-textconv")
    args = ("diff", *flags, base, sha, "--") if base else ("diff-tree", "--root", "--no-commit-id", "-r", *flags, sha, "--")
    fields = iter(_text(_git(repo, *args)).rstrip("\0").split("\0"))
    rows = []
    for status in fields:
        if not status:
            break
        path = next(fields)
        previous_path = None
        if status[0] in {"R", "C"}:
            previous_path, path = path, next(fields)
        rows.append({"path": path, "previous_path": previous_path, "status": status[0], "kind": _kind(path)})
    return {"revision": sha, "base": base, "files": rows[offset:offset + limit], "total": len(rows),
            "next_offset": offset + limit if offset + limit < len(rows) else None}


def comparison_revisions(repo_id: str, revision: str, base: str | None = None) -> tuple[str, str | None]:
    repo = _repository(repo_id)
    sha = _commit(repo, revision)
    if base is None:
        parents = _text(_git(repo, "show", "-s", "--format=%P", sha)).split()
        base = parents[0] if parents else None
    else:
        _commit(repo, base)
    return sha, base


class BlobUnavailable(ValueError):
    """A path exists but cannot be treated as a regular file for analysis."""


def _validate_path(path: str) -> None:
    if not path or "\0" in path or any(part in {"", ".", ".."} for part in path.split("/")):
        raise ValueError("Choose a repository file.")


def _tree_entry(repo_id: str, revision: str, path: str) -> tuple[Path, tuple[str, str, str] | None]:
    repo = _repository(repo_id)
    sha = _commit(repo, revision)
    _validate_path(path)
    matches = _git(repo, "--literal-pathspecs", "ls-tree", "-z", sha, "--", path)
    if not matches:
        return repo, None
    info, _ = matches.rstrip(b"\0").split(b"\t", 1)
    mode, kind, object_id = info.decode("ascii").split()
    return repo, (mode, kind, object_id)


def file_exists(repo_id: str, revision: str, path: str) -> bool:
    _, entry = _tree_entry(repo_id, revision, path)
    return entry is not None and entry[0] in {"100644", "100755"} and entry[1] == "blob"


def regular_blob(repo_id: str, revision: str, path: str, *, max_bytes: int) -> bytes | None:
    """Read a regular Git blob, returning None only for an absent path."""
    repo, entry = _tree_entry(repo_id, revision, path)
    if entry is None:
        return None
    mode, kind, object_id = entry
    if kind != "blob" or mode not in {"100644", "100755"}:
        raise BlobUnavailable("This path is not a regular file in the selected commit.")
    if int(_git(repo, "cat-file", "-s", object_id)) > max_bytes:
        raise BlobUnavailable(f"This file exceeds the {max_bytes // (1024 * 1024)} MiB analysis limit.")
    return _git(repo, "cat-file", "blob", object_id)


def preview(repo_id: str, revision: str, path: str) -> dict:
    repo = _repository(repo_id)
    sha = _commit(repo, revision)
    _validate_path(path)
    obj = f"{sha}:{path}"
    try:
        kind = _text(_git(repo, "cat-file", "-t", obj)).strip()
    except GitHubError:
        raise KeyError(path) from None
    if kind != "blob":
        raise KeyError(path)
    size = int(_git(repo, "cat-file", "-s", obj))
    if size > _MAX_PREVIEW:
        return {"text": None, "reason": "File exceeds the 128 KB preview limit.", "size": size}
    data = _git(repo, "cat-file", "blob", obj)
    try:
        content = None if b"\0" in data else data.decode("utf-8")
    except UnicodeDecodeError:
        content = None
    return {"text": content, "reason": None if content is not None else "Binary or non-UTF-8 file.", "size": size}
