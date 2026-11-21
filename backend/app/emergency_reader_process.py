"""Private pipe entrypoint; all ordinary/native stdout and stderr are discarded."""
from base64 import b64decode, b64encode
import json
import os
import sys


MAX_INPUT_BYTES = 36 * 1024 * 1024


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError()
        result[key] = value
    return result


def _invalid_number(_):
    raise ValueError()


def _limits(seconds):
    if os.name != 'posix':
        return
    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    memory = 1024 * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    resource.setrlimit(resource.RLIMIT_CPU, (seconds+2, seconds+3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64*1024*1024, 64*1024*1024))


def main():
    # Keep a private protocol descriptor; third-party prints/native diagnostics
    # cannot contaminate it or publish sensitive parser/model errors.
    protocol = os.fdopen(os.dup(sys.stdout.fileno()), 'wb')
    with open(os.devnull, 'wb') as sink:
        os.dup2(sink.fileno(), sys.stdout.fileno())
        os.dup2(sink.fileno(), sys.stderr.fileno())
    response = {'ok': False, 'code': 'PROCESS_INPUT_INVALID'}
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES+1)
        if len(raw) > MAX_INPUT_BYTES: raise ValueError()
        request = json.loads(raw, object_pairs_hook=_unique, parse_constant=_invalid_number)
        if not isinstance(request, dict) or set(request) != {'mode', 'data', 'page', 'pages', 'language', 'model', 'port', 'timeout'}:
            raise ValueError()
        timeout = request['timeout']
        if type(timeout) is not int or not 1 <= timeout <= 900: raise ValueError()
        _limits(timeout)
        from .emergency_reader import ReaderError, extract_source, inspect_source, render_page
        data = b64decode(request['data'], validate=True)
        if request['mode'] == 'inspect': result = inspect_source(data)
        elif request['mode'] == 'render': result = b64encode(render_page(data, request['page'])).decode('ascii')
        elif request['mode'] == 'read': result = extract_source(data, language=request['language'])
        elif request['mode'] == 'ai':
            from .emergency_local_ai import review_text
            pages = request['pages']
            if not isinstance(pages, list) or not 1 <= len(pages) <= 50: raise ValueError()
            result = review_text([{'page': page['page'], 'text': page['text']} for page in pages],
                                 model=request['model'], port=request['port'])
        elif request['mode'] == 'vision':
            from .emergency_local_ai import read_image_candidates
            preview = render_page(data, request['page'])
            result = read_image_candidates(b64encode(preview).decode('ascii'), model=request['model'],
                                           port=request['port'], page=request['page'])
        else: raise ValueError()
        response = {'ok': True, 'result': result}
    except Exception as failure:
        # ReaderError is imported only after input validation. Never serialize
        # an arbitrary exception's message or a supposedly safe arbitrary code.
        from .emergency_reader import ReaderError
        response = {'ok': False, 'code': failure.code if isinstance(failure, ReaderError) else 'PROCESS_FAILED'}
    try:
        protocol.write(json.dumps(response, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8'))
        protocol.flush()
    except Exception:
        pass
    finally:
        protocol.close()


if __name__ == '__main__':
    main()
