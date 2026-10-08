# 財務処理の業務キュー連携

## 範囲

章27・36の内部Partialを減らす限定Slice。章全体のCompleted、10本のCross-module E2E、完成Releaseの証拠ではない。

「今日の業務」は財務提案の原記録ID・版・状態・関係・必要権限だけを参照する。金額、理由、科目名、契約名、原本名は複製しない。自分が作成した未正式承認の提案と、現在の権限でHuman確認・正式承認できる提案を表示する。取消・正式承認済みは対象外。

## 使用手順

1. ログインして「今日の業務」を開く。
2. 財務・予算のカードで「元記録を開く」を選択する。
3. 既存の「契約・調達・予算」画面で現時点の金額・残額・原本・状態を確認する。
4. 確認・正式承認は既存画面のHuman操作で行う。キューには変更・承認APIを追加していない。
5. 取消・正式承認後は再読込する。「自分が作成・借用したもの」では自分が作成した財務提案に限定する。

## 安全境界

- finance.read、document.read、原本・関連契約の推移的な必要権限を確認し、対象を除外してから件数・ページングする。
- module.budget.enabled=falseでは財務カードを出さない。無効モジュールの過去原記録を読む一般方針（章46）は決定していない。
- 元画面は固定allowlistから開き、応答のURLや関数名は実行しない。
- 権限・セッション再確認、原画面のHuman Gate・楽観ロック・監査は既存実装を維持する。
- 別の操作が所有する画面へ、権限確認・一覧・提案・残額の旧応答を反映しない。
- 複数業務間の原子的snapshotではない。並行変更は再読込で反映し、正式操作では原サービスが現在の根拠と版を再照合する。
- DB追加・migration追加・依存パッケージ追加はない。本部別DB・実行環境・原本・バックアップ分離は変更しない。

## 検証

新規財務キューAPI試験は実FastAPI・認証・RBAC・合成SQLiteデータを使用。金額・原本情報非露出、作成者/権限関係、取消・正式承認後の除外、承認権限のない作成者の確認済み提案、権限失効、module flag、件数・ページング前の除外、契約原本の対象物権限を検証する。レビューで反対仕訳・支出負担・請求の間接根拠の追跡漏れを再現し、共通の推移的権限処理で修復した。請求→検収等の参照も訪問済み集合で循環を防ぎながら追跡する。

本番JavaScriptを実行する状態試験は4地点の遅延応答でREDを確認し、所有権検査追加後に成功した。HTTP/DOMのみ合成で、Chromiumの証拠ではない。

既存Chromiumの業務キューjourneyには財務カード→実財務画面→Human操作権限→取消後再読込を追加した。実Chromium/PostgreSQL・PR/main CI結果は実行後のEvidenceに記録する。skipを成功と数えない。

残差: 財務候補・契約/請求期限のキュー、章27の残り正式仕様、章36の全モジュール対応、実運用規模性能測定は未完。

## CI再開とセッション試験の修復（2026-10-09 JST）

リポジトリをpublicへ変更後、PR #80 head `46b57e75ed0177ad52f81158f172cb6fab09d262` の run `37700838286` attempt 3は実際に起動した。過去の課金・利用制限による起動前失敗とは区別する。

- backend-tests job `113584198257`: 成功、実PostgreSQLを含む `1212 passed / 96 skipped`。Migration parser、JavaScript syntaxも成功。
- administration-browser job `113584198465`: `1 failed / 71 passed`。失敗は既存 `test_hazardous_browser.py` の同一職員・新セッション試験。run全体は失敗であり、このheadをmergeできない。

原因を実 `shared-session.js` と `hazardous.js` で再現した。背景の権限・セッション照合が先にresetした場合、旧試験が呼ぶownerなしの新規 `hazardousList` は新セッションの新規画面を開く。実画面の旧ボタンは元ownerを保持しており、背景reset後には取得・再表示を行わない。修復はセッション変更前に実 `hazardousListNav.onclick` を捕捉し、その同じ旧操作を変更後に実行する。modal消去・login表示・権限キャッシュ消去のassertionは維持する。遅延や無条件再実行は追加しない。

状態回帰試験では、背景resetが操作前に起きる場合と、旧操作の照合中に起きる場合の両方で、modalなし・権限0・危険物原記録の追加取得0を確認する。危険物状態試験はローカル `25 passed`。本番セッション処理・RBAC・Human Gateは変更していない。新headの実Chromium・全CI結果は別途検証するまで未完。

修復head `d18de9bba8c62e369ea183d0d42d4145b9f04edf` の run37858927140も、実backendは成功したが、Chromiumは同じmodal assertionで1failed/71passed。先のタイミング説明だけでは実失敗の解消を証明できない。追加の試験不備として、handler保存の代入式が関数値を返し、Playwright自身がその関数を実行していた。[公式page.evaluate契約](https://playwright.dev/python/docs/api/class-page#page-evaluate)とインストール済Playwrightの実UtilityScriptで、保存だけのつもりがviewGenerationを1→2へ進めるREDを再現。返り値なしの関数で保存する形に直すと、この実評価器のprobeはGreen。評価器内部への依存は恒久テストに追加せず、native journey自身で保存後も変更履歴画面のままであることを確認する。

さらに実ブラウザのauth/contextとHTTP fixtureの新session IDが一致することを確認し、modal失敗時は合成UI/非秘密session ID/page errorの診断と合成screenshotを残す。Cookie/tokenは出力しない。ブラウザ試験の選択集合は全16ファイルを維持し、危険物を先頭にして失敗時だけ停止する。Green時は全選択を実行する。新headのnative/full CI成功までmergeしない。

head `a0937930e21e4899fa61211028b0dd1b9a97f2e7` の run37860714550の先頭native試験は87.62秒で同じmodal assertionに失敗した。browser/HTTP両者の新session UUID一致は実測でき、Cookie共有の不一致は本失敗を説明しない。UIには権限140・login非表示が残り、page errorは空だった。次の診断では、元の所有権検査とresetを必ずそのまま呼ぶwrapperで、ticket/current generationとreset開始・終了・例外だけを記録する。正式データ・Cookie・token・権限処理は変更しない。原因が未確定の段階で成功扱いしない。
