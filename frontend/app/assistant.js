// The career assistant (#/assistant, or #/assistant/12 to ask about one career).
// The server finds the careers your question is about and asks Gemini to answer ONLY from those
// records (backend/assistant.py). Without a Gemini key it lists matching careers instead.

const SUGGESTIONS = [
  "I like biology but don't want to be a doctor. What else can I do?",
  "What should I learn first to become a data analyst?",
  "My parents want engineering but I love design. How do I talk to them?",
  "Which careers are there in agriculture?",
];

PAGES.assistant = async (params) => {
  const careerId = Number(params[0]) || null;
  state.chat = state.chat || [];
  show(`<div class="spread"><div><p class="kicker">Ask</p><h1>Career assistant</h1>
      <p class="soft small" style="margin-top:6px" id="modeNote">Answers come from Pathfinder's career data. Always double-check exam and college details on official websites.</p></div>
      <button class="btn quiet" type="button" id="clearChat">Clear chat</button></div>
    <div class="chat"><div class="msgs" id="msgs"></div>
      <div class="composer"><div class="chips" id="sugg"></div>
        <form id="chatForm"><input id="chatBox" class="input" maxlength="1000" autocomplete="off" aria-label="Your question"
          placeholder="${careerId ? "Ask about this career…" : "Ask anything about careers, courses or skills…"}">
          <button class="btn go" type="submit">Send</button></form></div></div>`);
  try {
    const s = await api.assistantStatus();
    if (s.mode === "offline") $("modeNote").innerHTML = "<b>Offline mode:</b> no Gemini key is set on the server (GEMINI_API_KEY in .env), so the assistant can only list matching careers.";
  } catch (e) { /* status is only informative */ }

  const draw = () => {
    $("msgs").innerHTML = state.chat.length ? state.chat.map(m => `<div class="msg ${m.role === "user" ? "user" : "bot"}">${esc(m.text)}
      ${m.sources && m.sources.length ? `<div class="src">${m.sources.map(c => `<a class="tag green" href="#/career/${c.career_id}">${esc(c.display_title)}</a>`).join("")}</div>` : ""}</div>`).join("")
      : `<div class="msg bot">Hi${state.name ? " " + esc(state.name.split(" ")[0]) : ""}! Tell me what you enjoy or what you are confused about, and I will help you think it through.${careerId ? " You can ask about the career you were looking at." : ""}</div>`;
    $("sugg").innerHTML = state.chat.length ? "" : SUGGESTIONS.map(s => `<button type="button">${esc(s)}</button>`).join("");
    $("sugg").querySelectorAll("button").forEach(b => b.onclick = () => send(b.textContent));
    window.scrollTo(0, document.body.scrollHeight);
  };
  let busy = false;
  async function send(text) {
    text = text.trim();
    if (!text || busy) return;
    busy = true;
    const history = state.chat.map(m => ({ role: m.role, text: m.text }));
    state.chat.push({ role: "user", text }); draw();
    $("chatBox").value = "";
    $("msgs").insertAdjacentHTML("beforeend", `<div class="msg bot faint" id="typing">Thinking…</div>`);
    try {
      const r = await api.chat(text, history.slice(-10), careerId);
      state.chat.push({ role: "assistant", text: r.reply, sources: r.sources });
    } catch (err) {
      state.chat.push({ role: "assistant", text: "Sorry, I could not answer: " + err.message });
    }
    saveState(); busy = false; draw(); $("chatBox").focus();
  }
  $("chatForm").onsubmit = (e) => { e.preventDefault(); send($("chatBox").value); };
  $("clearChat").onclick = () => { state.chat = []; saveState(); draw(); };
  draw();
  $("chatBox").focus();
};
