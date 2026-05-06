const API_BASE = "https://general-rag-model-backend.onrender.com";

const indexScreen = document.getElementById("index-screen");
const chatScreen = document.getElementById("chat-screen");

const siteForm = document.getElementById("site-form");
const siteInput = document.getElementById("site-input");
const siteStatus = document.getElementById("site-status");

const reindexOpen = document.getElementById("reindex-open");
const reindexModal = document.getElementById("reindex-modal");
const reindexClose = document.getElementById("reindex-close");
const reindexForm = document.getElementById("reindex-form");
const reindexInput = document.getElementById("reindex-input");
const reindexStatus = document.getElementById("reindex-status");

const sitePillText = document.getElementById("site-pill-text");

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

function setActiveScreen(screen) {
  if (screen === "chat") {
    indexScreen.classList.remove("screen-active");
    indexScreen.classList.add("screen-hidden");
    chatScreen.classList.add("screen-active");
    chatScreen.classList.remove("screen-hidden");
    return;
  }

  chatScreen.classList.remove("screen-active");
  chatScreen.classList.add("screen-hidden");
  indexScreen.classList.add("screen-active");
  indexScreen.classList.remove("screen-hidden");
}

function openReindexModal() {
  reindexModal.classList.remove("hidden");
  reindexInput.focus();
}

function closeReindexModal() {
  reindexModal.classList.add("hidden");
  reindexStatus.textContent = "";
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

function setIndexStatus(text) {
  siteStatus.textContent = text;
  reindexStatus.textContent = text;
}

async function indexSiteFlow(url) {
  siteReady = false;
  setChatEnabled(false);
  setIndexStatus("Starting...");

  const created = await createIndex(url);
  siteId = created.site_id;

  sitePillText.textContent = url;
  addMessage(`Indexing ${url}\n\nThis can take a bit for larger sites.`, "assistant");

  for (;;) {
    const st = await getIndexStatus(siteId);
    if (st.status === "queued" || st.status === "running") {
      setIndexStatus(st.status === "queued" ? "Queued..." : "Indexing...");
      await new Promise((r) => setTimeout(r, 1200));
      continue;
    }

    if (st.status === "done") {
      siteReady = true;
      setIndexStatus("Ready");
      addMessage(st.message || "Index ready.", "assistant");
      setChatEnabled(true);
      setActiveScreen("chat");
      closeReindexModal();
      input.focus();
      return;
    }

    setIndexStatus("Error");
    addMessage(st.message || "Indexing failed.", "assistant");
    return;
  }
}

async function sendMessage(message) {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: message, site_id: siteId }),
  });

  if (!res.ok) {
    const text = await res.text();
    console.error("backend response:", text);
    throw new Error(text || `HTTP ${res.status}`);
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
    setIndexStatus("Error");
    addMessage("Could not start indexing. Check the URL and try again.", "assistant");
  } finally {
    siteInput.disabled = false;
    siteForm.querySelector("button").disabled = false;
  }
});

reindexOpen.addEventListener("click", () => openReindexModal());
reindexClose.addEventListener("click", () => closeReindexModal());
reindexModal.addEventListener("click", (e) => {
  const target = e.target;
  if (target && target.dataset && target.dataset.close === "true") closeReindexModal();
});
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !reindexModal.classList.contains("hidden")) closeReindexModal();
});

reindexForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const url = reindexInput.value.trim();
  if (!url) return;

  reindexInput.disabled = true;
  reindexForm.querySelector("button").disabled = true;

  try {
    await indexSiteFlow(url);
  } catch (err) {
    console.error(err);
    setIndexStatus("Error");
    addMessage("Could not start indexing. Check the URL and try again.", "assistant");
  } finally {
    reindexInput.disabled = false;
    reindexForm.querySelector("button").disabled = false;
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
setActiveScreen("index");

