"""スクリーンショット撮影。使い方:  python scripts/capture.py [BASE_URL] [OUT_DIR]

BASE_URL を省略するとローカル (http://localhost:8080)。デプロイ後は Cloud Run の URL を渡すと、
実際の Gemini の応答で撮り直せる。
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "submission/screenshots")
OUT.mkdir(parents=True, exist_ok=True)
GOAL = "来月の清掃活動のお知らせを、住民向けに書きたい"
PROMPT = "お知らせ文を書いてください。清掃活動があります。"
GOOD = ("あなたは町内会の広報担当です。来月の清掃活動を、高齢の住民にも伝わるように知らせる文章を書いてください。"
        "条件：300字以内、丁寧な口調、日時と持ち物を入れる。日時は「〇月〇日 9時から」と仮に書いてください。"
        "不確かな点があれば、最後に「確認してほしい点」として挙げてください。")


def flow(page, tag, *, shots):
    page.goto(BASE)
    page.fill("#goal", GOAL)
    page.click("#btnPlan"); page.wait_for_selector("#s2:not([hidden])"); page.wait_for_selector("#skillList li")
    page.wait_for_timeout(600)
    if "plan" in shots: page.screenshot(path=str(OUT / f"{tag}-2-skills.png"), full_page=True)
    page.click("#btnToPrompt"); page.fill("#prompt", PROMPT)
    page.click("#btnReview"); page.wait_for_selector("#s4:not([hidden])"); page.wait_for_selector("#scoreList li")
    page.wait_for_timeout(600)
    if "weak" in shots: page.screenshot(path=str(OUT / f"{tag}-3-review-first.png"), full_page=True)
    page.fill("#prompt", GOOD)
    page.click("#btnReview"); page.wait_for_timeout(2500)
    page.wait_for_function("document.querySelectorAll('#scoreList li').length>0 && !document.querySelector('#btnReview').disabled")
    page.wait_for_timeout(500)
    if "review" in shots: page.screenshot(path=str(OUT / f"{tag}-4-review-second.png"), full_page=True)
    page.click("#btnRunMine"); page.wait_for_selector("#s5:not([hidden])"); page.wait_for_function("document.querySelector('#answer').textContent.length>5")
    page.wait_for_timeout(600)
    if "run" in shots: page.screenshot(path=str(OUT / f"{tag}-5-run.png"), full_page=True)
    with page.expect_response(lambda r: r.url.endswith("/api/quiz")) as ri:
        page.click("#btnQuiz")
    ans = [q["answer_index"] for q in ri.value.json()["questions"]]
    page.wait_for_selector("#s6:not([hidden])"); page.wait_for_selector(".q")
    for i, q in enumerate(page.query_selector_all(".q")):
        q.query_selector_all(".opt")[ans[i] if i != 1 else (ans[i] + 1) % 3].click()  # 2問は正解、1問はわざと外す
    page.wait_for_timeout(600)
    if "quiz" in shots: page.screenshot(path=str(OUT / f"{tag}-6-quiz.png"), full_page=True)
    page.evaluate("document.querySelector('#traceCard details').open = true")
    page.locator("#traceCard").scroll_into_view_if_needed(); page.wait_for_timeout(300)
    if "trace" in shots: page.locator("#traceCard").screenshot(path=str(OUT / f"{tag}-7-trace.png"))


with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    # デスクトップ
    ctx = b.new_context(viewport={"width": 1100, "height": 900}, locale="ja-JP", bypass_csp=True)
    pg = ctx.new_page()
    pg.goto(BASE); pg.wait_for_timeout(500)
    pg.screenshot(path=str(OUT / "desktop-1-top.png"))
    flow(pg, "desktop", shots={"plan", "review", "run", "quiz", "trace"})
    ctx.close()
    # スマホ
    ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, locale="ja-JP", bypass_csp=True)
    pg = ctx.new_page()
    pg.goto(BASE); pg.wait_for_timeout(500)
    pg.screenshot(path=str(OUT / "mobile-1-top.png"))
    flow(pg, "mobile", shots={"plan", "review", "quiz"})
    ctx.close()
    b.close()
print("saved to", OUT)
