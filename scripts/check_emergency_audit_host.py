"""Read-only host readiness, or explicit create-only local key initialization.

No downloads, model pull, document access, DB write or path/secret output.
The supplied manifest must be approved and protected by the administrator;
matching its hashes is not itself proof of organizational approval.
"""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'backend'))
SUPPORTED_PLATFORM = os.name == 'posix' and sys.platform.startswith('linux')
SHA = re.compile(r'[0-9a-f]{64}\Z', re.ASCII)
LANGUAGE = re.compile(r'[A-Za-z0-9_]{1,40}\Z', re.ASCII)


def _config():
    from app.settings import settings
    return settings


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError()
        result[key] = value
    return result


def _hash(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > 256*1024*1024:
        raise ValueError()
    digest = sha256()
    with path.open('rb') as stream:
        while part := stream.read(1024*1024): digest.update(part)
    return digest.hexdigest()


def _manifest(path):
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > 65_536 or (os.name == 'posix' and path.stat().st_mode & 0o022):
        raise ValueError()
    with path.open('rb') as stream: value = json.loads(stream.read(65_537), object_pairs_hook=_unique)
    if not isinstance(value, dict) or set(value) != {'schema_version', 'tesseract'} or type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise ValueError()
    native = value['tesseract']
    if not isinstance(native, dict) or set(native) != {'version', 'executable_sha256', 'traineddata'}:
        raise ValueError()
    if (not isinstance(native['version'], str) or not re.fullmatch(r'[0-9]+(?:\.[0-9]+){1,3}', native['version'])
            or not isinstance(native['executable_sha256'], str) or not SHA.fullmatch(native['executable_sha256'])
            or not isinstance(native['traineddata'], dict) or not 1 <= len(native['traineddata']) <= 20):
        raise ValueError()
    for language, digest in native['traineddata'].items():
        if not LANGUAGE.fullmatch(language) or not isinstance(digest, str) or not SHA.fullmatch(digest):
            raise ValueError()
    return native


def _run_native(command):
    env = {key: os.environ[key] for key in ('PATH', 'LD_LIBRARY_PATH', 'TESSDATA_PREFIX') if key in os.environ}
    env['LC_ALL'] = 'C'
    result = subprocess.run(command, capture_output=True, timeout=5, check=False, env=env)
    if result.returncode or len(result.stdout) > 65_536: raise ValueError()
    return result.stdout.decode('utf-8', errors='strict')


def _native_status(manifest_path, required):
    if manifest_path is None:
        return 'MANIFEST_REQUIRED'
    try:
        native = _manifest(manifest_path)
    except Exception:
        return 'NATIVE_MANIFEST_INVALID'
    if not set(required) <= set(native['traineddata']):
        return 'NATIVE_MANIFEST_LANGUAGE_MISSING'
    try:
        executable = shutil.which('tesseract')
        if not executable: return 'OCR_ENGINE_UNAVAILABLE'
        if _hash(executable) != native['executable_sha256']: return 'NATIVE_EXECUTABLE_MISMATCH'
        version = _run_native([executable, '--version']).splitlines()[0]
        match = re.fullmatch(r'tesseract ([0-9]+(?:\.[0-9]+){1,3})', version.strip())
        if not match or match.group(1) != native['version']: return 'NATIVE_VERSION_MISMATCH'
        lines = _run_native([executable, '--list-langs']).splitlines()
        header = re.fullmatch(r'List of available languages in "([^"\r\n]+)" \([0-9]+\):', lines[0])
        if not header: return 'NATIVE_PROBE_FAILED'
        available = {line.strip() for line in lines[1:] if LANGUAGE.fullmatch(line.strip())}
        if not set(required) <= available: return 'OCR_LANGUAGE_UNAVAILABLE'
        folder = Path(header.group(1))
        for language in required:
            if _hash(folder / (language + '.traineddata')) != native['traineddata'][language]:
                return 'NATIVE_LANGUAGE_MISMATCH'
        return 'VERIFIED'
    except Exception:
        return 'NATIVE_PROBE_FAILED'


def _key_location(config, backup_roots, *, creating=False):
    if not config.emergency_audit_key_file: return None, 'KEY_NOT_CONFIGURED'
    path = Path(config.emergency_audit_key_file)
    if not path.is_absolute(): return None, 'KEY_PATH_INVALID'
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        return None, 'KEY_LOCATION_INVALID'
    resolved = path.resolve()
    forbidden = [Path(config.storage_root).resolve(), ROOT.resolve(), Path('/var/backups/fire-ai')]
    forbidden.extend(Path(item).resolve() for item in backup_roots)
    if any(resolved.is_relative_to(folder) for folder in forbidden): return None, 'KEY_LOCATION_INVALID'
    if creating:
        if not path.parent.is_dir(): return None, 'KEY_PATH_INVALID'
        if os.name == 'posix' and path.parent.stat().st_mode & 0o077:
            return None, 'KEY_PARENT_PERMISSIONS_INVALID'
    return path, None


def _key_status(config, backup_roots):
    _, issue = _key_location(config, backup_roots)
    if issue: return issue
    from app import emergency_vault as vault
    try:
        vault._key()
        return 'READY'
    except vault.VaultError as failure:
        allowed = {'KEY_NOT_CONFIGURED', 'KEY_LOCATION_INVALID', 'KEY_INVALID', 'KEY_PERMISSIONS_INVALID'}
        return failure.code if failure.code in allowed else 'PRIVATE_STORAGE_UNAVAILABLE'


def _temporary_status():
    try:
        # tempfile.gettempdir() can create probe files during discovery. Inspect
        # the declared Linux location without writing anything instead.
        location = Path(os.environ.get('TMPDIR') or os.environ.get('TEMP') or os.environ.get('TMP') or '/tmp').resolve()
        if not location.is_dir() or not os.access(location, os.W_OK | os.X_OK):
            return 'DISK_BACKED_OR_UNKNOWN'
        matches = []
        for line in Path('/proc/self/mountinfo').read_text().splitlines():
            parts = line.split(); divider = parts.index('-')
            mount = Path(re.sub(r'\\([0-7]{3})', lambda item: chr(int(item.group(1), 8)), parts[4]))
            if location == mount or mount in location.parents:
                matches.append((len(str(mount)), parts[divider+1]))
        filesystem = max(matches)[1] if matches else None
        return 'MEMORY_BACKED' if filesystem in {'tmpfs', 'ramfs'} else 'DISK_BACKED_OR_UNKNOWN'
    except Exception:
        return 'DISK_BACKED_OR_UNKNOWN'


def check_host(*, manifest_path=None, backup_roots=()):
    config = _config()
    language = config.emergency_audit_ocr_language
    valid_language = (isinstance(language, str) and len(language) <= 64 and 'jpn' in language.split('+')
                      and all(LANGUAGE.fullmatch(item) for item in language.split('+')))
    required = sorted(set(language.split('+'))) if valid_language else []
    platform = 'SUPPORTED' if SUPPORTED_PLATFORM else 'PROCESS_PLATFORM_UNSUPPORTED'
    native = (_native_status(manifest_path, required) if SUPPORTED_PLATFORM and valid_language
              else 'OCR_LANGUAGE_INVALID' if not valid_language else 'NOT_CHECKED')
    key = _key_status(config, backup_roots)
    temporary = _temporary_status()
    ready = platform == 'SUPPORTED' and native == 'VERIFIED' and key == 'READY' and temporary == 'MEMORY_BACKED' and config.emergency_audit_enabled
    return {'schema_version': 1, 'ready_for_reader': ready, 'production_accepted': False,
            'platform': {'status': platform}, 'native': {'status': native, 'required_languages': required},
            'private_storage': {'status': key}, 'temporary_storage': {'status': temporary},
            'optional_ai': {'status': 'CONFIGURED_NOT_VERIFIED' if config.emergency_audit_ai_model else 'NOT_CONFIGURED'},
            'gpu': {'status': 'NOT_ASSESSED', 'required_for_reader': False},
            'runtime': {'audit_enabled': config.emergency_audit_enabled,
                        'internal_data_enabled': config.emergency_audit_internal_enabled,
                        'database_worker_and_tenant': 'NOT_CHECKED'}}


def initialize_key(*, backup_roots=()):
    config = _config(); created = False; path = None
    try:
        path, issue = _key_location(config, backup_roots, creating=True)
        if issue: return {'schema_version': 1, 'status': issue, 'created': False}
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        created = True
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(os.urandom(32)); stream.flush(); os.fsync(stream.fileno())
        return {'schema_version': 1, 'status': 'KEY_CREATED', 'created': True}
    except FileExistsError:
        return {'schema_version': 1, 'status': 'KEY_ALREADY_EXISTS', 'created': False}
    except Exception:
        if created and path is not None:
            try: path.unlink()
            except OSError: pass
        return {'schema_version': 1, 'status': 'KEY_CREATION_FAILED', 'created': False}


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError()


def main(argv=None):
    try:
        parser = SafeParser(description='Private audit host readiness; does not download software or models')
        parser.add_argument('--manifest', type=Path, default=os.environ.get('FIRE_AI_EMERGENCY_AUDIT_NATIVE_MANIFEST') or None)
        parser.add_argument('--backup-root', action='append', type=Path, default=[])
        parser.add_argument('--initialize-key', action='store_true', help='Explicitly create one absent configured key, never overwrite')
        args = parser.parse_args(argv)
        if args.initialize_key:
            result = initialize_key(backup_roots=args.backup_root)
            ok = result['created']
        else:
            result = check_host(manifest_path=args.manifest, backup_roots=args.backup_root)
            ok = result['ready_for_reader']
    except Exception:
        result = {'schema_version': 1, 'status': 'HOST_CHECK_FAILED', 'ready_for_reader': False, 'production_accepted': False}
        ok = False
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if ok else 2


if __name__ == '__main__':
    raise SystemExit(main())
