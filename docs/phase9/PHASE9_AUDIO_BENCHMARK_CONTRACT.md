# Phase 9 Japanese Audio Benchmark Contract

更新日: 2026-10-05

## Purpose

火災調査の録音文字起こしについて、実音声で次を測定する。

- 日本語文字認識精度
- 話者分離精度
- 不確実性マーカー精度

ベンチマーク結果はEvidenceであり、正式供述・時系列・出火原因・報告書を自動承認しない。

## Dataset unit

1録音につきReference JSONとHypothesis JSONを用意する。

Referenceは人間が音声を聞いて確定した正解データ。
HypothesisはLocal AI/STTの出力。

### JSON fields

- transcript_text
- speaker_segments[]
  - start_ms
  - end_ms
  - speaker
- uncertainty_markers[]
  - start_ms
  - end_ms
  - type

## Metrics

### Text

日本語は空白区切りWord Error Rateが安定しないため、v1ではCharacter Error Rate (CER)を主要指標とする。

- substitutions
- insertions
- deletions
- CER

### Speaker diarization

Reference時間に対して:
- correct speaker ms
- speaker confusion ms
- missed ms
- speaker error rate

v1はReferenceのspeaker labelとHypothesis labelを同一IDへ事前対応付けした状態で評価する。
自動speaker permutation最適化は次版。

### Uncertainty markers

完全一致する(start_ms,end_ms,type)で:
- precision
- recall
- F1

将来は時間許容幅付き評価を追加する。

## Acceptance process

本番品質PASSは現時点では未定義。
最初の実データBaselineを取得してから、用途別の許容閾値をHuman Gateで設定する。

禁止:
- Benchmark未実行でproduction-quality STTと表現する
- 単一録音だけで全体精度を断定する
- 不確実箇所を無視して供述を正式化する

## Tool

`scripts/benchmark_fire_audio.py`

例:

```bash
python scripts/benchmark_fire_audio.py \
  --reference reference.json \
  --hypothesis hypothesis.json \
  --output result.json
```
