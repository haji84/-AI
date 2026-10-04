# Phase 5 法令ルール・必要書類/消防用設備 判定支援

更新日: 2026-10-05

## 目的

対象物の正規化済みデータに対し、Version管理された正式ルールを決定的に適用し、
必要書類・消防用設備の「候補判定」を根拠付きで提示する。

本Phaseでは実法令の条文内容を推測で投入しない。
ルールエンジンの器、承認、評価、監査、UIを実装する。

## 安全原則

- 承認済みルールVersionのみ評価対象。
- 出典文書または出典参照が無いRule Versionは承認不可。
- 同一Ruleで適用期間が重なる承認済みVersionを禁止。
- 未承認Draftは判定に一切使用しない。
- 判定結果は `candidate` として保存し、正式判断ではない。
- 対象物DB、届出、設備情報を自動更新しない。
- AIがルール本文や法令条件を自己改変しない。
- 実法令・条例・告示の登録は一次資料確認後にHuman Gateを通す。

## DB

Migration 008:
- `legal_rules`
- `legal_rule_versions`
- `requirement_evaluations`

Rule Versionには以下を保持する。
- Version番号
- 適用開始/終了日
- 条件JSON
- 結果JSON
- 出典document_idまたは出典参照
- Draft/Approved/Retired
- 承認者・承認日時
- 楽観ロックVersion

## 初期判定フィールド

Phase 5 v1で評価可能な正規化項目:
- status
- classification_code
- structure
- above_ground_floors
- basement_floors
- building_area
- total_floor_area
- occupancy_total
- employee_total
- floor_count

対応演算子:
- eq / ne
- in / contains
- gte / lte / gt / lt
- exists

未定義フィールドを使うRuleは登録時に422で拒否する。

## API

- `GET /legal-rules`
- `POST /legal-rules`
- `GET /legal-rules/{rule_id}/versions`
- `POST /legal-rules/{rule_id}/versions`
- `POST /legal-rules/versions/{version_id}/approve`
- `POST /legal-rules/evaluate/{building_id}`
- `GET /legal-rules/evaluations/{building_id}`

## 権限

- `legal_rule.read`
- `legal_rule.manage`
- `legal_rule.approve`
- `legal_rule.evaluate`

通常の予防業務担当はread/evaluateのみ。
ルール作成者と正式承認者を分離可能とする。

## UI

対象物詳細に以下を追加。
- 必要書類候補
- 必要設備候補

表示内容:
- 候補名
- Rule Code
- Rule Version
- 出典
- 一致条件
- 「職員確認待ち」

画面上でも正式判断と誤認させない。

## 次Slice

1. 公式一次資料の登録フロー
2. 条文/条例/告示VersionとRule Versionの厳密な出典関係
3. 令別表用途や複合用途の条件モデル拡張
4. 階別条件・無窓階・地下階等の詳細条件
5. 必要書類判定結果と届出提出状況の照合
6. 必要設備判定結果と既設設備情報の差分検出
7. Human Reviewで正式確認済み状態を保存
