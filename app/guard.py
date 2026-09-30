"""入力ガード。LLMに渡す前に決定的なルールで検査する。

- 個人情報らしき文字列（メール・電話・マイナンバー形式・カード番号・郵便番号・APIキー）を検出したら止める
- 「以前の指示を無視して」のような指示の上書きを狙う文を検出したら止める
- 検出した文字列そのものは返さない（ログにも出さない）。種類だけを返す
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

_PII_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    ("email", "メールアドレス", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")),
    ("phone", "電話番号", re.compile(r"(?<!\d)0\d{1,4}[-ー\s]?\d{1,4}[-ー\s]?\d{3,4}(?!\d)")),
    ("postal", "郵便番号", re.compile(r"(?:〒\s*)?(?<!\d)\d{3}-\d{4}(?!\d)")),
    ("mynumber", "12桁の番号（マイナンバー形式）", re.compile(r"(?<!\d)\d{4}[-\s]?\d{4}[-\s]?\d{4}(?!\d)")),
    ("apikey", "APIキーらしき文字列", re.compile(r"(?:AIza[0-9A-Za-z_\-]{20,}|sk-[A-Za-z0-9_\-]{16,}|ghp_[A-Za-z0-9]{20,})")),
]
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){13,16}(?!\d)")

_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"(以前|これまで|上記|前)の(指示|命令|ルール|プロンプト)を(すべて|全て)?(無視|忘れ|破棄)",
        r"(指示|命令|ルール)を(すべて|全て)?(無視|忘れて)",
        r"システム(プロンプト|メッセージ|指示)を(表示|出力|教え|見せ)",
        r"ignore (all |any )?(the )?(previous|prior|above) (instructions|prompts?|rules)",
        r"(reveal|show|print|repeat) (your |the )?(system|hidden) (prompt|instructions?)",
        r"disregard (all |any )?(previous|prior|above)",
        r"you are now (?:dan|in developer mode)",
    ]
]


@dataclass
class GuardResult:
    ok: bool
    code: str = ""
    message: str = ""
    kinds: list[str] = field(default_factory=list)


def _luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).replace("\u0000", "")


def find_pii(text: str) -> list[str]:
    t = normalize(text)
    kinds: list[str] = []
    for _key, label, pat in _PII_PATTERNS:
        if pat.search(t) and label not in kinds:
            kinds.append(label)
    for m in _CARD.finditer(t):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 16 and _luhn(digits) and "クレジットカード番号" not in kinds:
            kinds.append("クレジットカード番号")
    return kinds


def has_injection(text: str) -> bool:
    t = normalize(text)
    return any(p.search(t) for p in _INJECTION_PATTERNS)


def check_text(text: str, *, max_chars: int, label: str) -> GuardResult:
    """ユーザー入力を検査する。okでなければ、画面にそのまま出せる日本語メッセージを返す。"""
    t = normalize(text or "").strip()
    if not t:
        return GuardResult(False, "empty", f"{label}が空です。書いてから送ってください。")
    if len(t) > max_chars:
        return GuardResult(False, "too_long", f"{label}は{max_chars}文字までです（いま{len(t)}文字）。短くまとめてください。")
    kinds = find_pii(t)
    if kinds:
        return GuardResult(
            False,
            "pii",
            "個人情報らしき内容（" + "、".join(kinds) + "）が含まれています。"
            "AIに送る前に「〇〇」のような伏せ字に置きかえてください。この文章は送信していません。",
            kinds,
        )
    if has_injection(t):
        return GuardResult(
            False,
            "injection",
            "AIへの指示を上書きしようとする文が含まれています。この練習では使えません。目的を書きなおしてください。",
        )
    return GuardResult(True)


def redact_output(text: str) -> tuple[str, bool]:
    """AIの出力に個人情報らしき文字列が混ざっていたら伏せる。"""
    t = text
    changed = False
    for _key, _label, pat in _PII_PATTERNS:
        new = pat.sub("〇〇", t)
        if new != t:
            changed = True
            t = new
    return t, changed
