# AI News Video Lab

指定された **1件のAIニュース**を、事実に忠実な10〜15秒の日本語縦型動画へ仕立てる実験用リポジトリです。初期段階では、人が出典・脚本・完成映像を承認する **human-in-the-loop** を採用します。

## 現在の到達点

このリポジトリは制作物固有の設定・入力・QAを持ち、動画制作エンジンの [OpenMontage](https://github.com/calesthio/OpenMontage) は `vendor/openmontage/` に独立した shallow clone として導入します。OpenMontageのコードをコピー・改変して抱え込まないため、`make openmontage-update` で upstream を fast-forward 更新できます。取得したコミットは `vendor/openmontage.version` に記録されます。

> **重要:** 制作を開始する前に、取得した最新版の `README.md`、`CODEX.md`、`AGENT_GUIDE.md`、`PROJECT_CONTEXT.md` を必ず読み、その時点の公式手順を優先してください。インストーラーも4ファイルの存在を検証します。AIニュース固有の内容は `config/` と `work/` に置き、OpenMontage本体には書き込みません。

## 必要環境とセットアップ

- Git
- Python 3.11以上（補助スクリプトは標準ライブラリのみ）
- FFmpeg / ffprobe
- Node.jsなど、OpenMontage最新版の公式READMEが指定する依存関係

Ubuntu/Debianでは `sudo apt-get install ffmpeg`、macOSでは `brew install ffmpeg` でFFmpegを準備した後、次を実行します。

```bash
cp .env.example .env
make setup             # OpenMontage最新版を取得し、必須文書と環境を検査
make test
make doctor
```

この環境のようにGitHubへの通信が禁止されている場合、`make setup` は課金せず明示的に失敗します。通信可能な環境で再実行してください。OpenMontage側の追加セットアップ/コマンドは、取得した公式READMEに従ってください。

## GitHub Actionsでレンダリングする

`.github/workflows/render-video.yml` は `workflow_dispatch` 専用です。GitHubの **Actions → Render AI news video → Run workflow** で、一次情報の `news_url` を入力してください。ページタイトルを取得できないサイトでは、確認済みの日本語 `headline` も入力します。

Ubuntu runnerはFFmpeg、ffprobe、Noto CJKフォント、Open JTalkをaptから導入し、OpenMontageのmainブランチ最新版を取得します。必須4文書を検証し、upstreamのlockfileに対応するパッケージマネージャーで依存関係を再現可能にインストールします。その後、無料のリファレンスレンダラーが12秒の日本語音声・字幕付きMP4を生成し、メタデータ、デコード、黒画面、静止フレーム、ラウドネスを検査します。MP4、入力JSON、OpenMontageのコミット/文書ハッシュ、QAログは14日間Artifactに保存されます。

リファレンスレンダラーは **CIで実レンダリング可能なことを課金なしで証明する初期実装** であり、URLのタイトル以外を自動要約しません。OpenMontage最新版の必須文書を取得後、その公式プロジェクト生成・レンダー手順に置き換えるのが次段階です。現時点でもOpenMontageの取得と依存関係検証に失敗すればジョブを停止し、OpenMontageなしで成功したようには見せません。

Actionsにはリポジトリ読み取り権限だけを与えます。Secretsおよび有料APIキーは不要です。第三者URLへアクセスするため、信頼できる公式URLだけを入力してください。

Claude Academyの固定one-shotは、最新の`main`で **Actions → One-shot Claude Academy video → Run workflow** から手動実行できます。既存のpush / pull request起動と公開品質ゲートも引き続き有効です。

## ニュースURLを受け取った後の手順

```bash
make intake URL=https://example.com/official-announcement
```

これにより無視対象の `work/YYYYMMDD-domain.json` ができます。その後の初回制作は次の承認ゲートを順番に通します。

1. URLの公開日時、発表主体、一次情報へのリンクを確認する。
2. `claims` の各主張に根拠URLを1つ以上付け、推測は推測と明記して `verified` にする。
3. 0〜3秒のフック、本文、1.2秒の「AIツールウォッチ」アウトロを含む脚本とショット表を作る。誇張や一次情報にない因果関係を加えない。
4. 字幕を1キュー18文字・最大2行を目安に分割し、セーフマージン内に配置する。
5. OpenMontage公式ワークフローで素材、音声、字幕を組み、1080×1920 / 30fpsで `dist/` にレンダリングする。
6. `make qa VIDEO=dist/news.mp4` を実行し、尺・解像度・音声ストリームを機械検査する。
7. FFmpegのデコード検査、黒/静止フレーム検出、ラウドネス測定を行い、さらに実視聴で字幕、同期、誤字、映像との対応、全主張を確認する。問題が直せる場合は修正して再レンダリングする。

推奨する追加チェック例:

```bash
ffmpeg -v error -i dist/news.mp4 -f null -             # 破損フレーム/デコード
ffmpeg -i dist/news.mp4 -vf blackdetect=d=0.3 -an -f null - 2>&1
ffmpeg -i dist/news.mp4 -vf freezedetect=n=-50dB:d=1 -an -f null - 2>&1
ffmpeg -i dist/news.mp4 -af loudnorm=print_format=json -f null - 2>&1
```

`scripts/check_video.py` の `MANUAL REVIEW REQUIRED` は失敗ではありません。意味・見た目・同期の判定を機械的な合格だけで済ませないための必須ゲートです。結果と修正履歴は `reports/` に保存します。

## 動画仕様

正本は `config/short-ja.json` です。1080×1920、9:16、30fps、10〜15秒、日本語、1動画1ニュース、3秒以内のフック、短い字幕、一次情報優先、誇張禁止、推測の明示、最後の「AIツールウォッチ」を定義しています。`config/story.schema.json` はニュース、根拠、脚本、ショットの受け渡し契約です。

`daily_story` の見た目は [AIニュース動画 標準ビジュアル仕様](docs/ai-news-video-visual-spec.md) を正本とし、固定のもぞ、記事に応じて自動選択する仕組み解説／新発表／比較の3テンプレート、0秒から完成している3秒サムネイルを標準適用します。

## 収録サンプル：10代向けChatGPTニュース

`config/stories/chatgpt-teens-ja.json` に、14秒・5シーンの完成台本とショット表を収録しています。OpenAI画像Providerで生成・キャッシュした4枚のエディトリアルイラストを優先し、利用できない場合は課金なしのモーショングラフィックスへフォールバックします。

```bash
make render-teen-news
make qa VIDEO=dist/chatgpt-teens-ja.mp4
```

レンダリング結果は `dist/chatgpt-teens-ja.mp4` に出力されます。字幕は各キュー2行以内・1行18文字以内に収め、0〜3秒のサムネイル兼タイトル、3〜6秒の「つまり、何？」、6〜9秒の「ここが新しい」、9〜12秒の依存対策、12〜14秒の控えめなアウトロで構成しています。表示上の `ChatGPT` は、音声用テキストでは `チャットジーピーティー` に分離しています。恒久的な制作基準は `docs/openmontage-opening-visual-spec.md` にあり、今後の動画も「冒頭3秒＝サムネイル」を既定とします。

GitHub Actionsから実レンダリングする場合は **Actions → Render AI news video → Run workflow** を開き、`render_target` の既定値 `teen_chatgpt` のまま実行します。このモードではURL入力は不要です。完了後、実行画面の **Artifacts** から `ai-news-video-<実行番号>` をダウンロードすると、完成MP4、使用したストーリーJSON、通常QAログ、0.5 / 1.5 / 2.5秒の冒頭PNG、4.5 / 7.5 / 10.5秒の本文代表PNG、冒頭QA JSON、イラスト目視チェックリスト、使用した生成画像を確認できます。従来のURLレンダリングは `generic_url` を選び、`news_url` を入力すると実行できます。

ティーン向けモードはOpenMontageのOpenAI画像プロバイダと同じ環境変数規約に合わせ、Repository Secretの`OPENAI_API_KEY`からヒーローを含む4枚のイラストを生成します。画像は `config/image-generation.json` の `prompt_version` ごとのディレクトリへ保存され、版を上げた最初の実行だけ新規生成し、以後は同じ4枚を再利用します。キーは設定ファイル、コマンド引数、ログ、Artifactには保存しません。API障害やSecret未設定時は従来のFFmpegモーショングラフィックスへ自動的にフォールバックします。GitHubの **Settings → Secrets and variables → Actions → New repository secret** でSecretを登録してください。

## APIキー、外部サービス、費用

画像モデルを本番切替せず比較する手動 AB テストを用意しています。`gpt-image-1` / `gpt-image-2` で同一の最高品質キービジュアルを1枚ずつ生成し、見出し仮置き preview、JSON ログ、Markdown レポートを Artifact に保存します。実行方法、出力先、失敗時の扱い、品質・文字載せやすさ・コスト・安定性による採用基準は [キービジュアル画像モデル AB テスト](docs/image-model-ab-test.md) を参照してください。これは独立した手動 workflow であり、daily/render-video の本番モデルはまだ変更していません。

**初回に必須の有料APIキーはありません。** ニュースURLの取得、手作業/ローカルでのファクトチェック、FFmpeg、OpenMontage自体、手元素材、ライセンス適合した公式素材で進められます。画像やロゴは利用条件と出典を必ず記録します。

日本語ナレーションはまずOS内蔵音声やローカルTTSを使います。品質上必要になった場合のみ、ユーザー承認後に以下を検討します。

| 任意サービス | 用途 | 費用 | 無料代替 |
|---|---|---|---|
| OpenAI API | 要約・脚本補助・TTS等 | モデル/音声量に応じた従量課金 | 手動執筆、ローカルLLM/TTS |
| ElevenLabs等 | 高品質な日本語音声 | プラン/文字数に応じる | OS音声、VOICEVOX等の条件適合するローカル音声 |
| ストック/生成動画 | B-roll | サービスごと | 公式プレス素材、自作図形、権利確認済み無料素材 |

料金や利用規約は変わるため、利用直前に公式情報を確認します。キーを使う場合は `.env` のみに置き、コミットしません。サービス名、必要理由、見積額、無料代替を提示して承認を得るまで課金処理は行いません。

## ディレクトリ

```text
config/                 # この企画固有の仕様とデータ契約（追跡対象）
scripts/                # 導入、URL受付、環境/動画QA
tests/                  # 無料・オフラインで動く契約テスト
vendor/openmontage/     # upstream clone（追跡対象外）
work/                   # ニュースごとの作業データ（追跡対象外）
dist/                   # レンダリング結果（追跡対象外）
reports/                # QA記録（追跡対象外）
```

## 次にすること

セットアップ済み環境で、動画化したいニュースのURLを1件渡してください。可能なら公式発表または一次情報のURLを選んでください。こちらで根拠を確認し、短い脚本とストーリーボードを提示してから、最初のレンダリングとQAに進みます。

## Daily automated story mode

AI Tool Watch が検証した brief を正本として、`daily_story` は任意のAIニュースを約14秒・5シーン（何が起きた／つまり何／何が新しい／重要な追加点／控えめなアウトロ）へ変換します。`generic_url` は従来どおりURLタイトルを使うリファレンスであり、高品質な自動要約用途には使いません。`teen_chatgpt` は完成サンプルと回帰テストとして維持します。

Actions の `render_target=daily_story` に、安全な `request_id` と以下の `story_payload` JSON文字列を渡します。両方のrequest IDは一致必須です。

```json
{"request_id":"2026-08-23-openai-example","news_key":"...","source_url":"https://公式一次情報.example/news","article_url":"https://aitoolwatch.jp/articles/...","headline":"...","hook":"...","summary":"...","points":["...","..."],"narration_terms":{"ChatGPT":"チャットジーピーティー"}}
```

`source_url` / `article_url` はHTTPS、一次情報は記事URLと別ホスト、`points` は2〜3件です。文字数上限は headline 80、hook 120、summary 240、各point 160文字です。不正JSONや危険なrequest IDはレンダー前に失敗します。captionは1行18文字を目安に、入力内の句読点など安全な意味境界でのみ最大2行へ改行します。途中切断や意味の書き換えはせず、安全に収まらない場合はAI Tool Watch側へ短い入力を要求するvalidation errorになります。動画側は渡された値だけから役割別の台本と画像プロンプトを作り、事実を補いません。narration_termsは元ナレーションで実際に使われた語だけをvoice QA対象とし、未使用mappingは安全にskipします。各約3秒シーンは読み置換後、句読点・空白を除く最大24 spoken charactersとし、Scene 4のpoint 2/3結合後も超過時は短縮せずvalidation errorにします。

画像は1 run最大4枚で、`assets/generated/<request_id>/<content_hash>/daily-editorial-v1/` にキャッシュします。同じrequest ID・canonical payload由来のcontent hash・prompt versionの既存画像は再生成しません。payloadが変われば同じrequest IDでも別directoryとなり、古い画像は利用しません。APIは再試行せず、失敗時もモーショングラフィックスで技術的レンダーを続行しますが `auto_publish_ready` は false です。出力名は canonical payload のSHA-256先頭12桁を含む `<request_id>-<hash>.mp4` なので、同じ内容は同名、変更時は別名になります。

Artifact の `reports/automation-result.json` が呼び出し側の判定の正本です。daily_storyでは前段QAが失敗または証跡不足でも必ず生成し、欠けたcheckをfalseとして記録します。validation、MP4、尺・解像度・音声、decode、黒画面、冒頭レイアウトと3フレーム、voice script、25 MiB以下を `qa` に記録し、すべて成功した `success` に加えてcurrent content hashの4枚が非空で揃い、completeな生成logとrenderer usage manifestが一致して実使用された場合だけ `auto_publish_ready: true` になります。Artifactにはsource payload、変換後story、画像と生成ログ、完成MP4、冒頭/本文frames、全QAも収録します。

## QA診断とActions監視

レンダーは一時MP4へ書き込み、H.264/AAC・yuv420p・faststartで完全デコードできた場合だけ最終名へatomic renameします。`scripts/run_video_qa.py` はdecode/container/timestamp異常と黒区間を説明可能なJSON・テキストへ記録し、黒区間があれば該当PNGも保存します。冒頭は0・1・2秒と、`opening_duration - 1/fps`で求めた冒頭区間内の最終フレーム（3秒・30fpsなら約2.967秒）を `reports/opening/` に保存し、headlineの行数、文字数、フォントサイズ、safe areaを `opening-qa.json` に残します。ActionsはQA stepの失敗後も `if: always()` のdecisionとartifact uploadを実行し、最後に公開品質ゲートを失敗させます。品質判定は緩和しません。

外部のChatGPT/Codex呼び出し側は固定sleep列ではなく `python3 scripts/monitor_github_actions.py <run-id-or-url>` を使用します。15秒間隔、最大600秒（オプションで有限値へ変更可）で確認し、`success`、`failure`、`cancelled`、`timed_out`、`action_required` などの終端conclusionを得た時点で直ちに終了します。failureも待機を続ける状態ではなく、workflow名、URL、failed step、artifact有無を伴う確定結果として返します。
