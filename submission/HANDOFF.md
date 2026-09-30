# 引き継ぎメモ（なかさん向け）

## 済んでいること
- アプリ（FastAPI + Gemini / Vertex AI）、テスト24件、README、LICENSE(MIT)、Dockerfile、deploy.sh
- 提出用の文章：`submission/texts/`（文字数は下記）
- アーキテクチャ図：`submission/diagram/architecture.png`（1920x1080）
- スクリーンショット：`submission/screenshots/`（PC・スマホ。疑似応答モードで撮影。「デモモード」の帯が写っている）
- デモ動画の台本：`submission/demo_script.md`／下書き動画：`submission/video/demo_DRAFT_mock.mp4`（疑似応答。提出には使わない）
- gcloud（587.0.0）を `~/google-cloud-sdk/bin/gcloud` に導入済み（未ログイン）

## 残っていること（順番どおり）
1. GitHub：公開リポジトリ `wirelessml/ai-no-tsukaikata` を作って push（この箱の `gh` は未ログイン。GitHub コネクタは repo 作成が 403）
2. Google Cloud：`gcloud auth login --no-launch-browser`（wirelessml@gmail.com）→ 請求先アカウントの用意（クーポン適用にはカード登録が必須）
3. `BILLING_ACCOUNT_ID=... ./deploy.sh`
4. デプロイ後：`python scripts/capture.py <URL> submission/screenshots-live` と `python scripts/record_demo.py <URL> submission/video/demo.mp4` で本物の Gemini の画面に撮り直す
5. 動画をYouTubeに上げ、Zenn の提出タブに各項目を貼る。提出ボタンと同意チェックはなかさんが押す

## 注意
- 提出後は、連携リポジトリのデフォルトブランチを12月1日まで変更しない
- 費用は自己負担。予算アラートを付ける（`BUDGET_JPY=1500 BILLING_ACCOUNT_ID=... ./deploy.sh` で作成）
