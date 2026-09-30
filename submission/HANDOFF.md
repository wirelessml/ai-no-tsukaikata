# 引き継ぎメモ（なかさん向け）

## 済んでいること
- アプリ（FastAPI + Gemini / Vertex AI）、テスト24件（現在も24件）、README、LICENSE(MIT)、Dockerfile、deploy.sh
- 提出用の文章：`submission/texts/`（文字数は下記）
- アーキテクチャ図：`submission/diagram/architecture.png`（1920x1080）
- スクリーンショット：`submission/screenshots/`（PC・スマホ。デプロイ済みURLから本物の Gemini の応答で撮影。「デモモード」の帯なし）
- デモ動画：`submission/video/demo.mp4`（デプロイ済みURLで録画。ナレーション・字幕付き。台本は `submission/demo_script.md`）
- gcloud（587.0.0）を `~/google-cloud-sdk/bin/gcloud` に導入済み（wirelessml@gmail.com でログイン済み）
- GitHub：https://github.com/wirelessml/ai-no-tsukaikata に push 済み

## デプロイ情報（2026-09-30 時点）
- URL：https://ai-no-tsukaikata-7d47rhuteq-an.a.run.app （別名 https://ai-no-tsukaikata-1091564391492.asia-northeast1.run.app）
- プロジェクトID：`project-729e5437-4b92-4165-b5d`（番号 1091564391492）／請求先アカウント 01357E-7C3592-8069FC
- サービス：Cloud Run `ai-no-tsukaikata`（asia-northeast1、max-instances 2、min-instances 0、512Mi）
- モデル：`gemini-3.5-flash`（Vertex AI、location=global で動作確認済み）
- ヘルスチェック：`/api/health`（`*.run.app` では `/healthz` は Google 側で 404 になるため追加。ローカルでは `/healthz` も可）
- 予算アラート：月 1,500 円、50%/90%/100% で通知（請求先アカウントの予算 `ai-no-tsukaikata`）
- 再デプロイ：`PROJECT_ID=project-729e5437-4b92-4165-b5d ./deploy.sh`

## 後片付け（審査終了後）
- 審査期間（〜2026-12-01）が終わったら、費用を止めるためプロジェクトごと削除する：
  `gcloud projects delete project-729e5437-4b92-4165-b5d`
  （削除するとURLも無効になる。30日以内なら復元できる）。あわせて予算 `ai-no-tsukaikata` も削除してよい
- 審査が終わるまでは削除しないこと（審査員がURLを開く）

## 残っていること（順番どおり）
1. $300 クーポンの適用を確認する（請求先アカウントに紐づいているか）
2. 動画（`submission/video/demo.mp4`）をYouTubeに上げ、Zenn の提出タブに各項目（`submission/texts/`）を貼る。画像は `submission/screenshots/` と `submission/diagram/architecture.png`。提出ボタンと同意チェックはなかさんが押す

## 注意
- 提出後は、連携リポジトリのデフォルトブランチを12月1日まで変更しない
- 費用は自己負担。予算アラートは作成済み（上記）
