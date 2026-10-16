// Shared helpers, the page router and the header. Every page file registers itself in PAGES.
// Pages are addressed by the part after "#": #/explore, #/career/12, #/roadmap/12 ...
// so the browser's back button works and a page can be bookmarked.

const PAGES = {};                                   // name -> function(params) that draws the page
const STATE_KEY = "pathfinder.state";
const blankState = () => ({ name: "", email: "", assessmentId: null, location: "", aboutMe: "", recs: null,
                            draft: { interests: {}, skills: {}, subjects: {} }, quizStep: 0 });
let state = loadState() || blankState();

function loadState() { try { return JSON.parse(sessionStorage.getItem(STATE_KEY)); } catch (e) { return null; } }
function saveState() { try { sessionStorage.setItem(STATE_KEY, JSON.stringify(state)); } catch (e) { /* blocked */ } }

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (x) => x == null ? "–" : Math.round(x * 100) + "%";
// "84%" or "84–98%"; one number when both ends round to the same percent.
const pctRange = (lo, hi) => lo == null ? "–" : (hi == null || Math.round(lo * 100) === Math.round(hi * 100)) ? pct(lo) : `${Math.round(lo * 100)}–${pct(hi)}`;
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const loggedIn = () => !!api.token();

function toast(msg) { const t = $("toast"); t.textContent = msg; t.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(() => { t.hidden = true; }, 3500); }
function show(html) { $("view").innerHTML = html; }
function loading(text = "Loading…") { show(`<p class="loading">${esc(text)}</p>`); }
function failed(err) { show(`<div class="card empty"><h2>Something went wrong</h2><p class="soft">${esc(err.message || err)}</p><a class="btn" href="#/">Home</a></div>`); }
function notice(html) { $("notice").innerHTML = html ? `<div>${html}</div>` : ""; $("notice").hidden = !html; }

// Pages that need an account send the student to the login page and come back afterwards.
function needLogin(next) {
  if (loggedIn()) return false;
  sessionStorage.setItem("pathfinder.next", next || location.hash);
  location.hash = "#/login";
  return true;
}
// An expired token (401) while on a page: same idea.
function handle(err) {
  if (err && err.status === 401) { toast("Please log in again."); renderWho(); needLogin(location.hash); return; }
  failed(err);
}

// ---------------------------------------------------------------- router
function route() {
  const parts = (location.hash.replace(/^#\/?/, "") || "home").split("/").map(decodeURIComponent);
  const name = PAGES[parts[0]] ? parts[0] : "home";
  const nav = name === "search" ? "explore" : name;
  document.querySelectorAll(".nav a").forEach(a => a.dataset.nav === nav ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
  document.onkeydown = null;                        // the quiz sets its own keyboard shortcuts
  window.scrollTo(0, 0);
  Promise.resolve(PAGES[name](parts.slice(1))).catch(handle);
}

async function start() {
  window.addEventListener("hashchange", route);
  if (loggedIn() && !state.name) {                  // e.g. page reloaded: fetch the student again
    try { await syncMe(); } catch (e) { api.logout(); }
  }
  renderWho();
  route();
}

async function syncMe() {
  const me = await api.me();
  if (state.email !== me.email) state = blankState();
  Object.assign(state, { name: me.name, email: me.email, assessmentId: me.latest_assessment_id,
                         location: state.location || me.preferred_location || "" });
  saveState();
}

function renderWho() {
  $("who").innerHTML = loggedIn()
    ? `<span>${esc(state.name || state.email)}</span><button class="btn quiet" type="button" id="logoutBtn">Log out</button>`
    : `<a class="btn" href="#/login">Log in</a>`;
  const b = $("logoutBtn");
  if (b) b.onclick = () => { api.logout(); state = blankState(); saveState(); renderWho(); location.hash = "#/"; toast("Logged out."); };
}

// ---------------------------------------------------------------- wording shared by several pages
// O*NET Job Zone -> what it usually means for a student in India (same wording as ml/career_needs.py).
const PREP = {
  1: "Little preparation: can start after school",
  2: "After Class 10/12 with short training",
  3: "Diploma, ITI or a related degree",
  4: "Bachelor's degree",
  5: "Postgraduate or professional degree",
};
const prepLabel = (jz) => PREP[jz] || "Preparation not rated";

function scoreHtml(r) {
  if (r.display === "withheld" || r.match_low == null) return `<div class="score" style="font-size:20px">Not enough answers</div><span class="tiny soft">interest fit ${pct(r.interest_fit)}</span>`;
  const lo = Math.round(r.match_low), hi = Math.round(r.match_high);
  return lo === hi ? `<div class="score num">${lo}<small> / 100</small></div><span class="tiny soft">profile match</span>`
                   : `<div class="score num">${lo}–${hi}<small> / 100</small></div><span class="tiny soft">range: some answers were “Not sure”</span>`;
}

// ---------------------------------------------------------------- outside links (search pages only; no invented course links)
const q = encodeURIComponent;
function jobLinks(title, place) {
  const where = place || "India";
  return [["LinkedIn jobs", `https://www.linkedin.com/jobs/search/?keywords=${q(title)}&location=${q(where)}`],
          ["Indeed jobs", `https://in.indeed.com/jobs?q=${q(title)}&l=${q(place || "")}`],
          ["National Career Service", "https://www.ncs.gov.in/"]];
}
const salaryCheckLink = (title) => `https://www.google.com/search?q=${q(title + " salary in India")}`;
function learnLinks(skill) {
  return [["Videos", `https://www.youtube.com/results?search_query=${q(skill + " for beginners")}`],
          ["SWAYAM (free govt. courses)", "https://swayam.gov.in/"],
          ["NPTEL", "https://nptel.ac.in/"]];
}
const linkList = (links) => links.map(([t, u]) => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(t)}</a>`).join(" · ");

PAGES.home = async () => {
  show(`<section class="hero">
      <div>
        <p class="kicker">Career guidance for every field</p>
        <h1>Not sure what to do after college? Start with what you enjoy.</h1>
        <p class="lead">A short quiz about your interests, skills and subjects. Pathfinder compares your answers with
          ${"<span id=\"careerCount\">900+</span>"} careers – from nursing and farming to film editing and engineering – and shows
          why each one fits, what to learn next and how to get there.</p>
        <div class="row" style="margin-top:22px">
          <a class="btn go" href="#/quiz">Take the quiz (about 4 minutes)</a>
          <a class="btn" href="#/explore">Browse careers</a>
        </div>
      </div>
      <div class="paths">
        <a href="#/quiz"><span class="n">1</span><span><b>Answer 24 quick questions</b><br><span class="soft small">One at a time. “Not sure” is a fine answer.</span></span></a>
        <a href="#/explore"><span class="n">2</span><span><b>Explore by industry</b><br><span class="soft small">Medicine, engineering, beauty, agriculture, film and more.</span></span></a>
        <a href="#/assistant"><span class="n">3</span><span><b>Ask the assistant</b><br><span class="soft small">Talk through your doubts about courses and careers.</span></span></a>
      </div>
    </section>`);
  try {
    const h = await api.health();
    $("careerCount") && ($("careerCount").textContent = h.careers_ranked);
    notice(h.storage === "mysql" ? "" : "<b>Demo mode:</b> MySQL is not connected, so accounts and answers are lost when the server stops.");
  } catch (e) { notice(`<b>Server not reachable.</b> ${esc(e.message)}`); }
};
