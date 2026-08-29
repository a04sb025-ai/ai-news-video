# キービジュアル画像モデル AB テスト

## 目的と範囲

`gpt-image-1` と `gpt-image-2` を、同じ検証済みニュース、同じプロンプト、サイズ、品質で **キービジュアル1枚だけ** 生成して比較する。高品質を維持しながら本番自動運転のコストを最適化できるかを人が判断するための実験であり、日次レンダーや `generate_story_images.py` のモデル、画像枚数、フォールバック動作は変更していない。

## Actions から実行する

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

## 採用判断

複数ニュースで、(1) 内容が一目で伝わる品質、(2) スマホでの主役の強さと文字の載せやすさ、(3) 実測コスト、(4) API の成功率・生成時間・安定性を比較する。十分なサンプルをレビューし、価格は判断時点の公式情報で再確認してから、別の変更として本番モデル切替を検討する。
