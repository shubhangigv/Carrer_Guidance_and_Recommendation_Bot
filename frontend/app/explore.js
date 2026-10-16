// Explore (#/explore, #/explore/beauty-wellness, #/search/nurse): browse careers by industry or search by
// name. Industries and which careers belong to them are set in config/industries.csv.

function searchForm(value = "") {
  return `<form id="searchForm" class="row" role="search" style="gap:8px">
    <input id="searchBox" class="input" type="search" minlength="2" maxlength="100" value="${esc(value)}"
      placeholder="Search a job: nurse, chef, pilot, sommelier, data…" aria-label="Search careers" style="flex:1 1 260px">
    <button class="btn go" type="submit">Search</button></form>`;
}
function wireSearch() {
  $("searchForm").onsubmit = (e) => {
    e.preventDefault();
    const v = $("searchBox").value.trim();
    if (v.length >= 2) location.hash = "#/search/" + encodeURIComponent(v);
  };
}
function careerItem(c) {
  return `<li><a class="linkrow" href="#/career/${c.career_id}"><span><b>${esc(c.display_title)}</b>
    ${c.matched_title ? `<span class="tiny faint"> · also called “${esc(c.matched_title)}”</span>` : ""}
    ${c.excluded_reason ? `<span class="tag red">Not recommended in India</span>` : ""}</span>
    <span class="tiny faint" style="text-align:right">${esc(prepLabel(c.job_zone))}</span></a></li>`;
}

PAGES.explore = async (params) => {
  if (params[0]) return industryPage(params[0]);
  loading();
  const list = await api.industries();
  show(`<div><p class="kicker">Explore</p><h1>Careers by industry</h1>
      <p class="soft" style="margin-top:6px">Pick an area you are curious about, or search for a job by name.</p></div>
    ${searchForm()}
    <div class="grid">${list.filter(i => i.careers > 0).map(i => `<a class="card" href="#/explore/${esc(i.id)}" style="text-decoration:none;color:inherit;display:flex;flex-direction:column;gap:6px">
      <b style="font-family:var(--serif);font-size:19px">${esc(i.name)}</b><span class="small soft">${esc(i.description)}</span>
      <span class="tiny faint" style="margin-top:auto">${plural(i.careers, "career")}</span></a>`).join("")}</div>`);
  wireSearch();
};

async function industryPage(id) {
  loading();
  const ind = await api.industry(id);
  show(`<a class="btn quiet" href="#/explore" style="align-self:flex-start">← All industries</a>
    <div><p class="kicker">Industry</p><h1>${esc(ind.name)}</h1><p class="soft" style="margin-top:6px">${esc(ind.description)}</p></div>
    <div class="row"><input id="filter" class="input" type="search" placeholder="Filter these ${ind.careers.length} careers…" aria-label="Filter careers" style="flex:1 1 240px">
      <select id="prep" class="input" style="flex:0 1 260px" aria-label="Preparation"><option value="">Any preparation</option>
        ${[1, 2, 3, 4, 5].map(z => `<option value="${z}">${esc(PREP[z])}</option>`).join("")}</select></div>
    <div class="card" style="padding-top:6px;padding-bottom:6px"><ul class="list" id="careerList"></ul></div>`);
  const draw = () => {
    const f = $("filter").value.trim().toLowerCase(), z = $("prep").value;
    const rows = ind.careers.filter(c => (!f || (c.display_title + " " + c.title).toLowerCase().includes(f)) && (!z || String(c.job_zone) === z));
    $("careerList").innerHTML = rows.length ? rows.map(careerItem).join("") : `<li class="soft">No careers match.</li>`;
  };
  $("filter").oninput = draw; $("prep").onchange = draw;
  draw();
}

PAGES.search = async (params) => {
  const q = (params.join("/") || "").trim();
  show(`<a class="btn quiet" href="#/explore" style="align-self:flex-start">← Explore</a><h1>Search careers</h1>${searchForm(q)}<div id="results" class="card" style="padding-top:6px;padding-bottom:6px"><p class="loading">Searching…</p></div>`);
  wireSearch();
  if (q.length < 2) { $("results").innerHTML = `<p class="soft">Type at least 2 letters.</p>`; return; }
  const hits = await api.searchCareers(q);
  $("results").innerHTML = hits.length ? `<ul class="list">${hits.map(careerItem).join("")}</ul>` : `<p class="soft">No careers found for “${esc(q)}”. Try a shorter word.</p>`;
};
