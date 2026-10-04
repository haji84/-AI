# Emergency Import Contract v0.1

## Source of truth

Imported source rows are immutable facts from the upstream export. Import normalization may create derived fields, but never silently discards a source row.

## Case identity

`source_case_key = normalize(覚知年月) | normalize(署所コード) | normalize(出場番号)`

The audited workbook has 2,958 case rows with complete unique keys.

## Patient identity

`source_patient_key = source_case_key | normalize(救護者番号)`

The audited workbook has 2,950 patient rows with complete unique keys.

## Crew identity

Preferred identity:

`source_case_key | normalize(隊員種別) | normalize(隊員コード)`

The audited workbook contains 66 crew rows with blank `隊員コード`. Those rows must be preserved.

Fallback identity for an incomplete crew row:

`source_file_sha256 | source_sheet | source_row_no`

Such rows are stored with `source_identity_status = missing_crew_code`. They can later be reconciled to `employees` without modifying the original raw payload.

## Idempotency

- Same source file hash must not create duplicate import batches unless explicitly forced by an administrator.
- Complete business keys use UPSERT semantics.
- Fallback row identities use source file hash + row number.
- Import result records inserted/updated/skipped/error counts.

## Raw preservation

All source columns remain available in `raw_payload`. Typed columns are an indexable normalized projection, not a destructive replacement.

## AI-derived clinical flags

CPA/allergy/contraindication classifications are stored separately with evidence and review state. AI-derived values must never rewrite the original source fields.