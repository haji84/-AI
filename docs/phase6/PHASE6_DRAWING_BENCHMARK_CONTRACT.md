# Phase 6 Drawing AI Benchmark Contract

更新日: 2026-10-05
Format: `fire-ai-drawing-benchmark-v1`

## Purpose

実図面に対するLocal Vision/AIの性能を、Human Referenceと比較して測定する。

Benchmark結果は性能Evidenceであり、設備台帳・建物情報・法令適合判定を自動確定しない。

## Input

ReferenceとHypothesisはPhase 6のDrawing Manifestに近いJSONを使う。

主要配列:
- `elements[]`
- `equipment_candidates[]`
- `fact_candidates[]`

### Element geometry

v1は以下をbounding boxへ正規化してIoUを計算する。

- `{x,y,width,height}`
- `{x1,y1,x2,y2}`
- `{bbox:[x,y,width,height]}`
- `{points:[...]}` の外接矩形

図面ページが異なるElementは一致しない。

## Metrics

### Geometry detection
Human Reference elementとAI elementを1対1対応し、IoUが閾値以上なら検出候補とする。

- TP / FP / FN
- Precision / Recall / F1
- mean IoU
- element_type accuracy

同じAI elementを複数Referenceへ重複マッチしない。

### Symbol classification

Geometryで一致したElementのうち、Referenceに`symbol_code`または`extracted_data.symbol`があるものを評価する。

- reference scored
- correct
- accuracy

### Equipment candidates

Element参照がある場合は、Geometryで対応したElementと設備種別コードを使って比較する。
Element参照がない場合はfloor/location/typeのfallback identityを使う。

- TP / FP / FN
- Precision / Recall / F1

### Facility fact candidates

`target_path + proposed_value`の正規化値で比較する。

- TP / FP / FN
- Precision / Recall / F1

## Dataset Manifest

```json
{
  "iou_threshold": 0.5,
  "drawings": [
    {
      "id": "plan-001",
      "reference": "reference/plan-001.json",
      "hypothesis": "hypothesis/plan-001.json",
      "metadata": {
        "drawing_type": "floor_plan",
        "scan_quality": "good"
      }
    }
  ]
}
```

ResultにはManifest/Reference/Hypothesis SHA-256を保存する。

## Tool

`scripts/benchmark_drawing_analysis.py`

```bash
python scripts/benchmark_drawing_analysis.py \
  --manifest benchmark-manifest.json \
  --output benchmark-result.json
```

## Human acceptance gate

本番品質の閾値はv1へ固定しない。

実図面Baseline後にHuman Gateで最低でも以下を決める。

- Geometry Precision / Recall / F1
- mean IoU
- element_type accuracy
- symbol accuracy
- equipment candidate Precision / Recall / F1
- fact candidate Precision / Recall / F1
- IoU threshold
- 必要な図面件数
- 図面種別、画質、縮尺、スキャン/写真条件のCoverage

Benchmark未実行でproduction-quality drawing AIとは表現しない。


## N/A semantics

実図面によっては評価対象が存在しないカテゴリがある。

例:
- 住宅平面図に評価対象の消防設備記号が存在しない
- ReferenceにもHypothesisにもequipment candidateが存在しない
- Referenceにsymbol codeが付与されていない

この場合は満点ではない。

- TP=0 / FP=0 / FN=0 のカテゴリは `applicable=false`
- Precision / Recall / F1 またはAccuracyは `null`
- 比較APIも片側がN/Aならdeltaを `null` にする

一方、Referenceが0件でもAIが候補を誤検出した場合はN/AではなくFalse Positiveとして評価する。

これにより「評価対象が無かっただけ」を「精度100%」と誤表示しない。


## Human Reference execution gate

Human Referenceとして明示されたReferenceは、Human確認前にBenchmark実行へ使わない。

対象:
- `reference_format` が `fire-ai-drawing-human-reference...` で始まるReference

実行可能条件:
- `reference_status=human_accepted`
- Draftが`human_gate.required=true`を持つ場合は、さらに`human_gate.accepted=true`
- またはHuman Annotation APIからexportされた`human_review.status=reviewed`のReference

`pending_human_acceptance`のReferenceをBaselineへ投入するとEvaluatorは失敗する。

目的:
- AI/Assistantが作ったGeometry Draftを自分自身の正解として採点しない
- Human修正前のopen-plan境界やcirculation境界を正式な正解値にしない
- accepted Reference SHAをBaseline Evidenceへ固定する


## Hypothesis export and source binding

Local Vision / AI側のBenchmark入力は、`DrawingAnalysis`から次でexportする。

```
GET /drawing-analyses/{analysis_id}/benchmark-hypothesis
```

export条件:
- `analysis_method=ai`
- statusが`analyzed`または`reviewed`
- `model_version`が存在する

Hypothesisにはsource DocumentのSHA-256を含める。

EvaluatorはReferenceとHypothesisの両方にsource SHA-256がある場合、値が一致しなければ実行を拒否する。

これにより別図面のHuman ReferenceとAI結果を誤って比較しない。

Human Reference側はReviewed Annotation exportまたは明示的Human acceptance済みRepository Referenceを使用する。
