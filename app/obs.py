"""構造化ログ（Cloud Logging が JSON として解釈する形式）。

ユーザーが入力した本文は一切ログに出さない。記録するのは、ステップ名・結果・所要時間・トークン数・ガードの判定コードだけ。
"""
from __future__ import annotations

import json
import sys
import time
from typing import Any


def log(severity: str, message: str, **fields: Any) -> None:
    rec = {"severity": severity, "message": message, "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    rec.update(fields)
    sys.stdout.write(json.dumps(rec, ensure_ascii=False) + "\n")
    sys.stdout.flush()
