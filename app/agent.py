"""講師エージェント本体。

流れ:  plan（判定・スキル選定） → review（採点・改善案） → run（実行体験） → quiz（適応クイズ）

エージェントとしての設計:
- 判断: 目的の可否、リスク区分、教えるスキルの選定、弱点に合わせた出題は Gemini が判断する
- 制御: 選べるスキルは固定カタログのみ。出力は JSON スキーマで縛り、コード側で検証する。
        検証に失敗したら既定値や固定クイズに切り替える（フォールバック）
- 安全: 入力は guard.py で個人情報と指示の上書きを検査してから渡す。出力も個人情報を伏せる
- 可観測性: 各ステップの判断・ガード・所要時間・トークン数を trace として画面に返し、構造化ログにも出す
"""
from __future__ import annotations

import time
from typing import Any

from . import config, guard, obs, prompts
from . import schemas as S
from .llm import LLM, LLMError
from .ratelimit import DailyBudget
from .skills import DEFAULT_SKILLS, FALLBACK_QUIZ, SKILLS


class AgentError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message
        super().__init__(message)


class Tutor:
    def __init__(self, llm: LLM, budget: DailyBudget):
        self.llm = llm
        self.budget = budget

    # ---------- 共通 ----------
    def _call(self, step: str, schema: type, system: str, user: str, trace: list[dict], temperature: float = 0.4):
        if not self.budget.take():
            obs.log("WARNING", "daily_budget_exceeded", step=step)
            raise AgentError(503, "budget", "本日の利用上限に達しました。明日もう一度お試しください。")
        t0 = time.monotonic()
        try:
            out, usage = self.llm.generate(schema, system, user, temperature=temperature)
        except LLMError as e:
            ms = int((time.monotonic() - t0) * 1000)
            obs.log("ERROR", "llm_error", step=step, error=str(e), ms=ms)
            raise
        ms = int((time.monotonic() - t0) * 1000)
        obs.log("INFO", "llm_ok", step=step, ms=ms, backend=self.llm.name, model=config.GEMINI_MODEL, **usage)
        trace.append({"step": step, "event": "gemini", "ms": ms})
        return out

    @staticmethod
    def _guard(text: str, max_chars: int, label: str, step: str, trace: list[dict]) -> str:
        r = guard.check_text(text, max_chars=max_chars, label=label)
        if not r.ok:
            trace.append({"step": step, "event": "guard_blocked", "code": r.code})
            obs.log("WARNING", "guard_blocked", step=step, code=r.code, kinds=r.kinds)
            raise AgentError(422, r.code, r.message)
        return guard.normalize(text).strip()

    @staticmethod
    def _valid_ids(ids: list[str]) -> list[str]:
        out: list[str] = []
        for i in ids:
            if i in SKILLS and i not in out:
                out.append(i)
        return out

    # ---------- 1. plan ----------
    def plan(self, goal_raw: str) -> dict[str, Any]:
        trace: list[dict] = []
        goal = self._guard(goal_raw, config.MAX_GOAL_CHARS, "やりたいこと", "plan", trace)
        try:
            p = self._call("plan", S.PlanOut, prompts.PLAN_SYSTEM, f"<goal>{goal}</goal>", trace, 0.2)
        except LLMError:
            trace.append({"step": "plan", "event": "fallback", "detail": "既定のスキルを使用"})
            p = S.PlanOut(allowed=True, refusal_reason="", task_type="その他", risk_level="low", risk_note="",
                          skills=[S.PlanSkill(skill_id=i, reason=SKILLS[i]["desc"]) for i in DEFAULT_SKILLS],
                          starter_tip="まず「誰に向けて」「何のために」を1行ずつ書いてみましょう。")
        if not p.allowed:
            trace.append({"step": "plan", "event": "refused"})
            raise AgentError(422, "refused", (p.refusal_reason or "この目的は練習では扱えません。")[:200])
        picked, seen = [], set()
        for s in p.skills:
            if s.skill_id in SKILLS and s.skill_id not in seen:
                seen.add(s.skill_id)
                picked.append({"skill_id": s.skill_id, "name": SKILLS[s.skill_id]["name"], "desc": SKILLS[s.skill_id]["desc"],
                               "example": SKILLS[s.skill_id]["example"], "reason": s.reason[:120]})
        dropped = len(p.skills) - len(picked)
        if dropped:
            trace.append({"step": "plan", "event": "invalid_skill_dropped", "count": dropped})
        if len(picked) < 2:
            for i in DEFAULT_SKILLS:
                if i not in seen and len(picked) < 3:
                    picked.append({"skill_id": i, "name": SKILLS[i]["name"], "desc": SKILLS[i]["desc"],
                                   "example": SKILLS[i]["example"], "reason": SKILLS[i]["desc"]})
        picked = picked[:4]
        risk = p.risk_level if p.risk_level in ("low", "medium", "high") else "low"
        trace.append({"step": "plan", "event": "decision", "risk": risk, "skills": [s["skill_id"] for s in picked]})
        return {"goal": goal, "task_type": p.task_type[:20], "risk_level": risk, "risk_note": p.risk_note[:160],
                "skills": picked, "starter_tip": p.starter_tip[:160], "trace": trace}

    # ---------- 2. review ----------
    def review(self, goal_raw: str, skill_ids: list[str], prompt_raw: str) -> dict[str, Any]:
        trace: list[dict] = []
        goal = self._guard(goal_raw, config.MAX_GOAL_CHARS, "やりたいこと", "review", trace)
        prompt = self._guard(prompt_raw, config.MAX_PROMPT_CHARS, "AIへの指示文", "review", trace)
        ids = self._valid_ids(skill_ids) or DEFAULT_SKILLS
        user = f"<goal>{goal}</goal>\n<skills>{','.join(ids)}</skills>\n" + " ".join(f"skill:{i}" for i in ids) + f"\n<prompt>{prompt}</prompt>"
        try:
            r = self._call("review", S.ReviewOut, prompts.REVIEW_SYSTEM, user, trace, 0.3)
        except LLMError:
            raise AgentError(502, "llm", "採点に失敗しました。少し待ってからもう一度お試しください。")
        by_id = {s.skill_id: s for s in r.scores if s.skill_id in ids}
        scores = []
        for i in ids:
            s = by_id.get(i)
            scores.append({"skill_id": i, "name": SKILLS[i]["name"], "score": max(0, min(2, s.score)) if s else 0,
                           "comment": (s.comment if s else "採点できませんでした。")[:160]})
        improved, redacted = guard.redact_output(r.improved_prompt[:800])
        if redacted:
            trace.append({"step": "review", "event": "output_redacted"})
        total = sum(s["score"] for s in scores)
        weak = [s["skill_id"] for s in scores if s["score"] < 2]
        trace.append({"step": "review", "event": "decision", "total": total, "max": 2 * len(scores), "weak": weak})
        return {"scores": scores, "total": total, "max": 2 * len(scores), "weak_skill_ids": weak,
                "good_points": [g[:120] for g in r.good_points[:2]], "improvements": [x[:160] for x in r.improvements[:3]],
                "improved_prompt": improved, "trace": trace}

    # ---------- 3. run ----------
    def run(self, goal_raw: str, prompt_raw: str, risk_level: str) -> dict[str, Any]:
        trace: list[dict] = []
        goal = self._guard(goal_raw, config.MAX_GOAL_CHARS, "やりたいこと", "run", trace)
        prompt = self._guard(prompt_raw, config.MAX_PROMPT_CHARS, "AIへの指示文", "run", trace)
        risk = risk_level if risk_level in ("low", "medium", "high") else "low"
        user = f"<risk_level>{risk}</risk_level>\n<goal>{goal}</goal>\n<prompt>{prompt}</prompt>"
        try:
            r = self._call("run", S.RunOut, prompts.RUN_SYSTEM, user, trace, 0.6)
        except LLMError:
            raise AgentError(502, "llm", "AIの実行に失敗しました。少し待ってからもう一度お試しください。")
        answer, red = guard.redact_output(r.answer[:2500])
        if red:
            trace.append({"step": "run", "event": "output_redacted"})
        if risk == "high" and not answer.startswith("これは参考の文章です"):
            answer = "これは参考の文章です。専門家に確認してください。\n\n" + answer
            trace.append({"step": "run", "event": "disclaimer_added"})
        trace.append({"step": "run", "event": "decision", "risk": risk})
        return {"answer": answer, "check_points": [c[:140] for c in r.check_points[:3]], "trace": trace}

    # ---------- 4. quiz ----------
    def quiz(self, goal_raw: str, prompt_raw: str, skill_ids: list[str], weak_ids: list[str]) -> dict[str, Any]:
        trace: list[dict] = []
        goal = self._guard(goal_raw, config.MAX_GOAL_CHARS, "やりたいこと", "quiz", trace)
        prompt = self._guard(prompt_raw, config.MAX_PROMPT_CHARS, "AIへの指示文", "quiz", trace)
        ids = self._valid_ids(skill_ids) or DEFAULT_SKILLS
        weak = self._valid_ids(weak_ids)
        user = (f"<goal>{goal}</goal>\n<skills>{','.join(ids)}</skills>\n<weak>{','.join(weak)}</weak>\n"
                + " ".join(f"skill:{i}" for i in (weak + [x for x in ids if x not in weak])) + f"\n<prompt>{prompt}</prompt>")
        questions: list[dict] = []
        try:
            q = self._call("quiz", S.QuizOut, prompts.QUIZ_SYSTEM, user, trace, 0.5)
            for item in q.questions:
                if item.skill_id in SKILLS and len(item.choices) == 3 and 0 <= item.answer_index <= 2 and item.question.strip():
                    questions.append({"skill_id": item.skill_id, "question": item.question[:200],
                                      "choices": [c[:120] for c in item.choices], "answer_index": item.answer_index,
                                      "explanation": item.explanation[:300]})
        except (LLMError, AgentError) as e:
            if isinstance(e, AgentError) and e.code != "budget":
                raise
            trace.append({"step": "quiz", "event": "fallback", "detail": "固定クイズを使用"})
        questions = questions[:3]
        if len(questions) < 3:
            trace.append({"step": "quiz", "event": "fallback", "detail": "不足分を固定クイズで補完"})
            used = {x["skill_id"] for x in questions}
            for i in weak + ids + list(FALLBACK_QUIZ):
                if len(questions) >= 3:
                    break
                if i in FALLBACK_QUIZ and i not in used:
                    questions.append({"skill_id": i, **FALLBACK_QUIZ[i]})
                    used.add(i)
        trace.append({"step": "quiz", "event": "decision", "focus": weak or ids})
        return {"questions": questions, "trace": trace}
