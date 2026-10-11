#!/usr/bin/env python3
"""Privately collect and secret-scan selected published GitHub surfaces.

The caller selects exact pull-request and workflow-run IDs. Downloaded bytes,
API payloads and scanner reports remain in private temporary directories.
"""
import argparse
import bz2
from contextlib import contextmanager
import gzip
import hashlib
import importlib.util
import json
import lzma
import os
from pathlib import Path, PurePosixPath
import re
import signal
import stat
import struct
import tarfile
import tempfile
import time
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile
import io


MAX_DOWNLOAD_BYTES = 256 * 1024 * 1024
MAX_ARTIFACT_DOWNLOAD_BYTES = 512 * 1024 * 1024
MAX_EXTRACTED_BYTES = 512 * 1024 * 1024
MAX_FILES = 20_000
MAX_ENTRY_BYTES = 64 * 1024 * 1024
MAX_HISTORY_SURFACES = 10_000
MAX_HISTORY_DISCOVERY_SECONDS = 300
DOWNLOAD_TIMEOUT_SECONDS = 60
NESTED_ARCHIVE_SUFFIXES = {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar"}
ZIP_CONTAINER_SUFFIXES = {".zip", ".whl", ".docx", ".xlsx", ".pptx"}
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
REVIEWED_PUBLIC_DEPENDENCY_FINDINGS = frozenset(
    {
        (
            "wheelhouse/cryptography-50.0.2-cp311-abi3-manylinux_2_34_x86_64.whl.expanded/cryptography/hazmat/bindings/_rust/openssl/hpke.pyi",
            "a7f8462e7e981fe11aac91755796d4b14b638a9be2100a5c4793b4b141c92ed7",
            "generic-api-key",
            77,
            77,
            10,
            45,
        ),
        (
            "wheelhouse/cryptography-50.0.2-cp311-abi3-manylinux_2_34_x86_64.whl.expanded/cryptography/hazmat/bindings/_rust/openssl/hpke.pyi",
            "a7f8462e7e981fe11aac91755796d4b14b638a9be2100a5c4793b4b141c92ed7",
            "generic-api-key",
            101,
            101,
            6,
            41,
        ),
        (
            "wheelhouse/sqlalchemy-2.1.4-cp311-cp311-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl.expanded/sqlalchemy/orm/unitofwork.py",
            "7b0c565b1559c3ad8b9dd24bd0afcbdd515a0027bff66eee6f4c3e8f6bf22235",
            "generic-api-key",
            247,
            247,
            23,
            67,
        ),
        (
            "wheelhouse/sqlalchemy-2.1.4-cp311-cp311-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl.expanded/sqlalchemy/orm/mapped_collection.py",
            "2089fde1a3852233fe960ab0a9412484c31e353c2395484aafe7b54007dfbabb",
            "generic-api-key",
            321,
            321,
            10,
            75,
        ),
    }
)
REVIEWED_EMBEDDED_ZIP_WRAPPERS = frozenset(
    {
        (
            "pymupdf/libmupdf.so.28.2",
            "64ea1ff04304a3e90d5ae7fb38de4fb8e4057ff776434e747fe5a62d219b1cfa",
        ),
    }
)


class AuditFailure(Exception):
    """Private details must never be printed by the CLI."""


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise AuditFailure()


@contextmanager
def absolute_deadline(seconds):
    """Bound connection, headers and body by one Linux wall-clock deadline."""
    try:
        previous_timer = signal.getitimer(signal.ITIMER_REAL)
        previous_handler = signal.getsignal(signal.SIGALRM)
        if previous_timer != (0.0, 0.0):
            raise AuditFailure()

        def expired(_signum, _frame):
            raise AuditFailure()

        signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, seconds)
    except AuditFailure:
        raise
    except Exception as error:
        raise AuditFailure() from error
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


class PrivateRedirectHandler(HTTPRedirectHandler):
    """Never forward the GitHub bearer token to a download origin."""

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        redirected = super().redirect_request(
            request, file_pointer, code, message, headers, new_url
        )
        if redirected is None:
            return None
        old = urlparse(request.full_url)
        new = urlparse(new_url)
        if new.scheme not in {"http", "https"}:
            raise AuditFailure()
        if old.scheme == "https" and new.scheme != "https":
            raise AuditFailure()
        if (old.scheme, old.hostname, old.port) != (new.scheme, new.hostname, new.port):
            redirected.remove_header("Authorization")
        return redirected


def scanner_module():
    path = Path(__file__).with_name("security_scan.py")
    spec = importlib.util.spec_from_file_location("fire_aios_private_scanner", path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def request_bytes(
    url,
    token,
    *,
    accept="application/vnd.github+json",
    deadline=None,
):
    request = Request(
        url,
        headers={
            "Accept": accept,
            "Authorization": f"Bearer {token}",
            "User-Agent": "fire-aios-private-published-surface-audit",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        timeout = DOWNLOAD_TIMEOUT_SECONDS
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AuditFailure()
            timeout = min(timeout, remaining)
        with absolute_deadline(timeout):
            with build_opener(PrivateRedirectHandler()).open(
                request, timeout=timeout
            ) as response:
                expected = response.headers.get("Content-Length")
                if expected and int(expected) > MAX_DOWNLOAD_BYTES:
                    raise AuditFailure()
                chunks = []
                size = 0
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_DOWNLOAD_BYTES:
                        raise AuditFailure()
                    chunks.append(chunk)
                return b"".join(chunks)
    except AuditFailure:
        raise
    except Exception as error:
        raise AuditFailure() from error


def download_to_private_file(
    url,
    token,
    destination,
    *,
    accept="application/vnd.github+json",
    max_bytes=None,
):
    if max_bytes is None:
        max_bytes = MAX_ARTIFACT_DOWNLOAD_BYTES
    if type(max_bytes) is not int or max_bytes <= 0:
        raise AuditFailure()
    request = Request(
        url,
        headers={
            "Accept": accept,
            "Authorization": f"Bearer {token}",
            "User-Agent": "fire-aios-private-published-surface-audit",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    destination.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    try:
        with absolute_deadline(DOWNLOAD_TIMEOUT_SECONDS):
            with build_opener(PrivateRedirectHandler()).open(
                request, timeout=DOWNLOAD_TIMEOUT_SECONDS
            ) as response:
                expected = response.headers.get("Content-Length")
                if expected and int(expected) > max_bytes:
                    raise AuditFailure()
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW
                descriptor = os.open(destination, flags, 0o600)
                try:
                    with os.fdopen(descriptor, "wb") as output:
                        descriptor = None
                        size = 0
                        while True:
                            chunk = response.read(64 * 1024)
                            if not chunk:
                                break
                            size += len(chunk)
                            if size > max_bytes:
                                raise AuditFailure()
                            output.write(chunk)
                finally:
                    if descriptor is not None:
                        os.close(descriptor)
        return destination
    except AuditFailure:
        destination.unlink(missing_ok=True)
        raise
    except Exception as error:
        destination.unlink(missing_ok=True)
        raise AuditFailure() from error


def json_request(url, token, *, deadline=None):
    try:
        value = json.loads(request_bytes(url, token, deadline=deadline))
    except AuditFailure:
        raise
    except Exception as error:
        raise AuditFailure() from error
    return value


def paginated_list(api_url, path, token):
    rows = []
    for page in range(1, 1001):
        query = urlencode({"per_page": 100, "page": page})
        value = json_request(f"{api_url}{path}?{query}", token)
        if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
            raise AuditFailure()
        rows.extend(value)
        if len(value) < 100:
            return rows
    raise AuditFailure()


def artifact_list(api_url, repository, run_id, token):
    rows = []
    expected = None
    for page in range(1, 1001):
        query = urlencode({"per_page": 100, "page": page})
        value = json_request(
            f"{api_url}/repos/{repository}/actions/runs/{run_id}/artifacts?{query}", token
        )
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("artifacts"), list)
            or any(not isinstance(row, dict) for row in value["artifacts"])
        ):
            raise AuditFailure()
        if expected is None:
            expected = value.get("total_count")
            if type(expected) is not int or expected < 0:
                raise AuditFailure()
        rows.extend(value["artifacts"])
        if len(value["artifacts"]) < 100:
            if len(rows) != expected:
                raise AuditFailure()
            return rows
    raise AuditFailure()


def nested_archive_kind(path, payload, *, allow_embedded=False):
    name = path.name.lower()
    allowed_zip = path.suffix.lower() in ZIP_CONTAINER_SUFFIXES
    allowed_tar = name.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz"))
    if zipfile.is_zipfile(io.BytesIO(payload)):
        if allowed_zip:
            return "zip"
        identity = (path.as_posix(), hashlib.sha256(payload).hexdigest())
        if allow_embedded and identity in REVIEWED_EMBEDDED_ZIP_WRAPPERS:
            return "embedded_zip"
        return "unsupported"
    signatures = (
        b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08",
        b"7z\xbc\xaf\x27\x1c",
        b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00",
    )
    if payload.startswith(signatures):
        return "unsupported"
    if (
        payload.startswith((b"\x1f\x8b", b"\xfd7zXZ\x00", b"BZh"))
        or payload[257:262] == b"ustar"
    ):
        return "tar" if allowed_tar or allow_embedded else "unsupported"
    if path.suffix.lower() in NESTED_ARCHIVE_SUFFIXES:
        return "tar" if allowed_tar else "unsupported"
    return None


def is_nested_archive(path, payload):
    return nested_archive_kind(path, payload) is not None


def charge_extraction_budget(budget, size):
    budget["files"] += 1
    budget["bytes"] += size
    if (
        budget["files"] > MAX_FILES
        or size > MAX_ENTRY_BYTES
        or budget["bytes"] > MAX_EXTRACTED_BYTES
    ):
        raise AuditFailure()


def charge_archive_entry(budget, size):
    budget["files"] += 1
    if budget["files"] > MAX_FILES or size > MAX_ENTRY_BYTES:
        raise AuditFailure()


def charge_raw_expansion(budget, size):
    budget["bytes"] += size
    if budget["bytes"] > MAX_EXTRACTED_BYTES:
        raise AuditFailure()


def write_private_file(target, data):
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("xb") as destination:
            destination.write(data)
    except Exception as error:
        raise AuditFailure() from error


def validate_expansion_namespaces(entries, max_nested_depth):
    paths = [path.parts for path, _kind in entries]
    for path, kind in entries:
        if kind is None:
            continue
        if kind == "unsupported" or max_nested_depth <= 0:
            raise AuditFailure()
        expanded = path.with_name(f"{path.name}.expanded").parts
        if any(candidate[: len(expanded)] == expanded for candidate in paths):
            raise AuditFailure()


def write_or_expand(data, target, max_nested_depth, budget, *, kind, allow_embedded):
    if kind is None:
        write_private_file(target, data)
        return
    if max_nested_depth <= 0 or kind == "unsupported":
        raise AuditFailure()
    write_private_file(target, data)
    expanded = target.with_name(f"{target.name}.expanded")
    if kind in {"zip", "embedded_zip"}:
        extract_zip(
            data,
            expanded,
            max_nested_depth=max_nested_depth - 1,
            budget=budget,
            allow_embedded=True,
            allow_wrapping=kind == "embedded_zip",
        )
    else:
        extract_tar(
            data,
            expanded,
            max_nested_depth=max_nested_depth - 1,
            budget=budget,
            allow_embedded=True,
        )


def decompress_tar_payload(payload, budget):
    remaining = MAX_EXTRACTED_BYTES - budget["bytes"]
    if remaining < 0:
        raise AuditFailure()
    try:
        if payload.startswith(b"\x1f\x8b"):
            source = gzip.GzipFile(fileobj=io.BytesIO(payload))
        elif payload.startswith(b"BZh"):
            source = bz2.BZ2File(io.BytesIO(payload))
        elif payload.startswith(b"\xfd7zXZ\x00"):
            source = lzma.LZMAFile(io.BytesIO(payload))
        else:
            source = io.BytesIO(payload)
        with source:
            raw = source.read(remaining + 1)
    except Exception as error:
        raise AuditFailure() from error
    if len(raw) > remaining:
        raise AuditFailure()
    charge_raw_expansion(budget, len(raw))
    return raw


def validate_tar_padding(raw, archive_offset):
    if (
        type(archive_offset) is not int
        or archive_offset < 0
        or archive_offset % tarfile.BLOCKSIZE
        or len(raw) % tarfile.BLOCKSIZE
        or len(raw) - archive_offset < tarfile.BLOCKSIZE * 2
        or any(memoryview(raw)[archive_offset:])
    ):
        raise AuditFailure()


def extract_tar(
    payload,
    destination,
    *,
    max_nested_depth=0,
    budget=None,
    allow_embedded=False,
):
    if budget is None:
        budget = {"files": 0, "bytes": 0}
    raw = decompress_tar_payload(payload, budget)
    try:
        archive = tarfile.open(fileobj=io.BytesIO(raw), mode="r:")
    except Exception as error:
        raise AuditFailure() from error
    destination.mkdir(parents=True, mode=0o700, exist_ok=False)
    try:
        with archive:
            members = []
            paths = set()
            for member in archive:
                path = PurePosixPath(member.name)
                if path.is_absolute() or not path.parts or ".." in path.parts:
                    raise AuditFailure()
                if path.parts in paths:
                    raise AuditFailure()
                paths.add(path.parts)
                if member.sparse is not None or any(
                    key.startswith("GNU.sparse.") for key in member.pax_headers
                ):
                    raise AuditFailure()
                charge_archive_entry(budget, member.size)
                if member.isdir():
                    members.append((member, path, None))
                    continue
                if not member.isfile():
                    raise AuditFailure()
                source = archive.extractfile(member)
                if source is None:
                    raise AuditFailure()
                data = source.read(member.size + 1)
                if len(data) != member.size:
                    raise AuditFailure()
                kind = nested_archive_kind(
                    path, data, allow_embedded=allow_embedded
                )
                members.append((member, path, kind))
            validate_tar_padding(raw, archive.offset)
            validate_expansion_namespaces(
                [(path, kind) for _member, path, kind in members],
                max_nested_depth,
            )
            for member, path, kind in members:
                if member.isdir():
                    continue
                source = archive.extractfile(member)
                if source is None:
                    raise AuditFailure()
                data = source.read(member.size + 1)
                if len(data) != member.size:
                    raise AuditFailure()
                target = destination.joinpath(*path.parts)
                write_or_expand(
                    data,
                    target,
                    max_nested_depth,
                    budget,
                    kind=kind,
                    allow_embedded=allow_embedded,
                )
    except AuditFailure:
        raise
    except Exception as error:
        raise AuditFailure() from error


def has_prior_zip(payload):
    start = 0
    while True:
        location = payload.find(zipfile.stringEndArchive, start)
        if location < 0:
            return False
        start = location + 1
        if location + zipfile.sizeEndCentDir > len(payload):
            continue
        comment_size = int.from_bytes(
            payload[
                location
                + zipfile.sizeEndCentDir
                - 2 : location
                + zipfile.sizeEndCentDir
            ],
            "little",
        )
        archive_end = location + zipfile.sizeEndCentDir + comment_size
        if archive_end > len(payload):
            continue
        try:
            end_record = zipfile._EndRecData(io.BytesIO(payload[:archive_end]))
            if end_record is None:
                continue
            entries = end_record[zipfile._ECD_ENTRIES_TOTAL]
            entries_on_disk = end_record[zipfile._ECD_ENTRIES_THIS_DISK]
            directory_size = end_record[zipfile._ECD_SIZE]
            directory_offset = end_record[zipfile._ECD_OFFSET]
            end_location = end_record[zipfile._ECD_LOCATION]
            prefix_size = end_location - directory_size - directory_offset
            directory_start = end_location - directory_size
        except Exception:
            continue
        if (
            type(entries) is int
            and entries >= 0
            and entries_on_disk == entries
            and prefix_size >= 0
            and directory_start >= prefix_size
            and directory_start <= location
            and (
                (entries == 0 and directory_size == 0)
                or payload[
                    directory_start : directory_start
                    + len(zipfile.stringCentralDir)
                ]
                == zipfile.stringCentralDir
            )
        ):
            return True


def count_central_directory_entries(payload, start, size, max_entries):
    if (
        type(start) is not int
        or type(size) is not int
        or start < 0
        or size < 0
        or type(max_entries) is not int
        or max_entries < 0
        or start + size > len(payload)
    ):
        raise AuditFailure()
    offset = start
    end = start + size
    count = 0
    try:
        while offset < end:
            if count >= max_entries or end - offset < zipfile.sizeCentralDir:
                raise AuditFailure()
            central = struct.unpack_from(zipfile.structCentralDir, payload, offset)
            if central[zipfile._CD_SIGNATURE] != zipfile.stringCentralDir:
                raise AuditFailure()
            variable_size = (
                central[zipfile._CD_FILENAME_LENGTH]
                + central[zipfile._CD_EXTRA_FIELD_LENGTH]
                + central[zipfile._CD_COMMENT_LENGTH]
            )
            offset += zipfile.sizeCentralDir + variable_size
            if offset > end:
                raise AuditFailure()
            count += 1
    except AuditFailure:
        raise
    except Exception as error:
        raise AuditFailure() from error
    if offset != end:
        raise AuditFailure()
    return count


def count_central_directory_file_entries(source, start, size, max_entries):
    if (
        type(start) is not int
        or type(size) is not int
        or start < 0
        or size < 0
        or type(max_entries) is not int
        or max_entries < 0
    ):
        raise AuditFailure()
    offset = start
    end = start + size
    count = 0
    try:
        source.seek(start)
        while offset < end:
            if count >= max_entries or end - offset < zipfile.sizeCentralDir:
                raise AuditFailure()
            header = source.read(zipfile.sizeCentralDir)
            if len(header) != zipfile.sizeCentralDir:
                raise AuditFailure()
            central = struct.unpack(zipfile.structCentralDir, header)
            if central[zipfile._CD_SIGNATURE] != zipfile.stringCentralDir:
                raise AuditFailure()
            variable_size = (
                central[zipfile._CD_FILENAME_LENGTH]
                + central[zipfile._CD_EXTRA_FIELD_LENGTH]
                + central[zipfile._CD_COMMENT_LENGTH]
            )
            if offset + zipfile.sizeCentralDir + variable_size > end:
                raise AuditFailure()
            source.seek(variable_size, os.SEEK_CUR)
            offset += zipfile.sizeCentralDir + variable_size
            count += 1
    except AuditFailure:
        raise
    except Exception as error:
        raise AuditFailure() from error
    if offset != end:
        raise AuditFailure()
    return count


def preflight_zip(payload, budget, *, allow_wrapping=False):
    try:
        end_record = zipfile._EndRecData(io.BytesIO(payload))
    except Exception as error:
        raise AuditFailure() from error
    if end_record is None:
        raise AuditFailure()

    try:
        entries = end_record[zipfile._ECD_ENTRIES_TOTAL]
        entries_on_disk = end_record[zipfile._ECD_ENTRIES_THIS_DISK]
        disk = end_record[zipfile._ECD_DISK_NUMBER]
        directory_disk = end_record[zipfile._ECD_DISK_START]
        directory_size = end_record[zipfile._ECD_SIZE]
        directory_offset = end_record[zipfile._ECD_OFFSET]
        end_location = end_record[zipfile._ECD_LOCATION]
        comment = end_record[zipfile._ECD_COMMENT]
    except Exception as error:
        raise AuditFailure() from error

    standard_end_location = payload.rfind(zipfile.stringEndArchive)
    if standard_end_location < 0:
        raise AuditFailure()
    declared_comment_size = int.from_bytes(
        payload[
            standard_end_location
            + zipfile.sizeEndCentDir
            - 2 : standard_end_location
            + zipfile.sizeEndCentDir
        ],
        "little",
    )
    archive_end = (
        standard_end_location + zipfile.sizeEndCentDir + declared_comment_size
    )
    if (
        type(entries) is not int
        or entries < 0
        or entries > MAX_FILES - budget["files"]
        or entries_on_disk != entries
        or disk != 0
        or directory_disk != 0
        or type(directory_size) is not int
        or type(directory_offset) is not int
        or type(end_location) is not int
        or min(directory_size, directory_offset, end_location) < 0
        or archive_end > len(payload)
    ):
        raise AuditFailure()

    prefix_size = end_location - directory_size - directory_offset
    if prefix_size < 0 or prefix_size > len(payload):
        raise AuditFailure()
    actual_entries = count_central_directory_entries(
        payload,
        end_location - directory_size,
        directory_size,
        MAX_FILES - budget["files"],
    )
    if actual_entries != entries or actual_entries > MAX_FILES - budget["files"]:
        raise AuditFailure()
    if allow_wrapping:
        if has_prior_zip(payload[:prefix_size]):
            raise AuditFailure()
    elif prefix_size != 0 or archive_end != len(payload):
        raise AuditFailure()
    return entries


def preflight_zip_file(path, budget):
    try:
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode):
            raise AuditFailure()
        with path.open("rb") as source:
            end_record = zipfile._EndRecData(source)
            if end_record is None:
                raise AuditFailure()
            entries = end_record[zipfile._ECD_ENTRIES_TOTAL]
            entries_on_disk = end_record[zipfile._ECD_ENTRIES_THIS_DISK]
            disk = end_record[zipfile._ECD_DISK_NUMBER]
            directory_disk = end_record[zipfile._ECD_DISK_START]
            directory_size = end_record[zipfile._ECD_SIZE]
            directory_offset = end_record[zipfile._ECD_OFFSET]
            end_location = end_record[zipfile._ECD_LOCATION]
            tail_size = min(
                metadata.st_size,
                zipfile.ZIP_MAX_COMMENT + zipfile.sizeEndCentDir,
            )
            source.seek(metadata.st_size - tail_size)
            tail = source.read(tail_size)
            relative_standard_end = tail.rfind(zipfile.stringEndArchive)
            if (
                relative_standard_end < 0
                or len(tail) - relative_standard_end < zipfile.sizeEndCentDir
            ):
                raise AuditFailure()
            standard_end_location = (
                metadata.st_size - tail_size + relative_standard_end
            )
            declared_comment_size = int.from_bytes(
                tail[
                    relative_standard_end
                    + zipfile.sizeEndCentDir
                    - 2 : relative_standard_end
                    + zipfile.sizeEndCentDir
                ],
                "little",
            )
            archive_end = (
                standard_end_location
                + zipfile.sizeEndCentDir
                + declared_comment_size
            )
            if (
                type(entries) is not int
                or entries < 0
                or entries > MAX_FILES - budget["files"]
                or entries_on_disk != entries
                or disk != 0
                or directory_disk != 0
                or type(directory_size) is not int
                or type(directory_offset) is not int
                or type(end_location) is not int
                or min(directory_size, directory_offset, end_location) < 0
                or archive_end != metadata.st_size
            ):
                raise AuditFailure()
            prefix_size = end_location - directory_size - directory_offset
            if prefix_size != 0:
                raise AuditFailure()
            actual_entries = count_central_directory_file_entries(
                source,
                end_location - directory_size,
                directory_size,
                MAX_FILES - budget["files"],
            )
            if actual_entries != entries:
                raise AuditFailure()
            return entries
    except AuditFailure:
        raise
    except Exception as error:
        raise AuditFailure() from error


def extract_zip(
    payload,
    destination,
    *,
    max_nested_depth=0,
    budget=None,
    allow_embedded=False,
    allow_wrapping=False,
):
    if budget is None:
        budget = {"files": 0, "bytes": 0}
    expected_entries = preflight_zip(
        payload, budget, allow_wrapping=allow_wrapping
    )
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except Exception as error:
        raise AuditFailure() from error
    extract_zip_archive(
        archive,
        destination,
        expected_entries,
        max_nested_depth=max_nested_depth,
        budget=budget,
        allow_embedded=allow_embedded,
    )


def extract_zip_archive(
    archive,
    destination,
    expected_entries,
    *,
    max_nested_depth,
    budget,
    allow_embedded,
):
    destination.mkdir(parents=True, mode=0o700, exist_ok=False)
    try:
        with archive:
            members = archive.infolist()
            if len(members) != expected_entries:
                raise AuditFailure()
            paths = set()
            entries = []
            for member in members:
                path = PurePosixPath(member.filename)
                mode = member.external_attr >> 16
                if path.is_absolute() or not path.parts or ".." in path.parts:
                    raise AuditFailure()
                if path.parts in paths:
                    raise AuditFailure()
                paths.add(path.parts)
                file_type = stat.S_IFMT(mode)
                if file_type and file_type not in (stat.S_IFREG, stat.S_IFDIR):
                    raise AuditFailure()
                if member.is_dir():
                    charge_archive_entry(budget, 0)
                    entries.append((member, path, None))
                    continue
                charge_extraction_budget(budget, member.file_size)
                data = archive.read(member)
                if len(data) != member.file_size:
                    raise AuditFailure()
                kind = nested_archive_kind(
                    path, data, allow_embedded=allow_embedded
                )
                entries.append((member, path, kind))
            validate_expansion_namespaces(
                [(path, kind) for _member, path, kind in entries],
                max_nested_depth,
            )
            for member, path, kind in entries:
                if member.is_dir():
                    continue
                target = destination.joinpath(*path.parts)
                data = archive.read(member)
                if len(data) != member.file_size:
                    raise AuditFailure()
                write_or_expand(
                    data,
                    target,
                    max_nested_depth,
                    budget,
                    kind=kind,
                    allow_embedded=allow_embedded,
                )
    except AuditFailure:
        raise
    except Exception as error:
        raise AuditFailure() from error


def extract_zip_file(
    path,
    destination,
    *,
    max_nested_depth=0,
    budget=None,
):
    if budget is None:
        budget = {"files": 0, "bytes": 0}
    expected_entries = preflight_zip_file(path, budget)
    try:
        archive = zipfile.ZipFile(path)
    except Exception as error:
        raise AuditFailure() from error
    extract_zip_archive(
        archive,
        destination,
        expected_entries,
        max_nested_depth=max_nested_depth,
        budget=budget,
        allow_embedded=False,
    )


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True))


def parse_id_list(value, repeated):
    if not value:
        return list(repeated)
    if not re.fullmatch(r"[1-9][0-9]*(,[1-9][0-9]*)*", value):
        raise AuditFailure()
    return [int(item) for item in value.split(",")] + list(repeated)


def _check_history_deadline(deadline):
    if time.monotonic() >= deadline:
        raise AuditFailure()


def _historical_pull_requests(api_url, repository, token, deadline):
    numbers = []
    pages = []
    base = f"/repos/{repository}/pulls"
    for page in range(1, 1001):
        _check_history_deadline(deadline)
        query = urlencode(
            {
                "state": "all",
                "sort": "created",
                "direction": "asc",
                "per_page": 100,
                "page": page,
            }
        )
        value = json_request(f"{api_url}{base}?{query}", token, deadline=deadline)
        _check_history_deadline(deadline)
        if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
            raise AuditFailure()
        pages.append(value)
        if len(numbers) + len(value) > MAX_HISTORY_SURFACES:
            raise AuditFailure()
        for row in value:
            number = row.get("number")
            full_name = row.get("base", {}).get("repo", {}).get("full_name")
            if type(number) is not int or number <= 0 or full_name != repository:
                raise AuditFailure()
            numbers.append(number)
        if len(value) < 100:
            break
    else:
        raise AuditFailure()

    if numbers != sorted(set(numbers)):
        raise AuditFailure()

    for page, expected_page in enumerate(pages, start=1):
        query = urlencode(
            {
                "state": "all",
                "sort": "created",
                "direction": "asc",
                "per_page": 100,
                "page": page,
            }
        )
        repeated_page = json_request(
            f"{api_url}{base}?{query}", token, deadline=deadline
        )
        if repeated_page != expected_page:
            raise AuditFailure()
    return numbers


def _historical_workflow_runs(api_url, repository, token, deadline):
    all_run_ids = set()
    completed_run_ids = []
    expected = None
    pages = []
    base = f"/repos/{repository}/actions/runs"
    for page in range(1, 1001):
        _check_history_deadline(deadline)
        query = urlencode({"per_page": 100, "page": page})
        value = json_request(f"{api_url}{base}?{query}", token, deadline=deadline)
        _check_history_deadline(deadline)
        if (
            not isinstance(value, dict)
            or type(value.get("total_count")) is not int
            or value["total_count"] < 0
            or not isinstance(value.get("workflow_runs"), list)
            or any(not isinstance(row, dict) for row in value["workflow_runs"])
        ):
            raise AuditFailure()
        if expected is None:
            expected = value["total_count"]
            if expected > MAX_HISTORY_SURFACES:
                raise AuditFailure()
        elif value["total_count"] != expected:
            raise AuditFailure()
        pages.append(value)
        for row in value["workflow_runs"]:
            run_id = row.get("id")
            if (
                type(run_id) is not int
                or run_id <= 0
                or not isinstance(row.get("status"), str)
                or row.get("repository", {}).get("full_name") != repository
                or run_id in all_run_ids
            ):
                raise AuditFailure()
            all_run_ids.add(run_id)
            if row["status"] == "completed":
                completed_run_ids.append(run_id)
        if len(value["workflow_runs"]) < 100:
            break
    else:
        raise AuditFailure()
    if len(all_run_ids) != expected:
        raise AuditFailure()

    for page, expected_page in enumerate(pages, start=1):
        query = urlencode({"per_page": 100, "page": page})
        repeated_page = json_request(
            f"{api_url}{base}?{query}", token, deadline=deadline
        )
        if repeated_page != expected_page:
            raise AuditFailure()
    return sorted(all_run_ids), sorted(completed_run_ids)


def discover_historical_inventory(api_url, repository, token):
    if not token or not REPOSITORY.fullmatch(repository):
        raise AuditFailure()
    deadline = time.monotonic() + MAX_HISTORY_DISCOVERY_SECONDS
    pull_requests = _historical_pull_requests(
        api_url, repository, token, deadline
    )
    workflow_runs, completed_workflow_runs = _historical_workflow_runs(
        api_url, repository, token, deadline
    )
    identity = {
        "version": "fire-aios-published-surface-inventory-v2",
        "repository": repository,
        "pull_requests": pull_requests,
        "workflow_runs": workflow_runs,
        "completed_workflow_runs": completed_workflow_runs,
    }
    digest = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "repository": repository,
        "pull_requests": pull_requests,
        "workflow_runs": workflow_runs,
        "completed_workflow_runs": completed_workflow_runs,
        "pull_request_count": len(pull_requests),
        "workflow_run_count": len(workflow_runs),
        "completed_workflow_run_count": len(completed_workflow_runs),
        "inventory_sha256": digest,
    }


def _history_snapshot_bounds(
    inventory,
    *,
    through_pull_request,
    through_workflow_run,
    snapshot_initialized,
):
    pull_requests = inventory.get("pull_requests")
    workflow_runs = inventory.get("workflow_runs")
    if (
        not isinstance(pull_requests, list)
        or not isinstance(workflow_runs, list)
        or type(through_pull_request) is not int
        or through_pull_request < 0
        or type(through_workflow_run) is not int
        or through_workflow_run < 0
        or type(snapshot_initialized) is not bool
    ):
        raise AuditFailure()
    if snapshot_initialized:
        snapshot_pull_request = through_pull_request
        snapshot_workflow_run = through_workflow_run
    else:
        if through_pull_request or through_workflow_run:
            raise AuditFailure()
        snapshot_pull_request = pull_requests[-1] if pull_requests else 0
        snapshot_workflow_run = workflow_runs[-1] if workflow_runs else 0
    if (
        snapshot_pull_request
        and snapshot_pull_request not in pull_requests
    ) or (
        snapshot_workflow_run
        and snapshot_workflow_run not in workflow_runs
    ):
        raise AuditFailure()
    return snapshot_pull_request, snapshot_workflow_run


def historical_snapshot_sha256(
    inventory, *, through_pull_request, through_workflow_run
):
    repository = inventory.get("repository")
    pull_requests = inventory.get("pull_requests")
    workflow_runs = inventory.get("workflow_runs")
    if (
        not isinstance(repository, str)
        or not REPOSITORY.fullmatch(repository)
        or not isinstance(pull_requests, list)
        or not isinstance(workflow_runs, list)
    ):
        raise AuditFailure()
    snapshot_pull_request, snapshot_workflow_run = _history_snapshot_bounds(
        inventory,
        through_pull_request=through_pull_request,
        through_workflow_run=through_workflow_run,
        snapshot_initialized=True,
    )
    identity = {
        "version": "fire-aios-published-surface-snapshot-v1",
        "repository": repository,
        "through_pull_request": snapshot_pull_request,
        "through_workflow_run": snapshot_workflow_run,
        "pull_requests": [
            value for value in pull_requests if value <= snapshot_pull_request
        ],
        "workflow_runs": [
            value for value in workflow_runs if value <= snapshot_workflow_run
        ],
    }
    return hashlib.sha256(
        json.dumps(
            identity,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def historical_cursor_sha256(
    inventory,
    *,
    after_pull_request,
    after_workflow_run,
    through_pull_request=0,
    through_workflow_run=0,
    snapshot_initialized=False,
):
    repository = inventory.get("repository")
    pull_requests = inventory.get("pull_requests")
    workflow_runs = inventory.get("workflow_runs")
    completed_workflow_runs = inventory.get("completed_workflow_runs")
    if (
        not isinstance(repository, str)
        or not REPOSITORY.fullmatch(repository)
        or not isinstance(pull_requests, list)
        or not isinstance(workflow_runs, list)
        or not isinstance(completed_workflow_runs, list)
        or type(after_pull_request) is not int
        or after_pull_request < 0
        or type(after_workflow_run) is not int
        or after_workflow_run < 0
    ):
        raise AuditFailure()
    snapshot_pull_request, snapshot_workflow_run = _history_snapshot_bounds(
        inventory,
        through_pull_request=through_pull_request,
        through_workflow_run=through_workflow_run,
        snapshot_initialized=snapshot_initialized,
    )
    if (
        after_pull_request > snapshot_pull_request
        or after_workflow_run > snapshot_workflow_run
    ):
        raise AuditFailure()
    completed = set(completed_workflow_runs)
    identity = {
        "version": "fire-aios-published-surface-cursor-v1",
        "repository": repository,
        "after_pull_request": after_pull_request,
        "after_workflow_run": after_workflow_run,
        "through_pull_request": snapshot_pull_request,
        "through_workflow_run": snapshot_workflow_run,
        "pull_requests": [
            value for value in pull_requests if value <= after_pull_request
        ],
        "workflow_runs": [
            [value, value in completed]
            for value in workflow_runs
            if value <= after_workflow_run
        ],
    }
    return hashlib.sha256(
        json.dumps(
            identity,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def select_historical_batch(
    inventory,
    *,
    after_pull_request,
    after_workflow_run,
    pull_request_limit,
    workflow_run_limit,
    expected_cursor_sha256="",
    through_pull_request=0,
    through_workflow_run=0,
    snapshot_initialized=False,
    expected_snapshot_sha256="",
):
    if not snapshot_initialized and (
        after_pull_request
        or after_workflow_run
        or expected_cursor_sha256
        or expected_snapshot_sha256
    ):
        raise AuditFailure()
    for value in (after_pull_request, after_workflow_run):
        if type(value) is not int or value < 0:
            raise AuditFailure()
    for value in (pull_request_limit, workflow_run_limit):
        if type(value) is not int or not 1 <= value <= 100:
            raise AuditFailure()
    pull_requests = inventory.get("pull_requests")
    workflow_runs = inventory.get("workflow_runs")
    completed_workflow_runs = inventory.get("completed_workflow_runs")
    if (
        not isinstance(pull_requests, list)
        or not isinstance(workflow_runs, list)
        or not isinstance(completed_workflow_runs, list)
        or pull_requests != sorted(set(pull_requests))
        or workflow_runs != sorted(set(workflow_runs))
        or completed_workflow_runs != sorted(set(completed_workflow_runs))
        or not set(completed_workflow_runs).issubset(workflow_runs)
        or any(
            type(value) is not int or value <= 0
            for value in pull_requests + workflow_runs + completed_workflow_runs
        )
        or (after_pull_request and after_pull_request not in pull_requests)
        or (
            after_workflow_run
            and after_workflow_run not in completed_workflow_runs
        )
    ):
        raise AuditFailure()
    snapshot_pull_request, snapshot_workflow_run = _history_snapshot_bounds(
        inventory,
        through_pull_request=through_pull_request,
        through_workflow_run=through_workflow_run,
        snapshot_initialized=snapshot_initialized,
    )
    snapshot_pull_requests = [
        value for value in pull_requests if value <= snapshot_pull_request
    ]
    snapshot_workflow_runs = [
        value for value in workflow_runs if value <= snapshot_workflow_run
    ]
    snapshot_completed_workflow_runs = [
        value
        for value in completed_workflow_runs
        if value <= snapshot_workflow_run
    ]
    if (
        (after_pull_request and after_pull_request not in snapshot_pull_requests)
        or (
            after_workflow_run
            and after_workflow_run not in snapshot_completed_workflow_runs
        )
    ):
        raise AuditFailure()
    snapshot_sha256 = historical_snapshot_sha256(
        inventory,
        through_pull_request=snapshot_pull_request,
        through_workflow_run=snapshot_workflow_run,
    )
    if snapshot_initialized:
        if (
            not re.fullmatch(r"[0-9a-f]{64}", expected_snapshot_sha256)
            or expected_snapshot_sha256 != snapshot_sha256
        ):
            raise AuditFailure()
    elif expected_snapshot_sha256:
        raise AuditFailure()
    actual_cursor_sha256 = historical_cursor_sha256(
        inventory,
        after_pull_request=after_pull_request,
        after_workflow_run=after_workflow_run,
        through_pull_request=snapshot_pull_request,
        through_workflow_run=snapshot_workflow_run,
        snapshot_initialized=True,
    )
    if (
        (snapshot_initialized or after_pull_request or after_workflow_run)
        and not expected_cursor_sha256
    ) or (
        expected_cursor_sha256
        and (
            not re.fullmatch(r"[0-9a-f]{64}", expected_cursor_sha256)
            or expected_cursor_sha256 != actual_cursor_sha256
        )
    ):
        raise AuditFailure()
    remaining_pull_requests = [
        value for value in snapshot_pull_requests if value > after_pull_request
    ]
    selected_pull_requests = remaining_pull_requests[:pull_request_limit]
    completed = set(snapshot_completed_workflow_runs)
    selected_workflow_runs = []
    for value in (
        item for item in snapshot_workflow_runs if item > after_workflow_run
    ):
        if value not in completed:
            break
        selected_workflow_runs.append(value)
        if len(selected_workflow_runs) == workflow_run_limit:
            break
    next_workflow_run = (
        selected_workflow_runs[-1] if selected_workflow_runs else after_workflow_run
    )
    unprocessed_workflow_runs = [
        value for value in snapshot_workflow_runs if value > next_workflow_run
    ]
    blocked_workflow_run = (
        unprocessed_workflow_runs[0]
        if unprocessed_workflow_runs and unprocessed_workflow_runs[0] not in completed
        else None
    )
    return {
        "pull_requests": selected_pull_requests,
        "workflow_runs": selected_workflow_runs,
        "next_pull_request": (
            selected_pull_requests[-1] if selected_pull_requests else after_pull_request
        ),
        "next_workflow_run": next_workflow_run,
        "remaining_pull_requests": len(remaining_pull_requests) - len(selected_pull_requests),
        "remaining_workflow_runs": sum(
            value > next_workflow_run
            for value in snapshot_completed_workflow_runs
        ),
        "blocked_workflow_run": blocked_workflow_run,
        "snapshot_pull_request": snapshot_pull_request,
        "snapshot_workflow_run": snapshot_workflow_run,
        "snapshot_initialized": True,
        "snapshot_sha256": snapshot_sha256,
        "next_cursor_sha256": historical_cursor_sha256(
            inventory,
            after_pull_request=(
                selected_pull_requests[-1]
                if selected_pull_requests
                else after_pull_request
            ),
            after_workflow_run=next_workflow_run,
            through_pull_request=snapshot_pull_request,
            through_workflow_run=snapshot_workflow_run,
            snapshot_initialized=True,
        ),
    }


def collect_surfaces(api_url, repository, pull_requests, workflow_runs, token, root):
    if not token or not REPOSITORY.fullmatch(repository):
        raise AuditFailure()
    pull_requests = sorted(set(pull_requests))
    workflow_runs = sorted(set(workflow_runs))
    if not pull_requests and not workflow_runs:
        raise AuditFailure()
    if any(value <= 0 for value in pull_requests + workflow_runs):
        raise AuditFailure()
    root.mkdir(parents=True, mode=0o700, exist_ok=False)
    manifest = {"pull_requests": 0, "workflow_runs": 0, "artifacts": 0}

    for number in pull_requests:
        base = f"/repos/{repository}"
        metadata = json_request(f"{api_url}{base}/pulls/{number}", token)
        if (
            not isinstance(metadata, dict)
            or type(metadata.get("number")) is not int
            or metadata.get("number") != number
        ):
            raise AuditFailure()
        location = root / "pull-requests" / str(number)
        write_json(location / "metadata.json", metadata)
        write_json(location / "issue-comments.json", paginated_list(api_url, f"{base}/issues/{number}/comments", token))
        write_json(location / "review-comments.json", paginated_list(api_url, f"{base}/pulls/{number}/comments", token))
        write_json(location / "reviews.json", paginated_list(api_url, f"{base}/pulls/{number}/reviews", token))
        manifest["pull_requests"] += 1

    for run_id in workflow_runs:
        base = f"/repos/{repository}/actions"
        metadata = json_request(f"{api_url}{base}/runs/{run_id}", token)
        if (
            not isinstance(metadata, dict)
            or type(metadata.get("id")) is not int
            or metadata.get("id") != run_id
            or metadata.get("status") != "completed"
            or metadata.get("repository", {}).get("full_name") != repository
        ):
            raise AuditFailure()
        location = root / "workflow-runs" / str(run_id)
        write_json(location / "metadata.json", metadata)
        logs = request_bytes(
            f"{api_url}{base}/runs/{run_id}/logs", token, accept="application/vnd.github+json"
        )
        extract_zip(logs, location / "logs")
        artifacts = artifact_list(api_url, repository, run_id, token)
        write_json(location / "artifacts.json", artifacts)
        for artifact in artifacts:
            artifact_id = artifact.get("id") if isinstance(artifact, dict) else None
            if type(artifact_id) is not int or artifact_id <= 0 or artifact.get("expired") is not False:
                raise AuditFailure()
            archive_path = location / "artifact-downloads" / f"{artifact_id}.zip"
            try:
                download_to_private_file(
                    f"{api_url}{base}/artifacts/{artifact_id}/zip",
                    token,
                    archive_path,
                    accept="application/vnd.github+json",
                )
                extract_zip_file(
                    archive_path,
                    location / "artifacts" / str(artifact_id),
                    max_nested_depth=2,
                )
            finally:
                archive_path.unlink(missing_ok=True)
            manifest["artifacts"] += 1
        manifest["workflow_runs"] += 1
    write_json(root / "manifest.json", manifest)
    return manifest


def main(argv=None):
    parser = SafeParser(description="Privately scan selected published GitHub surfaces.")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pull-request", type=int, action="append", default=[])
    parser.add_argument("--workflow-run", type=int, action="append", default=[])
    parser.add_argument("--pull-requests", default="")
    parser.add_argument("--workflow-runs", default="")
    parser.add_argument("--historical", action="store_true")
    parser.add_argument("--history-after-pull-request", type=int, default=0)
    parser.add_argument("--history-after-workflow-run", type=int, default=0)
    parser.add_argument("--history-pull-request-limit", type=int, default=10)
    parser.add_argument("--history-workflow-run-limit", type=int, default=1)
    parser.add_argument("--history-cursor-sha256", default="")
    parser.add_argument("--history-through-pull-request", type=int, default=0)
    parser.add_argument("--history-through-workflow-run", type=int, default=0)
    parser.add_argument("--history-snapshot-initialized", action="store_true")
    parser.add_argument("--history-snapshot-sha256", default="")
    parser.add_argument("--gitleaks", type=Path, required=True)
    parser.add_argument("--api-url", default="https://api.github.com", help=argparse.SUPPRESS)
    try:
        args = parser.parse_args(argv)
        token = os.environ.get("FIRE_AI_GITHUB_AUDIT_TOKEN")
        if not token:
            raise AuditFailure()
        explicit_pull_requests = parse_id_list(
            args.pull_requests, args.pull_request
        )
        explicit_workflow_runs = parse_id_list(
            args.workflow_runs, args.workflow_run
        )
        if args.historical and (explicit_pull_requests or explicit_workflow_runs):
            raise AuditFailure()
        if args.historical:
            inventory = discover_historical_inventory(
                args.api_url.rstrip("/"), args.repository, token
            )
            batch = select_historical_batch(
                inventory,
                after_pull_request=args.history_after_pull_request,
                after_workflow_run=args.history_after_workflow_run,
                pull_request_limit=args.history_pull_request_limit,
                workflow_run_limit=args.history_workflow_run_limit,
                expected_cursor_sha256=args.history_cursor_sha256,
                through_pull_request=args.history_through_pull_request,
                through_workflow_run=args.history_through_workflow_run,
                snapshot_initialized=args.history_snapshot_initialized,
                expected_snapshot_sha256=args.history_snapshot_sha256,
            )
            pull_requests = batch["pull_requests"]
            workflow_runs = batch["workflow_runs"]
        else:
            inventory = None
            batch = None
            pull_requests = explicit_pull_requests
            workflow_runs = explicit_workflow_runs
        with tempfile.TemporaryDirectory(
            prefix="fire-aios-published-surface-", dir="/tmp"
        ) as location:
            private = Path(location) / "collected"
            if pull_requests or workflow_runs:
                manifest = collect_surfaces(
                    args.api_url.rstrip("/"), args.repository,
                    pull_requests, workflow_runs, token, private,
                )
                findings = scanner_module().scan_directory(
                    private,
                    args.gitleaks,
                    accepted_findings=REVIEWED_PUBLIC_DEPENDENCY_FINDINGS,
                )
            elif args.historical:
                manifest = {"pull_requests": 0, "workflow_runs": 0, "artifacts": 0}
                findings = 0
            else:
                raise AuditFailure()
        if inventory is not None:
            manifest.update(
                {
                    "inventory_pull_requests": inventory["pull_request_count"],
                    "inventory_workflow_runs": inventory["workflow_run_count"],
                    "inventory_completed_workflow_runs": inventory[
                        "completed_workflow_run_count"
                    ],
                    "inventory_sha256": inventory["inventory_sha256"],
                    "next_pull_request": batch["next_pull_request"],
                    "next_workflow_run": batch["next_workflow_run"],
                    "remaining_pull_requests": batch["remaining_pull_requests"],
                    "remaining_workflow_runs": batch["remaining_workflow_runs"],
                    "blocked_workflow_run": batch["blocked_workflow_run"],
                    "snapshot_pull_request": batch["snapshot_pull_request"],
                    "snapshot_workflow_run": batch["snapshot_workflow_run"],
                    "snapshot_initialized": batch["snapshot_initialized"],
                    "snapshot_sha256": batch["snapshot_sha256"],
                    "next_cursor_sha256": batch["next_cursor_sha256"],
                }
            )
        counts = "; ".join(f"{key}={value}" for key, value in manifest.items())
        print(
            f"Published-surface secret audit {'blocked' if findings else 'passed'}; "
            f"{counts}; findings={findings}"
        )
        return 1 if findings else 0
    except Exception:
        print("Published-surface secret audit failed closed; findings=unknown")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
