// Your matches (#/matches): the top 10 careers, grouped into "in your areas" and "also worth a look",
// with a "Not for me" button on each, and - if you wrote something about yourself - the careers whose
// descriptions best match your own words.

const METHOD_NAME = (m) => (m || "").startsWith("sbert") ? "Sentence-BERT (matches by meaning)" : "TF-IDF (matches shared words)";

// Fetch the matches for the current assessment and keep them (with the notes) in state.
async function loadRecs() {
  const res = await api.recommend(state.assessmentId, 10);
  state.recs = res.recommendations;
  state.recInfo = { notes: res.notes || [], chosenAreas: res.chosen_areas || [], areasFrom: res.areas_from };
  saveState();
}

PAGES.matches = async () => {
  if (needLogin("#/matches")) return;
  if (!state.recs || !state.recInfo) {
    if (!state.assessmentId) {
      return show(`<div class="card empty"><h2>No matches yet</h2><p class="soft">Take the quiz to see careers that fit you.</p>
        <a class="btn go" href="#/quiz">Take the quiz</a></div>`);
    }
    loading("Getting your matches…");
    try { await loadRecs(); } catch (err) { return handle(err); }
  }
  const info = state.recInfo;
  const mine = state.recs.filter(r => r.group === "your_areas");
  const rest = state.recs.filter(r => r.group !== "your_areas");
  const areaText = info.chosenAreas.join(", ");
  const heading = mine.length
    ? `<h2 class="group-title">In your areas <span class="soft">· ${esc(areaText)}${info.areasFrom === "course" ? " (from your course)" : ""}</span></h2>`
    : "";
  shared = sharedReasons(state.recs);
  const restTitle = mine.length ? `<h2 class="group-title">Also worth a look <span class="soft">· outside your areas, but they fit your answers</span></h2>` : "";
  show(`<div class="spread"><div><p class="kicker">Your matches</p><h1>Careers that fit you</h1>
      <p class="soft" style="margin-top:6px">Open one to see the skills it needs and your roadmap. Not interested? Tap “Not for me” and we will show another.</p></div>
      <div class="row"><a class="btn" href="#/quiz" id="retake">Change my answers</a></div></div>
    ${flatWarning()}
    ${shared.size ? `<div class="card notes"><p class="tiny faint">Why these careers came up</p><ul class="why">${[...shared].map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>` : ""}
    ${info.notes.length ? `<div class="card notes"><p class="tiny faint">What we used</p><ul class="why">${info.notes.map(n => `<li>${esc(n)}</li>`).join("")}</ul>
      ${info.notes.some(n => n.includes("not for me")) ? `<button class="btn quiet" type="button" id="unhideAll">Show hidden careers again</button>` : ""}</div>` : ""}
    ${heading}${mine.length ? `<div class="card" style="padding-top:4px;padding-bottom:4px">${mine.map(matchRow).join("")}</div>` : ""}
    ${restTitle}${rest.length ? `<div class="card" style="padding-top:4px;padding-bottom:4px">${rest.map(matchRow).join("")}</div>` : ""}
    <section id="wordsBox"></section>`);
  $("retake").onclick = () => { state.quizStep = QUESTIONS.length; saveState(); };
  document.querySelectorAll("[data-hide]").forEach(b => b.onclick = () => hideCareer(Number(b.dataset.hide), b));
  if ($("unhideAll")) $("unhideAll").onclick = unhideAll;
  if ($("fixFlat")) $("fixFlat").onclick = () => { state.quizStep = QUESTIONS.findIndex(q => q.key === "strengths"); saveState(); };
  if (state.aboutMe) renderWordMatches();
};

// Reasons that appear on most cards (e.g. "High Social interest") are shown once at the top instead,
// so each card only lists what is special about that career.
let shared = new Set();
function sharedReasons(recs) {
  const count = {};
  recs.forEach(r => new Set(r.reasons).forEach(x => { count[x] = (count[x] || 0) + 1; }));
  const most = Math.max(3, Math.ceil(recs.length * 0.6));
  return new Set(Object.keys(count).filter(x => count[x] >= most && !x.startsWith("In an area")));
}

// All skills rated the same and no strongest skills picked: the skill answers cannot tell careers apart.
function flatWarning() {
  const ratings = Object.values(state.draft.skills || {}).filter(v => typeof v === "number");
  const flat = ratings.length >= 6 && new Set(ratings).size === 1;
  if (!flat || (state.draft.profile.strengths || []).length) return "";
  return `<p class="alert">You gave every skill the same rating, so your skills cannot separate careers - your interests decide most of the order.
    <a href="#/quiz" id="fixFlat">Pick your 3 strongest skills</a> for sharper matches.</p>`;
}

async function hideCareer(id, btn) {
  btn.disabled = true; btn.textContent = "Hiding…";
  try {
    await api.hideCareer(id);
    await loadRecs();
    toast("Hidden. We will not show it again - you can undo this above.");
    route();
  } catch (err) { btn.disabled = false; btn.textContent = "Not for me"; handle(err); }
}

async function unhideAll() {
  try {
    const { career_ids } = await api.hidden();
    for (const id of career_ids) await api.unhideCareer(id);
    await loadRecs();
    route();
  } catch (err) { handle(err); }
}

function matchRow(r) {
  const parts = [["Interests", r.interest_fit, r.interest_fit], ["Skills", r.skill_low, r.skill_high], ["Subjects", r.subject_low, r.subject_high]];
  const official = r.career !== r.display_title ? `<p class="tiny faint">O*NET: ${esc(r.career)}</p>` : "";
  const tags = [`<span class="tag">${esc(r.field)}</span>`]
    .concat((r.areas || []).map(a => `<span class="tag green">${esc(a)}</span>`))
    .concat(r.course_link ? [`<span class="tag gold">Fits your course</span>`] : []);
  const own = r.reasons.filter(x => !shared.has(x));
  return `<article class="match" data-career="${r.career_id}">
    <div class="rank num">${r.rank}</div>
    <div><h2 style="font-size:22px"><a href="#/career/${r.career_id}" style="color:inherit;text-decoration:none">${esc(r.display_title)}</a></h2>${official}
      ${r.summary ? `<p class="soft small" style="margin-top:4px"><b>What you'd do:</b> ${esc(r.summary)}</p>` : ""}
      <div class="tags" style="margin-top:6px">${tags.join("")}</div>
      ${own.length ? `<ul class="why">${own.slice(0, 3).map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : `<p class="soft small" style="margin-top:8px">Fits the reasons at the top of this page.</p>`}
      ${r.follow_ups.length ? `<p class="tiny" style="margin-top:8px;color:var(--gold-text)">To make this score exact, answer: ${r.follow_ups.map(f => esc(f.item)).join(", ")}</p>` : ""}
      <div class="row" style="margin-top:10px"><a class="btn" href="#/career/${r.career_id}">Skills &amp; details</a><a class="btn quiet" href="#/roadmap/${r.career_id}">Roadmap →</a>
        <button class="btn quiet" type="button" data-hide="${r.career_id}">Not for me</button></div>
    </div>
    <div class="side">${scoreHtml(r)}
      <div class="parts">${parts.map(([n, lo, hi]) => `<span>${n}</span><div class="meter"><i style="width:${Math.round((lo ?? 0) * 100)}%"></i></div>
        <span class="num">${pctRange(lo, hi)}</span>`).join("")}</div></div>
  </article>`;
}

async function renderWordMatches() {
  const box = $("wordsBox");
  box.innerHTML = `<p class="loading">Matching what you wrote…</p>`;
  try {
    const res = await api.matchText(state.aboutMe, 6);
    if (!box.isConnected) return;
    const quote = esc(state.aboutMe.length > 80 ? state.aboutMe.slice(0, 80) + "…" : state.aboutMe);
    box.innerHTML = `<div class="card"><p class="kicker">From your own words</p>
      <h2 style="margin-top:4px">Careers that match “${quote}”</h2>
      <p class="tiny faint" style="margin-top:6px">Method: ${esc(METHOD_NAME(res.method))}. This list is separate from the quiz score above.</p>
      ${res.results.length ? `<ul class="list" style="margin-top:10px">${res.results.map(c => `<li><a class="linkrow" href="#/career/${c.career_id}">
        <span><b>${esc(c.display_title)}</b> <span class="tag">${esc(c.field)}</span></span><span class="tiny faint num">similarity ${c.similarity.toFixed(2)}</span></a></li>`).join("")}</ul>`
        : `<p class="soft" style="margin-top:10px">No confident match: “${quote}” is too general to point to a career. Say what you enjoy <i>doing</i> - tap some ideas below or rewrite it.</p>`}
      <details style="margin-top:12px" ${res.results.length ? "" : "open"}><summary class="tiny">Change what you wrote</summary>
        <div class="chips" style="margin-top:8px">${IDEAS.map(t => `<button type="button" data-idea2="${esc(t)}">+ ${esc(t)}</button>`).join("")}</div>
        <textarea id="about2" class="input" maxlength="1000" style="margin-top:8px">${esc(state.aboutMe)}</textarea>
        <button class="btn go" type="button" id="rematch" style="margin-top:8px">Match again</button></details></div>`;
    // careers in the quiz list that ALSO match the text get a tag
    const hits = new Set(res.results.map(c => c.career_id));
    document.querySelectorAll("article.match[data-career]").forEach(a => {
      if (hits.has(Number(a.dataset.career)) && !a.querySelector(".tag.words"))
        a.querySelector(".tags").insertAdjacentHTML("beforeend", `<span class="tag gold words">Matches what you wrote</span>`);
    });
    const input = $("about2");
    document.querySelectorAll("[data-idea2]").forEach(b => b.onclick = () => {
      const t = input.value.trim(), idea = b.dataset.idea2;
      const vague = !t || /^i (love|like) (using )?(a )?(laptop|computer|phone)s?\.?$/i.test(t);
      input.value = vague ? `I enjoy ${idea}` : `${t.replace(/[.\s]+$/, "")}, ${idea}`;
    });
    $("rematch").onclick = () => {
      const t = input.value.trim();
      if (t.length < 3) return toast("Write a few words about what you enjoy.");
      state.aboutMe = t; saveState(); renderWordMatches();
    };
  } catch (err) { box.innerHTML = `<p class="tiny faint">Could not match your words: ${esc(err.message)}</p>`; }
}
