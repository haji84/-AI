# Signed legal update completion plan

Spec: SPECIFICATION.md section38; main fb2c9900 includes tenant/personnel foundation. Source originals become versioned evidence and review_required candidates; never automatically approved rules.

1. RED tests for detached Ed25519 signature, externally installed trust keys, manifest/payload hash mismatch, unknown/revoked key, path escape/symlink/duplicate JSON, unsigned production refusal. Implement bounded verifier and immutable staged payload copies before importer writes.
2. Sign existing e-Gov and official HTML collector manifests with collector-only protected key. Runtime reads public trust configuration only. Signed metadata includes source URLs/version/diff plus all raw hashes. Reject mismatched adapter/source origin and unverified payload before DB/storage changes. Retain explicit unbound development compatibility only.
3. Integrate both existing importers and offline update folder processor; candidate-only, source UUID fixed, replay unchanged/idempotent. Record verified signer/manifest/source hashes in version provenance and operation audit.
4. Tests actual synthetic signed collector → verifier → importer → review_required candidate, malformed rejection with no DB/original change. Full suite, migration/parser/JS, fresh branch review, PR/CI/main merge.
5. Publish collector/trust rotation/revocation/offline folder/admin instructions and refresh completion audit. Actual production trust key selection and official Human Rule approval remain external; missing verification code is not External Gate.

Ruling: detached signature covers exact manifest bytes with protocol domain separator. Trust is operator-installed public keys, never an embedded bundle key. Ed25519 is a technical library choice; no production private key is generated or deployed by development.
