#!/usr/bin/env python3
"""Generate assets only; operator reviews before any live-server changes."""
import argparse
import os
from pathlib import Path
from app.tenant_deployment import render_department


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--slug', required=True)
    parser.add_argument('--tenant-id', required=True)
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--release-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    values = vars(args).copy();output = values.pop('output')
    assets = render_department(**values)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    for name, content in assets.items():
        with os.fdopen(os.open(output / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
            stream.write(content)
    print(f'Generated {len(assets)} reviewable files in {output}; no server was modified')


if __name__ == '__main__':
    main()
