import pytest
from fastapi.testclient import TestClient

from app import main, schemas as S
from app.agent import Tutor
from app.llm import LLMError
from app.mock_llm import MockLLM
from app.ratelimit import DailyBudget, SlidingWindowLimiter


@pytest.fixture()
def client():
    main.limiter = SlidingWindowLimiter(1000, 60)
    main.set_tutor(Tutor(MockLLM(), DailyBudget(1000)))
    return TestClient(main.app)


def test_health_and_index(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/api/health").json() == {"status": "ok"}
    r = client.get("/")
    assert r.status_code == 200 and "AIの使い方を教えます" in r.text
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in r.headers["content-security-policy"]


def test_config(client):
    d = client.get("/api/config").json()
    assert len(d["skills"]) == 7 and d["limits"]["goal"] == 120


def test_full_flow(client):
    p = client.post("/api/plan", json={"goal": "来月の清掃活動のお知らせを住民向けに書きたい"}).json()
    ids = [s["skill_id"] for s in p["skills"]]
    assert 2 <= len(ids) <= 4 and p["risk_level"] == "low"
    prompt = "あなたは町内会の広報担当です。住民向けに、300字以内で清掃活動のお知らせを書いてください。不確かな点は確認してほしい点として挙げてください。"
    r = client.post("/api/review", json={"goal": p["goal"], "skill_ids": ids, "prompt": prompt}).json()
    assert r["max"] == 2 * len(ids) and r["total"] > 0
    run = client.post("/api/run", json={"goal": p["goal"], "prompt": prompt, "risk_level": "low"}).json()
    assert run["answer"] and run["check_points"]
    q = client.post("/api/quiz", json={"goal": p["goal"], "prompt": prompt, "skill_ids": ids, "weak_skill_ids": r["weak_skill_ids"]}).json()
    assert len(q["questions"]) == 3
    for x in q["questions"]:
        assert len(x["choices"]) == 3 and 0 <= x["answer_index"] <= 2


def test_high_risk_gets_disclaimer(client):
    p = client.post("/api/plan", json={"goal": "確定申告の書き方を知りたい"}).json()
    assert p["risk_level"] == "high"
    run = client.post("/api/run", json={"goal": p["goal"], "prompt": "確定申告について教えて", "risk_level": "high"}).json()
    assert run["answer"].startswith("これは参考の文章です")
    assert any(t["event"] == "disclaimer_added" for t in run["trace"])


def test_refused_goal(client):
    r = client.post("/api/plan", json={"goal": "不正アクセスの方法を知りたい"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "refused"


def test_pii_blocked_before_llm(client):
    calls = []
    class Spy(MockLLM):
        def generate(self, *a, **k):
            calls.append(1)
            return super().generate(*a, **k)
    main.set_tutor(Tutor(Spy(), DailyBudget(100)))
    r = client.post("/api/plan", json={"goal": "090-1234-5678 に電話する文を作りたい"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "pii"
    assert calls == []


def test_length_cap(client):
    r = client.post("/api/plan", json={"goal": "あ" * 121})
    assert r.status_code == 422 and r.json()["error"]["code"] == "too_long"
    r = client.post("/api/plan", json={"goal": "あ" * 3000})
    assert r.status_code == 422


def test_rate_limit():
    main.limiter = SlidingWindowLimiter(2, 60)
    main.set_tutor(Tutor(MockLLM(), DailyBudget(1000)))
    c = TestClient(main.app)
    codes = [c.post("/api/plan", json={"goal": "お知らせを書きたい"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_daily_budget_blocks():
    main.limiter = SlidingWindowLimiter(1000, 60)
    main.set_tutor(Tutor(MockLLM(), DailyBudget(1)))
    c = TestClient(main.app)
    assert c.post("/api/plan", json={"goal": "お知らせを書きたい"}).status_code == 200
    r = c.post("/api/plan", json={"goal": "お知らせを書きたい"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "budget"


class BadLLM:
    name = "bad"
    def __init__(self, mode): self.mode = mode
    def generate(self, schema, system, user, **k):
        if self.mode == "error":
            raise LLMError("boom")
        if schema is S.PlanOut:
            return S.PlanOut(allowed=True, refusal_reason="", task_type="x", risk_level="weird", risk_note="",
                             skills=[S.PlanSkill(skill_id="hack", reason="r"), S.PlanSkill(skill_id="verify", reason="r")], starter_tip="t"), {}
        if schema is S.QuizOut:
            return S.QuizOut(questions=[S.QuizQuestion(skill_id="verify", question="q", choices=["a", "b"], answer_index=5, explanation="e")]), {}
        if schema is S.RunOut:
            return S.RunOut(answer="連絡は x@y.jp へ", check_points=["c"]), {}
        raise LLMError("x")


def test_invalid_model_output_is_sanitized():
    main.limiter = SlidingWindowLimiter(1000, 60)
    main.set_tutor(Tutor(BadLLM("weird"), DailyBudget(100)))
    c = TestClient(main.app)
    p = c.post("/api/plan", json={"goal": "お知らせを書きたい"}).json()
    ids = [s["skill_id"] for s in p["skills"]]
    assert "hack" not in ids and p["risk_level"] == "low" and len(ids) >= 2
    assert any(t["event"] == "invalid_skill_dropped" for t in p["trace"])
    q = c.post("/api/quiz", json={"goal": "g", "prompt": "p", "skill_ids": ids, "weak_skill_ids": []}).json()
    assert len(q["questions"]) == 3 and all(len(x["choices"]) == 3 for x in q["questions"])
    run = c.post("/api/run", json={"goal": "g", "prompt": "p", "risk_level": "low"}).json()
    assert "y.jp" not in run["answer"] and any(t["event"] == "output_redacted" for t in run["trace"])


def test_llm_failure_fallbacks():
    main.limiter = SlidingWindowLimiter(1000, 60)
    main.set_tutor(Tutor(BadLLM("error"), DailyBudget(100)))
    c = TestClient(main.app)
    p = c.post("/api/plan", json={"goal": "お知らせを書きたい"})
    assert p.status_code == 200 and len(p.json()["skills"]) == 3
    q = c.post("/api/quiz", json={"goal": "g", "prompt": "p", "skill_ids": ["verify"], "weak_skill_ids": []})
    assert q.status_code == 200 and len(q.json()["questions"]) == 3
    assert c.post("/api/review", json={"goal": "g", "skill_ids": ["verify"], "prompt": "p"}).status_code == 502
