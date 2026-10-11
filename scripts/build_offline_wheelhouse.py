#!/usr/bin/env python3
"""Build and verify a hash-locked, wheel-only offline dependency directory.

The lock is authoritative.  Build downloads one compatible wheel for every
locked runtime distribution without importing or executing downloaded code.
Verify is network-free and rejects any byte not bound to both the lock and the
manifest.  This is integrity and reproducibility evidence, not authenticity or
production approval.
"""
from __future__ import annotations

import argparse
from email.parser import BytesParser
from email.policy import compat32
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import zipfile


MANIFEST_NAME = "WHEELHOUSE_MANIFEST.json"
LOCK_LINE_RE = re.compile(
    r"([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9][A-Za-z0-9.!+_-]*)(.*)\Z"
)
HASH_RE = re.compile(r"--hash=sha256:([0-9a-f]{64})")
TARGET_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}\Z")
MAX_WHEELS = 200
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_WHEEL_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 20_000
MAX_ARCHIVE_EXPANDED = 512 * 1024 * 1024


class WheelhouseError(ValueError):
    """The lock, wheel directory, or manifest violates the offline contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise WheelhouseError(message)


def canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def logical_lock_lines(text: str) -> list[str]:
    result: list[str] = []
    pending = ""
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        pending = f"{pending} {stripped}".strip()
        if pending.endswith("\\"):
            pending = pending[:-1].rstrip()
            continue
        result.append(pending)
        pending = ""
    require(not pending, "invalid lock: unterminated continuation")
    return result


def parse_lock(lock_path: Path) -> dict[str, dict[str, object]]:
    require(lock_path.is_file() and not lock_path.is_symlink(), "invalid lock file")
    try:
        text = lock_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise WheelhouseError("invalid lock encoding") from error
    entries: dict[str, dict[str, object]] = {}
    for line in logical_lock_lines(text):
        match = LOCK_LINE_RE.fullmatch(line)
        require(match is not None, f"invalid lock requirement: {line!r}")
        name, version, suffix = match.groups()
        hashes = HASH_RE.findall(suffix)
        residue = HASH_RE.sub("", suffix).strip()
        require(not residue and hashes, f"invalid lock hashes/options for {name}")
        key = canonical_name(name)
        require(key not in entries, f"duplicate distribution in lock: {key}")
        entries[key] = {"version": version, "hashes": frozenset(hashes)}
    require(entries, "invalid lock: no requirements")
    return entries


def numeric_version(value: str) -> tuple[int, ...]:
    require(bool(re.fullmatch(r"\d+(?:\.\d+)*", value)),
            f"unsupported non-numeric project version: {value}")
    return tuple(int(part) for part in value.split("."))


def compare_versions(left: str, right: str) -> int:
    left_parts = numeric_version(left)
    right_parts = numeric_version(right)
    width = max(len(left_parts), len(right_parts))
    left_parts += (0,) * (width - len(left_parts))
    right_parts += (0,) * (width - len(right_parts))
    return (left_parts > right_parts) - (left_parts < right_parts)


def locked_version_satisfies(version: str, specifier: str) -> bool:
    if not specifier:
        return True
    for clause in specifier.split(","):
        match = re.fullmatch(r"(==|!=|>=|<=|>|<)(\d+(?:\.\d+)*)", clause.strip())
        require(match is not None, f"unsupported project requirement clause: {clause}")
        operator, required = match.groups()
        comparison = compare_versions(version, required)
        accepted = {
            "==": comparison == 0,
            "!=": comparison != 0,
            ">=": comparison >= 0,
            "<=": comparison <= 0,
            ">": comparison > 0,
            "<": comparison < 0,
        }[operator]
        if not accepted:
            return False
    return True


def parse_requirement(requirement: str) -> tuple[str, frozenset[str], str, str | None]:
    require("@" not in requirement, f"unsupported requirement URL: {requirement!r}")
    marker_parts = requirement.split(";", 1)
    requirement_part = marker_parts[0].strip()
    marker = marker_parts[1].strip() if len(marker_parts) == 2 else None
    match = re.fullmatch(
        r"([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[([A-Za-z0-9,._-]+)\])?\s*(.*)",
        requirement_part,
    )
    require(match is not None, f"invalid requirement: {requirement!r}")
    name, extras_text, specifier = match.groups()
    if specifier.startswith("(") and specifier.endswith(")"):
        specifier = specifier[1:-1].strip()
    extras = frozenset(
        canonical_name(item) for item in (extras_text or "").split(",") if item
    )
    return canonical_name(name), extras, specifier.strip(), marker


def validate_project(
    project_path: Path,
    lock: dict[str, dict[str, object]],
    target: dict[str, str],
) -> dict[str, set[str]]:
    require(project_path.is_file() and not project_path.is_symlink(), "invalid project file")
    try:
        project = tomllib.loads(project_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise WheelhouseError("invalid project file") from error
    project_table = project.get("project", {})
    require(isinstance(project_table, dict), "invalid project table")
    requires_python = project_table.get("requires-python")
    if requires_python is not None:
        require(isinstance(requires_python, str), "invalid project requires-python")
        require(locked_version_satisfies(target["python_version"], requires_python),
                "target Python differs from project requires-python")
    dependencies = project_table.get("dependencies")
    require(isinstance(dependencies, list) and dependencies,
            "invalid project dependencies")
    selected_extras: dict[str, set[str]] = {}
    for requirement in dependencies:
        require(isinstance(requirement, str) and ";" not in requirement,
                f"unsupported project requirement: {requirement!r}")
        key, extras, specifier, marker = parse_requirement(requirement)
        require(marker is None, f"unsupported project requirement marker: {requirement!r}")
        require(key in lock, f"project dependency missing from lock: {key}")
        version = lock[key]["version"]
        assert isinstance(version, str)
        require(locked_version_satisfies(version, specifier),
                f"project requirement differs from lock: {requirement} != {version}")
        selected_extras.setdefault(key, set()).update(extras)
    return selected_extras


def safe_archive_name(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and "\\" not in name and all(
        part not in {"", ".", ".."} for part in path.parts
    )


def inspect_wheel(
    path: Path,
) -> tuple[str, str, str | None, frozenset[str], tuple[str, ...], frozenset[str]]:
    require(path.name == path.name.strip() and path.name.endswith(".whl"),
            f"sdist or non-wheel file is forbidden: {path.name}")
    mode = path.lstat().st_mode
    require(stat.S_ISREG(mode) and not path.is_symlink(), f"non-regular wheel: {path.name}")
    require(path.stat().st_size <= MAX_WHEEL_BYTES, f"wheel exceeds size limit: {path.name}")
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            require(0 < len(members) <= MAX_ARCHIVE_MEMBERS,
                    f"invalid wheel member count: {path.name}")
            seen: set[str] = set()
            expanded = 0
            metadata_members: list[zipfile.ZipInfo] = []
            wheel_members: list[zipfile.ZipInfo] = []
            for member in members:
                require(safe_archive_name(member.filename),
                        f"unsafe wheel member: {path.name}:{member.filename}")
                require(member.filename not in seen,
                        f"duplicate wheel member: {path.name}:{member.filename}")
                seen.add(member.filename)
                expanded += member.file_size
                require(expanded <= MAX_ARCHIVE_EXPANDED,
                        f"wheel expanded size limit exceeded: {path.name}")
                unix_mode = (member.external_attr >> 16) & 0o170000
                require(unix_mode in {0, stat.S_IFREG, stat.S_IFDIR},
                        f"special wheel member: {path.name}:{member.filename}")
                if member.filename.endswith(".dist-info/METADATA"):
                    metadata_members.append(member)
                elif member.filename.endswith(".dist-info/WHEEL"):
                    wheel_members.append(member)
            require(len(metadata_members) == 1 and len(wheel_members) == 1,
                    f"wheel must contain one METADATA and WHEEL file: {path.name}")
            message = BytesParser(policy=compat32).parsebytes(archive.read(metadata_members[0]))
            wheel_message = BytesParser(policy=compat32).parsebytes(archive.read(wheel_members[0]))
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        raise WheelhouseError(f"invalid wheel archive: {path.name}") from error
    name = message.get("Name")
    version = message.get("Version")
    require(isinstance(name, str) and isinstance(version, str) and name and version,
            f"wheel metadata missing Name/Version: {path.name}")
    requirements = tuple(message.get_all("Requires-Dist", []))
    require(all(isinstance(item, str) for item in requirements),
            f"invalid wheel requirements: {path.name}")
    wheel_tags = wheel_message.get_all("Tag", [])
    require(wheel_tags and all(isinstance(item, str) for item in wheel_tags),
            f"wheel metadata missing Tag: {path.name}")
    filename_parts = path.name[:-4].rsplit("-", 3)
    require(len(filename_parts) == 4, f"invalid wheel filename: {path.name}")
    filename_tags = expand_tag(filename_parts[1], filename_parts[2], filename_parts[3])
    metadata_tags: set[str] = set()
    for item in wheel_tags:
        tag_parts = item.split("-")
        require(len(tag_parts) == 3, f"invalid wheel Tag: {path.name}")
        metadata_tags.update(expand_tag(*tag_parts))
    require(metadata_tags == filename_tags, f"wheel filename/Tag mismatch: {path.name}")
    requires_python = message.get("Requires-Python")
    require(requires_python is None or isinstance(requires_python, str),
            f"invalid wheel Requires-Python: {path.name}")
    provides_extra_values = message.get_all("Provides-Extra", [])
    require(all(isinstance(item, str) and re.fullmatch(r"[A-Za-z0-9._-]+", item)
                for item in provides_extra_values), f"invalid wheel Provides-Extra: {path.name}")
    provides_extras = frozenset(canonical_name(item) for item in provides_extra_values)
    return (canonical_name(name), version, requires_python, provides_extras,
            requirements, frozenset(metadata_tags))


def expand_tag(python: str, abi: str, platform: str) -> set[str]:
    components = (python, abi, platform)
    require(all(re.fullmatch(r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*", item)
                for item in components), "invalid wheel compatibility tag")
    return {
        f"{python_tag}-{abi_tag}-{platform_tag}"
        for python_tag in python.split(".")
        for abi_tag in abi.split(".")
        for platform_tag in platform.split(".")
    }


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate manifest JSON key: {key}")
        result[key] = value
    return result


def target_dict(args: argparse.Namespace) -> dict[str, str]:
    result = {
        "implementation": args.implementation,
        "python_version": args.python_version,
        "abi": args.abi,
        "platform": args.platform,
    }
    require(all(isinstance(value, str) and TARGET_RE.fullmatch(value) for value in result.values()),
            "invalid target value")
    require(bool(re.fullmatch(r"3\.\d{1,2}", result["python_version"])),
            "invalid target Python version")
    return result


def compatible_platforms(platform: str) -> list[str]:
    """Return the ordered PEP 600 tags runnable by the stated glibc target."""
    match = re.fullmatch(r"manylinux_2_(\d+)_(x86_64|aarch64)", platform)
    if match is None:
        return [platform]
    minor = int(match.group(1))
    require(5 <= minor <= 99, "invalid manylinux target")
    architecture = match.group(2)
    result: list[str] = []
    for compatible_minor in range(minor, 4, -1):
        result.append(f"manylinux_2_{compatible_minor}_{architecture}")
        if architecture == "x86_64" and compatible_minor == 17:
            result.append("manylinux2014_x86_64")
        elif architecture == "x86_64" and compatible_minor == 12:
            result.append("manylinux2010_x86_64")
        elif architecture == "x86_64" and compatible_minor == 5:
            result.append("manylinux1_x86_64")
    return result


def tag_is_compatible(tag: str, target: dict[str, str]) -> bool:
    python_tag, abi_tag, platform_tag = tag.split("-")
    target_major, target_minor = (int(item) for item in target["python_version"].split("."))
    if platform_tag == "any" and abi_tag != "none":
        return False
    platform_ok = platform_tag == "any" or platform_tag in compatible_platforms(target["platform"])
    if not platform_ok:
        return False
    if python_tag == f"py{target_major}" or python_tag == f"py{target_major}{target_minor}":
        return abi_tag == "none"
    expected_python = f"{target['implementation']}{target_major}{target_minor}"
    if python_tag == expected_python:
        return abi_tag in {target["abi"], "abi3", "none"}
    match = re.fullmatch(r"cp(\d)(\d{1,2})", python_tag)
    if match and target["implementation"] == "cp" and abi_tag == "abi3":
        wheel_version = (int(match.group(1)), int(match.group(2)))
        return (3, 2) <= wheel_version <= (target_major, target_minor)
    return False


MARKER_TOKEN_RE = re.compile(
    r"\s*(?:(and|or|not|in)|([A-Za-z_][A-Za-z0-9_]*)|"
    r"(===|==|!=|<=|>=|<|>)|('(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")|([()]))"
)


def marker_environment(target: dict[str, str], extra: str) -> dict[str, str]:
    platform = target["platform"]
    if "linux" in platform:
        sys_platform, platform_system, os_name = "linux", "Linux", "posix"
    elif platform.startswith("win"):
        sys_platform, platform_system, os_name = "win32", "Windows", "nt"
    elif "macosx" in platform:
        sys_platform, platform_system, os_name = "darwin", "Darwin", "posix"
    else:
        raise WheelhouseError(f"unsupported target platform marker environment: {platform}")
    implementation_name = "cpython" if target["implementation"] == "cp" else target["implementation"]
    implementation_display = "CPython" if implementation_name == "cpython" else implementation_name
    return {
        "python_version": target["python_version"],
        "python_full_version": target["python_version"] + ".0",
        "implementation_name": implementation_name,
        "implementation_version": target["python_version"] + ".0",
        "platform_python_implementation": implementation_display,
        "sys_platform": sys_platform,
        "platform_system": platform_system,
        "os_name": os_name,
        "extra": extra,
    }


def tokenize_marker(marker: str) -> list[str]:
    tokens: list[str] = []
    position = 0
    while position < len(marker):
        match = MARKER_TOKEN_RE.match(marker, position)
        require(match is not None, f"unsupported dependency marker: {marker!r}")
        tokens.append(next(group for group in match.groups() if group is not None))
        position = match.end()
    return tokens


def marker_applies(marker: str | None, target: dict[str, str], extras: set[str]) -> bool:
    if marker is None:
        return True

    def evaluate(extra: str) -> bool:
        tokens = tokenize_marker(marker)
        environment = marker_environment(target, extra)
        position = 0

        def expression() -> bool:
            nonlocal position
            result = conjunction()
            while position < len(tokens) and tokens[position] == "or":
                position += 1
                right = conjunction()
                result = result or right
            return result

        def conjunction() -> bool:
            nonlocal position
            result = atom()
            while position < len(tokens) and tokens[position] == "and":
                position += 1
                right = atom()
                result = result and right
            return result

        def atom() -> bool:
            nonlocal position
            if position < len(tokens) and tokens[position] == "(":
                position += 1
                result = expression()
                require(position < len(tokens) and tokens[position] == ")",
                        f"invalid dependency marker: {marker!r}")
                position += 1
                return result
            require(position + 2 < len(tokens), f"invalid dependency marker: {marker!r}")
            left_token = tokens[position]
            position += 1
            operator = tokens[position]
            position += 1
            if operator == "not":
                require(position < len(tokens) and tokens[position] == "in",
                        f"invalid dependency marker: {marker!r}")
                position += 1
                operator = "not in"
            right_token = tokens[position]
            position += 1

            def value(token: str) -> str:
                if token[:1] in {"'", '"'}:
                    return bytes(token[1:-1], "utf-8").decode("unicode_escape")
                require(token in environment, f"unsupported dependency marker variable: {token}")
                return environment[token]

            left, right = value(left_token), value(right_token)
            version_variables = {"python_version", "python_full_version", "implementation_version"}
            if left_token in version_variables or right_token in version_variables:
                comparison = compare_versions(left, right)
            else:
                if left_token == "extra":
                    left, right = canonical_name(left), canonical_name(right)
                elif right_token == "extra":
                    left, right = canonical_name(left), canonical_name(right)
                comparison = (left > right) - (left < right)
            outcomes = {
                "==": comparison == 0,
                "===": comparison == 0,
                "!=": comparison != 0,
                "<": comparison < 0,
                "<=": comparison <= 0,
                ">": comparison > 0,
                ">=": comparison >= 0,
                "in": left in right,
                "not in": left not in right,
            }
            require(operator in outcomes, f"unsupported dependency marker operator: {operator}")
            return outcomes[operator]

        result = expression()
        require(position == len(tokens), f"invalid dependency marker: {marker!r}")
        return result

    return any(evaluate(extra) for extra in ({""} | extras))


def validate_dependency_closure(
    lock: dict[str, dict[str, object]],
    metadata_requirements: dict[str, tuple[str, ...]],
    provided_extras: dict[str, frozenset[str]],
    selected_extras: dict[str, set[str]],
    target: dict[str, str],
) -> None:
    extras_by_distribution = {name: set(extras) for name, extras in selected_extras.items()}
    pending = list(selected_extras)
    processed_extras: dict[str, frozenset[str]] = {}
    reachable: set[str] = set()
    while pending:
        distribution = pending.pop()
        extras = extras_by_distribution.get(distribution, set())
        missing_extras = extras - provided_extras[distribution]
        require(not missing_extras,
                f"selected extras not provided by {distribution}: "
                + ", ".join(sorted(missing_extras)))
        snapshot = frozenset(extras)
        if distribution in reachable and processed_extras.get(distribution) == snapshot:
            continue
        reachable.add(distribution)
        processed_extras[distribution] = snapshot
        for requirement in metadata_requirements[distribution]:
            name, dependency_extras, specifier, marker = parse_requirement(requirement)
            if not marker_applies(marker, target, extras):
                continue
            require(name in lock,
                    f"active dependency missing from lock: {distribution} -> {name}")
            version = lock[name]["version"]
            assert isinstance(version, str)
            require(locked_version_satisfies(version, specifier),
                    f"active dependency differs from lock: {distribution} -> {requirement}")
            existing = extras_by_distribution.setdefault(name, set())
            before = len(existing)
            existing.update(dependency_extras)
            if name not in reachable or len(existing) != before:
                pending.append(name)
    require(reachable == set(lock),
            "unreachable locked distributions: " + ", ".join(sorted(set(lock) - reachable)))


def load_manifest(path: Path) -> dict[str, object]:
    require(path.is_file() and not path.is_symlink(), "missing wheelhouse manifest")
    require(path.stat().st_size <= MAX_MANIFEST_BYTES, "wheelhouse manifest size limit exceeded")
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WheelhouseError("invalid wheelhouse manifest") from error
    require(isinstance(value, dict), "manifest must be an object")
    require(set(value) == {"schema_version", "lock_sha256", "project_sha256", "target", "files"},
            "invalid manifest fields")
    require(type(value["schema_version"]) is int and value["schema_version"] == 1,
            "unsupported manifest schema")
    require(isinstance(value["lock_sha256"], str)
            and bool(re.fullmatch(r"[0-9a-f]{64}", value["lock_sha256"])),
            "invalid manifest lock hash")
    require(isinstance(value["project_sha256"], str)
            and bool(re.fullmatch(r"[0-9a-f]{64}", value["project_sha256"])),
            "invalid manifest project hash")
    require(isinstance(value["target"], dict) and set(value["target"]) == {
        "implementation", "python_version", "abi", "platform"
    } and all(isinstance(item, str) for item in value["target"].values()),
            "invalid manifest target")
    require(isinstance(value["files"], dict) and len(value["files"]) <= MAX_WHEELS,
            "invalid manifest wheel list")
    return value


def inspect_directory(
    project_path: Path,
    lock_path: Path,
    wheelhouse: Path,
    target: dict[str, str],
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    lock = parse_lock(lock_path)
    selected_extras = validate_project(project_path, lock, target)
    require(wheelhouse.is_dir() and not wheelhouse.is_symlink(), "invalid wheelhouse directory")
    manifest = load_manifest(wheelhouse / MANIFEST_NAME)
    require(manifest["lock_sha256"] == sha256_file(lock_path), "lock hash mismatch")
    require(manifest["project_sha256"] == sha256_file(project_path), "project hash mismatch")

    children = list(wheelhouse.iterdir())
    forbidden = sorted(child.name for child in children
                       if child.name != MANIFEST_NAME and not child.name.endswith(".whl"))
    require(not forbidden, "sdist or non-wheel files are forbidden: " + ", ".join(forbidden))
    wheel_paths = sorted((child for child in children if child.name.endswith(".whl")),
                         key=lambda item: item.name)
    require(len(wheel_paths) <= MAX_WHEELS, "too many wheels")
    manifest_files = manifest["files"]
    assert isinstance(manifest_files, dict)
    actual_names = {path.name for path in wheel_paths}
    declared_names = set(manifest_files)
    require(not actual_names - declared_names,
            "extra wheel files: " + ", ".join(sorted(actual_names - declared_names)))
    require(not declared_names - actual_names,
            "missing wheel files: " + ", ".join(sorted(declared_names - actual_names)))

    total = 0
    found: dict[str, dict[str, object]] = {}
    metadata_requirements: dict[str, tuple[str, ...]] = {}
    provided_extras: dict[str, frozenset[str]] = {}
    for path in wheel_paths:
        entry = manifest_files[path.name]
        require(isinstance(entry, dict) and set(entry) == {
            "distribution", "version", "sha256", "size"
        }, f"invalid manifest wheel entry: {path.name}")
        require(isinstance(entry["distribution"], str) and isinstance(entry["version"], str)
                and isinstance(entry["sha256"], str)
                and bool(re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]))
                and type(entry["size"]) is int and 0 <= entry["size"] <= MAX_WHEEL_BYTES,
                f"invalid manifest wheel values: {path.name}")
        size = path.stat().st_size
        total += size
        require(total <= MAX_TOTAL_BYTES, "wheelhouse exceeds total size limit")
        digest = sha256_file(path)
        require(entry["sha256"] == digest, f"wheel hash mismatch: {path.name}")
        require(entry["size"] == size, f"wheel size mismatch: {path.name}")
        distribution, version, requires_python, extras, requirements, tags = inspect_wheel(path)
        require(distribution == canonical_name(entry["distribution"])
                and version == entry["version"], f"wheel metadata mismatch: {path.name}")
        require(any(tag_is_compatible(tag, target) for tag in tags),
                f"wheel is not compatible with declared target: {path.name}")
        if requires_python is not None:
            require(locked_version_satisfies(target["python_version"], requires_python),
                    f"target differs from wheel Requires-Python: {path.name}")
        require(distribution not in found, f"duplicate distribution wheel: {distribution}")
        require(distribution in lock, f"distribution not present in lock: {distribution}")
        locked = lock[distribution]
        require(version == locked["version"], f"wheel version differs from lock: {distribution}")
        require(digest in locked["hashes"], f"wheel digest is not an allowed lock hash: {distribution}")
        found[distribution] = dict(entry)
        metadata_requirements[distribution] = requirements
        provided_extras[distribution] = extras
    require(set(found) == set(lock),
            "missing locked distributions: " + ", ".join(sorted(set(lock) - set(found))))
    validate_dependency_closure(
        lock, metadata_requirements, provided_extras, selected_extras, target
    )
    return manifest, found


def write_manifest(project_path: Path, lock_path: Path, wheelhouse: Path, target: dict[str, str]) -> None:
    files: dict[str, dict[str, object]] = {}
    distributions: set[str] = set()
    for path in sorted(wheelhouse.glob("*.whl"), key=lambda item: item.name):
        distribution, version, requires_python, _, _, tags = inspect_wheel(path)
        require(any(tag_is_compatible(tag, target) for tag in tags),
                f"wheel is not compatible with declared target: {path.name}")
        if requires_python is not None:
            require(locked_version_satisfies(target["python_version"], requires_python),
                    f"target differs from wheel Requires-Python: {path.name}")
        require(distribution not in distributions, f"duplicate distribution wheel: {distribution}")
        distributions.add(distribution)
        files[path.name] = {
            "distribution": distribution,
            "version": version,
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
        }
    manifest = {
        "schema_version": 1,
        "lock_sha256": sha256_file(lock_path),
        "project_sha256": sha256_file(project_path),
        "target": target,
        "files": files,
    }
    (wheelhouse / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def build(args: argparse.Namespace) -> dict[str, object]:
    project_path = Path(args.project).resolve()
    lock_path = Path(args.lock).resolve()
    output = Path(args.wheelhouse).resolve()
    lock = parse_lock(lock_path)
    target = target_dict(args)
    validate_project(project_path, lock, target)
    require(not output.exists() and not output.is_symlink(),
            f"wheelhouse output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=output.parent))
    try:
        python_digits = target["python_version"].replace(".", "")
        command = [
            sys.executable, "-m", "pip", "download",
            "--disable-pip-version-check", "--no-input",
            "--require-hashes", "--only-binary=:all:",
            "--dest", str(temporary),
            "--implementation", target["implementation"],
            "--python-version", python_digits,
            "--abi", target["abi"],
        ]
        for platform in compatible_platforms(target["platform"]):
            command.extend(("--platform", platform))
        command.extend(("--requirement", str(lock_path)))
        result = subprocess.run(command, capture_output=True, text=True, timeout=600)
        require(result.returncode == 0,
                f"hash-locked wheel download failed with exit {result.returncode}")
        write_manifest(project_path, lock_path, temporary, target)
        manifest, files = inspect_directory(project_path, lock_path, temporary, target)
        require(manifest["target"] == target, "built wheelhouse target mismatch")
        os.replace(temporary, output)
        return {"wheelhouse": str(output), "wheels": len(files), "target": target}
    except (subprocess.TimeoutExpired, OSError) as error:
        raise WheelhouseError("hash-locked wheel download failed") from error
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def verify(args: argparse.Namespace) -> dict[str, object]:
    target = target_dict(args)
    manifest, files = inspect_directory(
        Path(args.project).resolve(), Path(args.lock).resolve(), Path(args.wheelhouse).resolve(),
        target,
    )
    require(manifest["target"] == target, "wheelhouse target mismatch")
    return {"wheelhouse": str(Path(args.wheelhouse).resolve()), "wheels": len(files), "target": target}


def add_target_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--implementation", required=True)
    parser.add_argument("--python-version", required=True)
    parser.add_argument("--abi", required=True)
    parser.add_argument("--platform", required=True)


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("build", "verify"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--project", required=True)
        subparser.add_argument("--lock", required=True)
        subparser.add_argument("--wheelhouse", required=True)
        add_target_arguments(subparser)
    return parser


def main() -> int:
    args = make_parser().parse_args()
    try:
        result = build(args) if args.command == "build" else verify(args)
    except (WheelhouseError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    print(f"Offline integrity verified for {result['wheels']} wheels; "
          "this is not authenticity or production acceptance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
