(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const state = { goal: "", plan: null, prompt: "", review: null, trace: [], limits: { goal: 120, prompt: 600 } };
  const STEP_NAMES = { plan: "計画", review: "採点", run: "実行", quiz: "クイズ" };

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function showError(msg) { const b = $("error"); b.textContent = msg; b.hidden = !msg; if (msg) b.scrollIntoView({ behavior: "smooth", block: "center" }); }
  function setStep(n) {
    document.querySelectorAll("#steps li").forEach((li) => {
      const k = Number(li.dataset.step);
      li.classList.toggle("on", k === n);
      li.classList.toggle("done", k < n);
    });
  }
  function reveal(id) { const s = $(id); s.hidden = false; setTimeout(() => s.scrollIntoView({ behavior: "smooth", block: "start" }), 30); }
  function busy(btn, on, label) {
    if (on) { btn.dataset.label = btn.textContent; btn.disabled = true; clear(btn); btn.appendChild(el("span", "spin")); btn.appendChild(document.createTextNode(label || "考え中…")); }
    else { btn.disabled = false; btn.textContent = btn.dataset.label || btn.textContent; }
  }
  async function api(path, body) {
    let r;
    try {
      r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    } catch (e) { throw new Error("通信に失敗しました。電波の状態を確認して、もう一度お試しください。"); }
    let data = null;
    try { data = await r.json(); } catch (e) { /* noop */ }
    if (!r.ok) throw new Error((data && data.error && data.error.message) || "うまく処理できませんでした。もう一度お試しください。");
    if (data && data.trace) state.trace.push(...data.trace);
    renderTrace();
    return data;
  }
  function counter(inputId, countId, max) {
    const i = $(inputId), c = $(countId);
    const f = () => { const n = i.value.length; c.textContent = n + " / " + max; c.classList.toggle("over", n > max); };
    i.addEventListener("input", f); f(); return f;
  }
  function renderTrace() {
    const list = $("traceList"); clear(list);
    state.trace.forEach((t) => {
      const li = el("li");
      li.appendChild(el("span", "tag", "[" + (STEP_NAMES[t.step] || t.step) + "] "));
      let msg = "";
      if (t.event === "gemini") msg = "Gemini が判断（" + t.ms + " ms）";
      else if (t.event === "decision") {
        if (t.step === "plan") msg = "リスク区分=" + t.risk + " / 選んだスキル=" + t.skills.join(", ");
        else if (t.step === "review") msg = "得点 " + t.total + "/" + t.max + " / 弱いスキル=" + (t.weak.join(", ") || "なし");
        else if (t.step === "run") msg = "リスク区分=" + t.risk + " に応じた表示を適用";
        else msg = "出題の重点=" + t.focus.join(", ");
      }
      else if (t.event === "guard_blocked") { msg = "入力ガードが停止（" + t.code + "）。Gemini には送っていません"; li.classList.add("warn"); }
      else if (t.event === "refused") msg = "目的が対象外のため停止";
      else if (t.event === "fallback") msg = "フォールバック：" + (t.detail || "");
      else if (t.event === "invalid_skill_dropped") msg = "カタログにないスキルを " + t.count + " 件除外";
      else if (t.event === "output_redacted") msg = "出力の個人情報らしき文字列を伏せた";
      else if (t.event === "disclaimer_added") msg = "専門分野の注意書きを追加";
      else msg = t.event;
      li.appendChild(document.createTextNode(msg));
      list.appendChild(li);
    });
    $("traceCard").hidden = state.trace.length === 0;
  }

  // ---- 1. 目的 ----
  counter("goal", "goalCount", state.limits.goal);
  $("samples").addEventListener("click", (e) => {
    const b = e.target.closest(".chip"); if (!b) return;
    $("goal").value = b.dataset.v; $("goal").dispatchEvent(new Event("input"));
  });
  $("btnPlan").addEventListener("click", async () => {
    showError("");
    const goal = $("goal").value.trim();
    if (!goal) return showError("やりたいことを書いてから押してください。");
    state.trace = []; renderTrace();
    busy($("btnPlan"), true, "先生が考えています…");
    try {
      const p = await api("/api/plan", { goal });
      state.goal = p.goal; state.plan = p;
      renderPlan(p); setStep(2); reveal("s2");
    } catch (e) { showError(e.message); } finally { busy($("btnPlan"), false); }
  });

  // ---- 2. スキル ----
  function renderPlan(p) {
    $("taskLine").textContent = "あなたの目的：" + p.goal + "（種類：" + p.task_type + "）";
    const rb = $("riskBox"); rb.className = "risk";
    if (p.risk_level !== "low" && p.risk_note) {
      rb.hidden = false; rb.classList.add(p.risk_level);
      rb.textContent = (p.risk_level === "high" ? "注意（専門家の確認が必要な分野）：" : "気をつけること：") + p.risk_note;
    } else rb.hidden = true;
    const ul = $("skillList"); clear(ul);
    p.skills.forEach((s, i) => {
      const li = el("li");
      li.appendChild(el("div", "n", (i + 1) + ". " + s.name));
      li.appendChild(el("div", "r", s.reason));
      li.appendChild(el("div", "e", "書き方の例：" + s.example));
      ul.appendChild(li);
    });
    $("tip").textContent = "最初の一歩：" + p.starter_tip;
  }
  $("btnToPrompt").addEventListener("click", () => {
    const r = $("skillRemind"); clear(r);
    state.plan.skills.forEach((s) => r.appendChild(el("span", null, s.name)));
    counter("prompt", "promptCount", state.limits.prompt);
    setStep(3); reveal("s3"); $("prompt").focus({ preventScroll: true });
  });

  // ---- 3-4. 採点 ----
  $("btnReview").addEventListener("click", async () => {
    showError("");
    const prompt = $("prompt").value.trim();
    if (!prompt) return showError("指示文を書いてから押してください。");
    busy($("btnReview"), true, "採点しています…");
    try {
      const r = await api("/api/review", { goal: state.goal, skill_ids: state.plan.skills.map((s) => s.skill_id), prompt });
      state.prompt = prompt; state.review = r; renderReview(r); setStep(4); reveal("s4");
    } catch (e) { showError(e.message); } finally { busy($("btnReview"), false); }
  });
  function renderReview(r) {
    const t = $("total"); clear(t);
    t.appendChild(document.createTextNode(r.total + " / " + r.max + " "));
    t.appendChild(el("small", null, "点"));
    const ul = $("scoreList"); clear(ul);
    r.scores.forEach((s) => {
      const li = el("li", "s" + s.score);
      li.appendChild(el("div", "mark", ["×", "△", "◎"][s.score]));
      li.appendChild(el("div", "nm", s.name + "（" + ["要素なし", "もう少し", "十分"][s.score] + "）"));
      li.appendChild(el("div", "cm", s.comment));
      ul.appendChild(li);
    });
    fillList("goodList", "goodBox", r.good_points);
    fillList("impList", "impBox", r.improvements);
    $("improved").textContent = r.improved_prompt;
  }
  function fillList(listId, boxId, items) {
    const ul = $(listId); clear(ul);
    items.forEach((x) => ul.appendChild(el("li", null, x)));
    $(boxId).hidden = items.length === 0;
  }
  $("btnUseImproved").addEventListener("click", () => { state.prompt = $("improved").textContent.slice(0, state.limits.prompt); runIt(); });
  $("btnRunMine").addEventListener("click", () => runIt());

  // ---- 5. 実行 ----
  async function runIt() {
    showError("");
    const btn = document.activeElement && document.activeElement.tagName === "BUTTON" ? document.activeElement : $("btnRunMine");
    busy(btn, true, "AIが実行しています…");
    try {
      const r = await api("/api/run", { goal: state.goal, prompt: state.prompt, risk_level: state.plan.risk_level });
      $("answer").textContent = r.answer;
      const ul = $("checkList"); clear(ul); r.check_points.forEach((c) => ul.appendChild(el("li", null, c)));
      setStep(5); reveal("s5");
    } catch (e) { showError(e.message); } finally { busy(btn, false); }
  }

  // ---- 6. クイズ ----
  $("btnQuiz").addEventListener("click", async () => {
    showError("");
    busy($("btnQuiz"), true, "問題を作っています…");
    try {
      const r = await api("/api/quiz", { goal: state.goal, prompt: state.prompt, skill_ids: state.plan.skills.map((s) => s.skill_id), weak_skill_ids: state.review ? state.review.weak_skill_ids : [] });
      renderQuiz(r.questions); setStep(6); reveal("s6");
    } catch (e) { showError(e.message); } finally { busy($("btnQuiz"), false); }
  });
  function renderQuiz(qs) {
    const box = $("quiz"); clear(box); $("quizDone").hidden = true; $("btnRestart").hidden = true;
    let answered = 0, right = 0;
    qs.forEach((q, qi) => {
      const wrap = el("div", "q");
      wrap.appendChild(el("p", null, "問" + (qi + 1) + ". " + q.question));
      const ex = el("div", "ex"); ex.hidden = true;
      q.choices.forEach((c, ci) => {
        const b = el("button", "opt", ["ア", "イ", "ウ"][ci] + "　" + c); b.type = "button";
        b.addEventListener("click", () => {
          if (wrap.dataset.done) return; wrap.dataset.done = "1";
          const ok = ci === q.answer_index;
          b.classList.add(ok ? "right" : "wrong");
          if (!ok) wrap.querySelectorAll(".opt")[q.answer_index].classList.add("right");
          ex.textContent = (ok ? "正解です。" : "残念、正解は「" + ["ア", "イ", "ウ"][q.answer_index] + "」です。") + q.explanation; ex.hidden = false;
          answered++; if (ok) right++;
          if (answered === qs.length) {
            const d = $("quizDone");
            d.textContent = qs.length + "問中 " + right + "問正解。" + (right === qs.length ? "全問正解です。次は自分の本当の用事で試してみましょう。" : "まちがえたところは、もう一度スキルの説明を読み返してみましょう。");
            d.hidden = false; $("btnRestart").hidden = false; $("btnRestart").scrollIntoView({ behavior: "smooth", block: "center" });
          }
        });
        wrap.appendChild(b);
      });
      wrap.appendChild(ex); box.appendChild(wrap);
    });
  }
  $("btnRestart").addEventListener("click", () => {
    ["s2", "s3", "s4", "s5", "s6"].forEach((id) => ($(id).hidden = true));
    $("goal").value = ""; $("prompt").value = ""; $("goal").dispatchEvent(new Event("input"));
    state.trace = []; renderTrace(); setStep(1); window.scrollTo({ top: 0, behavior: "smooth" });
  });

  fetch("/api/config").then((r) => r.json()).then((c) => {
    state.limits = c.limits;
    $("mockBanner").hidden = c.mode !== "mock";
    $("goal").maxLength = c.limits.goal * 2; $("prompt").maxLength = c.limits.prompt * 2;
    $("goal").dispatchEvent(new Event("input"));
  }).catch(() => {});
})();
