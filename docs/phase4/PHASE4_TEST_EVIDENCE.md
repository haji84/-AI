# Phase 4 Test Evidence

更新日: 2026-10-05

## 開発環境

- backend pytest: 37 passed
- Phase 0-3回帰を含む
- Tesseract 5.5.0 利用可能
- 日本語OCR言語データ `Japanese` / `jpn` を確認

## 検証済み

- 任意ファイル名のテキスト文書から書類種別候補を抽出
- 対象物候補生成
- 所在地等の差分候補生成
- Human Review前の受付確定拒否
- 正式届出番号の数字のみ制約
- 受付確定と原本document_id紐付け
- 差分項目を明示選択して反映
- 対象物Versionが変わった場合の409拒否
- PDF埋込文字の直接抽出
- DOCX抽出
- XLSX抽出
- 管理ストレージ外パスの解析拒否
- Phase 4 RBAC
- Migration 007存在・解析
- ブラウザの「文書解析して受付」導線

## 未実施Host Gate

- 実庁内LAN PostgreSQLへのMigration 001-007
- 実サーバーTesseract/OCR日本語辞書の確認
- 実際のスキャン帳票を用いたOCR精度評価
- 実帳票100件以上の分類/項目抽出精度評価
- HTTPSクライアントからの大容量PDF受付
- 2端末による同一差分提案の競合E2E

これらは実施するまでPASS扱いにしない。