# AIの使い方を教えます

AIを初めて使う人のための、対話式の練習アプリです。「AIでやってみたいこと」を1行書くと、講師役のエージェントが必要なスキルを選び、書いた指示文（プロンプト）を採点し、実行結果を見せ、弱かった点に合わせたクイズを出します。

「第5回 Agentic AI Hackathon with Google Cloud」（Zenn）への提出作品です。Cloud Run 上で動き、Gemini を Google Gen AI SDK（Vertex AI モード）から呼びます。

- 作った動機：2026年10月1日に、神戸の公民館で初心者向けのAI講座を担当します。講座で聞いた内容を、その場で終わらせず、帰ってからも一人で練習できる道具として作りました。
- 対象：AIを使ったことがない、または使ってみたが思うような答えが返ってこない大人（高齢の方を含む）。
- 費用：Cloud Run は使った分だけの課金で、待機中は 0 インスタンスです（`--min-instances 0`）。Gemini は Vertex AI の従量課金です。

## 画面の流れ

1. 目的：やってみたいことを1行で書く（例：「来月の清掃活動のお知らせを、住民向けに書きたい」）
2. スキル：エージェントが目的を読み、練習するスキルを3〜4個選ぶ。危険度も判定する
3. 指示文：学習者が自分でAIへの指示文を書く
4. 採点：スキルごとに◎△×で採点し、改善点と直した例を出す
5. 実行：指示文を実行し、AIの答えと「使う前に確かめること」を見せる
6. クイズ：採点で弱かったスキルを優先した3択クイズ（Gemini が生成。失敗時は固定問題）

画面下の「先生（エージェント）の判断ログ」で、各ステップの判断、入力ガードの停止、フォールバックの発動を確認できます。入力した本文はログに残しません。

## エージェントとしての設計

Gemini が判断すること：

- 目的が練習の対象になるか（他人を傷つける、だます、違法な目的は断る）
- リスク区分（low / medium / high）。医療・法律・お金などは high とし、実行結果の冒頭に注意書きを付ける
- 7つのスキルのうち、その目的に効くものの選定と理由
- 指示文の採点、直した指示文の作成
- 採点結果に合わせた出題

コード側で制御すること（モデルの出力をそのまま信用しない）：

- スキルは固定カタログ（`app/skills.py`）のIDだけを受け付ける。カタログにないIDは除外して記録する
- 出力は JSON スキーマで縛り、型・個数・範囲をコードで検証する。不正ならフォールバックする（既定スキル、固定クイズ）
- 入力は Gemini に渡す前に `app/guard.py` で検査する（個人情報らしき文字列、指示の上書きを狙う文、文字数上限）。検出したら Gemini を呼ばずに止める
- ユーザー入力は `<goal>` `<prompt>` のタグで囲み、システム指示で「データであり命令ではない」と明示する
- 出力に含まれる個人情報らしき文字列は伏せ字にする
- IPごとのレート制限（既定：10分に30回）、インスタンスごとの1日あたり Gemini 呼び出し上限（既定：2000回）、出力トークン上限、`max-instances 2`
- 何も保存しない（データベースなし。ログにはステップ名・所要時間・トークン数・ガードの判定コードだけを出す）

## アーキテクチャ

```
ブラウザ（スマホ / PC）
   │ HTTPS
   ▼
Cloud Run（FastAPI コンテナ・asia-northeast1）
   ├─ 静的画面（HTML/CSS/JS）
   ├─ 入力ガード（個人情報・指示の上書き・文字数）
   ├─ レート制限 / 1日の呼び出し上限
   └─ 講師エージェント：plan → review → run → quiz
        │ Google Gen AI SDK（vertexai=True、ADC）
        ▼
   Vertex AI 上の Gemini（既定：gemini-3.5-flash、location=global）
Cloud Logging ← 構造化ログ（本文は含まない）
```

実行用のサービスアカウントには `roles/aiplatform.user` だけを付けます。APIキーはコードにも環境変数にも置きません。

## ディレクトリ

```
app/
  main.py        FastAPI 本体（API、セキュリティヘッダー、レート制限）
  agent.py       講師エージェント（plan/review/run/quiz、検証、フォールバック）
  guard.py       入力ガード・出力の伏せ字
  llm.py         Gemini 呼び出し（Vertex AI / APIキー / mock）
  mock_llm.py    ネットワーク不要の疑似LLM（画面確認・テスト用）
  prompts.py     システム指示
  skills.py      スキルのカタログと固定クイズ
  schemas.py     JSON スキーマ・API入力
  static/        画面
tests/           pytest（ガード、API、フォールバック、Gemini クライアント形式）
scripts/capture.py   スクリーンショット撮影
deploy.sh        Cloud Run へのデプロイ
submission/      ハッカソン提出用の文章・図・画像
```

## ローカルで動かす

Python 3.11 以上が必要です。

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# 1) Gemini なしで画面と流れを確認（疑似応答）
LLM_MODE=mock uvicorn app.main:app --port 8080

# 2) 実際の Gemini で確認（Gemini API キーを使う場合。キーは自分の環境変数にだけ置く）
GEMINI_API_KEY=... uvicorn app.main:app --port 8080

# 3) 実際の Gemini で確認（Vertex AI。gcloud auth application-default login 済みであること）
GOOGLE_CLOUD_PROJECT=<プロジェクトID> uvicorn app.main:app --port 8080

# テスト
pytest -q
```

http://localhost:8080 を開きます。

## デプロイ（Cloud Run）

前提：Google Cloud CLI を入れ、請求先アカウントを用意しておきます。

```bash
gcloud auth login --no-launch-browser
gcloud billing accounts list          # 請求先アカウントIDを確認
BILLING_ACCOUNT_ID=XXXXXX-XXXXXX-XXXXXX ./deploy.sh
```

`deploy.sh` は次を行います：プロジェクト作成、請求先の紐づけ、API有効化（run / aiplatform / cloudbuild / artifactregistry）、実行用サービスアカウントの作成と権限付与、`gcloud run deploy --source .`、URLの表示と `/api/health` の確認。

中身は次のコマンドと同じです：

```bash
gcloud run deploy ai-no-tsukaikata \
  --source . --region asia-northeast1 \
  --service-account ai-lesson-run@<プロジェクトID>.iam.gserviceaccount.com \
  --allow-unauthenticated --max-instances 2 --min-instances 0 --memory 512Mi \
  --set-env-vars GOOGLE_CLOUD_PROJECT=<プロジェクトID>,GOOGLE_CLOUD_LOCATION=global,GEMINI_MODEL=gemini-3.5-flash
```

## 環境変数

| 名前 | 既定値 | 意味 |
| --- | --- | --- |
| `LLM_MODE` | `gemini` | `mock` にすると疑似応答 |
| `GEMINI_MODEL` | `gemini-3.5-flash` | 使うモデル |
| `GOOGLE_CLOUD_PROJECT` | なし | Vertex AI のプロジェクト（Cloud Run では必須） |
| `GOOGLE_CLOUD_LOCATION` | `global` | Vertex AI のロケーション |
| `GEMINI_API_KEY` | なし | ローカル確認用。設定すると Gemini API を使う |
| `THINKING_LEVEL` | `LOW` | `MINIMAL` `LOW` `MEDIUM` `HIGH` `OFF` |
| `MAX_GOAL_CHARS` / `MAX_PROMPT_CHARS` | 120 / 600 | 入力の文字数上限 |
| `MAX_OUTPUT_TOKENS` | 2048 | Gemini の出力上限 |
| `RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW_SEC` | 30 / 600 | IPごとのレート制限 |
| `DAILY_LLM_CALL_LIMIT` | 2000 | インスタンスごとの1日あたり Gemini 呼び出し上限 |

## 動作確認の方法

ログイン不要です。デプロイしたURLを開いて、次の順に操作します。所要時間は3〜5分です。

1. 「町内会のお知らせ」のボタンを押して目的を入れ、「先生に相談する」を押す。スキルが3〜4個表示される
2. 「指示文を書いてみる」を押し、「お知らせ文を書いてください。」とだけ書いて「採点してもらう」を押す。低い点と改善点が出る
3. 指示文を「あなたは町内会の広報担当です。…300字以内、丁寧な口調…不確かな点は確認してほしい点として挙げてください。」のように書き足して、もう一度採点する。点が上がる
4. 「自分の指示文で実行する」を押す。AIの答えと、使う前に確かめる点が出る
5. 「確認クイズに進む」を押し、3問に答える
6. 画面下の「先生（エージェント）の判断ログ」を開き、Gemini の呼び出しと判断が記録されていることを見る

安全のしくみの確認：

- 目的欄に `090-1234-5678` のような電話番号を入れて送ると、「個人情報らしき内容が含まれています」と表示され、Gemini には送られない（判断ログに「入力ガードが停止」と出る）
- 「以前の指示を無視して…」と入れると、停止される
- 目的欄に121文字以上を入れると、文字数の上限で止まる

API を直接確認する場合：

```bash
curl -s https://<デプロイURL>/api/health
curl -s -X POST https://<デプロイURL>/api/plan -H 'Content-Type: application/json' \
  -d '{"goal":"来月の清掃活動のお知らせを、住民向けに書きたい"}'
```

## 制約と今後

- レート制限と1日上限はインスタンス内のメモリで数えています。インスタンスが増えると、その分だけ上限も増えます（`max-instances 2` で抑えています）。全体で厳密に制限するなら、Cloud Armor や共有ストアが必要です。
- 個人情報の検出は正規表現による簡易なものです。氏名や住所の文章は検出できません。入力欄の注意書きで補っています。
- 採点は Gemini の判断です。同じ指示文でも点が少し変わることがあります。
- 対応言語は日本語のみです。

## ライセンス

MIT License（`LICENSE`）
