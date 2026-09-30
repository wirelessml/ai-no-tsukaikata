#!/usr/bin/env bash
# Cloud Run へのデプロイ（プロジェクト作成・API有効化・権限付与・デプロイ・URL表示）
#
# 事前に、次を自分で済ませておく（このスクリプトはログインしない）:
#   1) gcloud auth login --no-launch-browser
#   2) 請求先アカウント（クレジットカードまたはハッカソンのクーポンを紐づけたもの）を作成しておく
#        確認: gcloud billing accounts list
#
# 使い方:
#   BILLING_ACCOUNT_ID=XXXXXX-XXXXXX-XXXXXX ./deploy.sh
#   （既存プロジェクトを使うなら PROJECT_ID=既存のID も付ける。BILLING_ACCOUNT_ID は未リンクのときだけ必要）
#
# 任意の環境変数:
#   PROJECT_ID     既定: ai-no-tsukaikata-<乱数5桁>（初回に作成。2回目以降は .deploy-project に保存した値を使う）
#   REGION         既定: asia-northeast1
#   SERVICE        既定: ai-no-tsukaikata
#   GEMINI_MODEL   既定: gemini-3.5-flash
#   BUDGET_JPY     指定すると、その金額（円）で予算アラートも作成（50%/90%/100%）
set -euo pipefail
cd "$(dirname "$0")"

GCLOUD="${GCLOUD:-gcloud}"
command -v "$GCLOUD" >/dev/null 2>&1 || GCLOUD="$HOME/google-cloud-sdk/bin/gcloud"
command -v "$GCLOUD" >/dev/null 2>&1 || [ -x "$GCLOUD" ] || { echo "gcloud が見つかりません"; exit 1; }

REGION="${REGION:-asia-northeast1}"
SERVICE="${SERVICE:-ai-no-tsukaikata}"
GEMINI_MODEL="${GEMINI_MODEL:-gemini-3.5-flash}"
SA_NAME="ai-lesson-run"

ACCOUNT="$($GCLOUD auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -n1)"
if [ -z "$ACCOUNT" ]; then
  echo "ログインしていません。先に実行してください:  gcloud auth login --no-launch-browser"; exit 1
fi
echo "ログイン中のアカウント: $ACCOUNT"

if [ -z "${PROJECT_ID:-}" ]; then
  if [ -f .deploy-project ]; then PROJECT_ID="$(cat .deploy-project)"
  else PROJECT_ID="ai-no-tsukaikata-$(printf '%05d' $((RANDOM % 100000)))"; fi
fi
echo "プロジェクト: $PROJECT_ID / リージョン: $REGION / サービス: $SERVICE"

if ! $GCLOUD projects describe "$PROJECT_ID" >/dev/null 2>&1; then
  echo "== プロジェクトを作成します"
  $GCLOUD projects create "$PROJECT_ID" --name="AI no Tsukaikata"
fi
echo "$PROJECT_ID" > .deploy-project
$GCLOUD config set project "$PROJECT_ID" >/dev/null

BILLING_ENABLED="$($GCLOUD billing projects describe "$PROJECT_ID" --format='value(billingEnabled)' 2>/dev/null || echo False)"
if [ "$BILLING_ENABLED" != "True" ]; then
  if [ -z "${BILLING_ACCOUNT_ID:-}" ]; then
    echo "このプロジェクトには請求先アカウントが紐づいていません。"
    echo "候補:"; $GCLOUD billing accounts list || true
    echo "BILLING_ACCOUNT_ID=<ID> を付けて、もう一度実行してください。"; exit 1
  fi
  echo "== 請求先アカウントを紐づけます"
  $GCLOUD billing projects link "$PROJECT_ID" --billing-account="$BILLING_ACCOUNT_ID"
fi

echo "== API を有効化します（数分かかることがあります）"
$GCLOUD services enable \
  run.googleapis.com aiplatform.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com logging.googleapis.com

PROJECT_NUMBER="$($GCLOUD projects describe "$PROJECT_ID" --format='value(projectNumber)')"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

if ! $GCLOUD iam service-accounts describe "$SA_EMAIL" >/dev/null 2>&1; then
  echo "== 実行用サービスアカウントを作成します（Vertex AI を呼ぶ権限だけ）"
  $GCLOUD iam service-accounts create "$SA_NAME" --display-name="AI lesson runtime"
  sleep 8
fi
$GCLOUD projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" --role="roles/aiplatform.user" --condition=None >/dev/null

# --source デプロイのビルドは Compute Engine の既定サービスアカウントで動く。ビルド権限を付ける
BUILD_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
for role in roles/cloudbuild.builds.builder roles/run.builder; do
  $GCLOUD projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${BUILD_SA}" --role="$role" --condition=None >/dev/null 2>&1 || true
done

echo "== Cloud Run にデプロイします（ソースからビルド）"
$GCLOUD run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --service-account "$SA_EMAIL" \
  --allow-unauthenticated \
  --max-instances 2 \
  --min-instances 0 \
  --concurrency 20 \
  --cpu 1 --memory 512Mi \
  --timeout 60 \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=global,GEMINI_MODEL=${GEMINI_MODEL},LLM_MODE=gemini" \
  --quiet

URL="$($GCLOUD run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"

if [ -n "${BUDGET_JPY:-}" ] && [ -n "${BILLING_ACCOUNT_ID:-}" ]; then
  echo "== 予算アラートを作成します（${BUDGET_JPY}円）"
  $GCLOUD services enable billingbudgets.googleapis.com
  $GCLOUD billing budgets create --billing-account="$BILLING_ACCOUNT_ID" \
    --display-name="ai-no-tsukaikata" --budget-amount="${BUDGET_JPY}JPY" \
    --filter-projects="projects/${PROJECT_ID}" \
    --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 --threshold-rule=percent=1.0 || \
    echo "（予算アラートの作成に失敗しました。コンソールの［お支払い］→［予算とアラート］から手動で作成してください）"
fi

echo
echo "== 動作確認"
curl -fsS "${URL}/healthz" && echo
echo
echo "デプロイ完了: ${URL}"
echo "次の一歩: ブラウザで開き、README の「動作確認の方法」に沿って試す。撮り直しは:"
echo "  python scripts/capture.py ${URL} submission/screenshots-live"
