// Roadmap (#/roadmap and #/roadmap/12): a step-by-step plan for one career, made from O*NET and your
// quiz answers: qualification -> skills to build (most important gap first) -> skills to check ->
// experience -> applying. Tick steps as you finish them; progress is saved to your account.

PAGES.roadmap = async (params) => {
  if (needLogin(location.hash)) return;
  const id = Number(params[0]);
  if (!id) return roadmapList();
  loading("Building your roadmap…");
  const [first, path] = await Promise.all([api.roadmap(id), api.pathway(id)]);
  draw(first);

  function draw(plan) {
    const stages = ["Foundation", "Start now", "Next", "Later"];
    const done = plan.done, total = plan.total;
    show(`<a class="btn quiet" href="#/career/${plan.career_id}" style="align-self:flex-start">← ${esc(plan.display_title)}</a>
      <div class="spread"><div><p class="kicker">Your roadmap</p><h1>${esc(plan.display_title)}</h1>
        ${!state.assessmentId ? `<p class="soft" style="margin-top:6px">Take the quiz to put the skills you need in order.</p>` : ""}</div>
        <div style="min-width:200px"><div class="spread small"><span>Progress</span><span class="num">${done} of ${total} steps</span></div>
          <div class="meter" style="margin-top:6px"><i style="width:${Math.round(done / total * 100)}%"></i></div></div></div>
      ${stages.map(stage => {
        const steps = plan.steps.filter(s => s.stage === stage);
        return steps.length ? `<section class="card stage"><h2>${esc(stage)}</h2><ol class="steps" style="margin-top:6px">${steps.map(st => stepHtml(st, plan)).join("")}</ol></section>` : "";
      }).join("")}`);
    document.querySelectorAll("[data-step]").forEach(box => box.onchange = async () => {
      box.disabled = true;
      try { draw(await api.setStep(plan.career_id, box.dataset.step, box.checked)); }
      catch (err) { box.checked = !box.checked; box.disabled = false; err.status === 401 ? handle(err) : toast(err.message); }
    });
  }

  function stepHtml(s, plan) {
    let extra = "";
    if (s.key.startsWith("build:")) extra = `<p class="tiny" style="margin-top:6px">${coursesHtml(s.items[0].element, path.courses)}</p>`;
    if (s.key === "education" && path.routes.length) extra = `<p class="tiny" style="margin-top:6px">Route: ${path.routes[0].steps.map(st => esc(st.stage + ": " + st.text.split(".")[0])).join(" → ")}
      <a href="#/career/${plan.career_id}">full details →</a></p>`;
    if (s.key === "check") extra = `<div class="tags" style="margin-top:8px">${s.items.map(r => `<span class="tag">${esc(r.element)}</span>`).join("")}</div>`;
    if (s.key === "apply") extra = `<p class="tiny" style="margin-top:6px">${linkList(jobLinks(plan.display_title, placeFor(state.location)))}</p>`;
    return `<li class="step ${s.done ? "done" : ""}"><input type="checkbox" id="st-${esc(s.key)}" data-step="${esc(s.key)}" ${s.done ? "checked" : ""}
        aria-label="Mark “${esc(s.title)}” as done"><div><h3><label for="st-${esc(s.key)}">${esc(s.title)}</label></h3>
        <p class="soft small" style="margin-top:4px">${esc(s.detail)}</p>${extra}</div></li>`;
  }
};

async function roadmapList() {
  loading();
  const mine = await api.roadmaps();
  const recs = state.recs || [];
  show(`<div><p class="kicker">Roadmaps</p><h1>Plan your way into a career</h1>
      <p class="soft" style="margin-top:6px">Pick a career to see the qualification, skills and steps you need – in order.</p></div>
    ${mine.length ? `<div class="card"><h2>In progress</h2><ul class="list" style="margin-top:6px">${mine.map(m =>
      `<li><a class="linkrow" href="#/roadmap/${m.career_id}"><b>${esc(m.display_title)}</b><span class="small faint">${m.done} step${m.done === 1 ? "" : "s"} done</span></a></li>`).join("")}</ul></div>` : ""}
    <div class="card"><h2>From your matches</h2>${recs.length ? `<ul class="list" style="margin-top:6px">${recs.slice(0, 6).map(r =>
      `<li><a class="linkrow" href="#/roadmap/${r.career_id}"><b>${esc(r.display_title)}</b><span class="small faint">${esc(r.field)}</span></a></li>`).join("")}</ul>`
      : `<p class="soft" style="margin-top:8px">Take the quiz first, or pick any career from <a href="#/explore">Explore</a> and choose “Make my roadmap”.</p>`}</div>`);
}
