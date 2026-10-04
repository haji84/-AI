# Phase 5.2 条文構造化・Rule根拠紐付け

更新日: 2026-10-05

## 目的

取得済みの国法・地方例規を、単一の全文テキストではなく、
条・項・号・附則・別表・様式等のProvisionへ分解し、
業務判定Rule Versionから正確な根拠Provisionへ直接リンクできるようにする。

## 内部構造

LegalSourceDocumentVersion
→ LegalProvision
  → chapter / section / article / paragraph / item / subitem
  → supplementary
  → appendix / appendix_table / form 等

各Provision:
- stable provision_key
- parent_provision_id
- provision_type
- display_label
- heading_text
- body_text
- source_anchor
- source_path
- content_sha256
- present_in_source

## Rule根拠

LegalRuleVersion
→ LegalRuleCitation
→ LegalProvision

citation_role:
- primary
- definition
- exception
- reference
- supplementary

構造化法令Sourceを使うRule Versionは、
最低1件のLegalProvision Citationが無い限り承認不可。

Citation作成時に条文本文Snapshotも保存し、
将来の原文改正後でも当時の承認根拠を再現できる。

## 改正差分

同一LegalSourceDocumentの前後Versionをprovision_keyで比較する。

- added
- removed
- changed
- unchanged

差分はLegalUpdateCandidateへ格納し、
影響するRule Citationを逆引きする基礎とする。

## Parser

### e-Gov XML

XML構造を利用して以下を直接取得:
- 編/章/節/款
- 条
- 項
- 号
- 下位号
- 附則
- 別表
- 様式
- 図/注記

### 地方例規HTML

公式HTMLから以下を抽出:
- 第○条
- 算用数字の項
- 漢数字/イロハ等の号
- 附則
- 別表/別記/様式/別紙/附表

サイト固有構造が必要な場合は専用Adapterを追加する。

## API

- Source VersionのProvision検索
- Rule VersionのCitation一覧
- Draft Rule VersionへのCitation追加
- 評価結果へのCitation展開

## UI

必要設備・必要書類候補に、
Rule Code/Versionだけでなく具体的な条文ラベル・本文を表示する。

## Safety

AIは条文を根拠候補として提示できるが、
Rule条件・結論の正式有効化はHuman Gateを維持する。
原文改正でCitation先が変更・消滅した場合はRuleを自動書換えしない。
