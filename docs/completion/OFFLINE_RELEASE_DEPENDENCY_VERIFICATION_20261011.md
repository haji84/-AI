# Offline release dependency verification — 2026-10-11

## Scope

Issue #114 advances the Chapter 3/4/44/52 release prerequisite for the first
Linux target. The source base is main
`700b891ef0a088c9600e1cb5d7144f281a365a72`, tree
`a0f9ac1419234ae08cd5e0a87e9fc3abb73c6137`.

The bounded target is CPython 3.11 on x86_64 Linux with glibc 2.34 or newer.
`backend/requirements-release.lock` pins the 40 resolved runtime distributions
and their repository SHA-256 values. The wheelhouse builder uses pip
`--require-hashes` and `--only-binary=:all:` and records a manifest binding the
project, lock, target and selected wheel bytes.

## RED and repair

Synthetic tests first failed because no verifier existed. They now reject
range/unhashed lock entries, lock/project changes, missing/extra/tampered files,
sdists, duplicate distributions, metadata/version mismatch and the wrong target.

The first actual target download failed on `argon2-cffi-bindings`: requesting
only the literal `manylinux_2_34_x86_64` tag excluded valid lower-glibc wheels.
The repair expands a glibc 2.34 target only to compatible lower PEP 600 tags,
ordered newest to oldest; it never admits a higher-glibc tag.

Independent exact-tree review then reproduced three additional REDs: a wheel
whose tags were incompatible with the declared target was accepted, project
`requires-python` and selected-extra dependency closure were not enforced, and
the JSON manifest was decoded before any byte limit. The repaired verifier now
cross-checks filename and `WHEEL` tags against the declared target, evaluates
the active metadata dependency closure (including `uvicorn[standard]`), rejects
targets outside `requires-python`, and rejects manifests over 1 MiB before
decoding. It still does not import or execute downloaded wheel code.

A second exact-tree review found four narrower fail-open cases: native ABI tags
paired with `any`, non-canonical or reversed PEP 508 marker comparisons,
wheel-level `Requires-Python`, and unreachable stale lock entries. The final
design walks the active dependency graph from the declared project roots,
normalizes extras, handles version comparisons in either operand, validates
both project and wheel Python constraints, and requires every locked wheel to
be reachable. Native ABI wheels must carry a compatible platform tag.

Final review also bounded `abi3` to CPython 3.2 or newer and requires every
selected extra to be declared by the wheel's `Provides-Extra` metadata. This
prevents an obsolete or misspelled extra from silently producing an empty
closure.

## Local evidence

- focused synthetic regression: 15 passed / 6 subtests
- actual build: 40 wheels, wheel-only, about 62 MiB
- lock SHA-256: `dd5d6de434b8c77aa0f75fd6ad1f68731eb4706eac573aa60df56457bdda32aa`
- fresh CPython 3.11 venv install with `PIP_NO_INDEX=1`, `--no-index`,
  `--require-hashes`: success
- application import from source with the offline venv: success; `/health` route
  present

The committed workflow must still provide exact-head PR CI and independent main
CI evidence. Generated wheel bytes are CI artifacts, not Git-tracked files.

## Explicit limits

This does not cover Windows, other CPU architectures, Python/OS/PostgreSQL
binaries, OCR tools, Local AI runtimes/models, formal artifact signing,
production installation, all five deployment profiles, the ten Chapter 54
flows, HA/Owner Vault, or Human/External acceptance. SQLite import smoke is not
LAN/offline/HA/DR acceptance. Chapter 52 and the overall Release remain Partial.
