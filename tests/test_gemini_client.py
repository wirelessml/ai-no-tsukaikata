"""GeminiLLM が Gemini API の実際のリクエスト／レスポンス形式で動くかを、ローカルの偽サーバーで確認する。

本物の Gemini は呼ばない。SDK が組み立てる HTTP リクエスト（モデル名・system_instruction・JSONスキーマ・thinking設定）と、
JSON 応答のパース、エラー時の LLMError 変換を検証する。
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app import config, schemas as S
from app.llm import GeminiLLM, LLMError

SEEN: list[dict] = []
MODE = {"kind": "ok"}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append({"path": self.path, "body": body})
        if MODE["kind"] == "500":
            self.send_response(500); self.end_headers(); self.wfile.write(b'{"error":{"message":"x"}}'); return
        text = "not json" if MODE["kind"] == "badjson" else json.dumps({"answer": "こんにちは", "check_points": ["確認"]}, ensure_ascii=False)
        out = {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": "STOP"}],
               "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 7}}
        data = json.dumps(out).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(data)))
        self.end_headers(); self.wfile.write(data)


@pytest.fixture()
def llm(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("GOOGLE_GEMINI_BASE_URL", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "dummy-key-for-local-fake-server")
    monkeypatch.setattr(config, "GEMINI_MODEL", "gemini-3.5-flash")
    SEEN.clear(); MODE["kind"] = "ok"
    yield GeminiLLM()
    srv.shutdown()


def test_request_shape_and_parse(llm):
    out, usage = llm.generate(S.RunOut, "SYSTEM_TEXT", "<prompt>hi</prompt>")
    assert out.answer == "こんにちは" and usage == {"prompt_tokens": 11, "output_tokens": 7}
    req = SEEN[0]
    assert "gemini-3.5-flash:generateContent" in req["path"]
    b = req["body"]
    assert b["systemInstruction"]["parts"][0]["text"] == "SYSTEM_TEXT"
    gc = b["generationConfig"]
    assert gc["responseMimeType"] == "application/json" and "responseSchema" in gc or "responseJsonSchema" in gc
    tc = gc["thinkingConfig"]
    assert (tc.get("thinkingLevel") or tc.get("thinking_level")) == "LOW"
    assert gc["maxOutputTokens"] == config.MAX_OUTPUT_TOKENS


def test_gemini25_uses_thinking_budget(llm, monkeypatch):
    monkeypatch.setattr(config, "GEMINI_MODEL", "gemini-2.5-flash")
    llm.generate(S.RunOut, "s", "u")
    tc = SEEN[0]["body"]["generationConfig"]["thinkingConfig"]
    assert (tc.get("thinkingBudget") if "thinkingBudget" in tc else tc.get("thinking_budget")) == 0


def test_http_error_becomes_llmerror(llm):
    MODE["kind"] = "500"
    with pytest.raises(LLMError):
        llm.generate(S.RunOut, "s", "u")


def test_bad_json_becomes_llmerror(llm):
    MODE["kind"] = "badjson"
    with pytest.raises(LLMError, match="invalid_json"):
        llm.generate(S.RunOut, "s", "u")
