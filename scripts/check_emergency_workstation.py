r"""Portable, read-only workstation facts; no installation or acceptance claim.

Run on the device to inspect: py -3 .\check_emergency_workstation.py
An optional --context labels where the operator ran it; it is not verification.
Only a fixed local model-list GET is allowed. No document, database, key,
service, VM or WSL lifecycle operation is performed. Requires Python 3.9+;
the application reader itself still requires Python 3.11+ and Linux.
"""
import sys

sys.dont_write_bytecode = True

import argparse
import csv
import http.client
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import socket
import subprocess
import threading
import time
from typing import NamedTuple


COMMAND_TIMEOUT = 5.0
# Windows PowerShell startup and CIM/module initialization need their own
# bounded budget. Native tools retain the shorter five-second deadline.
POWERSHELL_TIMEOUT = 30.0
COMMAND_OUTPUT_LIMIT = 65536
MODEL_OUTPUT_LIMIT = 131072
PORTS = (8787, 8796, 8797, 11434)
ERROR_CODES = frozenset({
    'NOT_AVAILABLE', 'ACCESS_DENIED', 'TIMEOUT', 'OUTPUT_LIMIT', 'PROBE_FAILED',
    'INVALID_DATA', 'NOT_APPLICABLE', 'HTTP_ERROR', 'REDIRECT_BLOCKED',
})
CONTEXTS = {
    'unconfirmed': 'CURRENT_DEVICE_UNCONFIRMED', 'cloud': 'CLOUD',
    'workstation': 'WORKSTATION_DECLARED', 'linux-guest': 'LINUX_GUEST_DECLARED',
}
VERSION = re.compile(r'[0-9]{1,5}(?:\.[0-9]{1,5}){1,3}\Z', re.ASCII)
MODEL_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}\Z', re.ASCII)
LANGUAGE = re.compile(r'[A-Za-z0-9_]{1,40}\Z', re.ASCII)
# Unknown GPU branding is withheld, rather than accepting arbitrary device text.
GPU_NAME = re.compile(
    r'(?:NVIDIA )?(?:GeForce |Quadro |Tesla )?'
    r'(?:RTX (?:PRO )?(?:[A-Z]?[0-9]{3,4})|GTX [0-9]{3,4}|[AKMPVTHBL][0-9]{2,4})'
    r'(?: (?:Ti|SUPER|Laptop|GPU|Ada|Generation|Blackwell|Workstation|Edition|'
    r'Max-Q|with|Design|PCIE|PCIe|SXM[0-9]?|NVL|[0-9]{1,3}GB|HBM[0-9]))*\Z',
    re.ASCII,
)
MODULES = ('fitz', 'PIL', 'pytesseract', 'fastapi', 'sqlalchemy', 'cryptography')


class Probe(NamedTuple):
    status: str
    output: bytes = b''


def _stop_owned_process(process):
    """Only terminate the child/session this diagnostic created."""
    try:
        if os.name == 'posix':
            os.killpg(process.pid, signal.SIGKILL)
        elif process.poll() is None:
            process.kill()
    except (ProcessLookupError, PermissionError, OSError):
        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass
    try:
        process.wait(timeout=1)
    except (subprocess.TimeoutExpired, OSError):
        pass


def _run_command(command, *, timeout=COMMAND_TIMEOUT, max_output=COMMAND_OUTPUT_LIMIT):
    """Bound captured stdout while it is produced; never retain stderr."""
    environment = {name: os.environ[name] for name in (
        'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'LD_LIBRARY_PATH', 'TESSDATA_PREFIX',
    ) if name in os.environ}
    environment['LC_ALL'] = 'C'
    try:
        process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, shell=False, env=environment, close_fds=True,
            start_new_session=os.name == 'posix',
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0,
        )
    except FileNotFoundError:
        return Probe('NOT_AVAILABLE')
    except PermissionError:
        return Probe('ACCESS_DENIED')
    except OSError:
        return Probe('PROBE_FAILED')

    data = bytearray()
    finished = threading.Event()
    overflow = threading.Event()
    read_failed = threading.Event()

    def read_stdout():
        try:
            while True:
                chunk = process.stdout.read1(min(4096, max_output + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > max_output:
                    overflow.set()
                    break
        except (OSError, ValueError):
            read_failed.set()
        finally:
            finished.set()

    reader = threading.Thread(target=read_stdout, daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout
    status = 'PROBE_FAILED'
    try:
        while True:
            if overflow.is_set():
                status = 'OUTPUT_LIMIT'
                break
            if finished.is_set() and process.poll() is not None:
                status = 'OK' if process.returncode == 0 and not read_failed.is_set() else 'PROBE_FAILED'
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                status = 'TIMEOUT'
                break
            # Waiting on a separate event avoids spinning after stdout closes
            # while a child continues running.
            threading.Event().wait(min(0.01, remaining))
    finally:
        if status != 'OK':
            _stop_owned_process(process)
        reader.join(timeout=1)
        if not reader.is_alive():
            process.stdout.close()
    return Probe(status, bytes(data) if status == 'OK' else b'')


def _safe_probe(probe, *, limit=COMMAND_OUTPUT_LIMIT):
    if not isinstance(probe, Probe) or type(probe.status) is not str:
        return Probe('INVALID_DATA')
    if probe.status != 'OK':
        return Probe(probe.status if probe.status in ERROR_CODES else 'PROBE_FAILED')
    if type(probe.output) is not bytes:
        return Probe('INVALID_DATA')
    if len(probe.output) > limit:
        return Probe('OUTPUT_LIMIT')
    return probe


def _command(command, *, timeout=COMMAND_TIMEOUT):
    try:
        return _safe_probe(_run_command(command, timeout=timeout))
    except PermissionError:
        return Probe('ACCESS_DENIED')
    except Exception:
        return Probe('PROBE_FAILED')


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError()
        value[key] = item
    return value


def _decode_json(probe):
    if probe.status != 'OK':
        return probe.status, None
    try:
        value = json.loads(probe.output.decode('utf-8-sig'), object_pairs_hook=_unique_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if type(value) is not dict:
            raise ValueError()
        return 'OK', value
    except (ValueError, UnicodeError, RecursionError):
        return 'INVALID_DATA', None


def _integer(value, *, minimum=0, maximum=1 << 50):
    return type(value) is int and minimum <= value <= maximum


def _version(value):
    return type(value) is str and len(value) <= 32 and VERSION.fullmatch(value) is not None


def _powershell(body):
    # Each call is fixed source; no CLI input is interpolated into PowerShell.
    wrapper = (
        "$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';"
        "[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false);"
        'try {' + body + '} catch {'
        "$s='PROBE_FAILED';"
        "if ($_.Exception -is [System.UnauthorizedAccessException] -or "
        "$_.Exception -is [System.Security.SecurityException] -or "
        "$_.CategoryInfo.Category -eq 'PermissionDenied' -or "
        "$_.CategoryInfo.Category -eq 'SecurityError' -or "
        "$_.Exception.HResult -eq -2147024891) {$s='ACCESS_DENIED'};"
        '@{status=$s}|ConvertTo-Json -Compress}'
    )
    status, value = _decode_json(_command(
        ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', wrapper],
        timeout=POWERSHELL_TIMEOUT,
    ))
    if status != 'OK':
        return status, None
    code = value.get('status')
    if type(code) is not str:
        return 'INVALID_DATA', None
    if code != 'OK':
        return code if code in ERROR_CODES else 'PROBE_FAILED', None
    return 'OK', value


def _empty_system(family, status, scope):
    return {
        'os': {'family': family, 'version': None, 'status': status},
        'cpu': {'status': status, 'logical_count': None},
        'ram': {'status': status, 'total_bytes': None, 'free_bytes': None},
        'storage': {'status': status, 'scope': scope, 'volumes': []},
    }


def _windows_system():
    status, value = _powershell(
        '$o=Get-CimInstance Win32_OperatingSystem;'
        '$c=Get-CimInstance Win32_ComputerSystem;'
        '$d=@(Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3"|'
        'Where-Object {$_.Size -gt 0}|ForEach-Object {'
        '@{total_bytes=[long]$_.Size;free_bytes=[long]$_.FreeSpace}});'
        "@{status='OK';os_version=[string]$o.Version;cpu_count=[int]$c.NumberOfLogicalProcessors;"
        'ram_total_bytes=([long]$o.TotalVisibleMemorySize*1024);'
        'ram_free_bytes=([long]$o.FreePhysicalMemory*1024);fixed_disks=$d}'
        '|ConvertTo-Json -Depth 4 -Compress'
    )
    result = _empty_system('WINDOWS', status if status != 'OK' else 'INVALID_DATA', 'FIXED_VOLUMES')
    if status != 'OK':
        return result
    if _version(value.get('os_version')):
        result['os'].update(status='OK', version=value['os_version'])
    if _integer(value.get('cpu_count'), minimum=1, maximum=4096):
        result['cpu'].update(status='OK', logical_count=value['cpu_count'])
    total, free = value.get('ram_total_bytes'), value.get('ram_free_bytes')
    if _integer(total, minimum=1) and _integer(free, maximum=total):
        result['ram'].update(status='OK', total_bytes=total, free_bytes=free)
    volumes = value.get('fixed_disks')
    if type(volumes) is list and 1 <= len(volumes) <= 32:
        clean = []
        for volume in volumes:
            if type(volume) is not dict:
                break
            size, unused = volume.get('total_bytes'), volume.get('free_bytes')
            if not _integer(size, minimum=1) or not _integer(unused, maximum=size):
                break
            clean.append({'total_bytes': size, 'free_bytes': unused})
        else:
            result['storage'].update(status='OK', volumes=clean)
    return result


def _read_file(path, *, max_output=COMMAND_OUTPUT_LIMIT):
    try:
        with open(path, 'rb') as stream:
            data = stream.read(max_output + 1)
        return Probe('OUTPUT_LIMIT') if len(data) > max_output else Probe('OK', data)
    except FileNotFoundError:
        return Probe('NOT_AVAILABLE')
    except PermissionError:
        return Probe('ACCESS_DENIED')
    except OSError:
        return Probe('PROBE_FAILED')


def _linux_system():
    result = _empty_system('LINUX', 'INVALID_DATA', 'ROOT_FILESYSTEM')
    try:
        release = platform.release()
        match = re.match(r'([0-9]{1,5}(?:\.[0-9]{1,5}){1,3})(?:-|$)', release)
        if match:
            result['os'].update(status='OK', version=match.group(1))
    except Exception:
        result['os']['status'] = 'PROBE_FAILED'
    try:
        count = os.cpu_count()
        if _integer(count, minimum=1, maximum=4096):
            result['cpu'].update(status='OK', logical_count=count)
    except Exception:
        result['cpu']['status'] = 'PROBE_FAILED'
    memory = _safe_probe(_read_file('/proc/meminfo'))
    if memory.status != 'OK':
        result['ram']['status'] = memory.status
    else:
        try:
            values = {}
            for line in memory.output.decode('ascii').splitlines():
                key = line.partition(':')[0]
                if key not in ('MemTotal', 'MemFree'):
                    continue
                match = re.fullmatch(r'(MemTotal|MemFree):\s+([0-9]{1,14}) kB', line)
                if not match or key in values:
                    raise ValueError()
                values[key] = int(match.group(2)) * 1024
            total, free = values['MemTotal'], values['MemFree']
            if _integer(total, minimum=1) and _integer(free, maximum=total):
                result['ram'].update(status='OK', total_bytes=total, free_bytes=free)
        except (ValueError, KeyError, UnicodeError):
            pass
    try:
        disk = os.statvfs('/')
        total, free = disk.f_blocks * disk.f_frsize, disk.f_bavail * disk.f_frsize
        if _integer(total, minimum=1) and _integer(free, maximum=total):
            result['storage'].update(status='OK', volumes=[{'total_bytes': total, 'free_bytes': free}])
    except PermissionError:
        result['storage']['status'] = 'ACCESS_DENIED'
    except Exception:
        result['storage']['status'] = 'PROBE_FAILED'
    return result


def _hyperv_status(family):
    result = {'status': 'NOT_APPLICABLE', 'guests': None}
    if family != 'WINDOWS':
        return result
    status, value = _powershell(
        "if (-not (Get-Command Get-VM -ErrorAction SilentlyContinue)) {"
        "@{status='NOT_AVAILABLE'}|ConvertTo-Json -Compress} else {"
        # Do not read or serialize names/IDs. Successful enumeration is needed
        # to report an empty inventory; failure always remains unknown.
        '$v=@(Get-VM -ErrorAction Stop|Select-Object -First 17|ForEach-Object {'
        '@{state=[string]$_.State;cpu_count=[int]$_.ProcessorCount;'
        'memory_startup_bytes=[long]$_.MemoryStartup;memory_assigned_bytes=[long]$_.MemoryAssigned}});'
        "if ($v.Count -gt 16) {@{status='OUTPUT_LIMIT'}|ConvertTo-Json -Compress}"
        "else {@{status='OK';guests=$v}|ConvertTo-Json -Depth 4 -Compress}}"
    )
    result['status'] = status
    if status != 'OK':
        return result
    guests = value.get('guests')
    if type(guests) is not list:
        result['status'] = 'INVALID_DATA'
        return result
    if len(guests) > 16:
        result['status'] = 'OUTPUT_LIMIT'
        return result
    states = {'RUNNING', 'OFF', 'SAVED', 'PAUSED', 'STARTING', 'STOPPING', 'SAVING', 'PAUSING', 'RESUMING', 'RESET'}
    clean = []
    for guest in guests:
        if type(guest) is not dict:
            result['status'] = 'INVALID_DATA'
            return result
        state = guest.get('state')
        cpu, startup, assigned = (guest.get(name) for name in ('cpu_count', 'memory_startup_bytes', 'memory_assigned_bytes'))
        if (type(state) is not str or len(state) > 24 or state.upper() not in states
                or not _integer(cpu, minimum=1, maximum=4096)
                or not _integer(startup, minimum=1) or not _integer(assigned)):
            result['status'] = 'INVALID_DATA'
            return result
        clean.append({'state': state.upper(), 'cpu_count': cpu,
                      'memory_startup_bytes': startup, 'memory_assigned_bytes': assigned})
    result['guests'] = clean
    return result


def _gpu_status():
    probe = _command(['nvidia-smi', '--query-gpu=name,memory.total,memory.free,driver_version',
                      '--format=csv,noheader,nounits'])
    result = {'status': probe.status, 'devices': []}
    if probe.status != 'OK':
        return result
    try:
        rows = list(csv.reader(io.StringIO(probe.output.decode('utf-8'))))
        if not 1 <= len(rows) <= 16:
            raise ValueError()
        devices = []
        for row in rows:
            if len(row) != 4:
                raise ValueError()
            name, total_text, free_text, driver = (item.strip() for item in row)
            if (len(name) > 96 or not GPU_NAME.fullmatch(name) or not _version(driver)
                    or not re.fullmatch(r'[0-9]{1,8}', total_text)
                    or not re.fullmatch(r'[0-9]{1,8}', free_text)):
                raise ValueError()
            total, free = int(total_text), int(free_text)
            if not 0 < total <= 1048576 or not 0 <= free <= total:
                raise ValueError()
            devices.append({'name': name, 'total_vram_mib': total, 'free_vram_mib': free, 'driver_version': driver})
        result['devices'] = devices
    except (ValueError, UnicodeError, csv.Error):
        result['status'] = 'INVALID_DATA'
    return result


def _ocr_status():
    result = {'status': 'NOT_AVAILABLE', 'version': None,
              'languages': {name: None for name in ('jpn', 'jpn_vert', 'eng', 'osd')}}
    version = _command(['tesseract', '--version'])
    result['status'] = version.status
    if version.status != 'OK':
        return result
    try:
        first = version.output.decode('utf-8').splitlines()[0]
        match = re.fullmatch(r'tesseract ([0-9]{1,5}(?:\.[0-9]{1,5}){1,3})', first)
        if not match:
            raise ValueError()
        result['version'] = match.group(1)
    except (ValueError, UnicodeError, IndexError):
        result['status'] = 'INVALID_DATA'
        return result
    languages = _command(['tesseract', '--list-langs'])
    result['status'] = languages.status
    if languages.status != 'OK':
        return result
    try:
        lines = languages.output.decode('utf-8').splitlines()
        if not lines or not lines[0].startswith('List of available languages in '):
            raise ValueError()
        names = lines[1:]
        if len(names) > 256 or any(not LANGUAGE.fullmatch(name) for name in names):
            raise ValueError()
        result['languages'] = {name: name in names for name in result['languages']}
    except (ValueError, UnicodeError):
        result['status'] = 'INVALID_DATA'
    return result


def _read_ollama_tags(*, timeout=2.0, max_output=MODEL_OUTPUT_LIMIT):
    """Direct fixed-loopback GET; HTTPConnection has no proxy/redirect support.

    The watchdog covers headers as well as body reads: a server cannot extend
    the total deadline indefinitely by sending one byte before each timeout.
    """
    connection = http.client.HTTPConnection('127.0.0.1', 11434, timeout=timeout)
    transport = [None]
    expired = threading.Event()
    deadline = time.monotonic() + timeout

    def abort():
        expired.set()
        active = transport[0]
        if active is not None:
            try:
                active.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    watchdog = threading.Timer(timeout, abort)
    watchdog.daemon = True
    watchdog.start()
    response = None
    try:
        connection.connect()
        transport[0] = connection.sock
        if expired.is_set() or time.monotonic() >= deadline:
            return Probe('TIMEOUT')
        connection.request('GET', '/api/tags', headers={'Accept': 'application/json', 'Connection': 'close'})
        response = connection.getresponse()
        if expired.is_set():
            return Probe('TIMEOUT')
        if 300 <= response.status <= 399:
            return Probe('REDIRECT_BLOCKED')
        if response.status != 200:
            return Probe('HTTP_ERROR')
        length = response.getheader('Content-Length')
        if length is not None:
            if not re.fullmatch(r'[0-9]{1,16}', length):
                return Probe('INVALID_DATA')
            if int(length) > max_output:
                return Probe('OUTPUT_LIMIT')
        data = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if expired.is_set() or remaining <= 0:
                return Probe('TIMEOUT')
            # HTTPResponse closes its socket when Content-Length is exhausted;
            # a final read1() still returns EOF without touching that socket.
            if not response.isclosed():
                transport[0].settimeout(remaining)
            chunk = response.read1(min(4096, max_output + 1 - len(data)))
            if not chunk:
                if length is not None and len(data) != int(length):
                    return Probe('INVALID_DATA')
                return Probe('TIMEOUT') if expired.is_set() else Probe('OK', bytes(data))
            data.extend(chunk)
            if len(data) > max_output:
                return Probe('OUTPUT_LIMIT')
    except (TimeoutError, socket.timeout):
        return Probe('TIMEOUT')
    except PermissionError:
        return Probe('ACCESS_DENIED')
    except ConnectionRefusedError:
        return Probe('NOT_AVAILABLE')
    except (OSError, http.client.HTTPException):
        return Probe('TIMEOUT' if expired.is_set() else 'PROBE_FAILED')
    finally:
        watchdog.cancel()
        if response is not None:
            response.close()
        connection.close()
        watchdog.join(timeout=0.1)


def _local_model_status(requested_model):
    try:
        probe = _safe_probe(_read_ollama_tags(), limit=MODEL_OUTPUT_LIMIT)
    except Exception:
        probe = Probe('PROBE_FAILED')
    status, value = _decode_json(probe)
    result = {'status': status, 'model_count': None, 'requested_model_present': None}
    if status != 'OK':
        return result
    models = value.get('models')
    if (type(models) is not list or len(models) > 256
            or any(type(item) is not dict or type(item.get('name')) is not str
                   or not MODEL_NAME.fullmatch(item['name']) for item in models)):
        result['status'] = 'INVALID_DATA'
        return result
    result['model_count'] = len(models)
    if requested_model is not None:
        result['requested_model_present'] = any(item['name'] == requested_model for item in models)
    return result


def _ports_status(family):
    result = {str(port): {'status': 'NOT_APPLICABLE', 'listening': None} for port in PORTS}
    if family == 'WINDOWS':
        status, value = _powershell(
            '$p=@(Get-NetTCPConnection -State Listen -ErrorAction Stop|Select-Object -ExpandProperty LocalPort);'
            "@{status='OK';'8787'=($p -contains 8787);'8796'=($p -contains 8796);"
            "'8797'=($p -contains 8797);'11434'=($p -contains 11434)}|ConvertTo-Json -Compress"
        )
        for port, entry in result.items():
            entry['status'] = status
            if status == 'OK':
                if type(value.get(port)) is bool:
                    entry['listening'] = value[port]
                else:
                    entry['status'] = 'INVALID_DATA'
    elif family == 'LINUX':
        status, listening = _linux_listening_ports()
        for port, entry in result.items():
            entry['status'] = status
            if status == 'OK':
                entry['listening'] = int(port) in listening
    return result


def _linux_listening_ports():
    listening = set()
    for path in ('/proc/net/tcp', '/proc/net/tcp6'):
        probe = _safe_probe(_read_file(path))
        if path.endswith('tcp6') and probe.status == 'NOT_AVAILABLE':
            continue
        if probe.status != 'OK':
            return probe.status, set()
        try:
            lines = probe.output.decode('ascii').splitlines()
            if not lines or not {'local_address', 'st'} <= set(lines[0].split()):
                raise ValueError()
            for line in lines[1:]:
                fields = line.split()
                if (len(fields) < 4 or not re.fullmatch(r'(?:[0-9A-Fa-f]{8}|[0-9A-Fa-f]{32}):[0-9A-Fa-f]{4}', fields[1])
                        or not re.fullmatch(r'[0-9A-Fa-f]{2}', fields[3])):
                    raise ValueError()
                if fields[3].upper() == '0A':
                    port = int(fields[1].rsplit(':', 1)[1], 16)
                    if port in PORTS:
                        listening.add(port)
        except (ValueError, UnicodeError):
            return 'INVALID_DATA', set()
    return 'OK', listening


def _module_status():
    result = {}
    for name in MODULES:
        try:
            result[name] = importlib.util.find_spec(name) is not None
        except Exception:
            result[name] = None
    return result


def inspect_workstation(*, context='unconfirmed', requested_model=None):
    """Return allowlisted observations only; context never asserts acceptance."""
    if (type(context) is not str or context not in CONTEXTS
            or requested_model is not None and (type(requested_model) is not str or not MODEL_NAME.fullmatch(requested_model))):
        return {'schema_version': 1, 'diagnostic_status': 'INVALID_ARGUMENT'}
    system = platform.system()
    family = {'Windows': 'WINDOWS', 'Linux': 'LINUX'}.get(system, 'UNSUPPORTED')
    resources = (_windows_system() if family == 'WINDOWS' else _linux_system() if family == 'LINUX'
                 else _empty_system(family, 'NOT_APPLICABLE', 'NOT_ASSESSED'))
    report = {
        'schema_version': 1, 'diagnostic_status': 'COMPLETED',
        'execution_context': CONTEXTS[context],
        'acceptance': {'workstation_verified': False, 'accuracy_measured': False, 'production_accepted': False},
        'reader_platform_supported': family == 'LINUX',
        'python': {'version': '.'.join(str(number) for number in sys.version_info[:3]),
                   'supported_for_application': sys.version_info >= (3, 11)},
        **resources,
        'gpu': _gpu_status(), 'native_ocr': _ocr_status(), 'modules': _module_status(),
        'local_model': _local_model_status(requested_model), 'ports': _ports_status(family),
        'hyperv': _hyperv_status(family),
        'wsl': {'status': 'OK' if family == 'WINDOWS' else 'NOT_APPLICABLE',
                'launcher_available': bool(shutil.which('wsl.exe')) if family == 'WINDOWS' else None,
                'runtime_state': 'NOT_CHECKED'},
    }
    return report


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError('INVALID_ARGUMENT')


def main(argv=None):
    parser = _Parser(add_help=False, allow_abbrev=False)
    parser.add_argument('--context', choices=tuple(CONTEXTS), default='unconfirmed')
    parser.add_argument('--model')
    try:
        arguments = parser.parse_args(argv)
        result = inspect_workstation(context=arguments.context, requested_model=arguments.model)
        code = 2 if result['diagnostic_status'] == 'INVALID_ARGUMENT' else 0
    except (ValueError, TypeError):
        result, code = {'schema_version': 1, 'diagnostic_status': 'INVALID_ARGUMENT'}, 2
    except Exception:
        result, code = {'schema_version': 1, 'diagnostic_status': 'PROBE_FAILED'}, 1
    print(json.dumps(result, ensure_ascii=True, indent=2, allow_nan=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
