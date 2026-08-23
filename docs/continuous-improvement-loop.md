# AIニュース動画 継続改善ループ

日次公開と改善実験を分離し、**毎日の公開を止めずに、週1回だけ品質改善を回す**ための運用ルールです。

## 役割分離

- **日次公開**: AI Tool Watch側の `Publish daily video article` が毎朝7:10 JSTに実行する。最新の公開済み記事を動画化し、`ai-news-video` の最新mainとbounded self-healを使い、`auto_publish_ready: true` の場合だけ記事・動画を公開する。
- **復旧**: 画像生成、レンダー、opening、decode、black frame、容量など回復可能な制作失敗は、既存の `self_heal_daily_video.py` が最大2回だけ復旧する。事実・voice・headline truthなど意味に関わるゲートは自動で迂回しない。
- **継続改善**: `Weekly AI news visual improvement` が毎週月曜8:40 JSTに、現在のmainで同じ基準動画を実レンダーし、4枚のopening frameと公式もぞ設定資料をAIのcritical reviewerへ渡す。

## 週次レビューの評価軸

1. `stopping_power` — スマホのスクロールを止める強さ
2. `mobile_readability` — 見出しと情報階層を一瞬で読めるか
3. `topic_visual_clarity` — 汎用カードではなく、そのニュース内容が絵から分かるか
4. `mozo_consistency` — 公式もぞと一致し、自然に解説役として入っているか
5. `series_identity` — 毎回「もぞのAIニュース」と分かる統一感
6. `originality` — 他Shortsや媒体の強い模倣になっていないか

レビューは1〜10点で採点し、**その週に直す項目を必ず1件だけ**選びます。改善IssueはISO週ごとに1件だけ作成／更新し、Actionsの証拠、平均点、各評価、最優先改善、候補ファイルを残します。

## 重要な安全ルール

- 週次レビューやAIレビューAPIが失敗しても、日次公開ワークフローは影響を受けない。
- 週次レビューはmainへcommit/push/mergeしない。改善案をIssue化するだけ。
- 1改善=1PRを原則にする。複数のデザイン変更を一度に入れない。
- 改善PRは必ずunit/static checksと実レンダーを通す。
- 0 / 1 / 2 / 2.967秒のopening frameを比較し、変更前より悪化していないことを確認する。
- story validation、voice QA、headline semantic match、opening QA、decode、black frame、size、`auto_publish_ready` は一切緩めない。
- 設定資料 `mozo-character-reference.png` 自体を動画へ合成せず、動画には承認済みの `mozo-opening.png` を使う。

## 改善の採用基準

改善PRは、既存QAが全PASSしたうえで、週次レビューの最優先課題を明確に改善している場合だけ採用します。主観的な派手さより、スマホでの理解速度、ニュース固有の図解、もぞのシリーズ性を優先します。

日次公開は「今の十分な品質を積み上げるレーン」、週次改善は「次の1段だけ良くするレーン」として運用し、改善のために公開を止めないことを最優先とします。
