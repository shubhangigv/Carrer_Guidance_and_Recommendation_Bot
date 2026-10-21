// The quiz (#/quiz): one question per screen, click or press a number key, it moves on by itself.
// Order: areas you like + your course -> 6 interests -> 8 skills + your 3 strongest / 2 weakest ->
// 8 subjects -> work style + further study -> where you want to work -> "about you" (with idea chips).
// The 22 rated rows are the same as the Google Form and the engine; the other steps are optional.
// Answers are kept in the tab until you submit.

// The first value of each row is the engine's name (SKILL_MAP_V2 / SUBJECT_MAP_V2 in ml/recommender_v2.py)
// and must not change; the second is what students see; the third is an example.
const INTEREST_ROWS = [
  ["Realistic", "working with machines, tools or building things", "repairing things, farming, construction, operating machines"],
  ["Investigative", "solving problems, research and analysing data", "experiments, investigating, analysing numbers, science projects"],
  ["Artistic", "designing, writing or creating things", "drawing, music, acting, writing stories, fashion, film"],
  ["Social", "helping, teaching or caring for people", "teaching, nursing, counselling, volunteering"],
  ["Enterprising", "leading, persuading or starting a business", "selling, running an event, leading a team, starting a shop"],
  ["Conventional", "organising data and records, following clear procedures", "accounts, office work, keeping records, checking details"],
];
const SKILL_ROWS = [
  ["Mathematics", "working with numbers", "calculating, estimating, handling money, using maths in daily life"],
  ["Programming", "programming / coding", "writing code in Python, C or Java, building a website or an app"],
  ["Problem Solving", "solving tricky problems", "finding out why something is not working, puzzles, finding a better way"],
  ["Research", "researching and finding things out", "looking up information, doing experiments, checking facts"],
  ["Communication", "talking and listening to people", "explaining ideas, presentations, understanding what others need"],
  ["Writing", "writing clearly", "reports, essays, emails, posts"],
  ["Leadership", "leading and persuading people", "organising a team or an event, convincing others, settling arguments"],
  ["Technical/Practical Skills", "hands-on technical work", "fixing gadgets or vehicles, using machines and tools, setting up equipment"],
];
const SUBJECT_ROWS = [
  ["Mathematics", "Mathematics (as a subject)", "the maths you studied in school or college"],
  ["Physics/Chemistry", "Physics / Chemistry", ""],
  ["Biology", "Biology", ""],
  ["Computer Science", "Computer Science", ""],
  ["Commerce/Economics", "Commerce / Economics", "accounts, business studies, economics"],
  ["Languages", "Languages", "English, Hindi or any other language"],
  ["Social Sciences", "Social sciences", "history, geography, psychology, sociology"],
  ["Arts/Design", "Art / Design", "drawing, painting, design"],
];

const INTEREST_SCALE = ["Not at all", "Not much", "It's okay", "Quite a lot", "I'd love it"];
const SKILL_SCALE = ["Very weak", "Weak", "I can do it with help", "Good", "I can do it well on my own"];
const SUBJECT_SCALE = ["Very weak", "Weak", "Average", "Good", "Very good"];
const PLACES = ["Anywhere in India", "Near my home town", "Mumbai", "Delhi NCR", "Bengaluru", "Hyderabad", "Chennai", "Pune", "Kolkata", "Abroad"];
// "About you" idea chips: a click adds the phrase to the text, so the text matcher gets real words to work with.
const IDEAS = ["coding and building apps", "playing and making games", "helping people", "drawing and design", "sports and fitness",
  "cooking", "travelling", "teaching others", "animals and nature", "machines and engines", "business and money",
  "writing and stories", "music", "science experiments", "working with numbers", "law and justice", "making videos"];

let QUIZ_OPTS = null;                    // areas, courses, lifestyle choices (GET /quiz/options, loaded once)

const QUESTIONS = [
  { cat: "profile", key: "areas", multi: "areas", title: "Which areas would you like to work in?",
    ex: "Pick up to 3. Not sure? Skip it - we will use your course and answers instead." },
  { cat: "profile", key: "course", dynamic: "courses", title: "What are you studying now?",
    ex: "We use this to show careers your course leads to. You can still get careers from other fields." },
  ...INTEREST_ROWS.map(([key, text, ex]) => ({ cat: "interests", key, title: `How much would you enjoy ${text}?`, ex,
    options: INTEREST_SCALE.map((l, i) => [i + 1, l]) })),
  ...SKILL_ROWS.map(([key, text, ex]) => ({ cat: "skills", key, title: `How good are you at ${text}?`, ex,
    options: SKILL_SCALE.map((l, i) => [i + 1, l]).concat([["no_experience", "I have never tried it"], ["cant_assess", "Not sure"]]) })),
  { cat: "profile", key: "strengths", multi: "skills", title: "Which are your 3 strongest skills?",
    ex: "Compared with your other skills - even if you rated several of them the same." },
  { cat: "profile", key: "weaknesses", multi: "skills", title: "And your 2 weakest skills?",
    ex: "Be honest: it helps us avoid careers that depend on them." },
  ...SUBJECT_ROWS.map(([key, text, ex]) => ({ cat: "subjects", key, title: `How good are you at ${text}?`, ex,
    options: SUBJECT_SCALE.map((l, i) => [i + 1, l]).concat([["not_studied", "I have not studied it"]]) })),
  { cat: "profile", key: "work_setting", dynamic: "work_settings", title: "What kind of workday would you like?",
    ex: "We leave out careers that clearly do not fit (from O*NET work-context data)." },
  { cat: "profile", key: "further_study", dynamic: "further_study", title: "Would you study more after your current degree?",
    ex: "If not, we leave out careers that usually need a master's, PhD or medical degree." },
  { cat: "location", title: "Where would you like to work?", ex: "We use this to show job openings near you. You can change it later." },
  { cat: "about", title: "Anything else about what you enjoy? (optional)", ex: "Tap the ideas that fit you, or write in your own words." },
];
const SECTION = { profile: "Your direction", interests: "What you enjoy", skills: "Your skills", subjects: "Your subjects",
                  location: "Your preferences", about: "Your preferences" };
const MAX_PICKS = { areas: () => QUIZ_OPTS.max_areas, strengths: () => QUIZ_OPTS.max_strengths, weaknesses: () => QUIZ_OPTS.max_weaknesses };

// The choices of one question: [value, label, example?]
function optionsOf(qn) {
  if (qn.options) return qn.options;
  if (qn.dynamic) return QUIZ_OPTS[qn.dynamic].map(o => [o.key, o.label]);
  if (qn.multi === "areas") return QUIZ_OPTS.areas.map(o => [o.key, o.label, o.example]);
  if (qn.multi === "skills") return SKILL_ROWS.map(([key, text]) => [key, text[0].toUpperCase() + text.slice(1)])
    .filter(([key]) => qn.key !== "weaknesses" || !state.draft.profile.strengths.includes(key));
  return null;
}

PAGES.quiz = async () => {
  if (needLogin("#/quiz")) return;
  if (!QUIZ_OPTS) {
    loading("Loading the quiz…");
    try { QUIZ_OPTS = await api.quizOptions(); } catch (err) { return handle(err); }
  }
  const i = Math.min(state.quizStep || 0, QUESTIONS.length);
  if (i === QUESTIONS.length) return renderReview();
  const qn = QUESTIONS[i];
  const opts = optionsOf(qn);
  const bar = `<div class="quiz-bar"><span>${esc(SECTION[qn.cat])}</span><div class="meter"><i style="width:${Math.round(i / QUESTIONS.length * 100)}%"></i></div>
    <span class="num">${i + 1} / ${QUESTIONS.length}</span></div>`;
  let body;
  if (qn.multi) {
    const picked = state.draft.profile[qn.key];
    body = `<div class="choices ${qn.multi === "areas" ? "grid" : ""}" role="group" aria-label="${esc(qn.title)}">${opts.map(([v, label, ex]) =>
      `<button type="button" class="choice pick" data-v="${esc(v)}" aria-pressed="${picked.includes(v)}">
        <span><b>${esc(label)}</b>${ex ? `<span class="tiny faint" style="display:block">${esc(ex)}</span>` : ""}</span></button>`).join("")}</div>
      <p class="tiny faint" id="pickCount">${picked.length} of ${MAX_PICKS[qn.key]()} picked</p>`;
  } else if (opts) {
    const current = state.draft[qn.cat][qn.key];
    body = `<div class="choices" role="group" aria-label="${esc(qn.title)}">${opts.map(([v, label], k) =>
      `<button type="button" class="choice ${typeof v === "string" && qn.cat !== "profile" ? "other" : ""}" data-v="${esc(v)}" aria-pressed="${current === v}">
        <span class="key">${k < 9 ? k + 1 : ""}</span><span>${esc(label)}</span></button>`).join("")}</div>`;
  } else if (qn.cat === "location") {
    body = `<div class="field"><label for="loc">City, state or “Anywhere in India”</label>
      <input id="loc" class="input" maxlength="100" list="places" value="${esc(state.location)}" placeholder="e.g. Pune">
      <datalist id="places">${PLACES.map(p => `<option value="${esc(p)}">`).join("")}</datalist></div>
      <div class="chips">${PLACES.slice(0, 6).map(p => `<button type="button" data-place="${esc(p)}">${esc(p)}</button>`).join("")}</div>`;
  } else {
    body = `<div class="chips">${IDEAS.map(t => `<button type="button" data-idea="${esc(t)}">+ ${esc(t)}</button>`).join("")}</div>
      <textarea id="about" class="input" maxlength="1000" placeholder="e.g. I enjoy coding and building apps, and I like explaining things to friends…">${esc(state.aboutMe)}</textarea>`;
  }
  const single = opts && !qn.multi;
  show(`<div class="quiz">${bar}
      <div><h1>${esc(qn.title)}</h1>${qn.ex ? `<p class="example" style="margin-top:12px">${qn.options ? "For example: " : ""}${esc(qn.ex)}</p>` : ""}</div>
      ${body}
      <div class="spread"><button class="btn" type="button" id="back" ${i === 0 ? "disabled" : ""}>Back</button>
        ${single ? `<span class="tiny faint">Tip: press 1–${Math.min(opts.length, 9)} on your keyboard</span>` : ""}
        <button class="btn ${single ? "" : "go"}" type="button" id="next">${single ? "Skip for now" : "Continue"}</button></div>
    </div>`);

  const go = (step) => { state.quizStep = step; saveState(); route(); };
  $("back").onclick = () => go(i - 1);
  if (qn.multi) {
    document.onkeydown = null;
    const picked = state.draft.profile[qn.key];
    const most = MAX_PICKS[qn.key]();
    document.querySelectorAll(".choice.pick").forEach(b => b.onclick = () => {
      const v = b.dataset.v, at = picked.indexOf(v);
      if (at >= 0) picked.splice(at, 1);
      else if (picked.length < most) picked.push(v);
      else return toast(`You can pick up to ${most}. Unpick one first.`);
      if (qn.key === "weaknesses" && picked.includes(v) && Number(state.draft.skills[v]) >= 3)
        toast(`You rated ${v} as ${SKILL_SCALE[state.draft.skills[v] - 1].toLowerCase()} earlier - we will count it as weak.`);
      if (qn.key === "strengths") {                    // a strength cannot also be a weakness
        const w = state.draft.profile.weaknesses;
        state.draft.profile.weaknesses = w.filter(x => !picked.includes(x));
      }
      saveState();
      b.setAttribute("aria-pressed", picked.includes(v));
      $("pickCount").textContent = `${picked.length} of ${most} picked`;
    });
    $("next").onclick = () => go(i + 1);
  } else if (opts) {
    const pick = (v) => {
      state.draft[qn.cat][qn.key] = v; saveState();
      document.querySelectorAll(".choice").forEach(b => b.setAttribute("aria-pressed", b.dataset.v === String(v)));
      setTimeout(() => go(i + 1), 220);
    };
    document.querySelectorAll(".choice").forEach(b => b.onclick = () => pick(/^\d$/.test(b.dataset.v) ? Number(b.dataset.v) : b.dataset.v));
    $("next").onclick = () => go(i + 1);
    document.onkeydown = (e) => {
      if (location.hash !== "#/quiz" || e.altKey || e.ctrlKey || e.metaKey || e.target.tagName === "INPUT") return;
      const k = Number(e.key);
      if (k >= 1 && k <= Math.min(opts.length, 9)) pick(opts[k - 1][0]);
    };
  } else {
    document.onkeydown = null;
    const input = $("loc") || $("about");
    input.focus();
    document.querySelectorAll("[data-place]").forEach(b => b.onclick = () => { input.value = b.dataset.place; });
    document.querySelectorAll("[data-idea]").forEach(b => b.onclick = () => {
      const t = input.value.trim();
      if (t.toLowerCase().includes(b.dataset.idea)) return;
      input.value = t ? `${t.replace(/[.\s]+$/, "")}, ${b.dataset.idea}` : `I enjoy ${b.dataset.idea}`;
      b.disabled = true;
    });
    $("next").onclick = () => {
      if (qn.cat === "location") state.location = input.value.trim(); else state.aboutMe = input.value.trim();
      go(i + 1);
    };
  }
};

// Only the 22 rated rows are required; the "Your direction" steps are optional.
function missingQuestions() {
  return QUESTIONS.map((qn, i) => [qn, i]).filter(([qn]) => qn.options && state.draft[qn.cat][qn.key] == null);
}

function profileLabel(qn) {
  const v = state.draft.profile[qn.key];
  if (Array.isArray(v)) {
    if (!v.length) return "none picked";
    const names = Object.fromEntries(optionsOf({ ...qn, key: "strengths" }).map(([k, l]) => [k, l]));
    return v.map(k => names[k] || k).join(", ");
  }
  const o = optionsOf(qn).find(([x]) => x === v);
  return o ? o[1] : "not answered";
}

function renderReview() {
  document.onkeydown = null;
  const missing = missingQuestions();
  const label = (qn) => { const v = state.draft[qn.cat][qn.key]; const o = qn.options.find(([x]) => x === v); return o ? o[1] : "not answered"; };
  const steps = (cat) => QUESTIONS.map((qn, i) => [qn, i]).filter(([qn]) => qn.cat === cat);
  const group = (cat, title) => `<div class="card"><h3>${title}</h3><ul class="list" style="margin-top:6px">${steps(cat).map(([qn, i]) =>
    `<li class="spread"><span>${esc(qn.title.replace(/^How (much would you enjoy|good are you at) /, "").replace(/\?$/, ""))}</span>
     <button class="btn quiet" type="button" data-step="${i}">${esc(label(qn))}</button></li>`).join("")}</ul></div>`;
  const direction = `<div class="card"><h3>Your direction</h3><ul class="list" style="margin-top:6px">${steps("profile").map(([qn, i]) =>
    `<li class="spread"><span>${esc(qn.title.replace(/\?$/, ""))}</span>
     <button class="btn quiet" type="button" data-step="${i}">${esc(profileLabel(qn))}</button></li>`).join("")}</ul></div>`;
  show(`<div class="quiz" style="max-width:760px">
    <div><p class="kicker">Last step</p><h1>Check your answers</h1><p class="soft" style="margin-top:8px">Click any answer to change it.</p></div>
    ${missing.length ? `<p class="alert">${missing.length} question${missing.length > 1 ? "s are" : " is"} not answered yet. “Not sure” is a fine answer.
      <button class="btn quiet" type="button" data-step="${missing[0][1]}">Answer now</button></p>` : ""}
    ${direction}${group("interests", "What you enjoy")}${group("skills", "Your skills")}${group("subjects", "Your subjects")}
    <div class="card"><h3>Your preferences</h3><ul class="list" style="margin-top:6px">
      <li class="spread"><span>Where you want to work</span><button class="btn quiet" type="button" data-step="${QUESTIONS.length - 2}">${esc(state.location || "not given")}</button></li>
      <li class="spread"><span>About you</span><button class="btn quiet" type="button" data-step="${QUESTIONS.length - 1}">${esc(state.aboutMe ? state.aboutMe.slice(0, 40) + (state.aboutMe.length > 40 ? "…" : "") : "not given")}</button></li></ul></div>
    <p class="alert" id="submitError" hidden></p>
    <div class="spread"><button class="btn" type="button" data-step="${QUESTIONS.length - 1}">Back</button>
      <button class="btn go" type="button" id="submit" ${missing.length ? "disabled" : ""}>See my matches</button></div>
  </div>`);
  document.querySelectorAll("[data-step]").forEach(b => b.onclick = () => { state.quizStep = Number(b.dataset.step); saveState(); route(); });
  $("submit").onclick = submitQuiz;
}

async function submitQuiz() {
  const btn = $("submit");
  btn.disabled = true; btn.textContent = "Finding your matches…";
  const wrap = (obj) => Object.fromEntries(Object.entries(obj).map(([k, v]) => [k, typeof v === "number" ? { rating: v } : v]));
  const p = state.draft.profile;
  try {
    const saved = await api.saveAssessment({ interests: { ...state.draft.interests }, skills: wrap(state.draft.skills),
      subjects: wrap(state.draft.subjects), preferred_location: state.location || null, about_me: state.aboutMe || null,
      profile: { areas: p.areas, course: p.course, strengths: p.strengths, weaknesses: p.weaknesses,
                 work_setting: p.work_setting || "any", further_study: p.further_study || "any" } });
    state.assessmentId = saved.assessment_id;
    await loadRecs();
    state.quizStep = 0; saveState();
    location.hash = "#/matches";
  } catch (err) {
    if (err.status === 401) return handle(err);
    $("submitError").textContent = err.message; $("submitError").hidden = false;
    btn.disabled = false; btn.textContent = "See my matches";
  }
}
