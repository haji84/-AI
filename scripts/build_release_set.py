#!/usr/bin/env python3
"""Build and consume one hash-bound source plus offline-wheel release set.

The initial build command combines already verified source and wheelhouse
artifacts.  It is integrity evidence for one explicit target, not a signature,
production deployment, or completion acceptance.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import secrets
import stat
import subprocess
import sys
import tarfile
import tempfile
from types import ModuleType
import re

try:
    import fcntl
except ImportError:  # pragma: no cover - install/rollback target is Linux.
    fcntl = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_NAME = "RELEASE_SET_MANIFEST.json"
SOURCE_PATH = "source/source.tar.gz"
WHEELHOUSE_PATH = "wheelhouse"
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
GIT_ID_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
GENERATION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}\Z")
STATE_NAME = "state.json"
MARKER_NAME = "VERIFIED_GENERATION.json"
INPUT_NAME = "release-set"
LOCK_NAME = ".release-set-operation.lock"
REQUIRED_TARGET = {
    "implementation": "cp",
    "python_version": "3.11",
    "abi": "cp311",
    "platform": "manylinux_2_34_x86_64",
}
MIN_GLIBC = (2, 34)


class ReleaseSetError(ValueError):
    """A release set violates the bounded integrity contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseSetError(message)


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"cannot load verifier: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SOURCE_VERIFIER = load_module("fire_ai_release_bundle", ROOT / "scripts" / "build_release_bundle.py")
WHEEL_VERIFIER = load_module(
    "fire_ai_offline_wheelhouse", ROOT / "scripts" / "build_offline_wheelhouse.py"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: dict[str, object]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate manifest JSON key: {key}")
        result[key] = value
    return result


def load_release_set_manifest(path: Path) -> dict[str, object]:
    require(path.is_file() and not path.is_symlink(), "missing release-set manifest")
    require(path.stat().st_size <= MAX_MANIFEST_BYTES, "release-set manifest exceeds size limit")
    try:
        encoded = path.read_bytes()
        value = json.loads(encoded.decode("utf-8"), object_pairs_hook=unique_object)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReleaseSetError("invalid release-set manifest") from error
    require(isinstance(value, dict), "release-set manifest must be an object")
    require(set(value) == {
        "schema_version", "release_id", "commit", "tree", "status",
        "production_ready", "source", "wheelhouse",
    }, "invalid release-set manifest fields")
    require(type(value["schema_version"]) is int and value["schema_version"] == 1,
            "unsupported release-set manifest schema")
    require(value["status"] == "release-candidate" and value["production_ready"] is False,
            "release set must remain a non-production-ready candidate")
    require(isinstance(value["release_id"], str)
            and bool(SOURCE_VERIFIER.RELEASE_ID_RE.fullmatch(value["release_id"])),
            "invalid release-set release ID")
    for field in ("commit", "tree"):
        require(isinstance(value[field], str) and bool(GIT_ID_RE.fullmatch(value[field])),
                f"invalid release-set {field}")
    require(len(value["commit"]) == len(value["tree"]), "inconsistent Git object formats")

    source = value["source"]
    require(isinstance(source, dict) and set(source) == {"path", "sha256", "size"},
            "invalid release-set source entry")
    require(source["path"] == SOURCE_PATH, "invalid release-set source path")
    require(isinstance(source["sha256"], str) and bool(SHA256_RE.fullmatch(source["sha256"])),
            "invalid release-set source digest")
    require(type(source["size"]) is int and 0 <= source["size"] <= SOURCE_VERIFIER.MAX_ARCHIVE_BYTES,
            "invalid release-set source size")

    wheelhouse = value["wheelhouse"]
    require(isinstance(wheelhouse, dict) and set(wheelhouse) == {
        "path", "manifest_sha256", "lock_sha256", "project_sha256", "target",
        "wheel_count", "files",
    }, "invalid release-set wheelhouse entry")
    require(wheelhouse["path"] == WHEELHOUSE_PATH, "invalid release-set wheelhouse path")
    for field in ("manifest_sha256", "lock_sha256", "project_sha256"):
        require(isinstance(wheelhouse[field], str)
                and bool(SHA256_RE.fullmatch(wheelhouse[field])),
                f"invalid release-set wheelhouse {field}")
    require(isinstance(wheelhouse["target"], dict) and set(wheelhouse["target"]) == {
        "implementation", "python_version", "abi", "platform"
    } and all(isinstance(item, str) and 0 < len(item) <= 100
              for item in wheelhouse["target"].values()), "invalid release-set target")
    require(wheelhouse["target"] == REQUIRED_TARGET,
            "release-set target is outside the bounded Linux contract")
    require(type(wheelhouse["wheel_count"]) is int
            and 0 <= wheelhouse["wheel_count"] <= WHEEL_VERIFIER.MAX_WHEELS,
            "invalid release-set wheel count")
    require(isinstance(wheelhouse["files"], dict)
            and len(wheelhouse["files"]) == wheelhouse["wheel_count"],
            "invalid release-set wheel inventory")
    require(encoded == canonical_json(value), "release-set manifest is not canonical JSON")
    return value


def read_source_inputs(bundle: Path, destination: Path) -> tuple[Path, Path]:
    wanted = {
        "backend/pyproject.toml": destination / "pyproject.toml",
        "backend/requirements-release.lock": destination / "requirements-release.lock",
    }
    found: set[str] = set()
    with tarfile.open(bundle, "r:gz") as archive:
        for info in archive:
            if info.name not in wanted:
                continue
            member = archive.extractfile(info)
            require(member is not None, f"unreadable source member: {info.name}")
            wanted[info.name].write_bytes(member.read())
            found.add(info.name)
    require(found == set(wanted), "source bundle lacks project or release lock")
    return wanted["backend/pyproject.toml"], wanted["backend/requirements-release.lock"]


def prepare_managed_root(value: Path) -> tuple[Path, Path]:
    requested = Path(os.path.abspath(value))
    require(not requested.is_symlink(), "managed root must not be a symlink")
    if not requested.exists():
        requested.mkdir(mode=0o700)
    require(requested.is_dir() and not requested.is_symlink(), "invalid managed root")
    require(requested.resolve() == requested, "managed root path must not traverse symlinks")
    require(stat.S_IMODE(requested.stat().st_mode) & 0o077 == 0,
            "managed root must be private (mode 0700)")
    generations = requested / "generations"
    if not generations.exists():
        generations.mkdir(mode=0o700)
    require(generations.is_dir() and not generations.is_symlink(),
            "invalid managed generations directory")
    require(generations.resolve().parent == requested, "generations directory escapes managed root")
    return requested, generations


def pointer_fields(value: object, label: str) -> dict[str, str]:
    require(isinstance(value, dict) and set(value) == {
        "generation", "release_set_manifest_sha256", "commit", "tree",
    }, f"invalid {label} generation pointer")
    require(isinstance(value["generation"], str)
            and bool(GENERATION_RE.fullmatch(value["generation"])),
            f"invalid {label} generation name")
    require(isinstance(value["release_set_manifest_sha256"], str)
            and bool(SHA256_RE.fullmatch(value["release_set_manifest_sha256"])),
            f"invalid {label} manifest digest")
    for field in ("commit", "tree"):
        require(isinstance(value[field], str) and bool(GIT_ID_RE.fullmatch(value[field])),
                f"invalid {label} {field}")
    return value


def load_state(root: Path, *, required: bool) -> dict[str, object] | None:
    path = root / STATE_NAME
    if not path.exists():
        require(not required, "no active generation state")
        return None
    require(path.is_file() and not path.is_symlink(), "invalid generation state file")
    require(path.stat().st_size <= 16 * 1024, "generation state exceeds size limit")
    try:
        encoded = path.read_bytes()
        value = json.loads(encoded.decode("utf-8"), object_pairs_hook=unique_object)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReleaseSetError("invalid generation state") from error
    require(isinstance(value, dict) and set(value) == {"schema_version", "active", "previous"},
            "invalid generation state fields")
    require(type(value["schema_version"]) is int and value["schema_version"] == 1,
            "unsupported generation state schema")
    pointer_fields(value["active"], "active")
    require(value["previous"] is None or isinstance(value["previous"], dict),
            "invalid previous generation pointer")
    if value["previous"] is not None:
        pointer_fields(value["previous"], "previous")
    require(encoded == canonical_json(value), "generation state is not canonical JSON")
    return value


def atomic_write_json(
    path: Path,
    value: dict[str, object],
    *,
    replace_is_commit: bool = False,
) -> bool:
    encoded = canonical_json(value)
    temporary = path.parent / f".{path.name}.tmp-{secrets.token_hex(8)}"
    try:
        with temporary.open("xb") as target:
            os.chmod(temporary, 0o600)
            target.write(encoded)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            if replace_is_commit:
                return False
            raise
        return True
    finally:
        if temporary.exists():
            temporary.unlink()


@contextmanager
def operation_lock(root: Path):
    """Serialize state changes without an unlink/recreate lock-file race."""
    require(fcntl is not None, "release-set install and rollback require a POSIX file lock")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(root / LOCK_NAME, flags, 0o600)
    except OSError as error:
        raise ReleaseSetError("cannot open release-set operation lock") from error
    try:
        require(stat.S_ISREG(os.fstat(descriptor).st_mode),
                "release-set operation lock is not a regular file")
        os.fchmod(descriptor, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ReleaseSetError("another release-set operation is in progress") from error
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def copy_release_set(source: Path, destination: Path) -> None:
    """Copy a candidate into private staging; the caller verifies the copy."""
    require(not destination.exists(), "release-set snapshot destination already exists")
    destination.mkdir(mode=0o700)
    (destination / "source").mkdir(mode=0o700)
    (destination / WHEELHOUSE_PATH).mkdir(mode=0o700)
    shutil.copyfile(source / MANIFEST_NAME, destination / MANIFEST_NAME)
    shutil.copyfile(source / SOURCE_PATH, destination / SOURCE_PATH)
    for child in sorted((source / WHEELHOUSE_PATH).iterdir(), key=lambda item: item.name):
        require(child.is_file() and not child.is_symlink(),
                f"unsafe wheelhouse member during snapshot: {child.name}")
        shutil.copyfile(child, destination / WHEELHOUSE_PATH / child.name)


def extract_verified_source(bundle: Path, destination: Path) -> None:
    require(not destination.exists(), "source extraction destination already exists")
    destination.mkdir(mode=0o700)
    destination_root = destination.resolve()
    with tarfile.open(bundle, "r:gz") as archive:
        for info in archive:
            SOURCE_VERIFIER.validate_path(info.name)
            require(info.type == tarfile.REGTYPE and not info.linkname and not info.pax_headers,
                    f"non-regular source member: {info.name}")
            target = destination.joinpath(*info.name.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            require(target.parent.resolve().is_relative_to(destination_root),
                    f"source member escapes extraction root: {info.name}")
            member = archive.extractfile(info)
            require(member is not None, f"unreadable source member: {info.name}")
            data = member.read(SOURCE_VERIFIER.MAX_FILE_BYTES + 1)
            require(len(data) == info.size, f"truncated source member: {info.name}")
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(target, flags, info.mode & 0o777)
            try:
                with os.fdopen(descriptor, "wb", closefd=False) as output:
                    output.write(data)
                    output.flush()
                    os.fsync(output.fileno())
            finally:
                os.close(descriptor)
            os.chmod(target, info.mode & 0o777)


def verify_extracted_source(source: Path) -> dict[str, object]:
    require(source.is_dir() and not source.is_symlink(), "invalid generation source directory")
    manifest_path = source / SOURCE_VERIFIER.MANIFEST_NAME
    require(manifest_path.is_file() and not manifest_path.is_symlink(),
            "missing generation source manifest")
    manifest = SOURCE_VERIFIER.validate_manifest(manifest_path.read_bytes())
    expected = set(manifest["files"]) | {SOURCE_VERIFIER.MANIFEST_NAME}
    actual: set[str] = set()
    files: dict[str, bytes] = {}
    modes: dict[str, str] = {}
    for path in source.rglob("*"):
        require(not path.is_symlink(), "generation source contains a symlink")
        if path.is_dir():
            continue
        require(path.is_file(), "generation source contains a special file")
        name = path.relative_to(source).as_posix()
        actual.add(name)
        require(name in expected, f"unexpected generation source file: {name}")
        mode = stat.S_IMODE(path.stat().st_mode)
        modes[name] = "100755" if mode == 0o755 else "100644"
        require(mode in {0o644, 0o755}, f"invalid generation source mode: {name}")
        data = path.read_bytes()
        require(len(data) <= SOURCE_VERIFIER.MAX_FILE_BYTES,
                f"generation source file exceeds limit: {name}")
        files[name] = data
    require(actual == expected, "generation source file list mismatch")
    for name, entry in manifest["files"].items():
        require(len(files[name]) == entry["size"] and modes[name] == entry["mode"]
                and hashlib.sha256(files[name]).hexdigest() == entry["sha256"],
                f"generation source mismatch: {name}")
    source_files = {name: files[name] for name in manifest["files"]}
    algorithm = "sha1" if len(manifest["tree"]) == 40 else "sha256"
    require(SOURCE_VERIFIER.source_tree_hash(source_files, modes, algorithm) == manifest["tree"],
            "generation source tree mismatch")
    return manifest


def clean_subprocess_environment() -> dict[str, str]:
    allowed = ("PATH", "SYSTEMROOT", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL")
    return {key: os.environ[key] for key in allowed if key in os.environ}


def verify_interpreter_target(python: Path, target: dict[str, str]) -> None:
    require(python.exists() and python.is_file(), "installation Python is missing")
    code = (
        "import json,os,platform,sys\n"
        "implementation={'cpython':'cp'}.get(sys.implementation.name,sys.implementation.name)\n"
        "value={'implementation':implementation,"
        "'python_version':f'{sys.version_info.major}.{sys.version_info.minor}',"
        "'abi':f'cp{sys.version_info.major}{sys.version_info.minor}',"
        "'platform':sys.platform,'machine':platform.machine().lower(),"
        "'glibc_version':(os.confstr('CS_GNU_LIBC_VERSION') or '').split()[-1]}\n"
        "print(json.dumps(value,sort_keys=True))\n"
    )
    try:
        result = subprocess.run(
            [str(python), "-I", "-B", "-c", code],
            env=clean_subprocess_environment(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=15, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ReleaseSetError("installation Python target probe failed") from error
    require(result.returncode == 0 and len(result.stdout) <= 4096,
            "installation Python target probe failed")
    try:
        actual = json.loads(result.stdout.decode("utf-8"), object_pairs_hook=unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReleaseSetError("installation Python target probe failed") from error
    require(isinstance(actual, dict) and set(actual) == {
        "implementation", "python_version", "abi", "platform", "machine", "glibc_version"
    }, "installation Python target probe failed")
    for field in ("implementation", "python_version", "abi"):
        require(actual[field] == target[field],
                f"installation Python differs from release-set target: {field}")
    require(actual["platform"] == "linux",
            "installation Python differs from release-set target: platform")
    require(actual["machine"] in {"x86_64", "amd64"},
            "installation Python differs from release-set target: architecture")
    require(isinstance(actual["glibc_version"], str)
            and bool(re.fullmatch(r"[0-9]+\.[0-9]+", actual["glibc_version"])),
            "installation Python glibc probe failed")
    glibc = tuple(int(part) for part in actual["glibc_version"].split("."))
    require(glibc >= MIN_GLIBC,
            "installation Python differs from release-set target: glibc")


def run_checked(command: list[str], *, timeout: int, env: dict[str, str], cwd: Path | None = None,
                label: str) -> None:
    try:
        result = subprocess.run(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ReleaseSetError(f"{label} failed") from error
    require(result.returncode == 0, f"{label} failed with exit {result.returncode}")


def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def smoke_generation(generation: Path) -> None:
    source = generation / "source"
    python = venv_python(generation / "venv")
    require(python.exists() and python.is_file(), "generation virtualenv is missing Python")
    env = clean_subprocess_environment()
    env.update({
        "PIP_NO_INDEX": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(source / "backend"),
        "FIRE_AI_PRODUCTION_MODE": "false",
        "FIRE_AI_COOKIE_SECURE": "false",
        "FIRE_AI_DATABASE_URL": f"sqlite+pysqlite:///{generation / 'smoke.db'}",
        "FIRE_AI_STORAGE_ROOT": str(generation / "smoke-storage"),
    })
    code = (
        "from app.main import app\n"
        "paths={p for r in app.routes if (p:=getattr(r,'path',None))}\n"
        "assert app.title and '/health' in paths\n"
    )
    run_checked([str(python), "-B", "-c", code], timeout=90, env=env, cwd=source,
                label="offline application smoke")


def generation_marker(generation: Path) -> dict[str, object]:
    path = generation / MARKER_NAME
    require(path.is_file() and not path.is_symlink(), "missing verified-generation marker")
    require(path.stat().st_size <= 16 * 1024, "verified-generation marker exceeds size limit")
    try:
        encoded = path.read_bytes()
        value = json.loads(encoded.decode("utf-8"), object_pairs_hook=unique_object)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReleaseSetError("invalid verified-generation marker") from error
    require(isinstance(value, dict) and set(value) == {
        "schema_version", "generation", "release_id", "commit", "tree",
        "release_set_manifest_sha256", "source_manifest_sha256", "installed_target",
    }, "invalid verified-generation marker fields")
    require(type(value["schema_version"]) is int and value["schema_version"] == 1,
            "unsupported verified-generation marker schema")
    require(encoded == canonical_json(value), "verified-generation marker is not canonical JSON")
    pointer_fields({
        "generation": value["generation"],
        "release_set_manifest_sha256": value["release_set_manifest_sha256"],
        "commit": value["commit"],
        "tree": value["tree"],
    }, "marker")
    require(isinstance(value["release_id"], str)
            and bool(SOURCE_VERIFIER.RELEASE_ID_RE.fullmatch(value["release_id"])),
            "invalid marker release ID")
    require(isinstance(value["source_manifest_sha256"], str)
            and bool(SHA256_RE.fullmatch(value["source_manifest_sha256"])),
            "invalid marker source digest")
    require(isinstance(value["installed_target"], dict), "invalid marker target")
    return value


def verify_generation(root: Path, pointer: dict[str, str]) -> dict[str, object]:
    pointer = pointer_fields(pointer, "selected")
    generations = root / "generations"
    generation = generations / pointer["generation"]
    require(generation.is_dir() and not generation.is_symlink(), "selected generation is missing")
    require(generation.resolve().parent == generations.resolve(), "selected generation escapes root")
    marker = generation_marker(generation)
    for field in ("generation", "release_set_manifest_sha256", "commit", "tree"):
        require(marker[field] == pointer[field], f"generation marker mismatch: {field}")
    release_set = generation / INPUT_NAME
    set_verification = verify_release_set(release_set, pointer["commit"])
    require(set_verification["manifest_sha256"] == pointer["release_set_manifest_sha256"],
            "generation release-set manifest mismatch")
    set_manifest = load_release_set_manifest(release_set / MANIFEST_NAME)
    wheelhouse = set_manifest["wheelhouse"]
    assert isinstance(wheelhouse, dict)
    require(marker["installed_target"] == wheelhouse["target"],
            "generation installed target mismatch")
    source_manifest = verify_extracted_source(generation / "source")
    require(marker["release_id"] == source_manifest["release_id"],
            "generation release ID mismatch")
    require(marker["commit"] == source_manifest["commit"], "generation commit mismatch")
    require(marker["tree"] == source_manifest["tree"], "generation tree mismatch")
    require(marker["source_manifest_sha256"]
            == sha256_file(generation / "source" / SOURCE_VERIFIER.MANIFEST_NAME),
            "generation source manifest mismatch")
    smoke_generation(generation)
    return marker


def build_release_set(args: argparse.Namespace) -> dict[str, object]:
    source_bundle = Path(args.source_bundle).resolve()
    wheelhouse = Path(args.wheelhouse).resolve()
    output = Path(args.output).absolute()
    require(source_bundle.is_file() and not source_bundle.is_symlink(), "invalid source bundle")
    require(wheelhouse.is_dir() and not wheelhouse.is_symlink(), "invalid wheelhouse")
    require(not output.exists() and not output.is_symlink(), f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    source_result = SOURCE_VERIFIER.verify_bundle(source_bundle)
    target = {
        "implementation": args.implementation,
        "python_version": args.python_version,
        "abi": args.abi,
        "platform": args.platform,
    }
    require(target == REQUIRED_TARGET,
            "requested target is outside the bounded Linux contract")
    verification_dir = Path(tempfile.mkdtemp(prefix=".release-set-inputs-", dir=output.parent))
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=output.parent))
    try:
        project, lock = read_source_inputs(source_bundle, verification_dir)
        wheel_manifest, wheel_files = WHEEL_VERIFIER.inspect_directory(
            project, lock, wheelhouse, target
        )
        require(wheel_manifest["target"] == target, "wheelhouse target mismatch")

        source_target = stage / SOURCE_PATH
        source_target.parent.mkdir(mode=0o700)
        shutil.copyfile(source_bundle, source_target)
        wheels_target = stage / WHEELHOUSE_PATH
        wheels_target.mkdir(mode=0o700)
        for child in sorted(wheelhouse.iterdir(), key=lambda item: item.name):
            require(child.is_file() and not child.is_symlink(), f"unsafe wheelhouse member: {child.name}")
            shutil.copyfile(child, wheels_target / child.name)

        wheel_manifest_path = wheelhouse / WHEEL_VERIFIER.MANIFEST_NAME
        manifest: dict[str, object] = {
            "schema_version": 1,
            "release_id": source_result["release_id"],
            "commit": source_result["commit"],
            "tree": source_result["tree"],
            "status": "release-candidate",
            "production_ready": False,
            "source": {
                "path": SOURCE_PATH,
                "sha256": sha256_file(source_bundle),
                "size": source_bundle.stat().st_size,
            },
            "wheelhouse": {
                "path": WHEELHOUSE_PATH,
                "manifest_sha256": sha256_file(wheel_manifest_path),
                "lock_sha256": wheel_manifest["lock_sha256"],
                "project_sha256": wheel_manifest["project_sha256"],
                "target": target,
                "wheel_count": len(wheel_files),
                "files": wheel_manifest["files"],
            },
        }
        encoded = canonical_json(manifest)
        require(len(encoded) <= MAX_MANIFEST_BYTES, "release-set manifest exceeds size limit")
        (stage / MANIFEST_NAME).write_bytes(encoded)
        # Re-verify the copied candidate so a source/wheelhouse swap during
        # construction cannot produce a successful-but-invalid output.
        staged = verify_release_set(stage, source_result["commit"])
        require(staged["manifest_sha256"] == hashlib.sha256(encoded).hexdigest(),
                "staged release-set manifest mismatch")
        os.replace(stage, output)
        return {
            "release_set": str(output),
            "release_id": manifest["release_id"],
            "commit": manifest["commit"],
            "tree": manifest["tree"],
            "wheels": len(wheel_files),
            "manifest_sha256": hashlib.sha256(encoded).hexdigest(),
            "production_ready": False,
        }
    finally:
        shutil.rmtree(verification_dir, ignore_errors=True)
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)


def verify_release_set(path: Path, expected_commit: str | None = None) -> dict[str, object]:
    require(path.is_dir() and not path.is_symlink(), "invalid release-set directory")
    release_set = path.resolve()
    require({child.name for child in release_set.iterdir()} == {
        MANIFEST_NAME, "source", WHEELHOUSE_PATH,
    }, "release-set top-level files differ from manifest contract")
    require((release_set / "source").is_dir() and not (release_set / "source").is_symlink(),
            "invalid release-set source directory")
    require({child.name for child in (release_set / "source").iterdir()} == {"source.tar.gz"},
            "invalid release-set source directory contents")
    require((release_set / WHEELHOUSE_PATH).is_dir()
            and not (release_set / WHEELHOUSE_PATH).is_symlink(),
            "invalid release-set wheelhouse directory")

    manifest_path = release_set / MANIFEST_NAME
    manifest = load_release_set_manifest(manifest_path)
    commit = manifest["commit"]
    assert isinstance(commit, str)
    if expected_commit is not None:
        require(bool(GIT_ID_RE.fullmatch(expected_commit)),
                "expected commit must be a full lowercase Git ID")
        require(commit == expected_commit, "release-set commit does not match expected commit")

    source_entry = manifest["source"]
    assert isinstance(source_entry, dict)
    source_bundle = release_set / SOURCE_PATH
    require(source_bundle.is_file() and not source_bundle.is_symlink(), "invalid source bundle")
    require(source_bundle.stat().st_size == source_entry["size"], "source size mismatch")
    require(sha256_file(source_bundle) == source_entry["sha256"], "source digest mismatch")
    source_result = SOURCE_VERIFIER.verify_bundle(source_bundle, commit)
    require(source_result["release_id"] == manifest["release_id"], "source release ID mismatch")
    require(source_result["tree"] == manifest["tree"], "source tree mismatch")

    verification_dir = Path(tempfile.mkdtemp(prefix=".release-set-verify-"))
    try:
        project, lock = read_source_inputs(source_bundle, verification_dir)
        wheelhouse_entry = manifest["wheelhouse"]
        assert isinstance(wheelhouse_entry, dict)
        target = wheelhouse_entry["target"]
        assert isinstance(target, dict)
        wheelhouse = release_set / WHEELHOUSE_PATH
        for child in wheelhouse.iterdir():
            require(child.is_file() and not child.is_symlink(),
                    f"unsafe wheelhouse member: {child.name}")
        wheel_manifest_path = wheelhouse / WHEEL_VERIFIER.MANIFEST_NAME
        require(sha256_file(wheel_manifest_path) == wheelhouse_entry["manifest_sha256"],
                "wheelhouse manifest digest mismatch")
        wheel_manifest, wheel_files = WHEEL_VERIFIER.inspect_directory(
            project, lock, wheelhouse, target
        )
        require(wheel_manifest["target"] == target, "wheelhouse target mismatch")
        require(wheel_manifest["lock_sha256"] == wheelhouse_entry["lock_sha256"],
                "wheelhouse lock digest mismatch")
        require(wheel_manifest["project_sha256"] == wheelhouse_entry["project_sha256"],
                "wheelhouse project digest mismatch")
        require(wheel_manifest["files"] == wheelhouse_entry["files"],
                "wheelhouse inventory mismatch")
        require(len(wheel_files) == wheelhouse_entry["wheel_count"],
                "wheelhouse count mismatch")
        return {
            "release_set": str(release_set),
            "release_id": manifest["release_id"],
            "commit": commit,
            "tree": manifest["tree"],
            "wheels": len(wheel_files),
            "manifest_sha256": sha256_file(manifest_path),
            "production_ready": False,
            "verification": "integrity only, not authenticity or production acceptance",
        }
    finally:
        shutil.rmtree(verification_dir, ignore_errors=True)


def install_release_set(
    release_set_path: Path,
    managed_root_path: Path,
    python_executable: Path,
    expected_commit: str | None,
) -> dict[str, object]:
    initial = verify_release_set(release_set_path, expected_commit)
    release_set = Path(initial["release_set"])
    initial_manifest = load_release_set_manifest(release_set / MANIFEST_NAME)
    initial_wheelhouse = initial_manifest["wheelhouse"]
    assert isinstance(initial_wheelhouse, dict)
    initial_target = initial_wheelhouse["target"]
    assert isinstance(initial_target, dict)
    verify_interpreter_target(python_executable, initial_target)
    root, generations = prepare_managed_root(managed_root_path)
    with operation_lock(root):
        return install_release_set_locked(
            release_set, root, generations, python_executable, expected_commit
        )


def install_release_set_locked(
    release_set: Path,
    root: Path,
    generations: Path,
    python_executable: Path,
    expected_commit: str | None,
) -> dict[str, object]:
    state = load_state(root, required=False)
    if state is not None:
        active = state["active"]
        assert isinstance(active, dict)
        verify_generation(root, active)

    stage = generations / f".staging-{secrets.token_hex(12)}"
    require(not stage.exists(), "generation staging collision")
    stage.mkdir(mode=0o700)
    try:
        private_set = stage / INPUT_NAME
        copy_release_set(release_set, private_set)
        verification = verify_release_set(private_set, expected_commit)
        manifest = load_release_set_manifest(private_set / MANIFEST_NAME)
        wheelhouse = manifest["wheelhouse"]
        assert isinstance(wheelhouse, dict)
        target = wheelhouse["target"]
        assert isinstance(target, dict)
        verify_interpreter_target(python_executable, target)

        release_id = manifest["release_id"]
        assert isinstance(release_id, str)
        manifest_digest = verification["manifest_sha256"]
        assert isinstance(manifest_digest, str)
        generation_name = f"{release_id}-{manifest_digest[:12]}-{secrets.token_hex(8)}"
        require(bool(GENERATION_RE.fullmatch(generation_name)),
                "generated generation name is invalid")
        generation = generations / generation_name
        require(not generation.exists(), "generation collision")

        extract_verified_source(private_set / SOURCE_PATH, stage / "source")
        source_manifest = verify_extracted_source(stage / "source")
        require(source_manifest["commit"] == verification["commit"], "installed source commit mismatch")
        require(source_manifest["tree"] == verification["tree"], "installed source tree mismatch")

        env = clean_subprocess_environment()
        env.update({"PIP_NO_INDEX": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1"})
        run_checked([str(python_executable), "-m", "venv", str(stage / "venv")],
                    timeout=180, env=env, label="virtualenv creation")
        python = venv_python(stage / "venv")
        verify_interpreter_target(python, target)
        run_checked([
            str(python), "-m", "pip", "install", "--no-index",
            "--find-links", str(private_set / WHEELHOUSE_PATH), "--require-hashes",
            "--requirement", str(stage / "source" / "backend" / "requirements-release.lock"),
        ], timeout=600, env=env, label="offline dependency installation")
        smoke_generation(stage)

        marker: dict[str, object] = {
            "schema_version": 1,
            "generation": generation_name,
            "release_id": release_id,
            "commit": verification["commit"],
            "tree": verification["tree"],
            "release_set_manifest_sha256": manifest_digest,
            "source_manifest_sha256": sha256_file(
                stage / "source" / SOURCE_VERIFIER.MANIFEST_NAME
            ),
            "installed_target": wheelhouse["target"],
        }
        atomic_write_json(stage / MARKER_NAME, marker)
        os.replace(stage, generation)
        pointer = {
            "generation": generation_name,
            "release_set_manifest_sha256": manifest_digest,
            "commit": verification["commit"],
            "tree": verification["tree"],
        }
        previous = state["active"] if state is not None else None
        new_state: dict[str, object] = {
            "schema_version": 1,
            "active": pointer,
            "previous": previous,
        }
        try:
            state_durability_confirmed = atomic_write_json(
                root / STATE_NAME, new_state, replace_is_commit=True
            )
        except OSError:
            # The state rename did not commit.  The verified generation is not
            # reachable and can be removed without changing the active pointer.
            shutil.rmtree(generation, ignore_errors=True)
            raise
        return {
            "managed_root": str(root),
            "active_generation": generation_name,
            "previous_generation": previous["generation"] if isinstance(previous, dict) else None,
            "commit": verification["commit"],
            "tree": verification["tree"],
            "state_durability_confirmed": state_durability_confirmed,
            "production_ready": False,
        }
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)


def rollback_generation(managed_root_path: Path) -> dict[str, object]:
    root, _ = prepare_managed_root(managed_root_path)
    with operation_lock(root):
        return rollback_generation_locked(root)


def rollback_generation_locked(root: Path) -> dict[str, object]:
    state = load_state(root, required=True)
    assert state is not None
    active = state["active"]
    previous = state["previous"]
    assert isinstance(active, dict)
    require(isinstance(previous, dict), "no previously verified generation is available")
    verify_generation(root, active)
    marker = verify_generation(root, previous)
    new_state: dict[str, object] = {
        "schema_version": 1,
        "active": previous,
        "previous": active,
    }
    state_durability_confirmed = atomic_write_json(
        root / STATE_NAME, new_state, replace_is_commit=True
    )
    return {
        "managed_root": str(root),
        "active_generation": previous["generation"],
        "previous_generation": active["generation"],
        "commit": marker["commit"],
        "tree": marker["tree"],
        "state_durability_confirmed": state_durability_confirmed,
        "production_ready": False,
    }


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("--source-bundle", required=True)
    build.add_argument("--wheelhouse", required=True)
    build.add_argument("--output", required=True)
    build.add_argument("--implementation", required=True)
    build.add_argument("--python-version", required=True)
    build.add_argument("--abi", required=True)
    build.add_argument("--platform", required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("release_set")
    verify.add_argument("--expected-commit")
    install = commands.add_parser("install")
    install.add_argument("release_set")
    install.add_argument("--managed-root", required=True)
    install.add_argument("--python", required=True)
    install.add_argument("--expected-commit")
    rollback = commands.add_parser("rollback")
    rollback.add_argument("--managed-root", required=True)
    return parser


def main() -> int:
    args = make_parser().parse_args()
    try:
        if args.command == "build":
            result = build_release_set(args)
        elif args.command == "verify":
            result = verify_release_set(Path(args.release_set), args.expected_commit)
        elif args.command == "install":
            result = install_release_set(
                Path(args.release_set), Path(args.managed_root), Path(args.python),
                args.expected_commit,
            )
        else:
            result = rollback_generation(Path(args.managed_root))
    except (ReleaseSetError, OSError, ValueError, EOFError, tarfile.TarError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    print("Release-set integrity is not authenticity or production acceptance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
