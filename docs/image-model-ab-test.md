# キービジュアル画像モデル AB テスト

## 目的と範囲

`gpt-image-1` と `gpt-image-2` を、同じ検証済みニュース、同じプロンプト、サイズ、品質で **キービジュアル1枚だけ** 生成して比較する。高品質を維持しながら本番自動運転のコストを最適化できるかを人が判断するための実験として導入した。

2026-08-30 の比較結果を受け、本番画像生成の標準モデルは `gpt-image-2` に変更した。AB テスト機構は今後の再比較・回帰確認のため、そのまま維持する。

## 本番モデルと切り戻し

本番の標準画像モデルは `config/image-generation.json` の `model` で管理する。

```json
{
  "model": "gpt-image-2"
}
```

`generate_story_images.py` はこの設定値を参照するため、通常の daily story と収録サンプルを含む生成画像は `gpt-image-2` を使用する。品質問題、API障害、運用上の都合などで切り戻す場合は、同じ設定を次のように戻す。

```json
{
  "model": "gpt-image-1"
}
```

モデル名を生成スクリプトへ直接ベタ書きせず config で管理することで、コードロジックを変更せずに切り戻せる。サイズ `1024x1536`、品質 `high`、既存のプロンプト、フォールバック動作は今回変更しない。

## Actions から AB テストを実行する

1. GitHub の **Actions → AB test image models → Run workflow** を開く。
2. 通常は `story_json_path` と `payload_json_path` を空欄にし、`payload_json` に verified payload の JSON 本文を直接貼り付ける。GitHub Actions は checkout されたファイルしか参照できないため、ローカル専用や gitignore 対象の `work/.../story.json` をパス指定しても読めない。
3. リポジトリへコミット済みの prepared `story.json` がある場合のみ `story_json_path` を使う。コミット済みの verified payload を使う場合は `payload_json_path` を使う。入力優先順位は `story_json_path` → `payload_json_path` → `payload_json`。
4. 必要なら `request_id` を指定する。`models`（既定 `gpt-image-1,gpt-image-2`）、`size`（`1024x1536`）、`quality`（`high`）は通常そのまま実行する。
5. Repository Secret `OPENAI_API_KEY` が必要。片方が未対応または API エラーになっても他方の処理と成果物保存は続き、workflow の最後は「比較不能」として失敗する。別モデルへの暗黙のフォールバックはしない。

`payload_json` の最小例:

```json
{
  "request_id": "2026-08-29-image-ab-test",
  "source_url": "https://example.com/official-source",
  "article_url": "https://aitoolwatch.jp/articles/example",
  "headline": "検証済みのニュース見出し",
  "hook": "冒頭で伝える短いフック",
  "summary": "ニュースの検証済み要約",
  "points": ["重要ポイント1", "重要ポイント2"]
}
```

ローカルでも Pillow と API key を用意して実行できる。

```bash
OPENAI_API_KEY=... python3 scripts/ab_test_image_models.py \
  --story-json work/daily/story.json \
  --models gpt-image-1,gpt-image-2 --size 1024x1536 --quality high
```

## 成果物

Artifact（30日保持）とローカルの `assets/generated/ab-tests/<request_id>/<content_hash>/` に次を作る。

```text
gpt-image-1/key-visual.png
gpt-image-2/key-visual.png
preview-gpt-image-1.png
preview-gpt-image-2.png
comparison-log.json
comparison-report.md
```

preview は opening caption に近い短い見出しを仮置きするだけで、生成画像や本番動画を変更しない。レポートは画像を相対パスで表示し、生成時間、モデル別エラー、人間レビュー用チェックリストを収録する。

## 採用判断と今後の確認

初回の比較では `gpt-image-2` が画質・質感で優位、2回目の30B級モデル題材では画質に加えて「性能と扱いやすさのバランス」という主題を文字なしの視覚比喩で表現できたため、標準モデルとして採用した。

本番切替後も、(1) 内容が一目で伝わる品質、(2) スマホでの主役の強さと文字の載せやすさ、(3) 実測コスト、(4) API の成功率・生成時間・安定性を継続確認する。問題が出た場合は上記 config の `model` を `gpt-image-1` に戻して切り戻す。
