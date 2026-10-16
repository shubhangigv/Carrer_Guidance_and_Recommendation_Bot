// Your matches (#/matches): the top 10 careers from the quiz, and - if you wrote something about
// yourself - the careers whose descriptions best match your own words.

const METHOD_NAME = (m) => (m || "").startsWith("sbert") ? "Sentence-BERT (matches by meaning)" : "TF-IDF (matches shared words)";

PAGES.matches = async () => {
  if (needLogin("#/matches")) return;
  if (!state.recs) {
    if (!state.assessmentId) {
      return show(`<div class="card empty"><h2>No matches yet</h2><p class="soft">Take the quiz to see careers that fit you.</p>
        <a class="btn go" href="#/quiz">Take the quiz</a></div>`);
    }
    loading("Getting your matches…");
    state.recs = (await api.recommend(state.assessmentId, 10)).recommendations;
    saveState();
  }
  const fields = new Set(state.recs.map(r => r.field)).size;
  show(`<div class="spread"><div><p class="kicker">Your matches</p><h1>Careers that fit your answers</h1>
      <p class="soft" style="margin-top:6px">${state.recs.length} careers from ${fields} different fields. Open one to see the skills it needs and your roadmap.</p></div>
      <div class="row"><a class="btn" href="#/quiz" id="retake">Change my answers</a></div></div>
    <div class="card" style="padding-top:4px;padding-bottom:4px">${state.recs.map(matchRow).join("")}</div>
    <section id="wordsBox"></section>`);
  $("retake").onclick = () => { state.quizStep = QUESTIONS.length; saveState(); };
  if (state.aboutMe) renderWordMatches();
};

function matchRow(r) {
  const parts = [["Interests", r.interest_fit, r.interest_fit], ["Skills", r.skill_low, r.skill_high], ["Subjects", r.subject_low, r.subject_high]];
  const official = r.career !== r.display_title ? `<p class="tiny faint">O*NET: ${esc(r.career)}</p>` : "";
  return `<article class="match">
    <div class="rank num">${r.rank}</div>
    <div><h2 style="font-size:22px"><a href="#/career/${r.career_id}" style="color:inherit;text-decoration:none">${esc(r.display_title)}</a></h2>${official}
      <div class="tags" style="margin-top:6px"><span class="tag">${esc(r.field)}</span></div>
      ${r.reasons.length ? `<ul class="why">${r.reasons.slice(0, 3).map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : `<p class="soft small" style="margin-top:8px">Matched on your overall profile.</p>`}
      ${r.follow_ups.length ? `<p class="tiny" style="margin-top:8px;color:var(--gold-text)">To make this score exact, answer: ${r.follow_ups.map(f => esc(f.item)).join(", ")}</p>` : ""}
      <div class="row" style="margin-top:10px"><a class="btn" href="#/career/${r.career_id}">Skills &amp; details</a><a class="btn quiet" href="#/roadmap/${r.career_id}">Roadmap →</a></div>
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
    box.innerHTML = `<div class="card"><p class="kicker">From your own words</p>
      <h2 style="margin-top:4px">Careers that match “${esc(state.aboutMe.length > 80 ? state.aboutMe.slice(0, 80) + "…" : state.aboutMe)}”</h2>
      <p class="tiny faint" style="margin-top:6px">Method: ${esc(METHOD_NAME(res.method))}. This list is separate from the quiz score above.</p>
      ${res.results.length ? `<ul class="list" style="margin-top:10px">${res.results.map(c => `<li><a class="linkrow" href="#/career/${c.career_id}">
        <span><b>${esc(c.display_title)}</b> <span class="tag">${esc(c.field)}</span></span><span class="tiny faint num">similarity ${c.similarity.toFixed(2)}</span></a></li>`).join("")}</ul>`
        : `<p class="soft" style="margin-top:10px">No career descriptions share words with what you wrote. Try describing activities you enjoy.</p>`}</div>`;
  } catch (err) { box.innerHTML = `<p class="tiny faint">Could not match your words: ${esc(err.message)}</p>`; }
}
