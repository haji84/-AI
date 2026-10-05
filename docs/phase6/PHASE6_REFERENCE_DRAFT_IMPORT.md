# Phase 6 Human Reference Draft Import

更新日: 2026-10-06

## Purpose

Human Reference Draft JSONを、同一原本のDrawingAnalysisへ編集可能なHuman Annotation Draftとして読み込む。

用途:
- AI/Assistantが作成したGeometry DraftをHumanが画面上で修正する
- 頂点修正後の面積を自動再計算する
- 区画追加・削除・名称/用途修正を行う
- 最終的にHuman Review済みReferenceとしてexportする

## Import gate

Endpoint:

`POST /drawing-analyses/{analysis_id}/annotations/import-reference`

入力:

```json
{
  "reference": {
    "reference_format": "fire-ai-drawing-human-reference-draft-v1",
    "source": {
      "sha256": "..."
    },
    "elements": [],
    "equipment_candidates": [],
    "fact_candidates": []
  }
}
```

必須:
- `reference_format` は `fire-ai-drawing-human-reference...`
- Reference source SHA-256とDrawingAnalysisの原本Document SHA-256が完全一致
- coordinate_spaceはpixelまたはnormalized

## Important behavior

Import元Referenceが`human_accepted`でも、Import後のAnnotationは必ず:

`status = draft`

となる。

元ReferenceのHuman承認状態を、別DrawingAnalysisのReview状態へ自動継承しない。

## Geometry / area

Import時にbackendがGeometryを再計算する。

clientが渡した`derived_geometry`は信用せず上書きする。

保存後の編集も既存Annotation編集フローを使うため:

- vertex drag
- vertex add/remove
- room/zone add/remove
- label/use/floor correction
- two-point scale calibration
- px² / m² recalculation

がそのまま利用できる。

## Provenance

Imported Annotation payloadには`reference_import`を保存する。

保存項目:
- reference_format
- original reference_status
- source SHA-256
- source filename
- original human_review
- original human_gate

ただしこれらはprovenanceであり、現在のAnnotation statusを決めない。

## Human Gate

Import後:

1. HumanがGeometry/区画/縮尺を修正
2. Draft保存
3. Human Review
4. reviewed AnnotationからHuman Reference export
5. exportされたReferenceをBenchmarkへ利用

Reviewed exportだけが現在DrawingAnalysisに対するHuman truthになる。
