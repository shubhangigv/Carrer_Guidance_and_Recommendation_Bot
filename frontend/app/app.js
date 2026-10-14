// Pathfinder student app: screens and what happens when the student clicks.
// All server calls go through api.js. Nothing is scored here: the API runs engine v2.

// ---------------------------------------------------------------- the questions (same as the Google Form)
// Row names must match SKILL_MAP_V2 / SUBJECT_MAP_V2 in ml/recommender_v2.py.
const ANCHORS = "1 = never done it / very weak, 3 = can do it with help, 5 = can do it well on my own.";
const STEPS = [
  { key: "interests", label: "Interests", title: "How much do you enjoy these activities?",
    help: "1 = not at all, 3 = it is okay, 5 = I enjoy it a lot.", extra: [],
    rows: [["Realistic", "Working with machines, tools or building things"],
           ["Investigative", "Solving problems, research and analysing data"],
           ["Artistic", "Designing, writing or creating things"],
           ["Social", "Helping, teaching or caring for people"],
           ["Enterprising", "Leading, persuading or starting a business"],
           ["Conventional", "Organising data and records, following clear procedures"]] },
  { key: "skills", label: "Skills", title: "Rate your current ability in these skills",
    help: ANCHORS + " Choose “No experience” if you have never tried it, or “Can’t assess” if you are not sure how good you are.",
    extra: [["no_experience", "No experience"], ["cant_assess", "Can’t assess"]],
    rows: ["Mathematics", "Programming", "Problem Solving", "Research", "Communication", "Writing",
           "Leadership", "Technical/Practical Skills"].map(r => [r, r]) },
  { key: "subjects", label: "Subjects", title: "How good are you at these subjects?",
    help: ANCHORS + " Choose “Not studied” if you have not studied the subject.",
    extra: [["not_studied", "Not studied"]],
    rows: ["Mathematics", "Physics/Chemistry", "Biology", "Computer Science", "Commerce/Economics",
           "Languages", "Social Sciences", "Arts/Design"].map(r => [r, r]) },
  { key: "review", label: "Review", title: "Check your answers", help: "Change anything you like, then get your matches." },
];

// ---------------------------------------------------------------- state (kept for this browser tab only)
const STATE_KEY = "pathfinder.state";
const blank = () => ({ name: "", email: "", step: 0, answers: { interests: {}, skills: {}, subjects: {} },
                       assessmentId: null, recs: null, careerId: null });
let state = load() || blank();
let busy = false;

function load() { try { return JSON.parse(sessionStorage.getItem(STATE_KEY)); } catch (e) { return null; } }
function save() { try { sessionStorage.setItem(STATE_KEY, JSON.stringify(state)); } catch (e) { /* storage blocked */ } }

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (x) => x == null ? "–" : Math.round(x * 100) + "%";
const loggedIn = () => !!api.token();

function toast(msg) { const t = $("toast"); t.textContent = msg; t.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(() => { t.hidden = true; }, 3200); }
function showError(id, err) { const el = $(id); el.textContent = err ? err.message || String(err) : ""; el.hidden = !err; }

// Session expired or not logged in: send the student to the login screen.
function needLogin(err) {
  if (err && err.status === 401) { toast("Please log in again."); renderWho(); go("login", { tab: "login" }); return true; }
  return false;
}

// ---------------------------------------------------------------- navigation
const LOCKED = new Set(["assess", "results"]);           // need an account
function go(view, opts = {}) {
  if (LOCKED.has(view) && !loggedIn()) { toast("Create an account or log in first."); view = "login"; }
  document.querySelectorAll(".screen").forEach(s => { s.hidden = s.id !== "v-" + view; });
  document.querySelectorAll(".nav button").forEach(b => b.dataset.go === view
    ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current"));
  ({ home: renderHome, login: () => renderLogin(opts.tab), assess: renderAssess, results: renderResults,
     career: renderCareer, search: () => $("searchBox").focus() }[view] || (() => {}))();
  window.scrollTo(0, 0);
}
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-go]");
  if (b) go(b.dataset.go);
});

function renderWho() {
  $("who").innerHTML = loggedIn()
    ? `<span>${esc(state.name || state.email)}</span><button class="btn" type="button" id="logoutBtn">Log out</button>`
    : `<button class="btn" type="button" data-go="login">Log in</button>`;
  const out = $("logoutBtn");
  if (out) out.onclick = () => { api.logout(); state = blank(); save(); renderWho(); go("home"); toast("Logged out."); };
}

// ---------------------------------------------------------------- home: server status
async function renderHome() {
  try {
    const h = await api.health();
    $("homeStats").innerHTML = `<div class="stat"><b class="num">${h.careers_ranked}</b><span class="muted small">careers ranked</span></div>
      <div class="stat"><b class="num">${h.careers_total}</b><span class="muted small">careers in O*NET</span></div>`;
    $("banner").innerHTML = h.storage === "mysql" ? "" :
      `<div class="banner-in"><b>Demo mode.</b><span>MySQL is not connected, so accounts and answers are kept in memory and lost when the server stops.</span></div>`;
  } catch (err) {
    $("banner").innerHTML = `<div class="banner-in"><b>Server not reachable.</b><span>${esc(err.message)}</span></div>`;
  }
}
$("startBtn").onclick = () => go(loggedIn() ? "assess" : "login");

// ---------------------------------------------------------------- sign up / log in
function renderLogin(tab = "signup") {
  const signup = tab === "signup";
  $("signupForm").hidden = !signup; $("loginForm").hidden = signup;
  $("tabSignup").className = "btn" + (signup ? " primary" : ""); $("tabSignup").setAttribute("aria-selected", signup);
  $("tabLogin").className = "btn" + (signup ? "" : " primary"); $("tabLogin").setAttribute("aria-selected", !signup);
}
$("tabSignup").onclick = () => renderLogin("signup");
$("tabLogin").onclick = () => renderLogin("login");

async function afterLogin(name, email) {
  if (state.email !== email) state = blank();        // a different student: start fresh
  state.name = name || state.name || email; state.email = email; save();
  renderWho();
  go(state.recs ? "results" : "assess");
}

$("signupForm").onsubmit = async (e) => {
  e.preventDefault();
  if (busy) return;
  const body = { name: $("suName").value.trim(), email: $("suEmail").value.trim(), password: $("suPass").value,
                 degree: $("suDegree").value.trim() || null,
                 year_of_study: $("suYear").value ? Number($("suYear").value) : null };
  if (!body.name || !body.email || body.password.length < 8) {
    return showError("signupError", new Error("Fill in your name, email and a password of at least 8 characters."));
  }
  busy = true; showError("signupError", null);
  try {
    await api.register(body);
    await api.login(body.email, body.password);
    await afterLogin(body.name, body.email.toLowerCase());
  } catch (err) {
    showError("signupError", err.status === 409 ? new Error("This email already has an account. Use “Log in” instead.") : err);
  } finally { busy = false; }
};

$("loginForm").onsubmit = async (e) => {
  e.preventDefault();
  if (busy) return;
  const email = $("liEmail").value.trim(), password = $("liPass").value;
  busy = true; showError("loginError", null);
  try {
    await api.login(email, password);
    await afterLogin(null, email.toLowerCase());
  } catch (err) { showError("loginError", err); } finally { busy = false; }
};

// ---------------------------------------------------------------- assessment (4 steps)
function answered(stepIndex) {
  const st = STEPS[stepIndex];
  if (!st.rows) return true;
  return st.rows.every(([key]) => state.answers[st.key][key] != null);
}
const allAnswered = () => [0, 1, 2].every(answered);

function optionLabel(st, value) {
  if (typeof value === "number") return String(value);
  const hit = (st.extra || []).find(([v]) => v === value);
  return hit ? hit[1] : "not answered";
}

function renderAssess() {
  const i = state.step, st = STEPS[i];
  $("stepper").innerHTML = STEPS.map((s, k) => `<li><button type="button" data-step="${k}" class="${answered(k) ? "done" : ""}" ${k === i ? 'aria-current="step"' : ""}>${k + 1}. ${s.label}</button></li>`).join("");
  $("stepper").querySelectorAll("button").forEach(b => b.onclick = () => { state.step = Number(b.dataset.step); save(); renderAssess(); });
  $("stepTitle").textContent = st.title;
  $("stepHelp").textContent = st.help;
  showError("assessError", null);

  if (st.rows) {
    const options = [1, 2, 3, 4, 5].map(n => [n, String(n)]).concat(st.extra);
    $("questions").innerHTML = st.rows.map(([key, text], r) => {
      const current = state.answers[st.key][key];
      return `<fieldset class="rate"><legend>${esc(text)}</legend><div class="seg">${options.map(([v, lab]) =>
        `<label class="${current === v ? "on" : ""}"><input type="radio" name="q${r}" value="${esc(v)}" data-key="${esc(key)}" ${current === v ? "checked" : ""} aria-label="${esc(text)}: ${esc(lab)}">${esc(lab)}</label>`).join("")}</div></fieldset>`;
    }).join("");
    $("questions").querySelectorAll("input").forEach(inp => inp.onchange = () => {
      const v = /^\d$/.test(inp.value) ? Number(inp.value) : inp.value;
      state.answers[st.key][inp.dataset.key] = v; save();
      inp.closest(".seg").querySelectorAll("label").forEach(l => l.classList.toggle("on", l.contains(inp)));
      inp.closest("fieldset").classList.remove("missing");
      updateAssessMeta();
    });
  } else {
    $("questions").innerHTML = STEPS.slice(0, 3).map((s, k) => `<div class="card"><div class="row" style="justify-content:space-between"><h3>${esc(s.label)}</h3>
      <button class="btn link" type="button" data-step="${k}">Edit</button></div>
      <div class="chips" style="margin-top:10px">${s.rows.map(([key, text]) =>
        `<span class="chip ${state.answers[s.key][key] == null ? "gap" : ""}">${esc(s.key === "interests" ? text.split(",")[0] : key)}: ${esc(optionLabel(s, state.answers[s.key][key]))}</span>`).join("")}</div></div>`).join("");
    $("questions").querySelectorAll("[data-step]").forEach(b => b.onclick = () => { state.step = Number(b.dataset.step); save(); renderAssess(); });
  }
  $("prevStep").disabled = i === 0;
  $("nextStep").textContent = i === STEPS.length - 1 ? "Get my matches" : "Next";
  updateAssessMeta();
}

function updateAssessMeta() {
  const total = STEPS.slice(0, 3).reduce((n, s) => n + s.rows.length, 0);
  const done = STEPS.slice(0, 3).reduce((n, s) => n + s.rows.filter(([k]) => state.answers[s.key][k] != null).length, 0);
  $("assessMeta").textContent = `${done} of ${total} answered`;
  $("progressBar").style.width = Math.round(done / total * 100) + "%";
  $("stepper").querySelectorAll("button").forEach((b, k) => b.classList.toggle("done", answered(k)));
}

$("prevStep").onclick = () => { if (state.step > 0) { state.step--; save(); renderAssess(); } };
$("nextStep").onclick = async () => {
  const i = state.step;
  if (STEPS[i].rows && !answered(i)) {
    $("questions").querySelectorAll("fieldset").forEach((f, r) => f.classList.toggle("missing", state.answers[STEPS[i].key][STEPS[i].rows[r][0]] == null));
    return showError("assessError", new Error("Please answer every row. “Can’t assess” / “Not studied” are fine answers."));
  }
  if (i < STEPS.length - 1) { state.step++; save(); return renderAssess(); }
  if (!allAnswered()) { return showError("assessError", new Error("Some answers are missing. Use the steps above to finish them.")); }
  await submitAssessment();
};

// The API format: interests are numbers; a skill or subject is {"rating": n} or a word like "cant_assess".
function toApi(answers) {
  const wrap = (obj) => Object.fromEntries(Object.entries(obj).map(([k, v]) => [k, typeof v === "number" ? { rating: v } : v]));
  return { interests: { ...answers.interests }, skills: wrap(answers.skills), subjects: wrap(answers.subjects) };
}

async function submitAssessment() {
  if (busy) return;
  busy = true; $("nextStep").disabled = true; $("nextStep").textContent = "Finding your matches…";
  try {
    const saved = await api.saveAssessment(toApi(state.answers));
    state.assessmentId = saved.assessment_id;
    const res = await api.recommend(saved.assessment_id, 10);
    state.recs = res.recommendations; save();
    go("results");
  } catch (err) {
    if (!needLogin(err)) showError("assessError", err);
  } finally {
    busy = false; $("nextStep").disabled = false; $("nextStep").textContent = "Get my matches";
  }
}

// ---------------------------------------------------------------- matches
const TICK = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>`;

function scoreBlock(r) {
  if (r.display === "withheld" || r.match_low == null) {
    return `<div class="score" style="font-size:22px">Not enough answers</div><span class="muted small">Interest fit ${pct(r.interest_fit)}</span>`;
  }
  const lo = Math.round(r.match_low), hi = Math.round(r.match_high);
  return lo === hi
    ? `<div class="score num">${lo}<small>/100</small></div><span class="muted small">profile match</span>`
    : `<div class="score num">${lo}–${hi}<small>/100</small></div><span class="muted small">range: some answers were “Can’t assess”</span>`;
}

function partBars(r) {
  const parts = [["Interests", r.interest_fit, r.interest_fit], ["Skills", r.skill_low, r.skill_high], ["Subjects", r.subject_low, r.subject_high]];
  return `<div class="parts">${parts.map(([name, lo, hi]) => `<span>${name}</span><div class="bar"><span style="width:${Math.round((lo ?? 0) * 100)}%"></span></div>
    <span class="num">${lo == null ? "–" : lo === hi || hi == null ? pct(lo) : pct(lo) + "–" + pct(hi)}</span>`).join("")}</div>`;
}

function renderResults() {
  const el = $("v-results");
  if (!state.recs) {
    el.innerHTML = `<div class="card empty"><h2>No matches yet</h2><p class="muted">Finish the assessment to see the careers that fit you.</p>
      <button class="btn primary" type="button" data-go="assess">Take the assessment</button></div>`;
    return;
  }
  el.innerHTML = `<div class="row" style="justify-content:space-between"><div><h1 style="font-size:clamp(26px,4vw,36px)">Your top ${state.recs.length} matches</h1>
      <p class="muted" style="margin-top:6px">From ${new Set(state.recs.map(r => r.field)).size} different fields. Saved to your account (assessment #${esc(state.assessmentId)}).</p></div>
      <button class="btn" type="button" id="editAnswers">Edit answers</button></div>
    ${state.recs.map(r => `<article class="card rec">
      <div class="rank">${r.rank}</div>
      <div class="rec-body">
        <h2 style="font-size:21px">${esc(r.career)}</h2>
        <div class="chips"><span class="chip">${esc(r.field)}</span></div>
        ${r.reasons.length ? `<ul class="reasons">${r.reasons.map(x => `<li>${TICK}<span>${esc(x)}</span></li>`).join("")}</ul>`
                           : `<p class="muted small">Matched on your overall profile.</p>`}
        ${r.follow_ups.length ? `<p class="small" style="color:var(--warn-ink);background:var(--warn-bg);padding:8px 12px;border-radius:10px">To make this score exact, rate: ${r.follow_ups.map(f => esc(f.item)).join(", ")}</p>` : ""}
      </div>
      <div class="rec-side">${scoreBlock(r)}${partBars(r)}
        <button class="btn primary" type="button" data-career="${r.career_id}">View details</button></div>
    </article>`).join("")}`;
  $("editAnswers").onclick = () => { state.step = 0; save(); go("assess"); };
  el.querySelectorAll("[data-career]").forEach(b => b.onclick = () => openCareer(Number(b.dataset.career)));
}

// ---------------------------------------------------------------- career details
function openCareer(careerId) { state.careerId = careerId; save(); go("career"); }

function gapChart(gaps) {
  const shown = gaps.filter(g => g.your_level != null).slice(0, 6);
  const unknown = gaps.filter(g => g.your_level == null);
  if (!shown.length && !unknown.length) return `<p class="muted small">No important skill gaps: you meet the level this career needs in the areas you rated.</p>`;
  return `${shown.length ? `<div class="legend"><span><i style="background:var(--accent)"></i>You now</span><span><i style="background:var(--gap-soft);border:2px dashed var(--gap)"></i>Still to learn</span><span>Scale 0–7 (O*NET level)</span></div>` : ""}
    <div class="gapchart" style="margin-top:12px">${shown.map(g => {
      const you = Math.max(0, g.your_level) / 7 * 100, need = g.required_level / 7 * 100;
      return `<div class="gaprow"><div><b>${esc(g.element)}</b><div class="muted small">${esc(g.survey_row)}${g.note ? " · " + esc(g.note) : ""}</div></div>
        <div class="track" role="img" aria-label="${esc(g.element)}: you ${g.your_level}, needed ${g.required_level} of 7">
          <span class="you" style="width:${you}%"></span><span class="need" style="left:${you}%;width:${Math.max(0, need - you)}%"></span></div>
        <span class="chip gap num">+${g.gap}</span></div>`;
    }).join("")}</div>
    ${unknown.length ? `<p class="muted small" style="margin-top:12px">Not assessed yet: ${unknown.map(g => esc(g.element)).join(", ")}. Rate these to see the gap.</p>` : ""}`;
}

async function renderCareer() {
  const el = $("v-career"), id = state.careerId;
  if (!id) { el.innerHTML = `<div class="card empty"><h2>Pick a career first</h2><button class="btn primary" type="button" data-go="results">Go to matches</button></div>`; return; }
  el.innerHTML = `<div class="card empty"><p class="muted">Loading…</p></div>`;
  try {
    const career = await api.career(id);
    let t = null, note = "";
    if (!career.ranked) note = "O*NET has no skill and interest ratings for this career, so it cannot be scored.";
    else if (!loggedIn() || !state.assessmentId) note = "Take the assessment to see how ready you are for this career.";
    else {
      try { t = await api.target(id, state.assessmentId); }
      catch (err) { if (needLogin(err)) return; note = err.message; }
    }
    if (state.careerId !== id) return;                // the student clicked something else meanwhile
    const back = state.recs ? `<button class="btn link" type="button" data-go="results" style="align-self:flex-start">← All matches</button>`
                            : `<button class="btn link" type="button" data-go="search" style="align-self:flex-start">← Search</button>`;
    const r = t && t.readiness;
    el.innerHTML = `${back}
      <div class="split">
        <div class="main">
          <div class="card"><p class="eyebrow">${esc(career.field)} · O*NET ${esc(career.code)}${career.job_zone ? " · Job Zone " + career.job_zone + " of 5" : ""}</p>
            <h1 style="font-size:clamp(26px,4vw,38px);margin-top:6px">${esc(career.title)}</h1>
            <p style="margin-top:12px">${esc(career.description || "")}</p></div>
          ${t ? `<div class="card"><h2>Why it fits you</h2>${t.reasons.length ? `<ul class="reasons" style="margin-top:12px">${t.reasons.map(x => `<li>${TICK}<span>${esc(x)}</span></li>`).join("")}</ul>` : `<p class="muted" style="margin-top:8px">No single answer stands out; the match comes from your overall profile.</p>`}</div>
          <div class="card"><h2>Skills to build</h2><div style="margin-top:12px">${gapChart(t.gaps)}</div></div>` : `<div class="card"><p class="muted">${esc(note)}</p></div>`}
        </div>
        ${t ? `<div class="side">
          <div class="card"><h3>Your readiness</h3>
            <div style="margin-top:10px">${scoreBlock({ display: r.display, match_low: r.match_low, match_high: r.match_high, interest_fit: t.interest_fit.value })}</div>
            <div style="margin-top:12px">${partBars({ interest_fit: t.interest_fit.value, skill_low: r.skill_low, skill_high: r.skill_high, subject_low: r.subject_low, subject_high: r.subject_high })}</div>
            <p class="small muted" style="margin-top:12px">Interest fit is <b>${esc(t.interest_fit.label)}</b>: this career is mostly ${t.interest_fit.career_top_types.map(esc).join(" + ")}; your top interests are ${t.interest_fit.your_top_types.map(esc).join(" + ")}.</p></div>
          ${t.questions_needed.length ? `<div class="card"><h3>Answer to check</h3><p class="muted small" style="margin-top:6px">These matter for this career but you marked them “Can’t assess”: ${t.questions_needed.map(q => esc(q.item)).join(", ")}.</p></div>` : ""}
          ${t.alternatives.length ? `<div class="card"><h3>Similar careers</h3><div style="display:flex;flex-direction:column;margin-top:8px">${t.alternatives.map(a =>
            `<button type="button" class="btn link" data-career="${a.career_id}" style="justify-content:space-between;text-align:left;gap:12px;border-top:1px solid var(--line);border-radius:0;padding:12px 0;color:var(--ink)"><span>${esc(a.career)}</span><b class="num" style="color:var(--accent)">${a.match_low == null ? "–" : Math.round(a.match_low)}</b></button>`).join("")}</div></div>` : ""}
        </div>` : ""}
      </div>`;
    el.querySelectorAll("[data-career]").forEach(b => b.onclick = () => openCareer(Number(b.dataset.career)));
  } catch (err) {
    el.innerHTML = `<div class="card empty"><h2>Could not load this career</h2><p class="muted">${esc(err.message)}</p><button class="btn" type="button" data-go="results">Back</button></div>`;
  }
}

// ---------------------------------------------------------------- search
$("searchForm").onsubmit = async (e) => {
  e.preventDefault();
  const q = $("searchBox").value.trim(), out = $("searchResults");
  if (q.length < 2) { out.innerHTML = `<p class="muted">Type at least 2 letters.</p>`; return; }
  out.innerHTML = `<p class="muted">Searching…</p>`;
  try {
    const hits = await api.searchCareers(q);
    out.innerHTML = hits.length ? hits.map(h => `<button type="button" class="card" data-career="${h.career_id}" style="text-align:left;cursor:pointer;display:flex;flex-direction:column;gap:6px">
        <b>${esc(h.title)}</b><span class="muted small">${esc(h.field)}${h.matched_title ? " · also called “" + esc(h.matched_title) + "”" : ""}${h.ranked ? "" : " · not scored (no O*NET ratings)"}</span></button>`).join("")
      : `<p class="muted">No careers found for “${esc(q)}”.</p>`;
    out.querySelectorAll("[data-career]").forEach(b => b.onclick = () => openCareer(Number(b.dataset.career)));
  } catch (err) { out.innerHTML = `<p class="alert">${esc(err.message)}</p>`; }
};

// ---------------------------------------------------------------- start
renderWho();
go(loggedIn() && state.recs ? "results" : "home");
