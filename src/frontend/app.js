const API_BASE = "https://twodots-rag.onrender.com";

const siteForm = document.getElementById("site-form");
const siteInput = document.getElementById("site-input");
const siteStatus = document.getElementById("site-status");

const form = document.getElementById("chat-form");
const input = document.getElementById("message-input");
const chat = document.getElementById("chat");

let siteId = null;
let siteReady = false;


function addMessage(text, role, citations = []) {
  const wrapper = document.createElement("div");
  wrapper.className = `message ${role}`;

  const body = document.createElement("div");
  body.className = "message-body";
  body.textContent = typeof text === "string" ? text : JSON.stringify(text, null, 2);
  wrapper.appendChild(body);

  if (citations.length > 0) {
    const cites = document.createElement("div");
    cites.className = "citations";

    const title = document.createElement("div");
    title.className = "citations-title";
    title.textContent = "Sources";
    cites.appendChild(title);

    citations.forEach((url) => {
      const a = document.createElement("a");
      a.href = url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.textContent = url;
      cites.appendChild(a);
    });

    wrapper.appendChild(cites);
  }

  chat.appendChild(wrapper);
  chat.scrollTop = chat.scrollHeight;
}

function setChatEnabled(enabled) {
  input.disabled = !enabled;
  form.querySelector("button").disabled = !enabled;
}

async function createIndex(url) {
  const res = await fetch(`${API_BASE}/api/site`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}

async function getIndexStatus(id) {
  const res = await fetch(`${API_BASE}/api/site/${id}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}

async function indexSiteFlow(url) {
  siteReady = false;
  setChatEnabled(false);
  siteStatus.textContent = "Starting…";

  const created = await createIndex(url);
  siteId = created.site_id;

  addMessage(`Indexing ${url}\n\nThis can take a bit for larger sites.`, "assistant");

  for (;;) {
    const st = await getIndexStatus(siteId);
    if (st.status === "queued" || st.status === "running") {
      siteStatus.textContent = st.status === "queued" ? "Queued…" : "Indexing…";
      await new Promise((r) => setTimeout(r, 1200));
      continue;
    }

    if (st.status === "done") {
      siteReady = true;
      siteStatus.textContent = "Ready";
      addMessage(st.message || "Index ready.", "assistant");
      setChatEnabled(true);
      input.focus();
      return;
    }

    siteStatus.textContent = "Error";
    addMessage(st.message || "Indexing failed.", "assistant");
    return;
  }
}

async function sendMessage(message) {
  console.log("sending message:", message, typeof message);

  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ message: message, site_id: siteId }),
  });

  if (!res.ok) {
    const text = await res.text();
    console.error("backend response:", text);
    throw new Error(`HTTP ${res.status}`);
  }

  return res.json();
}

siteForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const url = siteInput.value.trim();
  if (!url) return;

  siteInput.disabled = true;
  siteForm.querySelector("button").disabled = true;

  try {
    await indexSiteFlow(url);
  } catch (err) {
    console.error(err);
    siteStatus.textContent = "Error";
    addMessage("Could not start indexing. Check the URL and try again.", "assistant");
  } finally {
    siteInput.disabled = false;
    siteForm.querySelector("button").disabled = false;
  }
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();

  const message = input.value.trim();
  if (!message) return;
  if (!siteReady) {
    addMessage("Index a website first.", "assistant");
    return;
  }

  addMessage(message, "user");
  input.value = "";
  input.disabled = true;

  const loadingEl = document.createElement("div");
  loadingEl.className = "message assistant";
  loadingEl.textContent = "Thinking...";
  chat.appendChild(loadingEl);
  chat.scrollTop = chat.scrollHeight;

  try {
    const data = await sendMessage(message);
    loadingEl.remove();
    console.log("frontend received:", data);
    console.log("answer field =", data.answer, typeof data.answer);
    addMessage(data.response, "assistant", data.citations || []);
  } catch (err) {
    loadingEl.remove();
    addMessage("Something went wrong talking to the API.", "assistant");
    console.error(err);
  } finally {
    input.disabled = false;
    input.focus();
  }
});

setChatEnabled(false);
