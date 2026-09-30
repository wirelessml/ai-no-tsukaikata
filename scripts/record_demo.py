"""ナレーション付きデモ動画を作る。

使い方:  python scripts/record_demo.py BASE_URL OUT.mp4 [architecture.png]

1. scripts/narration.py の各シーンを TTS（edge-tts）で音声化し、長さを測る
2. Playwright で実際の画面を操作して録画する。各シーンは、ナレーションの長さ以上の時間をかけて進める
3. シーン開始時刻に合わせて音声を重ね、字幕（画面下）と合わせて mp4 にする

BASE_URL にデプロイ後の Cloud Run の URL を渡せば、本物の Gemini の応答で録画できる。
必要: pip install playwright edge-tts / playwright install ffmpeg / ffmpeg / Google Chrome
"""
import asyncio
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from narration import SCENES  # noqa: E402

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "submission/demo.mp4")
ARCH = Path(sys.argv[3] if len(sys.argv) > 3 else "submission/diagram/architecture.png").resolve()
VOICE = "ja-JP-NanamiNeural"
GOAL = "来月の清掃活動のお知らせを、住民向けに書きたい"
WEAK = "お知らせ文を書いてください。清掃活動があります。"
GOOD = ("あなたは町内会の広報担当です。高齢の住民にも伝わるように、来月の清掃活動のお知らせを書いてください。"
        "300字以内、丁寧な口調で、日時と持ち物を入れてください。日時は「〇月〇日 9時から」と仮に書いてください。"
        "不確かな点は、最後に確認してほしい点として挙げてください。")
CAP = {
    "intro": "AIの使い方を教えます", "problem": "指示が短い・個人情報・確認不足", "plan": "① 目的を書く → スキルが選ばれる",
    "weak": "② 短い指示文を採点", "good": "③ 書き直して再採点", "run": "④ 実行して結果を確かめる",
    "quiz": "⑤ 弱点に合わせたクイズ", "trace": "判断ログ（本文は記録しない）", "pii": "個人情報は Gemini に送る前に停止",
    "arch": "Cloud Run + Vertex AI（Gemini）", "outro": "AIの使い方を教えます",
}
CAPTION_JS = """(t) => {
  let c = document.getElementById('__cap');
  if (!c) { c = document.createElement('div'); c.id = '__cap';
    c.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:99999;background:rgba(15,23,42,.88);color:#fff;font:600 30px/1.5 "Noto Sans CJK JP",sans-serif;padding:12px 32px;text-align:center';
    document.body.appendChild(c); }
  c.textContent = t; c.style.display = t ? 'block' : 'none'; }"""


async def _tts(text, path):
    import edge_tts
    await edge_tts.Communicate(text, VOICE, rate="-5%").save(str(path))


def duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def type_slow(page, sel, text, delay=40):
    page.click(sel); page.keyboard.type(text, delay=delay)


def main():
    tmp = Path(tempfile.mkdtemp())
    audio = {}
    for name, text in SCENES:
        f = tmp / f"{name}.mp3"
        asyncio.run(_tts(text, f))
        audio[name] = (f, duration(f))
    total_audio = sum(d for _, d in audio.values())
    print(f"narration total: {total_audio:.1f}s")

    starts = {}
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        ctx = b.new_context(viewport={"width": 1280, "height": 720}, record_video_dir=str(tmp),
                            record_video_size={"width": 1280, "height": 720}, locale="ja-JP", bypass_csp=True)
        pg = ctx.new_page()
        t0 = time.monotonic()
        pg.goto(BASE); pg.wait_for_timeout(800)

        def scene(name, action=None):
            start = time.monotonic()
            starts[name] = start - t0
            if name != "arch":
                pg.evaluate(CAPTION_JS, CAP[name])
            if action:
                action()
            rest = audio[name][1] + 0.8 - (time.monotonic() - start)
            if rest > 0:
                pg.wait_for_timeout(int(rest * 1000))

        def wait(sel):
            pg.wait_for_selector(sel, timeout=90000); pg.wait_for_timeout(600)

        def a_plan():
            type_slow(pg, "#goal", GOAL); pg.click("#btnPlan"); wait("#skillList li")
        def a_weak():
            pg.click("#btnToPrompt"); pg.wait_for_timeout(500); type_slow(pg, "#prompt", WEAK)
            pg.click("#btnReview"); wait("#scoreList li")
        def a_good():
            pg.evaluate("document.getElementById('s3').scrollIntoView()"); pg.wait_for_timeout(400)
            pg.fill("#prompt", ""); type_slow(pg, "#prompt", GOOD, delay=20)
            pg.click("#btnReview"); pg.wait_for_timeout(2500)
            pg.wait_for_function("!document.querySelector('#btnReview').disabled", timeout=90000); pg.wait_for_timeout(600)
        def a_run():
            pg.click("#btnRunMine"); wait("#s5:not([hidden])")
            pg.wait_for_function("document.querySelector('#answer').textContent.length>5", timeout=90000)
        def a_quiz():
            with pg.expect_response(lambda r: r.url.endswith("/api/quiz")) as ri:
                pg.click("#btnQuiz")
            ans = [q["answer_index"] for q in ri.value.json()["questions"]]
            wait(".q")
            for i, q in enumerate(pg.query_selector_all(".q")):
                pick = ans[i] if i != 1 else (ans[i] + 1) % 3  # 2問は正解、1問はわざと外して解説を見せる
                pg.wait_for_timeout(1200); q.query_selector_all(".opt")[pick].click()
        def a_trace():
            pg.evaluate("document.querySelector('#traceCard details').open = true")
            pg.evaluate("document.getElementById('traceCard').scrollIntoView({block:'center'})")
        def a_pii():
            pg.click("#btnRestart"); pg.wait_for_timeout(800)
            type_slow(pg, "#goal", "090-1234-5678 に電話する文を作りたい")
            pg.click("#btnPlan"); pg.wait_for_selector("#error:not([hidden])")
        def a_arch():
            pg.evaluate(CAPTION_JS, "")
            pg.goto(ARCH.as_uri()); pg.wait_for_timeout(300)

        scene("intro"); scene("problem"); scene("plan", a_plan); scene("weak", a_weak); scene("good", a_good)
        scene("run", a_run); scene("quiz", a_quiz); scene("trace", a_trace); scene("pii", a_pii)
        scene("arch", a_arch); scene("outro", lambda: (pg.goto(BASE), pg.wait_for_timeout(500)))
        vid = pg.video.path()
        ctx.close(); b.close()

    # 音声を開始時刻に合わせて重ねる
    inputs, filters, labels = [], [], []
    for i, (name, _t) in enumerate(SCENES):
        inputs += ["-i", str(audio[name][0])]
        ms = int((starts[name] + 0.35) * 1000)
        filters.append(f"[{i+1}:a]adelay={ms}|{ms}[a{i}]"); labels.append(f"[a{i}]")
    fc = ";".join(filters) + ";" + "".join(labels) + f"amix=inputs={len(SCENES)}:normalize=0[aout]"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(vid), *inputs, "-filter_complex", fc, "-map", "0:v", "-map", "[aout]",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23", "-c:a", "aac", "-b:a", "128k", "-shortest", str(OUT)], check=True)
    print("saved", OUT, f"{duration(OUT):.1f}s")


main()
