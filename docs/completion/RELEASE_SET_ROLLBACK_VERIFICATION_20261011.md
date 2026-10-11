# Unified release-set and rollback verification — 2026-10-11

## Scope

Issue #116 advances the Chapter 3/4/52 release prerequisite from main
`4980f9b64efaae6f862c5cfb09628553cb87104d`, tree
`81e9e85bf8112e1c402fffca21f932ad9ad67c16`. It binds the deterministic source
candidate and the Linux CPython 3.11 wheelhouse from Issue #114 into one strict
manifest and exercises safe extraction, isolated no-index installation,
atomic activation and rollback to one retained verified generation.

## RED and repair

The initial RED had no unified manifest or consumer command. Further REDs
showed that a successful pre-check alone would leave a swap window before pip,
concurrent install/rollback could race the state pointer, interpreter identity
was not bound to the wheel target, and application smoke attempted to mutate
the immutable extracted source through bytecode.

The repair copies each candidate to a private staging generation and verifies
that copy before extraction or pip. It retains the copied manifest, source and
wheel inventory with each generation. Source extraction accepts only bounded
regular allowlisted archive members, uses exclusive no-follow writes, then
rehashes every extracted file and reconstructs the Git tree. Dependencies use
a fresh venv with `PIP_NO_INDEX=1`, `--no-index` and `--require-hashes`.
Activation writes one canonical `state.json` atomically. A non-blocking process
lock serializes install and rollback. Rollback re-verifies both current and
prior retained release sets and extracted source, then reruns the application
smoke before one atomic state swap. Any failure leaves the active state intact.
The state rename is the explicit commit point: a failure before rename preserves
the old pointer and removes an unreachable new generation; a directory-fsync
failure after rename returns a committed result with
`state_durability_confirmed: false` instead of falsely reporting failure.

The manifest accepts only CPython 3.11 / cp311 /
`manylinux_2_34_x86_64`. Before creating a venv, the consumer probes the actual
interpreter, architecture and glibc and rejects non-x86_64 or glibc older than
2.34. It repeats the same probe against the newly created venv before pip, so a
launcher cannot validate itself and then activate a venv from another Python.
A platform label alone is not accepted as host evidence.

## Local evidence

- release-focused regression: 58 passed / 46 subtests
- deterministic source and wheel binding: passed with generated synthetic Git
  source and wheel fixtures
- source/wheel/manifest substitution and extra/symlink inputs: rejected
- mismatched interpreter target and concurrent operation: rejected
- wrong architecture, glibc below 2.34 and any non-bounded build target: rejected
- launcher that creates a wrong-version venv: rejected before pip or activation
- two independent staged installs and rollback: passed
- tampered retained source or wheel: rollback rejected without state change
- pre/post state-rename failure injection: old state preserved before commit;
  committed-but-durability-unconfirmed result reported after commit

The exact PR-head real 40-wheel build/install/rollback CI and independent main
CI remain required before acceptance. Synthetic fixtures do not replace them.

## Explicit limits

The artifact and consumer remain `production_ready: false`. Hashes provide
integrity, not publisher authenticity or code signing. The rehearsal does not
cover Windows or other architectures, Python/OS/PostgreSQL installation,
systemd/nginx, production paths, DB/schema/original-document rollback, secrets,
HA fencing, immutable backup, Owner Vault, all five deployment profiles, the
ten Chapter 54 E2E flows, or Human/External acceptance. SQLite smoke and a venv
generation pointer are not LAN/offline/HA/DR acceptance. Chapter 52 and overall
Release remain Partial.
