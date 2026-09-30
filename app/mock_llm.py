"""固定ルールによる疑似LLM。Gemini を呼ばずに画面とAPIの流れを確認するためのもの。

本番の判断はすべて Gemini が行う。ここは「ネットワークなしで動作確認できる」ことだけが目的。
"""
from __future__ import annotations

import re
from typing import TypeVar

from pydantic import BaseModel

from . import schemas as S
from .skills import FALLBACK_QUIZ, SKILLS

T = TypeVar("T", bound=BaseModel)

_HIGH = re.compile(r"(診断|病気|薬|症状|法律|裁判|契約|税金|確定申告|投資|株|借金|遺言)")
_BAD = re.compile(r"(爆弾|ハッキング|不正アクセス|なりすまし|詐欺|殺|違法)")


def _tag(text: str, name: str) -> str:
    m = re.search(rf"<{name}>(.*?)</{name}>", text, re.S)
    return m.group(1).strip() if m else ""


class MockLLM:
    name = "mock"

    def generate(self, schema: type[T], system: str, user: str, *, temperature: float = 0.4) -> tuple[T, dict]:
        usage = {"prompt_tokens": None, "output_tokens": None}
        if schema is S.PlanOut:
            return self._plan(_tag(user, "goal")), usage  # type: ignore[return-value]
        if schema is S.ReviewOut:
            return self._review(user), usage  # type: ignore[return-value]
        if schema is S.RunOut:
            return self._run(_tag(user, "prompt")), usage  # type: ignore[return-value]
        if schema is S.QuizOut:
            return self._quiz(user), usage  # type: ignore[return-value]
        raise ValueError("unknown schema")

    def _plan(self, goal: str) -> S.PlanOut:
        if _BAD.search(goal):
            return S.PlanOut(allowed=False, refusal_reason="他人を傷つけたり、法に触れたりするおそれのある目的は、この練習では扱えません。",
                             task_type="対象外", risk_level="high", risk_note="", skills=[], starter_tip="")
        high = bool(_HIGH.search(goal))
        ids = ["context", "constraints", "verify"] if not high else ["context", "constraints", "verify", "privacy"]
        reasons = {
            "context": "誰に向けて何に使うかを書くと、内容がずれにくくなります。",
            "constraints": "字数や口調をはっきり書くと、直す回数が減ります。",
            "verify": "AIの答えは、自分で確かめてから使います。",
            "privacy": "この目的では個人情報を含みやすいので、伏せ字にしてから入力します。",
        }
        return S.PlanOut(
            allowed=True, refusal_reason="", task_type="文章づくり" if "文" in goal or "書" in goal else "調べもの・整理",
            risk_level="high" if high else "low",
            risk_note="専門家の判断が必要な分野です。AIの答えは参考にとどめます。" if high else "",
            skills=[S.PlanSkill(skill_id=i, reason=reasons[i]) for i in ids],
            starter_tip="まず「誰に向けて」「何のために」を1行ずつ書くところから始めましょう。",
        )

    def _review(self, user: str) -> S.ReviewOut:
        prompt = _tag(user, "prompt")
        ids = [i for i in re.findall(r"skill:(\w+)", user) if i in SKILLS]
        checks = {
            "role": lambda p: "あなたは" in p,
            "context": lambda p: bool(re.search(r"(ため|向け|目的|用)", p)),
            "constraints": lambda p: bool(re.search(r"\d+\s*(字|文字|個|つ|行|分)", p)),
            "format": lambda p: bool(re.search(r"(箇条書き|表|件名|形式|見出し)", p)),
            "examples": lambda p: bool(re.search(r"(たとえば|例えば|例：|例:)", p)),
            "verify": lambda p: bool(re.search(r"(確認|不確か|根拠)", p)),
            "privacy": lambda p: "〇〇" in p,
        }
        scores = []
        for i in ids:
            ok = checks[i](prompt)
            scores.append(S.SkillScore(skill_id=i, score=2 if ok else 0,
                                       comment=f"「{SKILLS[i]['name']}」の要素が見つかりました。" if ok else f"「{SKILLS[i]['name']}」の要素が足りません。"))
        missing = [s for s in scores if s.score == 0]
        improved = prompt.rstrip("。 \n") + "。\n" + "\n".join(f"・{SKILLS[s.skill_id]['example']}" for s in missing[:3])
        return S.ReviewOut(
            scores=scores,
            good_points=["やりたいことが書かれています。"] if prompt else [],
            improvements=[f"{SKILLS[s.skill_id]['name']}：{SKILLS[s.skill_id]['desc']}" for s in missing[:3]],
            improved_prompt=improved[:800],
        )

    def _run(self, prompt: str) -> S.RunOut:
        return S.RunOut(
            answer="（デモ用の固定応答です。実際の環境では Gemini がここに回答を返します。）\n\n" + prompt[:200],
            check_points=["日付・金額・固有名詞が正しいか、公式の情報で確かめる。", "相手に合った口調になっているか読み返す。"],
        )

    def _quiz(self, user: str) -> S.QuizOut:
        ids = [i for i in re.findall(r"skill:(\w+)", user) if i in FALLBACK_QUIZ] or ["context", "constraints", "verify"]
        qs = [S.QuizQuestion(skill_id=i, **FALLBACK_QUIZ[i]) for i in ids[:3]]
        return S.QuizOut(questions=qs)
