/* Pathfinder recommendation engine (browser port of ml/baseline_recommender.py).
   Pure functions only: no DOM access, so it can be tested on its own. */
const RIASEC = ["Realistic", "Investigative", "Artistic", "Social", "Enterprising", "Conventional"];
const WEIGHTS = { skills: 0.30, interests: 0.25, academic: 0.15 };
const SKILL_MAP = {
  "Mathematics": ["Mathematics"],
  "Programming": ["Programming"],
  "Problem Solving": ["Complex Problem Solving"],
  "Logical Reasoning": ["Critical Thinking"],
  "Critical Thinking": ["Critical Thinking"],
  "Research": ["Science", "Active Learning"],
  "Communication": ["Speaking", "Active Listening"],
  "Writing": ["Writing"],
  "Public Speaking": ["Speaking"],
  "Leadership": ["Coordination", "Management of Personnel Resources"],
  "Teamwork": ["Social Perceptiveness", "Coordination"],
  "Time Management": ["Time Management"],
  "Project Management": ["Coordination", "Time Management", "Management of Material Resources"],
  "Financial/Business Skills": ["Management of Financial Resources", "Negotiation", "Persuasion"],
  "Teaching": ["Instructing", "Learning Strategies"],
  "Technical/Practical Skills": ["Installation", "Equipment Maintenance", "Troubleshooting",
    "Repairing", "Operation and Control", "Equipment Selection"]
};
const SUBJECT_MAP = {
  "Mathematics": ["Mathematics"],
  "Physics": ["Physics"],
  "Chemistry": ["Chemistry"],
  "Biology": ["Biology"],
  "Computer Science": ["Computers and Electronics"],
  "Economics": ["Economics and Accounting"],
  "Commerce/Accounting": ["Economics and Accounting", "Administration and Management"],
  "Languages": ["English Language", "Foreign Language"],
  "Social Sciences": ["Sociology and Anthropology", "Psychology", "History and Archeology", "Geography", "Law and Government"],
  "Arts/Design": ["Fine Arts", "Design"]
};

function mean(a) { return a.reduce((x, y) => x + y, 0) / a.length; }
function isNum(v) { return typeof v === "number" && !isNaN(v); }

/* Questionnaire ratings -> values keyed by O*NET element name */
function studentVector(ratings, map) {
  const c = {};
  for (const [item, v] of Object.entries(ratings || {})) {
    for (const e of (map[item] || [])) (c[e] = c[e] || []).push(Number(v));
  }
  const out = {};
  for (const k in c) out[k] = mean(c[k]);
  return out;
}

/* Pearson correlation of profile shapes, rescaled from [-1,1] to [0,1] */
function similarity(stu, names, values) {
  const idx = [];
  for (let i = 0; i < names.length; i++) if (stu[names[i]] !== undefined) idx.push(i);
  if (idx.length < 2) return 0.5;
  const raw = idx.map(i => values[i]);
  const known = raw.filter(isNum);
  if (!known.length) return 0.5;
  const fill = mean(known);
  const t = raw.map(v => (isNum(v) ? v : fill));
  const s = idx.map(i => stu[names[i]]);
  const sm = mean(s), tm = mean(t);
  let num = 0, ds = 0, dt = 0;
  for (let k = 0; k < s.length; k++) {
    const a = s[k] - sm, b = t[k] - tm;
    num += a * b; ds += a * a; dt += b * b;
  }
  const den = Math.sqrt(ds) * Math.sqrt(dt);
  return ((den > 0 ? num / den : 0) + 1) / 2;
}

function interestProfile(student) {
  const p = {};
  for (const t of RIASEC) p[t] = Number(student.interests[t]);
  return p;
}

/* Rank every career. Returns [{career, score, interests, skills, academic}] best first */
function recommend(student, data, opts) {
  const minZone = opts && opts.minJobZone;
  const stuInt = interestProfile(student);
  const stuSkill = studentVector(student.skills, SKILL_MAP);
  const stuKnow = studentVector(student.subjects, SUBJECT_MAP);
  const total = WEIGHTS.skills + WEIGHTS.interests + WEIGHTS.academic;
  const rows = [];
  for (const c of data.careers) {
    if (minZone && isNum(c.job_zone) && c.job_zone < minZone) continue;
    const interests = similarity(stuInt, data.riasec, c.interests);
    const skills = similarity(stuSkill, data.skills, c.skill_im);
    const academic = similarity(stuKnow, data.knowledge, c.know_im);
    const score = (skills * WEIGHTS.skills + interests * WEIGHTS.interests + academic * WEIGHTS.academic) / total * 100;
    rows.push({ career: c, score, interests, skills, academic });
  }
  rows.sort((a, b) => b.score - a.score);
  return rows;
}

function valueOf(data, c, list, key, name) {
  const i = data[list].indexOf(name);
  return i < 0 ? null : c[key][i];
}

/* Reasons (from the student's own answers) and skill gaps for one career */
function explain(student, data, c) {
  const reasons = [];
  const occ = data.riasec.map((n, i) => [n, c.interests[i]]).filter(x => isNum(x[1])).sort((a, b) => b[1] - a[1]).map(x => x[0]);
  const stu = Object.entries(interestProfile(student)).sort((a, b) => b[1] - a[1]);
  for (const [name, v] of stu.slice(0, 2)) {
    if (occ.slice(0, 3).includes(name) && v >= 3.5)
      reasons.push({ kind: "interest", text: `High ${name} interest (${fmt(v)}/5), a top interest type for this career` });
  }
  const imp = n => valueOf(data, c, "skills", "skill_im", n);
  let cands = [];
  for (const [item, r] of Object.entries(student.skills)) {
    const hits = (SKILL_MAP[item] || []).filter(e => (imp(e) || 0) >= 3.5);
    if (r >= 4 && hits.length) cands.push([Math.max(...hits.map(imp)), item, r, hits]);
  }
  cands.sort((a, b) => b[0] - a[0]);
  const used = new Set();
  let nSkill = 0;
  for (const [, item, r, hits0] of cands) {
    const hits = hits0.filter(e => !used.has(e));
    if (hits.length && nSkill < 2) {
      hits.forEach(e => used.add(e)); nSkill++;
      reasons.push({ kind: "skill", text: `Your ${item} (${r}/5) is important here (${hits.join(", ")})` });
    }
  }
  const kimp = n => valueOf(data, c, "knowledge", "know_im", n);
  cands = [];
  for (const [subj, r] of Object.entries(student.subjects)) {
    const hits = (SUBJECT_MAP[subj] || []).filter(e => (kimp(e) || 0) >= 3.5);
    if (r >= 4 && hits.length) cands.push([Math.max(...hits.map(kimp)), subj, r, hits]);
  }
  cands.sort((a, b) => b[0] - a[0]);
  for (const [, subj, r, hits] of cands.slice(0, 2))
    reasons.push({ kind: "subject", text: `${subj} (${r}/5): this career uses ${hits.join(", ")} knowledge` });
  return { reasons, gaps: skillGaps(student, data, c) };
}

/* Required level (O*NET LV, 0-7) vs self-rating mapped 1-5 -> 0-7 (rough, to be calibrated) */
function skillRows(student, data, c) {
  const stu = studentVector(student.skills, SKILL_MAP);
  const rows = [];
  for (const [el, r] of Object.entries(stu)) {
    const im = valueOf(data, c, "skills", "skill_im", el);
    const lv = valueOf(data, c, "skills", "skill_lv", el);
    if (!isNum(im) || !isNum(lv)) continue;
    const your = (r - 1) / 4 * 7;
    rows.push({ skill: el, importance: im, required: lv, your, gap: lv - your });
  }
  return rows.sort((a, b) => b.importance - a.importance);
}

function skillGaps(student, data, c) {
  return skillRows(student, data, c)
    .filter(r => r.importance >= 3 && r.gap > 0.5)
    .map(r => Object.assign({}, r, { priority: r.importance * r.gap }))
    .sort((a, b) => b.priority - a.priority);
}

function fmt(v) { return (Math.round(v * 10) / 10).toString(); }

if (typeof module !== "undefined") module.exports = { RIASEC, SKILL_MAP, SUBJECT_MAP, recommend, explain, skillGaps, skillRows, similarity, studentVector };
