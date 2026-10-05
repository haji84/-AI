# Phase 9 Audio Benchmark Run Registry

更新日: 2026-10-05

## Purpose

Japanese Audio Benchmark v2の結果を一時ファイルで終わらせず、
比較可能なEvidenceとしてLocal AI DBへ保存する。

Benchmark Evidenceは火災調査Evidenceと分離する。

保存・Human Reviewしても次を自動変更しない。

- transcript
- statement
- timeline
- fire cause
- formal report

## DB

Migration 027:
`fire_audio_benchmark_runs`

保存:
- benchmark format
- dataset label
- manifest SHA-256
- canonical result SHA-256
- recording count
- complete result payload
- review status
- Human baseline decision
- review notes
- optimistic version
- creator/reviewer/timestamps

同一result payloadはcanonical JSON SHA-256で冪等化する。

## API

- `GET /fire-investigations/audio-benchmarks`
- `POST /fire-investigations/audio-benchmarks`
- `POST /fire-investigations/audio-benchmarks/{id}/review`
- `GET /fire-investigations/audio-benchmarks/compare?left_id=...&right_id=...`

## Human Review

Decision:
- `accepted_baseline`
- `rejected_baseline`

accepted_baselineは「品質基準PASS」を意味しない。

意味:
- このDataset/Resultを今後の比較Baselineとして使用してよい

Acceptance thresholdは実データBaseline確認後に別Human Gateで設定する。

## Comparison

比較対象:
- CER
- Speaker Error Rate
- uncertainty-marker F1

Delta:
`right - left`

Direction:
- CER: lower is better
- Speaker Error Rate: lower is better
- Marker F1: higher is better

ただしDataset構成・録音条件が異なるRun間の差分を
モデル品質の改善/悪化として自動判定しない。

Recording metadataを必ず確認する。

## External gate

Registry完成後も実音声Benchmark未実行ならproduction-quality claimは禁止。

次の実データ手順:

1. real audio Dataset
2. Human Reference
3. Local STT Hypothesis
4. Benchmark v2
5. Registryへ結果保存
6. Human baseline review
7. Baseline比較
8. Human acceptance threshold設定
