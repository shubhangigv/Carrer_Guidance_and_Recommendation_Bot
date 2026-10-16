// Career details (#/career/12): what the career is, how ready you are, EVERY important skill and
// knowledge area it needs (not only the quiz questions), preparation, salary (only with a source),
// jobs near you and similar careers.

let industryNames = null;                           // id -> name, loaded once
async function industryName(id) {
  if (!industryNames) industryNames = Object.fromEntries((await api.industries()).map(i => [i.id, i.name]));
  return industryNames[id] || id;
}

const STATUS_TEXT = { build: "To build", have: "You have this", not_assessed: "You said “Not sure”", not_measured: "Not in the quiz – check yourself" };

PAGES.career = async (params) => {
  const id = Number(params[0]);
  if (!id) return failed(new Error("No career selected."));
  loading();
  const [career, reqs, path] = await Promise.all([api.career(id), api.requirements(id), api.pathway(id)]);
  let fit = null;
  if (loggedIn() && state.assessmentId && career.ranked) {
    try { fit = await api.target(id, state.assessmentId); } catch (e) { if (e.status === 401) return handle(e); }
  }
  const names = await Promise.all(career.industries.map(industryName));
  const needs = reqs.requirements;
  const measured = needs.some(r => r.your_level != null);
  const title = career.display_title;

  show(`<a class="btn quiet" href="javascript:history.back()" style="align-self:flex-start">← Back</a>
    <div><p class="kicker">${names.map(esc).join(" · ") || esc(career.field)}</p>
      <h1 style="margin-top:4px">${esc(title)}</h1>
      ${career.title !== title ? `<p class="soft small" style="margin-top:4px">Official O*NET title: ${esc(career.title)} (${esc(career.code)})</p>` : ""}
      <div class="tags" style="margin-top:10px"><span class="tag green">${esc(prepLabel(career.job_zone))}</span><span class="tag">${esc(career.field)}</span>
        ${career.excluded_reason ? `<span class="tag red">Not recommended in India</span>` : ""}</div></div>
    ${career.excluded_reason ? `<p class="alert">${esc(career.excluded_reason)}</p>` : ""}
    <div class="cols">
      <div class="wide">
        <div class="card"><h2>What the work is</h2><p style="margin-top:10px">${esc(career.description || "No description in O*NET.")}</p></div>
        ${pathwayHtml(path)}
        <div class="card" id="skillsCard"><div class="spread"><h2>${measured ? "Skills to build" : "What this career needs"}</h2>
          ${career.ranked && !career.excluded_reason ? `<a class="btn go" href="#/roadmap/${id}">Make my roadmap</a>` : ""}</div>
          <p class="soft small" style="margin-top:6px">${measured ? "Every skill and knowledge area O*NET rates as important (3 or more out of 5) for this career, compared with your quiz answers."
            : "Every skill and knowledge area O*NET rates as important for this career. " + (loggedIn() ? "Take the quiz to compare them with your level." : "Log in and take the quiz to compare them with your level.")}</p>
          ${skillsHtml(needs, measured, path.courses)}</div>
      </div>
      <div class="narrow">
        ${fit ? fitHtml(fit) : ""}
        <div class="card"><h3>Salary</h3>${career.salary
          ? `<p class="small" style="margin-top:8px"><b class="num">₹${career.salary.min_lpa}–${career.salary.max_lpa} lakh</b> per year</p>
             <p class="tiny faint">Source: ${career.salary.source_url ? `<a href="${esc(career.salary.source_url)}" target="_blank" rel="noopener">${esc(career.salary.source_name)}</a>` : esc(career.salary.source_name)}${career.salary.year ? ", " + esc(career.salary.year) : ""}</p>`
          : `<p class="small soft" style="margin-top:8px">We have not added verified Indian salary data for this career yet.</p>`}
          <p class="tiny" style="margin-top:8px"><a href="${esc(salaryCheckLink(title))}" target="_blank" rel="noopener">Check current salaries online →</a></p></div>
        <div class="card"><h3>Find openings${state.location ? " in " + esc(state.location) : ""}</h3><p class="small" style="margin-top:8px">${linkList(jobLinks(title, placeFor(state.location)))}</p></div>
        ${fit && fit.alternatives.length ? `<div class="card"><h3>Similar careers</h3><p class="tiny faint">Number = your match score for that career.</p><ul class="list" style="margin-top:6px">${fit.alternatives.map(a =>
          `<li><a class="linkrow" href="#/career/${a.career_id}"><b>${esc(a.display_title)}</b><span class="num faint small">${a.match_low == null ? "–" : Math.round(a.match_low)}</span></a></li>`).join("")}</ul></div>` : ""}
        <a class="btn" href="#/assistant/${id}">Ask the assistant about this career</a>
      </div>
    </div>`);
};

// "Anywhere in India" / "Abroad" are not places a job site understands.
function placeFor(loc) { return !loc || /anywhere|abroad|home town/i.test(loc) ? "" : loc; }

function fitHtml(t) {
  const r = t.readiness;
  return `<div class="card"><h3>Your fit</h3><div style="margin-top:10px">${scoreHtml({ display: r.display, match_low: r.match_low, match_high: r.match_high, interest_fit: t.interest_fit.value })}</div>
    <p class="small soft" style="margin-top:10px">Interest fit is <b>${esc(t.interest_fit.label)}</b>: this career is mostly
    ${t.interest_fit.career_top_types.map(esc).join(" + ")}; your strongest interests are ${t.interest_fit.your_top_types.map(esc).join(" + ")}.</p>
    ${t.reasons.length ? `<ul class="why">${t.reasons.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}</div>`;
}

function skillsHtml(needs, measured, courses) {
  if (!needs.length) return `<p class="soft" style="margin-top:12px">O*NET has no skill ratings for this career.</p>`;
  const row = (r) => {
    const you = r.your_level == null ? 0 : Math.min(100, r.your_level / 7 * 100);
    const need = r.required_level == null ? null : r.required_level / 7 * 100;
    const tag = r.status === "build" ? "gold" : r.status === "have" ? "green" : "";
    return `<div class="skill"><div><b>${esc(r.element)}</b><div class="tiny faint">${r.kind === "skill" ? "Skill" : "Knowledge"} · importance ${r.importance}/5${r.quiz_row ? " · quiz: " + esc(r.quiz_row) : ""}</div>
        ${r.status === "build" ? `<div class="tiny" style="margin-top:2px">${coursesHtml(r.element, courses)}</div>` : ""}</div>
      <div class="track" role="img" aria-label="${esc(r.element)}: ${r.your_level == null ? "your level unknown" : "you " + r.your_level}, needed ${r.required_level ?? "–"} of 7">
        ${r.your_level == null ? "" : `<span class="you" style="width:${you}%"></span>`}${need == null ? "" : `<span class="need" style="left:${need}%"></span>`}</div>
      ${measured ? `<span class="tag ${tag}">${esc(STATUS_TEXT[r.status])}</span>` : `<span class="tiny faint num">level ${r.required_level ?? "–"}/7</span>`}</div>`;
  };
  if (!measured) return `<div class="legend" style="margin-top:12px"><span><i style="background:var(--ink);width:3px"></i>Level needed (0–7)</span></div>${needs.map(row).join("")}`;
  const groups = [["To build", needs.filter(r => r.status === "build").sort((a, b) => b.priority - a.priority)],
                  ["Check yourself", needs.filter(r => r.status === "not_assessed" || r.status === "not_measured")],
                  ["You already have", needs.filter(r => r.status === "have")]];
  return `<div class="legend" style="margin-top:12px"><span><i style="background:var(--green)"></i>Your level</span><span><i style="background:var(--ink);width:3px"></i>Level needed (0–7)</span></div>
    ${groups.filter(([, rows]) => rows.length).map(([name, rows]) => `<h3 style="margin-top:18px">${name} <span class="faint small">(${rows.length})</span></h3>${rows.map(row).join("")}`).join("")}`;
}

// "How to get there": Indian education route(s), stream after Class 10, O*NET education (US), career ladder.
function pathwayHtml(p) {
  const routes = p.routes.map(r => `<div style="margin-top:14px"><div class="spread"><h3>${esc(r.name)}</h3>
      ${r.verified ? `<span class="tag green">Checked by the team</span>` : `<span class="tag gold">Not yet checked – confirm on the official site</span>`}</div>
      <ol class="steps">${r.steps.map((st, i) => `<li class="step" style="grid-template-columns:110px minmax(0,1fr)">
        <span class="kicker" style="color:var(--soft)">${esc(st.stage)}</span>
        <div><p>${esc(st.text)}</p>${st.link_url ? `<p class="tiny" style="margin-top:4px"><a href="${esc(st.link_url)}" target="_blank" rel="noopener">${esc(st.link_name || "Official website")} →</a></p>` : ""}</div></li>`).join("")}</ol></div>`).join("");
  const ladder = (title, rows, note) => rows.length ? `<div style="margin-top:14px"><h3>${title}</h3><p class="tiny faint">${note}</p><ul class="list">${rows.map(c =>
      `<li><a class="linkrow" href="#/career/${c.career_id}"><b>${esc(c.display_title)}</b><span class="tiny faint">${esc(prepLabel(c.job_zone))}</span></a></li>`).join("")}</ul></div>` : "";
  return `<div class="card"><h2>How to get there</h2>
    <div class="tags" style="margin-top:10px"><span class="tag green">${esc(prepLabel(p.job_zone))}</span>
      ${p.stream ? `<span class="tag">After Class 10: ${esc(p.stream.stream)}</span>` : ""}</div>
    ${p.stream && p.stream.because.length ? `<p class="tiny faint" style="margin-top:6px">Stream suggested because this career uses ${p.stream.because.map(esc).join(", ")} (Pathfinder's suggestion from O*NET data).</p>` : ""}
    ${routes || `<p class="soft small" style="margin-top:12px">We have not written an Indian education route for this career yet. Ask the assistant, or check the courses colleges offer for “${esc(p.display_title)}”.</p>`}
    ${p.education_us.length ? `<div style="margin-top:14px"><h3>What workers studied (US)</h3><p class="tiny faint">O*NET survey of people in this job in the USA – a rough guide only.</p>
      ${p.education_us.map(e => `<div class="parts" style="grid-template-columns:minmax(0,1fr) 120px auto"><span>${esc(e.label)}</span><div class="meter"><i style="width:${e.percent}%"></i></div><span class="num">${e.percent}%</span></div>`).join("")}</div>` : ""}
    ${ladder("Ways in", p.ways_in, "Related careers that need less preparation – a common starting point.")}
    ${ladder("Where you can grow", p.grow_into, "Related careers that need more preparation or experience.")}
  </div>`;
}
