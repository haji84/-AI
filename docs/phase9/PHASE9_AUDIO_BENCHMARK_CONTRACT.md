# Phase 9 Japanese Audio Benchmark Contract

更新日: 2026-10-05
Format: `fire-ai-japanese-stt-benchmark-v2`

## Purpose

火災調査の録音文字起こしについて、実音声で次を測定する。

- 日本語文字認識精度
- 話者分離精度
- 不確実性マーカー精度
- 複数録音をまとめたmicro集計

ベンチマーク結果はEvidenceであり、正式供述・時系列・出火原因・報告書を自動承認しない。

## Dataset unit

1録音につきReference JSONとHypothesis JSONを用意する。

Referenceは人間が音声を聞いて確定した正解データ。
HypothesisはLocal AI/STTの出力。

### Recording JSON fields

- `transcript_text`
- `speaker_segments[]`
  - `start_ms`
  - `end_ms`
  - `speaker`
- `uncertainty_markers[]`
  - `start_ms`
  - `end_ms`
  - `type`

時刻は0以上のmillisecond。
`end_ms > start_ms`を必須とする。

## Dataset Manifest

複数録音はManifestでまとめる。

```json
{
  "marker_tolerance_ms": 250,
  "recordings": [
    {
      "id": "interview-001",
      "reference": "reference/interview-001.json",
      "hypothesis": "hypothesis/interview-001.json"
    }
  ]
}
```

Manifestからの相対pathを使用する。

## Metrics

### Text

日本語では空白区切りWord Error Rateが安定しないため、Character Error Rate (CER)を主要指標とする。

- reference chars
- hypothesis chars
- substitutions
- insertions
- deletions
- errors
- CER

空白文字はCER計算から除外する。

### Speaker diarization

v2ではHypothesis speaker labelをReference speaker labelへ時間重複最大化で自動対応付けする。

例:
- Reference: `調査員`, `関係者`
- Hypothesis: `SPEAKER_00`, `SPEAKER_01`

Label文字列が一致していなくても、時間重複から最適な対応を求める。

測定:
- reference ms
- correct speaker ms
- speaker confusion ms
- missed ms
- false alarm ms
- speaker error rate
- speaker mapping

評価Timelineはsegment境界で分割し、同一時間を二重加算しない。

12話者以下はexact assignment。
それを超える場合はdeterministic greedy fallbackを使用する。

### Uncertainty markers

v2では同じ`type`に対し、start/endそれぞれの時間差が`marker_tolerance_ms`以内なら一致候補とする。

1つのHypothesis markerが複数Reference markerへ重複一致しないよう、最大二部matchingを使用する。

測定:
- reference markers
- hypothesis markers
- true positive
- false positive
- false negative
- precision
- recall
- F1
- tolerance ms

ToleranceはManifestまたはCLIで設定する。
Tolerance 0は完全一致。

## Dataset aggregate

複数録音ではmacro平均ではなく、v2の主要集計としてmicro集計を出す。

### Text micro
全Reference文字数と全Error数からCERを計算する。

### Diarization micro
全Reference時間と全speaker error時間からSpeaker Error Rateを計算する。

### Marker micro
全TP/FP/FNからPrecision/Recall/F1を計算する。

録音ごとの個別結果も保持する。

## Acceptance process

本番品質PASS閾値はコードへ固定しない。

最初の実データBaselineを取得した後に、用途別にHuman Gateで以下を決める。

- 許容CER
- 許容Speaker Error Rate
- Marker Precision/Recall/F1
- Marker time tolerance
- 必要なDataset件数
- 話者人数・録音環境・雑音条件のCoverage

禁止:
- Benchmark未実行でproduction-quality STTと表現する
- 単一録音だけで全体精度を断定する
- 自動speaker mapping結果を話者本人確認として扱う
- 不確実箇所を無視して供述を正式化する
- Benchmark scoreだけでEvidenceをHuman-reviewedへ昇格する

## Tool

`scripts/benchmark_fire_audio.py`

単一録音:

```bash
python scripts/benchmark_fire_audio.py \
  --reference reference.json \
  --hypothesis hypothesis.json \
  --marker-tolerance-ms 250 \
  --output result.json
```

複数録音:

```bash
python scripts/benchmark_fire_audio.py \
  --manifest benchmark-manifest.json \
  --output benchmark-result.json
```

話者Label自動対応を無効にする場合:

```bash
python scripts/benchmark_fire_audio.py \
  --manifest benchmark-manifest.json \
  --no-auto-speaker-map
```

## Next external gate

評価器v2完成後の未実施Gate:

1. 実際の日本語火災調査相当録音を準備
2. Human Referenceを作成
3. Local STT Hypothesisを作成
4. Dataset Manifestを作成
5. v2 benchmark実行
6. BaselineをEvidenceとして保存
7. Human GateでAcceptance thresholdを決定
