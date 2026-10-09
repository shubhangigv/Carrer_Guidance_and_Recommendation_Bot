const messages = document.getElementById("messages");
const form = document.getElementById("form");
const input = document.getElementById("input");
const chips = document.getElementById("chips");

const FOLLOW_UPS = ["roadmap for #1", "salary of #1", "about #2", "categories", "help"];

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function addMessage(text, who) {
  const div = document.createElement("div");
  div.className = `msg ${who}`;
  // Escape first, then render **bold** markdown from the bot.
  div.innerHTML = escapeHtml(text).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
}

function renderChips(done) {
  chips.innerHTML = "";
  if (!done) return;
  for (const label of FOLLOW_UPS) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip";
    b.textContent = label;
    b.onclick = () => send(label);
    chips.appendChild(b);
  }
}

async function post(body) {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}

async function send(text) {
  addMessage(text, "user");
  try {
    const data = await post({ message: text });
    addMessage(data.reply, "bot");
    renderChips(data.done);
  } catch {
    addMessage("Sorry, something went wrong. Please try again.", "bot");
  }
}

async function start() {
  messages.innerHTML = "";
  const data = await post({ start: true });
  addMessage(data.reply, "bot");
  renderChips(false);
  input.focus();
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  send(text);
});

document.getElementById("restart").addEventListener("click", start);
start();
