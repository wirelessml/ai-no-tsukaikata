"""環境変数から設定を読む。秘密情報はコードに置かない。"""
import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


# LLM_MODE: "gemini"（既定）または "mock"（ローカル確認・テスト用の固定応答）
LLM_MODE = os.environ.get("LLM_MODE", "gemini").lower()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")  # ローカル確認用。Cloud Run では使わない
GOOGLE_CLOUD_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
GOOGLE_CLOUD_LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
THINKING_LEVEL = os.environ.get("THINKING_LEVEL", "LOW").upper()  # MINIMAL/LOW/MEDIUM/HIGH/OFF

# 入力上限（文字数）
MAX_GOAL_CHARS = _int("MAX_GOAL_CHARS", 120)
MAX_PROMPT_CHARS = _int("MAX_PROMPT_CHARS", 600)
MAX_TEXT_CHARS = _int("MAX_TEXT_CHARS", 1500)  # 実行結果などをクイズに渡すときの上限

# 出力上限（トークン）
MAX_OUTPUT_TOKENS = _int("MAX_OUTPUT_TOKENS", 2048)

# 濫用対策
RATE_LIMIT_REQUESTS = _int("RATE_LIMIT_REQUESTS", 30)   # 窓内に許可するAPI呼び出し数（IPごと）
RATE_LIMIT_WINDOW_SEC = _int("RATE_LIMIT_WINDOW_SEC", 600)
DAILY_LLM_CALL_LIMIT = _int("DAILY_LLM_CALL_LIMIT", 2000)  # インスタンスごとの1日あたりGemini呼び出し上限
LLM_TIMEOUT_MS = _int("LLM_TIMEOUT_MS", 40000)
