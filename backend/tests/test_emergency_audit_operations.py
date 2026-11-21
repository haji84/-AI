"""Host checks are read-only; key creation is explicit, private and create-only."""
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import stat

import pytest


def operations():
    path = Path(__file__).resolve().parents[2] / 'scripts' / 'check_emergency_audit_host.py'
    spec = importlib.util.spec_from_file_location('synthetic_emergency_operations', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


@pytest.fixture
def host(tmp_path, monkeypatch):
    from app.settings import settings
    monkeypatch.setattr(settings, 'emergency_audit_enabled', True)
    monkeypatch.setattr(settings, 'emergency_audit_internal_enabled', False)
    monkeypatch.setattr(settings, 'emergency_audit_ai_model', None)
    monkeypatch.setattr(settings, 'emergency_audit_ocr_language', 'jpn+eng')
    monkeypatch.setattr(settings, 'storage_root', str(tmp_path / 'storage'))
    key_dir = tmp_path / 'keys'; key_dir.mkdir(mode=0o700)
    key = key_dir / 'audit.key'; monkeypatch.setattr(settings, 'emergency_audit_key_file', str(key))
    native = tmp_path / 'native'; native.mkdir()
    binary = native / 'tesseract'; binary.write_bytes(b'synthetic-approved-executable')
    tessdata = native / 'tessdata'; tessdata.mkdir()
    (tessdata / 'jpn.traineddata').write_bytes(b'synthetic-jpn-model')
    (tessdata / 'eng.traineddata').write_bytes(b'synthetic-eng-model')
    manifest = {'schema_version': 1, 'tesseract': {'version': '5.4.1',
        'executable_sha256': sha256(binary.read_bytes()).hexdigest(),
        'traineddata': {'jpn': sha256(b'synthetic-jpn-model').hexdigest(), 'eng': sha256(b'synthetic-eng-model').hexdigest()}}}
    manifest_file = tmp_path / 'approved-native.json'; manifest_file.write_text(json.dumps(manifest)); manifest_file.chmod(0o600)
    return {'root': tmp_path, 'key': key, 'binary': binary, 'data': tessdata,
            'manifest': manifest, 'manifest_file': manifest_file, 'settings': settings}


def prepared(host, monkeypatch):
    module = operations()
    monkeypatch.setattr(module.shutil, 'which', lambda name: str(host['binary']))
    def native(command):
        if command[-1] == '--version': return 'tesseract 5.4.1\nSynthetic build information'
        return f'List of available languages in "{host["data"]}" (2):\neng\njpn\n'
    monkeypatch.setattr(module, '_run_native', native)
    monkeypatch.setattr(module, '_temporary_status', lambda: 'MEMORY_BACKED')
    return module


def test_missing_manifest_does_not_create_key_or_write_files(host):
    module = operations(); before = set(host['root'].rglob('*'))
    result = module.check_host()
    assert result['native']['status'] == 'MANIFEST_REQUIRED'
    assert result['ready_for_reader'] is False and result['production_accepted'] is False
    assert result['optional_ai']['status'] == 'NOT_CONFIGURED'
    assert not host['key'].exists() and set(host['root'].rglob('*')) == before
    assert str(host['root']) not in json.dumps(result)


def test_pinned_native_version_executable_and_language_files_are_all_checked(host, monkeypatch):
    module = prepared(host, monkeypatch)
    assert module.initialize_key()['status'] == 'KEY_CREATED'
    before = {str(path.relative_to(host['root'])): path.read_bytes() for path in host['root'].rglob('*') if path.is_file()}
    result = module.check_host(manifest_path=host['manifest_file'])
    assert result['native']['status'] == 'VERIFIED'
    assert result['native']['required_languages'] == ['eng', 'jpn']
    assert result['ready_for_reader'] is True and result['production_accepted'] is False
    after = {str(path.relative_to(host['root'])): path.read_bytes() for path in host['root'].rglob('*') if path.is_file()}
    assert before == after
    assert str(host['root']) not in json.dumps(result)


@pytest.mark.parametrize('change,want', [
    ('version', 'NATIVE_VERSION_MISMATCH'), ('binary', 'NATIVE_EXECUTABLE_MISMATCH'),
    ('model', 'NATIVE_LANGUAGE_MISMATCH'), ('missing_language', 'OCR_LANGUAGE_UNAVAILABLE'),
])
def test_native_mismatch_cannot_report_ready(host, monkeypatch, change, want):
    module = prepared(host, monkeypatch); module.initialize_key()
    if change == 'version':
        host['manifest']['tesseract']['version'] = '9.9.9'
        host['manifest_file'].write_text(json.dumps(host['manifest']))
    elif change == 'binary': host['binary'].write_bytes(b'changed synthetic executable')
    elif change == 'model': (host['data'] / 'jpn.traineddata').write_bytes(b'changed synthetic language')
    else:
        monkeypatch.setattr(module, '_run_native', lambda command: 'tesseract 5.4.1\n' if command[-1] == '--version'
            else f'List of available languages in "{host["data"]}" (1):\neng\n')
    result = module.check_host(manifest_path=host['manifest_file'])
    assert result['native']['status'] == want and result['ready_for_reader'] is False


def test_malformed_manifest_or_native_failure_is_sanitized(host, monkeypatch):
    module = prepared(host, monkeypatch)
    host['manifest_file'].write_text('{"synthetic-private-sentinel":')
    result = module.check_host(manifest_path=host['manifest_file'])
    assert result['native']['status'] == 'NATIVE_MANIFEST_INVALID'
    assert 'synthetic-private-sentinel' not in json.dumps(result)


def test_key_creation_never_overwrites_existing_bytes_and_never_prints_secret(host, capsys):
    module = operations()
    assert module.main(['--initialize-key']) == 0
    first = host['key'].read_bytes()
    assert len(first) == 32 and stat.S_IMODE(host['key'].stat().st_mode) == 0o600
    output = capsys.readouterr().out
    assert first.hex() not in output and str(host['key']) not in output
    assert module.main(['--initialize-key']) == 2
    assert json.loads(capsys.readouterr().out)['status'] == 'KEY_ALREADY_EXISTS'
    assert host['key'].read_bytes() == first


@pytest.mark.parametrize('location', ['storage', 'backup', 'symlink', 'relative', 'shared_parent'])
def test_key_cannot_be_created_in_unprotected_or_backup_locations(host, monkeypatch, location):
    module = operations(); target = host['key']
    backup = host['root'] / 'backup'; backup.mkdir(mode=0o700)
    if location == 'storage':
        parent = Path(host['settings'].storage_root); parent.mkdir(mode=0o700); target = parent / 'bad.key'
    elif location == 'backup': target = backup / 'bad.key'
    elif location == 'symlink':
        real = host['root'] / 'real.key'; real.write_bytes(b'unchanged'); target.symlink_to(real)
    elif location == 'relative': target = Path('relative.key')
    elif location == 'shared_parent': host['key'].parent.chmod(0o755)
    monkeypatch.setattr(host['settings'], 'emergency_audit_key_file', str(target))
    result = module.initialize_key(backup_roots=[backup])
    assert result['status'] in {'KEY_LOCATION_INVALID', 'KEY_PATH_INVALID', 'KEY_ALREADY_EXISTS', 'KEY_PARENT_PERMISSIONS_INVALID'}
    if location == 'symlink': assert real.read_bytes() == b'unchanged'
    else: assert not target.exists()


def test_exposed_key_or_disk_temporary_directory_blocks_reader_readiness(host, monkeypatch):
    module = prepared(host, monkeypatch); module.initialize_key(); host['key'].chmod(0o644)
    result = module.check_host(manifest_path=host['manifest_file'])
    assert result['private_storage']['status'] == 'KEY_PERMISSIONS_INVALID'
    assert result['ready_for_reader'] is False
    host['key'].chmod(0o600); monkeypatch.setattr(module, '_temporary_status', lambda: 'DISK_BACKED_OR_UNKNOWN')
    result = module.check_host(manifest_path=host['manifest_file'])
    assert result['temporary_storage']['status'] == 'DISK_BACKED_OR_UNKNOWN'
    assert result['ready_for_reader'] is False


def test_optional_configured_model_is_not_claimed_running_or_accurate(host, monkeypatch):
    module = prepared(host, monkeypatch)
    monkeypatch.setattr(host['settings'], 'emergency_audit_ai_model', 'synthetic-model')
    result = module.check_host(manifest_path=host['manifest_file'])
    assert result['optional_ai']['status'] == 'CONFIGURED_NOT_VERIFIED'
    assert result['gpu']['status'] == 'NOT_ASSESSED'
    assert result['production_accepted'] is False


def test_cli_configuration_exception_does_not_echo_environment_or_paths(host, monkeypatch, capsys):
    module = operations()
    def invalid(): raise ValueError('synthetic-private-configuration')
    monkeypatch.setattr(module, '_config', invalid)
    assert module.main([]) == 2
    output = capsys.readouterr()
    assert json.loads(output.out)['status'] == 'HOST_CHECK_FAILED'
    assert 'synthetic-private-configuration' not in output.out + output.err


def test_japanese_host_check_cannot_be_satisfied_by_english_only_configuration(host, monkeypatch):
    module = prepared(host, monkeypatch)
    monkeypatch.setattr(host['settings'], 'emergency_audit_ocr_language', 'eng')
    result = module.check_host(manifest_path=host['manifest_file'])
    assert result['native']['status'] == 'OCR_LANGUAGE_INVALID'
    assert result['ready_for_reader'] is False


def test_temporary_location_check_does_not_probe_by_writing_files(monkeypatch):
    import tempfile
    if not Path('/dev/shm').is_dir(): pytest.skip('Linux shared-memory mount unavailable')
    module = operations()
    monkeypatch.setenv('TMPDIR', '/dev/shm')
    def writes(): raise AssertionError('tempfile default discovery can create probe files')
    monkeypatch.setattr(tempfile, 'gettempdir', writes)
    assert module._temporary_status() == 'MEMORY_BACKED'
