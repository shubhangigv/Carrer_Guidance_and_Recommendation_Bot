// Every call to the Pathfinder API lives in this one file.
// The page is served by the API itself (http://127.0.0.1:8000/app/), so requests go to the same
// address and no CORS setup is needed. To use another server, set API_BASE, e.g. "http://127.0.0.1:8000".
const API_BASE = "";
const TOKEN_KEY = "pathfinder.token";

const api = {
  token() { try { return sessionStorage.getItem(TOKEN_KEY); } catch (e) { return null; } },
  setToken(t) { try { t ? sessionStorage.setItem(TOKEN_KEY, t) : sessionStorage.removeItem(TOKEN_KEY); } catch (e) { /* storage blocked */ } },

  // One request. Throws an Error whose message is ready to show to the student.
  async call(method, path, body) {
    const headers = { "Accept": "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const token = api.token();
    if (token) headers["Authorization"] = "Bearer " + token;
    let res;
    try {
      res = await fetch(API_BASE + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
    } catch (e) {
      throw new Error("Cannot reach the server. Is uvicorn running?");
    }
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      if (res.status === 401 && path !== "/auth/login") api.setToken(null);
      throw Object.assign(new Error(api.errorText(res.status, data)), { status: res.status });
    }
    return data;
  },

  // FastAPI errors: {"detail": "text"} or {"detail": [{"loc": [...], "msg": "..."}]} for bad input (422).
  errorText(status, data) {
    const d = data && data.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d.length) return d.map(e => `${(e.loc || []).filter(x => x !== "body").join(" › ")}: ${e.msg}`).join("; ");
    return `Server error (${status})`;
  },

  // account
  health: () => api.call("GET", "/health"),
  register: (student) => api.call("POST", "/auth/register", student),
  async login(email, password) {
    const r = await api.call("POST", "/auth/login", { email, password });
    api.setToken(r.access_token);
    return r;
  },
  logout() { api.setToken(null); },
  me: () => api.call("GET", "/me"),

  // quiz and matches
  quizOptions: () => api.call("GET", "/quiz/options"),
  hidden: () => api.call("GET", "/feedback/hidden"),
  hideCareer: (id) => api.call("PUT", `/feedback/hidden/${id}`),
  unhideCareer: (id) => api.call("DELETE", `/feedback/hidden/${id}`),
  saveAssessment: (answers) => api.call("POST", "/assessment", answers),
  recommend: (assessmentId, topN = 10) => api.call("GET", `/recommend?assessment_id=${assessmentId}&top_n=${topN}`),
  matchText: (text, topN = 6) => api.call("POST", "/match/text", { text, top_n: topN }),

  // careers
  searchCareers: (q) => api.call("GET", `/careers/search?q=${encodeURIComponent(q)}&limit=30`),
  career: (id) => api.call("GET", `/careers/${id}`),
  requirements: (id) => api.call("GET", `/careers/${id}/requirements`),
  pathway: (id) => api.call("GET", `/careers/${id}/pathway`),
  target: (id, assessmentId) => api.call("POST", `/target/${id}`, { assessment_id: assessmentId }),
  industries: () => api.call("GET", "/industries"),
  industry: (id) => api.call("GET", `/industries/${encodeURIComponent(id)}`),

  // roadmap
  roadmap: (id) => api.call("GET", `/roadmap/${id}`),
  setStep: (id, stepKey, done) => api.call("PUT", `/roadmap/${id}/progress`, { step_key: stepKey, done }),
  roadmaps: () => api.call("GET", "/roadmaps"),

  // assistant
  assistantStatus: () => api.call("GET", "/assistant/status"),
  chat: (message, history, careerId) => api.call("POST", "/assistant/chat", { message, history, career_id: careerId || null }),
};
