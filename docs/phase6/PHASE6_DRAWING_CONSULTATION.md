# Phase 6 Drawing Consultation / Occupancy Classification Gate

更新日: 2026-10-05

## Goal

設備が未記載の相談図面でも、図面から用途・規模情報を整理し、消防法施行令別表第一の項候補をHuman確認した後に、Approved Ruleだけで必要設備候補を回答する。

## Flow

```
Drawing
-> DrawingAnalysis
-> Human-reviewed Annotation
-> Consultation Snapshot
-> occupancy_classification Approved Rules
-> classification candidates
-> Human confirms one classification
-> equipment_requirement Approved Rules
-> required equipment candidates with citations
-> equipment_placement Approved Rules
-> placement candidates / constraints
-> Human review
```

## Hard Gate

必要設備評価は`confirmed_classification_code`が無い限りHTTP 409で拒否する。

図面に設備が描かれていないことを「設備不要」と解釈しない。

## Consultation Snapshot

Human-reviewed Annotationから以下を作る。

- room labels
- room use tags
- floor numbers
- structure
- above/basement floors
- building area
- total floor area
- occupancy / employee count

相談時のHuman answersとして追加可能:

- primary_use
- use_tags
- has_sleeping_use
- has_food_service
- public_access
- mixed_use
- windowless_floor_count
- structure / floor / area / occupancy facts

## Occupancy Classification

Managed Legal Rule domain:

`occupancy_classification`

Approved Rule outcome example:

```json
{
  "decision": "classification_candidate",
  "classification_code": "(X)",
  "classification_label": "..."
}
```

AIやRule一致は候補だけ。
Humanが項を確定する。

候補Ruleを選ぶ場合、Rule Versionとclassification code/labelが一致しなければ拒否する。

Rule候補が無い場合も、Humanはreview_note付きで手動確定できる。
この場合は法令Ruleによる自動判定ではなくHuman manualとしてAuditへ残る。

## Missing Information

有効なApproved classification Ruleが無い場合:

`no approved occupancy_classification Rules`

Ruleが必要とする入力が欠ける場合、そのfieldをmissing_informationへ出す。

質問画面はこの情報から生成できる。

## Required Equipment

項確定後のみ、`equipment_requirement` domainのApproved Rulesを相談Snapshotへ適用する。

出力:

- equipment_type_code / name
- matched Rule
- Rule Version
- exact citations
- source reference
- outcome
- required candidate state

重要:

Matched Ruleが0件でも「必要設備なし」とは断定しない。
Approved Rule setの法的完全性がHuman Gateで確認されていない限り、0 matchは0 requirementを意味しない。

## Placement

Managed Legal Rule domain:

`equipment_placement`

Approved Ruleが無い設備は自動配置しない。

`placement_mode=room_candidate`かつ`target_room_use`が明示されたApproved Ruleだけ、Human-reviewed room geometryの中心をcandidate markerとして生成できる。

その他は`manual_placement_with_constraints`または`approved_placement_rule_missing`で止める。

配置Markerは設計確定ではなくHuman-reviewed candidate。

## Safety

1. 項未確定で必要設備を出さない。
2. 図面に設備が無いことを不要判定へ使わない。
3. Approved Ruleのみ自動判定へ使用。
4. Exact legal citationsを保持。
5. 0 matchを0 requirementと断定しない。
6. 配置Rule無しで設備記号を自動配置しない。
7. AI-seeded room geometryはHuman Review後のみ相談入力に使う。
