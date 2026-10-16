// Sign up / log in (#/login). After logging in the student returns to the page they wanted.

PAGES.login = (params) => {
  const signup = params[0] !== "existing";
  show(`<div class="cols">
    <div class="wide card" style="max-width:560px">
      <div class="tabs" role="tablist">
        <button type="button" role="tab" aria-selected="${signup}" id="tabNew">New here</button>
        <button type="button" role="tab" aria-selected="${!signup}" id="tabOld">I have an account</button>
      </div>
      <form id="signupForm" class="page" style="gap:14px;margin-top:16px" novalidate ${signup ? "" : "hidden"}>
        <div class="field"><label for="suName">Your name</label><input id="suName" autocomplete="name" maxlength="100"></div>
        <div class="field"><label for="suEmail">Email</label><input id="suEmail" type="email" autocomplete="email"></div>
        <div class="field"><label for="suPass">Password (at least 8 characters)</label><input id="suPass" type="password" autocomplete="new-password"></div>
        <div class="row" style="gap:12px;align-items:flex-start">
          <div class="field" style="flex:1 1 180px"><label for="suDegree">Course (optional)</label><input id="suDegree" maxlength="100" placeholder="e.g. B.Sc, B.Tech, BA"></div>
          <div class="field" style="flex:1 1 140px"><label for="suYear">Year (optional)</label>
            <select id="suYear"><option value="">–</option><option>1</option><option>2</option><option>3</option><option>4</option><option>5</option></select></div>
        </div>
        <p class="alert" id="suError" hidden></p>
        <button class="btn go" type="submit">Create account</button>
      </form>
      <form id="loginForm" class="page" style="gap:14px;margin-top:16px" novalidate ${signup ? "hidden" : ""}>
        <div class="field"><label for="liEmail">Email</label><input id="liEmail" type="email" autocomplete="email"></div>
        <div class="field"><label for="liPass">Password</label><input id="liPass" type="password" autocomplete="current-password"></div>
        <p class="alert" id="liError" hidden></p>
        <button class="btn go" type="submit">Log in</button>
      </form>
    </div>
    <div class="narrow card flat"><h3>Why an account?</h3>
      <p class="soft small" style="margin-top:8px">So your answers, matches and roadmap progress are saved and you can come back to them.
      Your password is stored only as a bcrypt hash. Your answers are used only to compute your matches.</p></div>
  </div>`);
  $("tabNew").onclick = () => { location.hash = "#/login"; };
  $("tabOld").onclick = () => { location.hash = "#/login/existing"; };
  const err = (id, e) => { $(id).textContent = e ? e.message : ""; $(id).hidden = !e; };
  let busy = false;

  $("signupForm").onsubmit = async (e) => {
    e.preventDefault();
    if (busy) return;
    const body = { name: $("suName").value.trim(), email: $("suEmail").value.trim(), password: $("suPass").value,
                   degree: $("suDegree").value.trim() || null, year_of_study: $("suYear").value ? Number($("suYear").value) : null };
    if (!body.name || !body.email || body.password.length < 8) return err("suError", new Error("Please fill in your name, email and a password of at least 8 characters."));
    busy = true; err("suError", null);
    try {
      await api.register(body);
      await api.login(body.email, body.password);
      await afterLogin();
    } catch (x) { err("suError", x.status === 409 ? new Error("This email already has an account – use “I have an account”.") : x); }
    finally { busy = false; }
  };
  $("loginForm").onsubmit = async (e) => {
    e.preventDefault();
    if (busy) return;
    busy = true; err("liError", null);
    try { await api.login($("liEmail").value.trim(), $("liPass").value); await afterLogin(); }
    catch (x) { err("liError", x); } finally { busy = false; }
  };
};

async function afterLogin() {
  await syncMe();
  renderWho();
  const next = sessionStorage.getItem("pathfinder.next");
  sessionStorage.removeItem("pathfinder.next");
  location.hash = next && next !== "#/login" ? next : (state.assessmentId ? "#/matches" : "#/quiz");
}
