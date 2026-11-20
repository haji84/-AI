# Direct backup encryption policy repair — Issue #131

Source main: `3fd2235146766704ccbed6d103c6555680f3940d`.
Source tree: `6455231952bf99b28a8274b1238290646aed76a6`.

The existing scheduled entry point validates `FIRE_AI_BACKUP_ENCRYPTION_REQUIRED`.
The direct `backup_phase1.py` CLI previously ignored that policy and could publish
the plaintext format2 manifest/database/originals pair if its recipient flag was
omitted, including when the configured requirement was `true` or malformed.

Two actual synthetic CLI regression cases failed against the source main with
`DID NOT RAISE SystemExit`; both printed a successful plaintext backup path.
The fixture uses a real disposable SQLite department and original document.
No actual department records, operational keys or credentials are used.

The minimum five-line preflight validates the existing true/false policy and
requires an explicit recipient environment name when encryption is mandatory.
Existing recipient environment resolution still rejects missing values. These
checks occur before DB binding, maintenance acquisition, backup audit, dump,
archive and publication. No defaults, keys, permissions, migrations or deployed
environment values change. Optional plaintext development fixtures remain valid.

Focused source baseline: 38 passed / 1 skipped.
Focused repaired regression: 41 passed / 1 skipped, including required-mode
encrypted publication and separate same-UUID target restore. Rejected calls
leave the fixture DB bytes unchanged and create no destination directory.
The skipped PostgreSQL encrypted round trip remains an independent CI gate.

Full-suite, exact review, PR and independent main CI evidence must be recorded on
Issue #131 and parent #93 before acceptance; focused green alone is not acceptance.
Chapter 42 remains Partial. Real recipient enrollment, custody/rotation,
immutable Owner Vault, HA/fencing, production application, actual-site/new-PC
recovery and final Release remain incomplete.
