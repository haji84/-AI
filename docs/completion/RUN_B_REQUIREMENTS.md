# Completion Run B — requirement acceptance ledger

Live audit as of main89e87e1739add38d2e5de7afac195c14e58b6a4f. This is not a completion claim. Grouped rows retain every requested business function; final review must split a row if only some members pass.

Completed requires merged API/models/migration/UI and applicable tests, not a scaffold or API alone. Partial/Missing remain internal backlog. External Gate is reserved for actual approved deployment, official originals/code meanings, formal Human decisions and measured real-model evaluation. Synthetic tests do not prove deployment or clinical accuracy.

| Module | Required behavior | Status | Evidence / remaining work |
|---|---|---|---|
| emergency | 救急事案・傷病者・出動隊員 | Partial | RUN_B_STATUS.md; final module report and acceptance evidence required |
| emergency | 救急報告・事後検証・救命処置録 | Partial | RUN_B_STATUS.md; final module report and acceptance evidence required |
| emergency | 搬送状況・搬送先・傷病分類・重症度 | Partial | RUN_B_STATUS.md; final module report and acceptance evidence required |
| emergency | CPA・処置からのCPA補助候補・アレルギー・心肺蘇生 | Partial | RUN_B_STATUS.md; final module report and acceptance evidence required |
| emergency | 時刻整合性・入力漏れ・矛盾・訂正支援 | Partial | RUN_B_STATUS.md; final module report and acceptance evidence required |
| emergency | 月次・年次・搬送先別件数割合・疾患状態別集計 | Partial | RUN_B_STATUS.md; final module report and acceptance evidence required |
| emergency | CSV/Excel既存データ移行・正式原本帳票接続 | Partial | RUN_B_STATUS.md; final module report and acceptance evidence required |
| operations | 火災・救助・救急支援・警戒・風水害・その他災害 | Completed | PR42; task-2-report.md; CI37470033732 and mainCI37470396667 SUCCESS |
| operations | 出動報告・出動隊・共通車両と隊員・時刻・活動 | Completed | PR42; task-2-report.md; CI37470033732 and mainCI37470396667 SUCCESS |
| operations | 出動手当の設定根拠・候補・Human承認・取消履歴 | Completed | PR42; task-2-report.md; CI37470033732 and mainCI37470396667 SUCCESS |
| operations | 共通事案IDによる再入力削減 | Completed | PR42; task-2-report.md; CI37470033732 and mainCI37470396667 SUCCESS |
| operations | 件数・月報・年報・正式様式と統計連携 | Partial | RUN_B_STATUS.md; final module report and acceptance evidence required |
| fire_investigation | Case・写真・動画・音声・図面・証拠管理 | Partial | RUN_B_STATUS.md; final module report and acceptance evidence required |
| fire_investigation | EXIF・重複候補・位置・図面位置紐付け | Partial | RUN_B_STATUS.md; final module report and acceptance evidence required |
| fire_investigation | 文字起こし・話者・不確実箇所・Human修正 | Partial | RUN_B_STATUS.md; final module report and acceptance evidence required |
| fire_investigation | 供述Draft・証拠比較・時系列・タイムライン | Partial | RUN_B_STATUS.md; final module report and acceptance evidence required |
| fire_investigation | 原因候補・AI候補・Human Gate・正式原因の分離 | Partial | RUN_B_STATUS.md; final module report and acceptance evidence required |
| fire_investigation | 報告Draft・正式原本帳票・Evidence追跡 | Partial | RUN_B_STATUS.md; final module report and acceptance evidence required |
| workforce | 勤務表・班・所属・勤務区分・人員配置 | Missing | RUN_B_STATUS.md; final module report and acceptance evidence required |
| workforce | 最低必要人員・救急出場可能人員・不足警告 | Missing | RUN_B_STATUS.md; final module report and acceptance evidence required |
| workforce | 年休・特別休暇・代休・休暇残数 | Missing | RUN_B_STATUS.md; final module report and acceptance evidence required |
| workforce | 勤務実績・出退勤・時間外・実績集計 | Missing | RUN_B_STATUS.md; final module report and acceptance evidence required |
| workforce | 応援配置・共通職員ID・人事異動追随 | Missing | RUN_B_STATUS.md; final module report and acceptance evidence required |
| fleet | 共通車両台帳・運行日誌・走行距離・使用と事案リンク | Completed | PR42; task-2-report.md; CI37470033732 and mainCI37470396667 SUCCESS |
| fleet | 給油・燃料受払・在庫・費用区分 | Completed | PR42; task-2-report.md; CI37470033732 and mainCI37470396667 SUCCESS |
| fleet | 点検・車検・修繕・故障履歴・修繕費 | Completed | PR42; task-2-report.md; CI37470033732 and mainCI37470396667 SUCCESS |
| fleet | 次回車検・次回点検・警告・Human故障解消 | Completed | PR42; task-2-report.md; CI37470033732 and mainCI37470396667 SUCCESS |
| fleet | 共通統計・ダッシュボード・原本帳票接続 | Partial | RUN_B_STATUS.md; final module report and acceptance evidence required |
| assets | 資機材台帳・配置・数量・共通ID | Missing | RUN_B_STATUS.md; final module report and acceptance evidence required |
| assets | ロット在庫・貸出・返却・移動履歴 | Missing | RUN_B_STATUS.md; final module report and acceptance evidence required |
| assets | 点検・修繕・更新・廃棄・耐圧検査 | Missing | RUN_B_STATUS.md; final module report and acceptance evidence required |
| assets | 使用期限・校正期限・警告 | Missing | RUN_B_STATUS.md; final module report and acceptance evidence required |
| assets | 消耗品・薬剤・在庫・発注候補 | Missing | RUN_B_STATUS.md; final module report and acceptance evidence required |
| procurement | 既存契約台帳・業者・期間・契約額・文書 | Partial | RUN_B_STATUS.md; final module report and acceptance evidence required |
| procurement | 支出・支出負担行為・見積 | Missing | RUN_B_STATUS.md; final module report and acceptance evidence required |
| procurement | 更新期限・検索・警告・年度管理 | Partial | RUN_B_STATUS.md; final module report and acceptance evidence required |
| budget | 年度・当初予算・補正・流用 | Missing | RUN_B_STATUS.md; final module report and acceptance evidence required |
| budget | 款・項・目・節・細節の科目階層 | Missing | RUN_B_STATUS.md; final module report and acceptance evidence required |
| budget | 執行額・残額・契約支出連携 | Missing | RUN_B_STATUS.md; final module report and acceptance evidence required |
| budget | 予算要求・次年度見積・集計・CSV/Excel | Missing | RUN_B_STATUS.md; final module report and acceptance evidence required |
| budget | 正式処理Human Gate・証拠・取消訂正履歴 | Missing | RUN_B_STATUS.md; final module report and acceptance evidence required |
| inquiries | 過去質問・回答案・年度検索・類似質問検索 | Missing | RUN_B_STATUS.md; final module report and acceptance evidence required |
| inquiries | 根拠資料・数値出典・関係データリンク | Missing | RUN_B_STATUS.md; final module report and acceptance evidence required |
| inquiries | AI Draft・Human確認・Evidence必須数値 | Missing | RUN_B_STATUS.md; final module report and acceptance evidence required |
| statistics | 救急・火災・救助統計 | Partial | RUN_B_STATUS.md; final module report and acceptance evidence required |
| statistics | 査察・届出・設備統計 | Partial | RUN_B_STATUS.md; final module report and acceptance evidence required |
| statistics | 人員・車両・その他業務統計 | Missing | RUN_B_STATUS.md; final module report and acceptance evidence required |
| statistics | 月次・年次・前年比較・実態調査 | Partial | RUN_B_STATUS.md; final module report and acceptance evidence required |
| statistics | 再入力不要・元データ追跡・CSV/Excel・正式原本 | Partial | RUN_B_STATUS.md; final module report and acceptance evidence required |
| document_intake | PDF・Word・Excel・CSV・画像・テキスト・音声 | Partial | RUN_B_STATUS.md; final module report and acceptance evidence required |
| document_intake | 内容に基づく文書種別・届出種別・対象物候補 | Partial | RUN_B_STATUS.md; final module report and acceptance evidence required |
| document_intake | 提出者・日付・内容・添付・入力保存先候補 | Partial | RUN_B_STATUS.md; final module report and acceptance evidence required |
| document_intake | 候補Evidence・Human確認・正式データ反映 | Partial | RUN_B_STATUS.md; final module report and acceptance evidence required |
| official_templates | 正式原本登録・版・モジュール・SHA追跡 | Partial | RUN_B_STATUS.md; final module report and acceptance evidence required |
| official_templates | DBデータ差込・PDF/Excel/Word出力 | Partial | RUN_B_STATUS.md; final module report and acceptance evidence required |
| official_templates | 各担当モジュール接続・Human状態・原本保全 | Partial | RUN_B_STATUS.md; final module report and acceptance evidence required |
| search_dashboard | 権限付き横断検索・各担当モジュール接続 | Partial | RUN_B_STATUS.md; final module report and acceptance evidence required |
| search_dashboard | 今日の作業・期限・未処理・Human Review | Missing | RUN_B_STATUS.md; final module report and acceptance evidence required |
| search_dashboard | 更新・点検・修繕・契約・予算・統計表示 | Missing | RUN_B_STATUS.md; final module report and acceptance evidence required |
| search_dashboard | 共通ヘッダー・ナビ・検索・Review・通知・ユーザー | Partial | RUN_B_STATUS.md; final module report and acceptance evidence required |

## Every-module acceptance

For each module, record concrete tests for CRUD, backend permissions, server-bound tenant separation, optimistic concurrency, audit, Human Gate, AI candidate separation (or explicit no-AI scope), actual import/export, search and shared-ID integration. SQLite-only evidence cannot establish PostgreSQL lock behavior. PC UI must expose the full operational workflow; separate apps or backend-only completeness do not pass.

## Final artifacts

Merged main code and all green CI; migrations; APIs; shared-shell UI; tests; module/permission/DB relationship/integration-point lists; explicit remaining External Gates; Completion Run B results; final INTEGRATION_HANDOFF.md. Main is the sole authority. Re-audit equivalent changes from Run A before each PR and renumber unmerged migrations on collisions.

Merged-main evidence: workflow37470396667 job112292064798 reports286 passed,168 warnings,88.90s; no skipped tests in CI. This includes the4 PostgreSQL tests skipped in the local SQLite-only environment.
