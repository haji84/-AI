#!/usr/bin/env python3
"""Build and inspect a deterministic, committed-source release candidate.

Examples (run from a Git checkout):
  python scripts/build_release_bundle.py build --repo . --ref <commit-or-ref> \
      --release-id fire-ai-rc.1 --output /tmp/fire-ai-rc.1.tar.gz
  python scripts/build_release_bundle.py verify /tmp/fire-ai-rc.1.tar.gz \
      --expected-commit <full-commit-sha>

Only allowlisted, UTF-8 committed source is included. Unsafe tracked files fail
closed; dirty/untracked files are never read. This is not a general secret
scanner: review the selected commit before distribution. A verified checksum is
integrity evidence, not authenticity, a signature, or production acceptance.
No install, deployment, network, runtime data, or extraction is performed.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import zlib


MANIFEST_NAME = "RELEASE_MANIFEST.json"
ROOT_FILES = frozenset({".gitignore", "AGENTS.md", "README.md", "PROJECT_STATE.md",
                        "INTEGRATION_HANDOFF.md"})
SOURCE_DIRS = frozenset({".github", "backend", "benchmarks", "config", "db",
                         "deploy", "docs", "frontend", "scripts"})
TEXT_SUFFIXES = frozenset({".py", ".md", ".sql", ".toml", ".json", ".yml", ".yaml",
                           ".js", ".html", ".css", ".txt", ".csv", ".sh", ".cmd",
                           ".service", ".timer", ".conf", ".ini", ".xml", ".svg"})
FORBIDDEN_PARTS = frozenset({".git", ".ssh", ".aws", ".venv", "venv", "__pycache__",
                            "node_modules", "runtime", "storage", "backup", "backups",
                            "data", "uploads", "original", "originals", "secrets",
                            "credentials", "private", "logs", "dist", "build"})
REQUIRED_FILES = frozenset({
    "AGENTS.md", "README.md", "PROJECT_STATE.md", "backend/.env.example",
    "backend/pyproject.toml", "backend/app/main.py", "backend/app/db.py",
    "backend/app/migrations.py", "db/schema_phase0_draft.sql", "frontend/index.html",
    "scripts/migrate_database.py", "docs/SPECIFICATION.md",
    "docs/phase1/LAN_DEPLOYMENT.md", "docs/architecture/TENANT_OPERATIONS.md",
    "deploy/systemd/fire-ai.service", "deploy/nginx/fire-ai.conf",
    "deploy/windows/start-fire-ai.cmd",
})
MAX_FILES = 10000
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
HASH_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
RELEASE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}\Z")


class BundleError(ValueError):
    """A repository or archive violates the bounded source release contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BundleError(message)


def validate_path(name: str) -> None:
    require(isinstance(name, str) and bool(name), "empty or invalid source path")
    parts = name.split("/")
    require(not name.startswith("/") and "\\" not in name
            and all(part not in {"", ".", ".."} for part in parts)
            and all(ord(char) >= 32 and ord(char) != 127 for char in name),
            f"unsafe source path: {name!r}")
    require(name == MANIFEST_NAME or name in ROOT_FILES or
            (len(parts) > 1 and parts[0] in SOURCE_DIRS),
            f"path outside source allowlist: {name}")
    lower_parts = [part.lower() for part in parts]
    require(not any(part in FORBIDDEN_PARTS for part in lower_parts),
            f"unsafe operational/credential path: {name}")
    basename = lower_parts[-1]
    require(not any(part.startswith(".env") and part != ".env.example" for part in lower_parts),
            f"unsafe environment path: {name}")
    require(not any(PurePosixPath(part).stem in {"credentials", "credential", "secret", "secrets",
                                               "backup", "private", "id_rsa", "id_ed25519"}
                    for part in lower_parts), f"unsafe operational/credential path: {name}")
    require(name == MANIFEST_NAME or name in ROOT_FILES or basename == ".env.example"
            or PurePosixPath(name).suffix.lower() in TEXT_SUFFIXES,
            f"non-source or binary extension: {name}")


def validate_text(name: str, data: bytes) -> None:
    require(len(data) <= MAX_FILE_BYTES, f"source file exceeds size limit: {name}")
    try:
        decoded = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise BundleError(f"non-UTF-8/binary source file: {name}") from error
    require(not any(ord(char) < 32 and char not in "\t\n\r" for char in decoded),
            f"binary/control bytes in source file: {name}")


def validate_required(names: set[str]) -> None:
    missing = sorted(REQUIRED_FILES - names)
    require(not missing, "missing required release source assets: " + ", ".join(missing))
    require(any(name.startswith("db/migrations/") and name.endswith(".sql") for name in names),
            "missing required db/migrations/*.sql source assets")


def git(repo: Path, *args: str) -> bytes:
    # No shell, working-tree filters, remote operation, or implicit checkout.
    env = {**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0",
           "GIT_OPTIONAL_LOCKS": "0"}
    result = subprocess.run(["git", "--no-replace-objects", "-c", "protocol.allow=never",
                             "-C", str(repo), *args], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise BundleError(f"Git source read failed: {detail}")
    return result.stdout


def collect_source(repo: Path, ref: str) -> tuple[str, str, dict[str, bytes], dict[str, str]]:
    commit = git(repo, "rev-parse", "--verify", "--end-of-options", ref + "^{commit}").decode().strip()
    require(bool(HASH_RE.fullmatch(commit)), "Git returned an invalid full commit ID")
    tree = git(repo, "rev-parse", "--verify", commit + "^{tree}").decode().strip()
    records = git(repo, "ls-tree", "-rz", "--full-tree", commit).split(b"\0")
    require(len(records) - 1 <= MAX_FILES, "committed source exceeds file-count limit")
    files: dict[str, bytes] = {}
    modes: dict[str, str] = {}
    total = 0
    for record in records:
        if not record:
            continue
        metadata, raw_name = record.split(b"\t", 1)
        try:
            name = raw_name.decode("utf-8")
        except UnicodeDecodeError as error:
            raise BundleError("Git contains a non-UTF-8 source path") from error
        mode, kind, oid = metadata.decode("ascii").split()
        validate_path(name)
        require(name != MANIFEST_NAME, f"reserved generated file already tracked: {name}")
        require(kind == "blob" and mode in {"100644", "100755"},
                f"unsafe tracked mode/type (symlink/submodule prohibited): {name} ({mode})")
        size = int(git(repo, "cat-file", "-s", oid))
        total += size
        require(size <= MAX_FILE_BYTES and total <= MAX_ARCHIVE_BYTES // 2,
                f"committed source exceeds size limit: {name}")
        data = git(repo, "cat-file", "blob", oid)
        validate_text(name, data)
        require(name not in files, f"duplicate Git source path: {name}")
        files[name], modes[name] = data, mode
    validate_required(set(files))
    return commit, tree, files, modes


def source_tree_hash(files: dict[str, bytes], modes: dict[str, str], algorithm: str) -> str:
    """Reconstruct Git blob/tree IDs without trusting the manifest's checksums."""
    def object_hash(kind: str, data: bytes) -> bytes:
        header = f"{kind} {len(data)}\0".encode("ascii")
        return hashlib.new(algorithm, header + data).digest()

    root: dict = {}
    for path, data in files.items():
        parts = path.split("/")
        node = root
        for part in parts[:-1]:
            child = node.setdefault(part, {})
            require(isinstance(child, dict), f"conflicting file/directory source path: {path}")
            node = child
        require(parts[-1] not in node, f"conflicting file/directory source path: {path}")
        node[parts[-1]] = (modes[path], object_hash("blob", data))

    def tree_hash(node: dict) -> bytes:
        contents = bytearray()
        # Git compares directory names as if they ended in '/', not as plain
        # strings; this matters for a.py, a/z.py, and a0.py siblings.
        ordered = sorted(node, key=lambda name: (name + ("/" if isinstance(node[name], dict) else "")).encode("utf-8"))
        for name in ordered:
            value = node[name]
            mode, digest = ("40000", tree_hash(value)) if isinstance(value, dict) else value
            contents.extend(mode.encode("ascii") + b" " + name.encode("utf-8") + b"\0" + digest)
        return object_hash("tree", bytes(contents))

    return tree_hash(root).hex()


def encode_manifest(manifest: dict) -> bytes:
    return (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def encode_tar(files: dict[str, bytes], modes: dict[str, str]) -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name in sorted(files):
            info = tarfile.TarInfo(name)
            info.size = len(files[name])
            info.mode = int(modes[name], 8) & 0o777
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            archive.addfile(info, io.BytesIO(files[name]))
    return stream.getvalue()


def encode_gzip(raw: bytes) -> bytes:
    stream = io.BytesIO()
    with gzip.GzipFile(fileobj=stream, mode="wb", filename="", mtime=0, compresslevel=9) as archive:
        archive.write(raw)
    return stream.getvalue()


def build_bundle(repo: Path, ref: str, release_id: str, output: Path) -> dict:
    require(bool(RELEASE_ID_RE.fullmatch(release_id)), "invalid release ID; use 1-80 safe filename characters")
    require(not output.exists() and not output.is_symlink(), f"output already exists: {output}")
    commit, tree, files, modes = collect_source(repo, ref)
    manifest = {
        "schema_version": 1, "release_id": release_id, "commit": commit, "tree": tree,
        "status": "release-candidate", "production_ready": False,
        "files": {name: {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data),
                         "mode": modes[name]} for name, data in sorted(files.items())},
    }
    files[MANIFEST_NAME] = encode_manifest(manifest)
    modes[MANIFEST_NAME] = "100644"
    bundle = encode_gzip(encode_tar(files, modes))
    # Exclusive creation handles races and refuses existing files or symlinks.
    with output.open("xb") as target:
        target.write(bundle)
    return {"release_id": release_id, "commit": commit, "tree": tree,
            "source_files": len(manifest["files"]), "sha256": hashlib.sha256(bundle).hexdigest(),
            "output": str(output)}


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate manifest JSON key: {key}")
        result[key] = value
    return result


def validate_manifest(data: bytes) -> dict:
    manifest = json.loads(data.decode("utf-8"), object_pairs_hook=unique_object)
    require(isinstance(manifest, dict), "manifest must be a JSON object")
    require(set(manifest) == {"schema_version", "release_id", "commit", "tree", "status",
                              "production_ready", "files"}, "invalid manifest fields")
    require(type(manifest["schema_version"]) is int and manifest["schema_version"] == 1,
            "unsupported manifest schema version")
    require(manifest["status"] == "release-candidate" and manifest["production_ready"] is False,
            "manifest must identify a non-production-ready release candidate")
    require(isinstance(manifest["release_id"], str)
            and bool(RELEASE_ID_RE.fullmatch(manifest["release_id"])), "invalid manifest release ID")
    for field in ("commit", "tree"):
        require(isinstance(manifest[field], str) and bool(HASH_RE.fullmatch(manifest[field])),
                f"invalid manifest {field} ID")
    require(len(manifest["commit"]) == len(manifest["tree"]), "inconsistent Git object ID formats")
    entries = manifest["files"]
    require(isinstance(entries, dict) and len(entries) <= MAX_FILES, "invalid manifest file list")
    for name, entry in entries.items():
        validate_path(name)
        require(name != MANIFEST_NAME, "manifest cannot list itself as source")
        require(isinstance(entry, dict) and set(entry) == {"sha256", "size", "mode"},
                f"invalid manifest file metadata: {name}")
        require(type(entry["size"]) is int and 0 <= entry["size"] <= MAX_FILE_BYTES,
                f"invalid manifest size: {name}")
        require(isinstance(entry["mode"], str) and entry["mode"] in {"100644", "100755"},
                f"invalid manifest mode: {name}")
        require(isinstance(entry["sha256"], str) and bool(SHA256_RE.fullmatch(entry["sha256"])),
                f"invalid manifest sha256: {name}")
    validate_required(set(entries))
    require(data == encode_manifest(manifest), "manifest is not canonical JSON")
    return manifest


def verify_bundle(path: Path, expected_commit: str | None = None) -> dict:
    require(path.stat().st_size <= MAX_ARCHIVE_BYTES, "compressed bundle exceeds size limit")
    with path.open("rb") as source:
        compressed = source.read(MAX_ARCHIVE_BYTES + 1)
    require(len(compressed) <= MAX_ARCHIVE_BYTES, "compressed bundle exceeds size limit")
    # Read through gzip CRC/trailer validation without extracting to the filesystem.
    with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb") as archive:
        raw = archive.read(MAX_ARCHIVE_BYTES + 1)
    require(len(raw) <= MAX_ARCHIVE_BYTES, "expanded bundle exceeds size limit")
    files: dict[str, bytes] = {}
    modes: dict[str, str] = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        for info in archive:
            validate_path(info.name)
            require(info.name not in files, f"duplicate archive member: {info.name}")
            require(info.type == tarfile.REGTYPE and not info.linkname and not info.pax_headers,
                    f"non-regular archive member: {info.name}")
            require(info.mode in {0o644, 0o755} and info.uid == info.gid == 0
                    and info.mtime == 0 and not info.uname and not info.gname,
                    f"noncanonical archive metadata: {info.name}")
            require(0 <= info.size <= MAX_FILE_BYTES, f"archive member exceeds size limit: {info.name}")
            require(len(files) < MAX_FILES + 1, "archive exceeds file-count limit")
            member = archive.extractfile(info)
            require(member is not None, f"unreadable archive member: {info.name}")
            data = member.read(MAX_FILE_BYTES + 1)
            require(len(data) == info.size, f"truncated archive member: {info.name}")
            validate_text(info.name, data)
            files[info.name] = data
            modes[info.name] = "100755" if info.mode == 0o755 else "100644"
    require(MANIFEST_NAME in files, "missing RELEASE_MANIFEST.json")
    require(modes[MANIFEST_NAME] == "100644", "invalid manifest archive mode")
    manifest = validate_manifest(files[MANIFEST_NAME])
    if expected_commit is not None:
        require(bool(HASH_RE.fullmatch(expected_commit)), "expected commit must be a full lowercase Git ID")
        require(manifest["commit"] == expected_commit, "manifest commit does not match expected commit")
    require(set(files) == set(manifest["files"]) | {MANIFEST_NAME},
            "archive file list differs from manifest (extra or missing members)")
    for name, entry in manifest["files"].items():
        require(len(files[name]) == entry["size"] and modes[name] == entry["mode"]
                and hashlib.sha256(files[name]).hexdigest() == entry["sha256"],
                f"source digest/size/mode mismatch: {name}")
    source_files = {name: files[name] for name in manifest["files"]}
    algorithm = "sha1" if len(manifest["tree"]) == 40 else "sha256"
    require(source_tree_hash(source_files, modes, algorithm) == manifest["tree"],
            "reconstructed Git tree does not match manifest tree")
    # Canonical comparison rejects hidden tar headers, unsorted members, alternate
    # metadata, concatenated/trailing payloads and noncanonical gzip wrappers.
    require(raw == encode_tar(files, modes), "noncanonical tar structure or trailing payload")
    require(compressed == encode_gzip(raw), "noncanonical gzip structure or trailing payload")
    return {"release_id": manifest["release_id"], "commit": manifest["commit"],
            "tree": manifest["tree"], "source_files": len(manifest["files"]),
            "sha256": hashlib.sha256(compressed).hexdigest(),
            "status": "release-candidate", "production_ready": False,
            "verification": "integrity only, not authenticity or production acceptance"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="package exact committed source from local Git objects")
    build.add_argument("--repo", type=Path, default=Path("."))
    build.add_argument("--ref", required=True, help="commit or ref resolved once to a full commit ID")
    build.add_argument("--release-id", required=True)
    build.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify", help="check integrity and safe structure without extracting")
    verify.add_argument("bundle", type=Path)
    verify.add_argument("--expected-commit", help="compare to a full commit ID obtained independently")
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            result = build_bundle(args.repo, args.ref, args.release_id, args.output)
        else:
            result = verify_bundle(args.bundle, args.expected_commit)
    except (BundleError, OSError, ValueError, EOFError, RecursionError, tarfile.TarError, zlib.error) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
