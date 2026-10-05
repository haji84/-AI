# Phase 9 Voice / Statement Intelligence and Evidence Comparison

更新日: 2026-10-05

## 目的

火災調査の録音文字起こし・供述草案・タイムラインを検索・比較できるようにする。
AIは証拠間の相違・矛盾・確認事項を候補提示できるが、正式供述・確定タイムライン・火災原因を自動変更しない。

## Transcript uncertainty

文字起こしSegmentは原文を保持し、次を別メタデータとして保存する。

- uncertainty_markers
- text_sha256
- search_text
- confidence
- model_version
- Human review_status

不確実表現の例:
- たぶん
- おそらく
- ～頃
- ～と思う
- ～かもしれない

不確実表現をAIが断定表現へ書き換えてはならない。

## Statement drafts

AI供述草案はHuman-accepted Transcript SegmentのみをEvidenceとして利用する。

Evidence Segmentにuncertainty markerがある場合:
- source_uncertainty_markersへ継承
- uncertainty_reviewed=falseで作成
- uncertainty_reviewed=trueをHumanが明示しない限りreviewedへ昇格不可

供述草案は正式供述原本ではない。

## Transcript search

Case単位で文字起こし検索を行う。

- query terms
- speaker
- accepted_only
- uncertain_only
- time order
- exact Segment evidence

検索は証拠の発見支援であり、意味解釈や真偽判定を行わない。

## Evidence comparison

AI Evidence Comparisonが参照できるEvidenceはHuman確認済みのみ。

- transcript_segment: accepted
- statement: reviewed
- timeline_event: confirmed

未確認EvidenceはComparison入力として拒否する。

Comparison:
- issue_type
- summary
- left_ref
- right_ref
- evidence_refs
- confidence
- model_version
- pending / accepted / rejected
- optimistic version

同一Evidenceを左右に指定することは禁止する。

## Idempotency

AI Comparison Manifestはcanonical JSON SHA-256で冪等化する。
同一Manifest再投入ではCandidateを重複生成しない。

## Hard safety gates

1. AI comparison is a candidate only.
2. accepted comparison does not mutate transcript text.
3. accepted comparison does not mutate reviewed statement text.
4. accepted comparison does not mutate confirmed timeline.
5. accepted comparison does not select or approve fire cause.
6. fire cause approval remains separate Human approval.
7. report approval remains separate Human approval.
8. all AI-derived objects retain model/version/evidence provenance.

## Migrations

- 025: uncertainty/search/evidence comparison
- 026: evidence_comparison manifest type

## Next slice

- Comparison UI in fire investigation case screen
- grouped issue review
- source Evidence jump/navigation
- accepted Comparison inclusion in report-draft evidence package
- explicit guard that report/cause approval never treats Comparison as established fact
- real audio/STT benchmark remains separate from code-level workflow verification
