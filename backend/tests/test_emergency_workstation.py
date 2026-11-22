"""Contract tests for the portable, read-only workstation diagnostic.

Windows is simulated at its process boundary. Child-process limits and the
fixed-loopback HTTP client are exercised with real processes/sockets.
"""
import importlib.util
import ctypes
import json
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'check_emergency_workstation.py'
SECRET = 'PRIVATE_SENTINEL_token=/private/user/report.pdf'


def load_script():
    assert SCRIPT.is_file(), 'The standalone diagnostic is not implemented yet'
    spec = importlib.util.spec_from_file_location('workstation_diagnostic', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def windows_fixture(monkeypatch, module, *, system=None, vm=None, gpu=None, tags=None):
    """Only replace external system data; keep parsing/validation/assembly real."""
    system = system if system is not None else {
        'status': 'OK', 'os_version': '10.0.26100', 'cpu_count': 16,
        'ram_total_bytes': 34359738368, 'ram_free_bytes': 17179869184,
        'fixed_disks': [{'total_bytes': 1000000000000, 'free_bytes': 300000000000,
                         'DeviceID': SECRET}], 'hostname': SECRET,
    }
    vm = vm if vm is not None else {'status': 'OK', 'guests': [{
        'state': 'Running', 'cpu_count': 8, 'memory_startup_bytes': 8589934592,
        'memory_assigned_bytes': 8589934592, 'name': SECRET, 'id': SECRET,
    }]}
    gpu = gpu if gpu is not None else b'NVIDIA RTX A2000 Laptop GPU, 4096, 3072, 572.83\n'
    tags = tags if tags is not None else {'models': [{'name': 'local-model:7b', 'details': SECRET}]}
    monkeypatch.setattr(module.platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(module.shutil, 'which', lambda name: '/private/installed/' + name)

    def run(command, **_):
        executable = Path(command[0]).name
        if command[0] == sys.executable:
            assert command[1:5] == ['-I', '-S', '-B', '-c']
            assert len(command) == 6
            return module.Probe('OK', json.dumps(system).encode())
        if executable == 'powershell.exe':
            assert command[1:3] == ['-NoProfile', '-NonInteractive']
            assert command[3] == '-Command'
            statement = command[4]
            if 'Get-VM' in statement:
                return module.Probe('OK', json.dumps(vm).encode())
            if 'Get-NetTCPConnection' in statement:
                return module.Probe('OK', b'{"status":"OK","8787":true,"8796":false,"8797":true,"11434":false}')
            pytest.fail('An unexpected PowerShell operation was requested')
        if executable == 'nvidia-smi':
            assert command[1:] == ['--query-gpu=name,memory.total,memory.free,driver_version',
                                   '--format=csv,noheader,nounits']
            return module.Probe('OK', gpu)
        if executable == 'tesseract':
            if command[1:] == ['--version']:
                return module.Probe('OK', b'tesseract 5.3.0\nprivate-library-path\n')
            if command[1:] == ['--list-langs']:
                return module.Probe('OK', ('List of available languages in "' + SECRET + '" (3):\neng\njpn\nosd\n').encode())
        pytest.fail('An unexpected executable or operation was requested')

    monkeypatch.setattr(module, '_run_command', run)
    monkeypatch.setattr(module, '_read_ollama_tags', lambda **_: module.Probe('OK', json.dumps(tags).encode()))


def test_windows_results_are_anonymous_and_do_not_claim_device_acceptance(monkeypatch):
    module = load_script()
    windows_fixture(monkeypatch, module)
    report = module.inspect_workstation(requested_model='local-model:7b')
    assert report['os'] == {'family': 'WINDOWS', 'version': '10.0.26100', 'status': 'OK',
                            'version_basis': 'WINDOWS_KERNEL32_VERSION'}
    assert report['cpu']['logical_count'] == 16
    assert report['ram'] == {'status': 'OK', 'total_bytes': 34359738368, 'free_bytes': 17179869184}
    assert report['storage']['volumes'] == [{'total_bytes': 1000000000000, 'free_bytes': 300000000000}]
    assert report['gpu']['devices'] == [{'name': 'NVIDIA RTX A2000 Laptop GPU',
                                       'total_vram_mib': 4096, 'free_vram_mib': 3072,
                                       'driver_version': '572.83'}]
    assert report['hyperv'] == {'status': 'OK', 'guests': [{'state': 'RUNNING',
                               'cpu_count': 8, 'memory_startup_bytes': 8589934592,
                               'memory_assigned_bytes': 8589934592}]}
    assert report['ports']['8787'] == {'status': 'OK', 'listening': True}
    assert report['native_ocr']['languages']['jpn'] is True
    assert report['local_model'] == {'status': 'OK', 'model_count': 1, 'requested_model_present': True}
    assert report['execution_context'] == 'CURRENT_DEVICE_UNCONFIRMED'
    assert report['acceptance'] == {'workstation_verified': False, 'accuracy_measured': False,
                                    'production_accepted': False}
    assert report['reader_platform_supported'] is False
    rendered = json.dumps(report)
    for forbidden in (SECRET, 'private', 'local-model', '127.0.0.1'):
        assert forbidden not in rendered


def test_vm_permission_failure_remains_unknown_instead_of_absent(monkeypatch):
    module = load_script()
    windows_fixture(monkeypatch, module, vm={'status': 'ACCESS_DENIED', 'error': SECRET, 'guests': []})
    report = module.inspect_workstation()
    assert report['hyperv'] == {'status': 'ACCESS_DENIED', 'guests': None}
    assert SECRET not in json.dumps(report)


@pytest.mark.parametrize('bad_value', [True, '16', -1, 1000000000, None, {'secret': SECRET}])
def test_invalid_windows_resource_types_do_not_become_measured_values(monkeypatch, bad_value):
    module = load_script()
    windows_fixture(monkeypatch, module, system={
        'status': 'OK', 'os_version': '10.0.26100', 'cpu_count': bad_value,
        'ram_total_bytes': 1024, 'ram_free_bytes': 512, 'fixed_disks': [],
    })
    report = module.inspect_workstation()
    assert report['cpu'] == {'status': 'INVALID_DATA', 'logical_count': None}
    assert SECRET not in json.dumps(report)


@pytest.mark.parametrize('payload', [
    {'status': 'OK', 'os_version': SECRET, 'cpu_count': 8, 'ram_total_bytes': 2, 'ram_free_bytes': 3, 'fixed_disks': []},
    {'status': 'OK', 'os_version': ['10.0'], 'cpu_count': 8, 'ram_total_bytes': True, 'ram_free_bytes': 1, 'fixed_disks': [SECRET]},
])
def test_invalid_os_ram_and_storage_data_are_rejected_without_echo(monkeypatch, payload):
    module = load_script()
    windows_fixture(monkeypatch, module, system=payload)
    report = module.inspect_workstation()
    assert report['os']['status'] == 'INVALID_DATA'
    assert report['os']['version'] is None
    assert report['ram']['status'] == 'INVALID_DATA'
    assert report['storage']['status'] == 'INVALID_DATA'
    assert SECRET not in json.dumps(report)


@pytest.mark.parametrize('gpu', [
    ('NVIDIA RTX A2000 ' + SECRET + ', 4096, 3072, 572.83\n').encode(),
    ('NVIDIA RTX A2000, 4096, 8192, ' + SECRET + '\n').encode(),
    b'NVIDIA RTX A2000, True, 3072, 572.83\n',
])
def test_gpu_untrusted_values_are_not_reflected(monkeypatch, gpu):
    module = load_script()
    windows_fixture(monkeypatch, module, gpu=gpu)
    result = module.inspect_workstation()['gpu']
    assert result == {'status': 'INVALID_DATA', 'devices': []}
    assert SECRET not in json.dumps(result)


@pytest.mark.parametrize('status', ['TIMEOUT', 'OUTPUT_LIMIT', 'ACCESS_DENIED', 'PRIVATE_ERROR_' + SECRET])
def test_failed_native_probes_expose_only_fixed_error_codes(monkeypatch, status):
    module = load_script()
    windows_fixture(monkeypatch, module)
    monkeypatch.setattr(module, '_run_command', lambda *_, **__: module.Probe(status, SECRET.encode()))
    report = module.inspect_workstation()
    expected = status if status != 'PRIVATE_ERROR_' + SECRET else 'PROBE_FAILED'
    assert report['gpu'] == {'status': expected, 'devices': []}
    assert report['hyperv']['guests'] is None
    assert SECRET not in json.dumps(report)


def test_subprocess_timeout_reaps_the_spawned_process(monkeypatch):
    module = load_script()
    processes = []
    real_popen = module.subprocess.Popen

    def spawn(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(module.subprocess, 'Popen', spawn)
    started = time.monotonic()
    result = module._run_command([sys.executable, '-c', 'import time; time.sleep(30)'],
                                 timeout=0.1, max_output=1024)
    assert result == module.Probe('TIMEOUT', b'')
    assert time.monotonic() - started < 2
    assert processes[0].poll() is not None


def test_subprocess_output_limit_stops_the_writer_without_retaining_output():
    module = load_script()
    started = time.monotonic()
    result = module._run_command([sys.executable, '-c',
                                 'import os; chunk=b"x"*65536\nwhile True: os.write(1, chunk)'],
                                timeout=2, max_output=1024)
    assert result == module.Probe('OUTPUT_LIMIT', b'')
    assert time.monotonic() - started < 2


def test_windows_probes_allow_cold_powershell_startup_without_extending_native_budgets(monkeypatch):
    module = load_script()
    windows_fixture(monkeypatch, module)
    original = module._run_command
    native_budgets = []

    def slow_powershell(command, *, timeout=5.0, **kwargs):
        if Path(command[0]).name == 'powershell.exe':
            # A cold, successful PowerShell/CIM probe can exceed the native
            # tools' five-second budget. It still needs a finite upper bound.
            assert 0 < timeout <= 30
            if timeout < 6:
                return module.Probe('TIMEOUT', SECRET.encode())
        else:
            native_budgets.append(timeout)
        return original(command, timeout=timeout, **kwargs)

    monkeypatch.setattr(module, '_run_command', slow_powershell)
    report = module.inspect_workstation()
    assert report['os']['status'] == 'OK'
    assert report['cpu']['logical_count'] == 16
    assert report['ram']['total_bytes'] == 34359738368
    assert report['storage']['status'] == 'OK'
    assert report['hyperv']['status'] == 'OK'
    assert report['ports']['8787'] == {'status': 'OK', 'listening': True}
    assert native_budgets == [5.0, 5.0, 5.0, 5.0]
    assert SECRET not in json.dumps(report)


def test_powershell_deadline_still_terminates_child_and_discards_partial_output(monkeypatch):
    module = load_script()
    original = module._run_command
    monkeypatch.setattr(module, 'POWERSHELL_TIMEOUT', 0.05, raising=False)

    def stalled_powershell(command, *, timeout=5.0, **kwargs):
        assert Path(command[0]).name == 'powershell.exe'
        return original([sys.executable, '-c',
                         'import time; print("PRIVATE_PARTIAL_OUTPUT", flush=True); time.sleep(30)'],
                        timeout=timeout, **kwargs)

    monkeypatch.setattr(module, '_run_command', stalled_powershell)
    started = time.monotonic()
    status, value = module._powershell("@{status='OK'}|ConvertTo-Json -Compress")
    assert (status, value) == ('TIMEOUT', None)
    assert time.monotonic() - started < 1


@pytest.mark.parametrize('tags', [
    {'models': SECRET}, {'models': [SECRET]}, {'models': [{'name': True}]},
    {'models': [{'name': 'x' * 10000}]}, {'models': [] , 'unused': SECRET},
])
def test_local_model_response_has_strict_types_and_never_echoes_names(monkeypatch, tags):
    module = load_script()
    windows_fixture(monkeypatch, module, tags=tags)
    result = module.inspect_workstation()['local_model']
    expected = 'OK' if tags['models'] == [] else 'INVALID_DATA'
    assert result['status'] == expected
    assert result['model_count'] == (0 if expected == 'OK' else None)
    assert result['requested_model_present'] is None
    assert SECRET not in json.dumps(result)


def test_cli_invalid_arguments_are_json_and_do_not_echo_secrets(capsys):
    module = load_script()
    assert module.main(['--context', SECRET]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {'schema_version': 1, 'diagnostic_status': 'INVALID_ARGUMENT'}
    assert captured.err == ''
    assert SECRET not in captured.out


@contextmanager
def local_tags_server(module, monkeypatch, *, body=b'{"models":[]}', status=200, drip_headers=False):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            requests.append((self.command, self.path))
            try:
                if drip_headers:
                    for byte in b'HTTP/1.1 200 OK\r\nContent-Length: 13\r\n\r\n{"models":[]}':
                        self.connection.sendall(bytes([byte]))
                        threading.Event().wait(0.02)
                    return
                self.send_response(status)
                self.send_header('Content-Length', str(len(body)))
                if status == 302:
                    self.send_header('Location', 'http://external.invalid/' + SECRET)
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
    worker.start()
    original_connection = module.http.client.HTTPConnection

    def connection(host, port, **kwargs):
        # An altered product endpoint is a regression, even though the test
        # isolates its listener on an ephemeral port.
        assert (host, port) == ('127.0.0.1', 11434)
        return original_connection('127.0.0.1', server.server_port, **kwargs)

    monkeypatch.setattr(module.http.client, 'HTTPConnection', connection)
    try:
        yield requests
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=1)


def test_model_list_uses_only_fixed_loopback_get_and_ignores_proxy(monkeypatch):
    module = load_script()
    monkeypatch.setenv('http_proxy', 'http://unreachable.invalid:1/' + SECRET)
    monkeypatch.setenv('HTTP_PROXY', 'http://unreachable.invalid:1/' + SECRET)
    with local_tags_server(module, monkeypatch) as requests:
        result = module._read_ollama_tags(timeout=1, max_output=1024)
    assert result == module.Probe('OK', b'{"models":[]}')
    assert requests == [('GET', '/api/tags')]


def test_model_list_redirect_is_rejected_without_following_or_exposing_it(monkeypatch):
    module = load_script()
    with local_tags_server(module, monkeypatch, status=302, body=SECRET.encode()) as requests:
        result = module._read_ollama_tags(timeout=1, max_output=1024)
    assert result == module.Probe('REDIRECT_BLOCKED', b'')
    assert requests == [('GET', '/api/tags')]


def test_model_list_response_limit_rejects_the_body_during_download(monkeypatch):
    module = load_script()
    with local_tags_server(module, monkeypatch, body=b'x' * 4096):
        result = module._read_ollama_tags(timeout=1, max_output=1024)
    assert result == module.Probe('OUTPUT_LIMIT', b'')


def test_model_list_total_deadline_stops_a_slow_header_stream(monkeypatch):
    module = load_script()
    started = time.monotonic()
    with local_tags_server(module, monkeypatch, drip_headers=True):
        result = module._read_ollama_tags(timeout=0.1, max_output=1024)
    assert result == module.Probe('TIMEOUT', b'')
    assert time.monotonic() - started < 1


def linux_fixture(monkeypatch, module, *, meminfo=None, tcp=None):
    windows_fixture(monkeypatch, module)
    monkeypatch.setattr(module.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(module.platform, 'release', lambda: '6.8.0-' + SECRET)
    monkeypatch.setattr(module.os, 'cpu_count', lambda: 8)
    monkeypatch.setattr(module.os, 'statvfs', lambda _: type('Disk', (), {'f_blocks': 1000, 'f_frsize': 4096, 'f_bavail': 250})())
    meminfo = meminfo if meminfo is not None else b'MemTotal: 8388608 kB\nMemFree: 2097152 kB\nMemAvailable: 4194304 kB\n'
    tcp = tcp if tcp is not None else (
        b'  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt uid timeout inode\n'
        b'   0: 0100007F:2253 00000000:0000 0A 00000000:00000000 00:00000000 00000000 1000 0 1\n'
        b'   1: 0100007F:225C 00000000:0000 01 00000000:00000000 00:00000000 00000000 1000 0 2\n'
    )

    def read_file(path, **_):
        values = {'/proc/meminfo': meminfo, '/proc/net/tcp': tcp,
                  '/proc/net/tcp6': b'  sl  local_address rem_address   st\n'}
        assert str(path) in values, 'The diagnostic attempted to read an unexpected file'
        return module.Probe('OK', values[str(path)])

    monkeypatch.setattr(module, '_read_file', read_file)


def test_linux_guest_resources_and_listening_flags_are_anonymous(monkeypatch):
    module = load_script()
    linux_fixture(monkeypatch, module)
    result = module.inspect_workstation(context='cloud')
    assert result['execution_context'] == 'CLOUD'
    assert result['os'] == {'family': 'LINUX', 'version': '6.8.0', 'status': 'OK'}
    assert result['cpu'] == {'status': 'OK', 'logical_count': 8}
    assert result['ram'] == {'status': 'OK', 'total_bytes': 8589934592, 'free_bytes': 2147483648}
    assert result['storage'] == {'status': 'OK', 'scope': 'ROOT_FILESYSTEM',
                                  'volumes': [{'total_bytes': 4096000, 'free_bytes': 1024000}]}
    assert result['ports']['8787'] == {'status': 'OK', 'listening': True}
    assert result['ports']['8796'] == {'status': 'OK', 'listening': False}
    assert result['reader_platform_supported'] is True
    assert result['hyperv']['guests'] is None
    assert result['wsl']['status'] == 'NOT_APPLICABLE'
    for forbidden in (SECRET, '/proc', '0100007F', '1000 0', '127.0.0.1'):
        assert forbidden not in json.dumps(result)


def test_missing_linux_memory_does_not_become_zero_memory(monkeypatch):
    module = load_script()
    linux_fixture(monkeypatch, module, meminfo=b'Other: 1024 kB\n')
    result = module.inspect_workstation()['ram']
    assert result == {'status': 'INVALID_DATA', 'total_bytes': None, 'free_bytes': None}


def test_malformed_linux_listener_table_cannot_report_ports_as_free(monkeypatch):
    module = load_script()
    linux_fixture(monkeypatch, module, tcp=SECRET.encode())
    result = module.inspect_workstation()['ports']
    assert all(entry == {'status': 'INVALID_DATA', 'listening': None} for entry in result.values())


def test_local_file_reads_are_capped_without_returning_partial_data(tmp_path):
    module = load_script()
    source = tmp_path / 'synthetic.txt'
    source.write_bytes(b'x' * 4096)
    assert module._read_file(source, max_output=1024) == module.Probe('OUTPUT_LIMIT', b'')


def test_nonzero_subprocess_drops_both_stdout_and_secret_stderr():
    module = load_script()
    result = module._run_command([sys.executable, '-c',
                                 'import sys; print("private stdout"); print("private stderr", file=sys.stderr); sys.exit(9)'])
    assert result == module.Probe('PROBE_FAILED', b'')


def test_cli_fails_closed_without_an_exception_stack(monkeypatch, capsys):
    module = load_script()

    def failed(**_):
        raise RuntimeError(SECRET)

    monkeypatch.setattr(module, 'inspect_workstation', failed)
    assert module.main([]) == 1
    output = capsys.readouterr()
    assert json.loads(output.out) == {'schema_version': 1, 'diagnostic_status': 'PROBE_FAILED'}
    assert output.err == ''


def test_successful_empty_hyperv_inventory_is_distinct_from_unknown(monkeypatch):
    module = load_script()
    windows_fixture(monkeypatch, module, vm={'status': 'OK', 'guests': []})
    assert module.inspect_workstation()['hyperv'] == {'status': 'OK', 'guests': []}


def test_oversized_hyperv_inventory_does_not_emit_a_partial_success(monkeypatch):
    module = load_script()
    guest = {'state': 'Running', 'cpu_count': 4, 'memory_startup_bytes': 4096,
             'memory_assigned_bytes': 4096, 'name': SECRET}
    windows_fixture(monkeypatch, module, vm={'status': 'OK', 'guests': [guest] * 17})
    assert module.inspect_workstation()['hyperv'] == {'status': 'OUTPUT_LIMIT', 'guests': None}


@pytest.mark.parametrize('guest', [SECRET, {'state': SECRET}, {
    'state': 'Running', 'cpu_count': True, 'memory_startup_bytes': 4096,
    'memory_assigned_bytes': 4096, 'name': SECRET,
}])
def test_malformed_hyperv_guest_does_not_leak_or_become_absence(monkeypatch, guest):
    module = load_script()
    windows_fixture(monkeypatch, module, vm={'status': 'OK', 'guests': [guest]})
    assert module.inspect_workstation()['hyperv'] == {'status': 'INVALID_DATA', 'guests': None}


def native_windows_payload(module, monkeypatch, capsys, *, failure=None, error=5):
    """Execute the exact child source with only Win32 API boundaries replaced."""
    def memory(pointer):
        assert ctypes.sizeof(pointer._obj) == 64
        assert pointer._obj.dwLength == 64
        if failure == 'memory':
            return 0
        pointer._obj.ullTotalPhys = 34359738368
        pointer._obj.ullAvailPhys = 17179869184
        return 1

    def drives():
        return 0 if failure == 'drives' else (1 << 2) | (1 << 3) | (1 << 25)

    def drive_type(root):
        return {'C:\\': 3, 'D:\\': 5, 'Z:\\': 4}[root]

    def disk(root, available, total, total_free):
        # Never query a remote or removable volume's capacity.
        assert root == 'C:\\'
        if failure == 'disk':
            return 0
        available._obj.value = 17179869184
        total._obj.value = 42949672960
        total_free._obj.value = 80000000000
        return 1

    api = SimpleNamespace(GlobalMemoryStatusEx=memory, GetLogicalDrives=drives,
                          GetDriveTypeW=drive_type, GetDiskFreeSpaceExW=disk)
    monkeypatch.setattr(ctypes, 'WinDLL', lambda name, **kwargs: api, raising=False)
    monkeypatch.setattr(ctypes, 'get_last_error', lambda: error, raising=False)
    monkeypatch.setattr(sys, 'getwindowsversion', lambda: SimpleNamespace(platform_version=(10, 0, 26100)), raising=False)
    monkeypatch.setattr(module.os, 'cpu_count', lambda: 16)
    source = getattr(module, 'WINDOWS_SYSTEM_CODE', None)
    assert source is not None, 'The native Windows child is not implemented'
    exec(compile(source, '<fixed-native-probe>', 'exec'), {})
    output = capsys.readouterr()
    assert output.err == ''
    return json.loads(output.out)


def test_native_windows_child_uses_64bit_anonymous_caller_capacity(monkeypatch, capsys):
    module = load_script()
    payload = native_windows_payload(module, monkeypatch, capsys)
    assert payload == {'status': 'OK', 'os_version': '10.0.26100', 'cpu_count': 16,
                       'ram_total_bytes': 34359738368, 'ram_free_bytes': 17179869184,
                       'fixed_disks': [{'total_bytes': 42949672960, 'free_bytes': 17179869184}]}
    for forbidden in ('C:', 'D:', 'Z:', SECRET):
        assert forbidden not in json.dumps(payload)


@pytest.mark.parametrize('failure', ['memory', 'drives', 'disk'])
@pytest.mark.parametrize('error, expected', [(5, 'ACCESS_DENIED'), (87, 'PROBE_FAILED')])
def test_native_windows_api_failure_remains_unknown(monkeypatch, capsys, failure, error, expected):
    module = load_script()
    payload = native_windows_payload(module, monkeypatch, capsys, failure=failure, error=error)
    assert payload == {'status': expected}


def test_native_windows_child_deadline_discards_partial_output(monkeypatch):
    module = load_script()
    original = module._run_command

    def stalled_child(command, *, timeout=5.0, **kwargs):
        assert command[:5] == [sys.executable, '-I', '-S', '-B', '-c']
        assert 0 < timeout <= 5
        return original([sys.executable, '-I', '-S', '-B', '-c',
                         'import time; print("PRIVATE_PARTIAL_OUTPUT", flush=True); time.sleep(30)'],
                        timeout=0.05, **kwargs)

    monkeypatch.setattr(module, '_run_command', stalled_child)
    started = time.monotonic()
    report = module._windows_system()
    assert report['os']['status'] == 'TIMEOUT'
    assert report['os']['version'] is None
    assert report['storage']['volumes'] == []
    assert 'PRIVATE_PARTIAL_OUTPUT' not in json.dumps(report)
    assert time.monotonic() - started < 1
