const API = "/api/v1";

const SIDEBAR_THEME_KEY = "demo_chat_sidebar_bg";
const SIDEBAR_TEXT_KEY = "demo_chat_sidebar_text";
const DEFAULT_SIDEBAR_BG = "#1a2744";

const BRANDING_TITLE_KEY = "demo_chat_app_title";
const BRANDING_LOGO_MODE_KEY = "demo_chat_logo_mode";
const BRANDING_LOGO_URL_KEY = "demo_chat_logo_url";
const DEFAULT_APP_TITLE = "Demo Chat";
const LOGO_MAX_DATA_URL = 500 * 1024;

const BUILTIN_LOGO_HTML_SIDEBAR = `<svg class="brand-logo-svg" viewBox="0 0 40 40" width="40" height="40" xmlns="http://www.w3.org/2000/svg">
<path fill="currentColor" fill-opacity="0.28" d="M4 14C4 9.03 8.03 5 13 5h10c4.97 0 9 4.03 9 9v5c0 4.97-4.03 9-9 9h-4.5l-5.2 6.2V28H13c-4.97 0-9-4.03-9-9v-5z"/>
<path fill="currentColor" d="M14 11c-3.31 0-6 2.69-6 6v7c0 3.31 2.69 6 6 6h2.8l4.5 5.4V30h2.7c3.31 0 6-2.69 6-6v-7c0-3.31-2.69-6-6-6H14z"/>
<circle class="brand-logo-dot" cx="17" cy="21" r="1.8" />
<circle class="brand-logo-dot" cx="22" cy="21" r="1.8" />
<circle class="brand-logo-dot" cx="27" cy="21" r="1.8" />
</svg>`;

const BUILTIN_LOGO_HTML_LOGIN = `<svg class="brand-logo-svg login-brand-svg" viewBox="0 0 40 40" width="44" height="44" xmlns="http://www.w3.org/2000/svg">
<path fill="var(--primary)" fill-opacity="0.22" d="M4 14C4 9.03 8.03 5 13 5h10c4.97 0 9 4.03 9 9v5c0 4.97-4.03 9-9 9h-4.5l-5.2 6.2V28H13c-4.97 0-9-4.03-9-9v-5z"/>
<path fill="var(--primary)" d="M14 11c-3.31 0-6 2.69-6 6v7c0 3.31 2.69 6 6 6h2.8l4.5 5.4V30h2.7c3.31 0 6-2.69 6-6v-7c0-3.31-2.69-6-6-6H14z"/>
<circle class="login-logo-dot" cx="17" cy="21" r="1.8" />
<circle class="login-logo-dot" cx="22" cy="21" r="1.8" />
<circle class="login-logo-dot" cx="27" cy="21" r="1.8" />
</svg>`;

const state = {
  token: null,
  me: null,
  channels: [],
  currentChannelId: null,
  messageIds: new Set(),
  messageCache: new Map(),
  nextBeforeId: null,
  hasMore: false,
  currentThreadRootId: null,
  threadRootMessage: null,
  threadMessageIds: new Set(),
  threadNextBeforeId: null,
  threadHasMore: false,
  ws: null,
  wsReady: false,
  presenceInterval: null,
};

function el(id) {
  return document.getElementById(id);
}

function hexToRgb(hex) {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex.trim());
  return m
    ? {
        r: parseInt(m[1], 16),
        g: parseInt(m[2], 16),
        b: parseInt(m[3], 16),
      }
    : null;
}

function rgbToHex(r, g, b) {
  return (
    "#" +
    [r, g, b]
      .map((x) =>
        Math.max(0, Math.min(255, Math.round(x)))
          .toString(16)
          .padStart(2, "0")
      )
      .join("")
  );
}

function mixRgb(hex, target, amount) {
  const c = hexToRgb(hex);
  if (!c) {
    return hex;
  }
  const t = target;
  return rgbToHex(
    c.r + (t.r - c.r) * amount,
    c.g + (t.g - c.g) * amount,
    c.b + (t.b - c.b) * amount
  );
}

function sidebarLuminance(hex) {
  const rgb = hexToRgb(hex);
  if (!rgb) {
    return 0;
  }
  const lin = (x) => {
    x /= 255;
    return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
  };
  const r = lin(rgb.r);
  const g = lin(rgb.g);
  const b = lin(rgb.b);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function defaultAutoTextForBg(bgHex) {
  return sidebarLuminance(bgHex) > 0.55 ? "#1c2433" : "#e8eef7";
}

function storedSidebarTextOverride() {
  const t = localStorage.getItem(SIDEBAR_TEXT_KEY);
  return t && /^#[0-9a-f]{6}$/i.test(t.trim()) ? t.trim() : null;
}

function applySidebarTheme(bgHex, opts = {}) {
  const root = document.documentElement;
  const app = el("app-view");
  const rawOverride = opts.textOverride;
  const hasTextOverride =
    typeof rawOverride === "string" &&
    /^#[0-9a-f]{6}$/i.test(String(rawOverride).trim());

  root.style.setProperty("--sidebar-bg", bgHex);
  const L = sidebarLuminance(bgHex);
  const lightBg = L > 0.55;

  if (lightBg) {
    app?.classList.add("sidebar-light");
  } else {
    app?.classList.remove("sidebar-light");
  }

  let textMain;
  let muted;
  let active;

  if (hasTextOverride) {
    const tx = String(rawOverride).trim();
    const txRgb = hexToRgb(tx);
    const bgRgb = hexToRgb(bgHex);
    textMain = tx;
    if (txRgb && bgRgb) {
      muted = mixRgb(tx, bgRgb, 0.42);
      active = mixRgb(bgHex, txRgb, 0.2);
    } else {
      muted = lightBg ? "#64748b" : "#8b9bb8";
      active = lightBg
        ? mixRgb(bgHex, { r: 30, g: 41, b: 59 }, 0.14)
        : mixRgb(bgHex, { r: 255, g: 255, b: 255 }, 0.16);
    }
  } else if (lightBg) {
    textMain = "#1c2433";
    muted = "#64748b";
    active = mixRgb(bgHex, { r: 30, g: 41, b: 59 }, 0.14);
  } else {
    textMain = "#e8eef7";
    muted = "#8b9bb8";
    active = mixRgb(bgHex, { r: 255, g: 255, b: 255 }, 0.16);
  }

  root.style.setProperty("--sidebar-text", textMain);
  root.style.setProperty("--sidebar-muted", muted);
  root.style.setProperty("--sidebar-active", active);
  root.style.setProperty("--sidebar-accent", "#2f6fed");
}

function syncSidebarAdminPickers() {
  const bgPicker = el("admin-sidebar-color");
  const textPicker = el("admin-sidebar-text-color");
  const storedBg = localStorage.getItem(SIDEBAR_THEME_KEY);
  const bg =
    storedBg && /^#[0-9a-f]{6}$/i.test(storedBg.trim())
      ? storedBg.trim()
      : DEFAULT_SIDEBAR_BG;
  if (bgPicker) {
    bgPicker.value = bg;
  }
  const storedText = storedSidebarTextOverride();
  if (textPicker) {
    textPicker.value = storedText || defaultAutoTextForBg(bg);
  }
}

function loadSidebarThemeFromStorage() {
  try {
    const raw = localStorage.getItem(SIDEBAR_THEME_KEY);
    const tx = storedSidebarTextOverride();
    const validBg =
      raw && /^#[0-9a-f]{6}$/i.test(raw.trim()) ? raw.trim() : null;
    if (validBg) {
      applySidebarTheme(validBg, tx ? { textOverride: tx } : {});
    } else if (tx) {
      applySidebarTheme(DEFAULT_SIDEBAR_BG, { textOverride: tx });
    }
    syncSidebarAdminPickers();
  } catch (_) {
    syncSidebarAdminPickers();
  }
}

function persistSidebarTheme(bgHex) {
  localStorage.setItem(SIDEBAR_THEME_KEY, bgHex);
}

function resetSidebarTheme() {
  localStorage.removeItem(SIDEBAR_THEME_KEY);
  localStorage.removeItem(SIDEBAR_TEXT_KEY);
  [
    "--sidebar-bg",
    "--sidebar-text",
    "--sidebar-muted",
    "--sidebar-active",
  ].forEach((p) => document.documentElement.style.removeProperty(p));
  el("app-view")?.classList.remove("sidebar-light");
  document.documentElement.style.removeProperty("--sidebar-accent");
  syncSidebarAdminPickers();
}

function isValidLogoSrc(url) {
  if (!url || typeof url !== "string") {
    return false;
  }
  const s = url.trim();
  if (s.length > 800000) {
    return false;
  }
  if (s.startsWith("/") && !s.startsWith("//")) {
    return true;
  }
  if (s.startsWith("data:image/")) {
    return s.length <= 700000;
  }
  try {
    const parsed = new URL(s, window.location.href);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

function readFileAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = () => reject(new Error("Could not read file"));
    r.readAsDataURL(file);
  });
}

function applyAppTitle(title) {
  const t =
    title !== undefined && title !== null && String(title).trim() !== ""
      ? String(title).trim()
      : DEFAULT_APP_TITLE;
  document.querySelectorAll(".js-app-title").forEach((n) => {
    n.textContent = t;
  });
  document.title = t;
}

function applyLogoDisplay(mode, url) {
  const sidebar = el("sidebar-logo-slot");
  const login = el("login-logo-slot");
  if (!sidebar || !login) {
    return;
  }
  const showBuiltIn = () => {
    sidebar.innerHTML = BUILTIN_LOGO_HTML_SIDEBAR;
    login.innerHTML = BUILTIN_LOGO_HTML_LOGIN;
    sidebar.classList.remove("js-logo-hidden");
    login.classList.remove("js-logo-hidden");
  };
  if (mode === "none") {
    sidebar.innerHTML = "";
    login.innerHTML = "";
    sidebar.classList.add("js-logo-hidden");
    login.classList.add("js-logo-hidden");
    return;
  }
  if (mode === "custom" && isValidLogoSrc(url)) {
    sidebar.innerHTML = "";
    login.innerHTML = "";
    const imgS = document.createElement("img");
    imgS.src = url;
    imgS.alt = "";
    imgS.className = "brand-logo-img brand-logo-img--sidebar";
    const imgL = document.createElement("img");
    imgL.src = url;
    imgL.alt = "";
    imgL.className = "brand-logo-img brand-logo-img--login";
    sidebar.appendChild(imgS);
    login.appendChild(imgL);
    sidebar.classList.remove("js-logo-hidden");
    login.classList.remove("js-logo-hidden");
    return;
  }
  showBuiltIn();
}

function loadBrandingFromStorage() {
  try {
    const storedTitle = localStorage.getItem(BRANDING_TITLE_KEY);
    if (storedTitle !== null && storedTitle.trim() !== "") {
      applyAppTitle(storedTitle.trim());
    } else {
      applyAppTitle(DEFAULT_APP_TITLE);
    }
    const mode = localStorage.getItem(BRANDING_LOGO_MODE_KEY) || "default";
    const src = localStorage.getItem(BRANDING_LOGO_URL_KEY) || "";
    applyLogoDisplay(mode, src);
  } catch (_) {
    applyAppTitle(DEFAULT_APP_TITLE);
    applyLogoDisplay("default", "");
  }
}

function syncAdminLogoCustomVisibility() {
  const mode = el("admin-logo-mode")?.value || "default";
  const wrap = el("admin-logo-custom-wrap");
  if (wrap) {
    wrap.classList.toggle("hidden", mode !== "custom");
  }
}

function syncAdminLogoModeFromStorage() {
  const modeSel = el("admin-logo-mode");
  if (modeSel) {
    modeSel.value = localStorage.getItem(BRANDING_LOGO_MODE_KEY) || "default";
  }
  syncAdminLogoCustomVisibility();
}

function populateAdminBrandingForm() {
  const titleIn = el("admin-app-title");
  if (titleIn) {
    const t = localStorage.getItem(BRANDING_TITLE_KEY);
    titleIn.value = t !== null && t !== "" ? t : "";
  }
  const modeSel = el("admin-logo-mode");
  if (modeSel) {
    modeSel.value = localStorage.getItem(BRANDING_LOGO_MODE_KEY) || "default";
  }
  const urlIn = el("admin-logo-url");
  if (urlIn) {
    const u = localStorage.getItem(BRANDING_LOGO_URL_KEY) || "";
    if (u.startsWith("data:image/")) {
      urlIn.value = "";
      urlIn.placeholder = "Uploaded image saved in this browser; paste a URL to replace";
    } else {
      urlIn.placeholder = "https://example.com/logo.png";
      urlIn.value = u;
    }
  }
  syncAdminLogoCustomVisibility();
  const fileIn = el("admin-logo-file");
  if (fileIn) {
    fileIn.value = "";
  }
  syncSidebarAdminPickers();
}

function resetBrandingTitleAndLogo() {
  localStorage.removeItem(BRANDING_TITLE_KEY);
  localStorage.removeItem(BRANDING_LOGO_MODE_KEY);
  localStorage.removeItem(BRANDING_LOGO_URL_KEY);
  applyAppTitle(DEFAULT_APP_TITLE);
  applyLogoDisplay("default", "");
  const urlIn = el("admin-logo-url");
  if (urlIn) {
    urlIn.placeholder = "https://example.com/logo.png";
  }
  populateAdminBrandingForm();
}

function showError(node, text) {
  if (!text) {
    node.classList.add("hidden");
    node.textContent = "";
    return;
  }
  node.classList.remove("hidden");
  node.textContent = text;
}

function stopPresencePolling() {
  if (state.presenceInterval) {
    clearInterval(state.presenceInterval);
    state.presenceInterval = null;
  }
}

function requireAuthOrLogin() {
  sessionStorage.removeItem("token");
  state.token = null;
  state.me = null;
  stopPresencePolling();
  if (state.ws) {
    try {
      state.ws.close();
    } catch (_) {}
    state.ws = null;
    state.wsReady = false;
  }
  showLogin();
  showError(
    el("login-error"),
    "Sign in to continue. Your session may have expired."
  );
}

async function api(path, options = {}) {
  const headers = { ...options.headers };
  if (state.token) {
    headers.Authorization = `Bearer ${state.token}`;
  }
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.json);
  }
  const res = await fetch(`${API}${path}`, { ...options, headers });
  if (res.status === 401 && path !== "/auth/login") {
    requireAuthOrLogin();
    throw new Error("Unauthorized");
  }
  if (res.status === 204) {
    return null;
  }
  const text = await res.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text };
    }
  }
  if (!res.ok) {
    const msg = data?.detail
      ? typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail)
      : res.statusText;
    throw new Error(msg);
  }
  return data;
}

function wsUrl() {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const token = encodeURIComponent(state.token || "");
  return `${proto}//${window.location.host}${API}/ws?token=${token}`;
}

function wsConnect() {
  if (state.ws) {
    try {
      state.ws.close();
    } catch (_) {}
  }
  state.wsReady = false;
  state.ws = new WebSocket(wsUrl());
  state.ws.onopen = () => {
    state.wsReady = true;
    if (state.currentChannelId) {
      wsSubscribe(state.currentChannelId);
    }
  };
  state.ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      // #region agent log
      fetch("http://127.0.0.1:7820/ingest/612cfd04-c745-4042-ae99-3cc9373167a7", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Debug-Session-Id": "b69983",
        },
        body: JSON.stringify({
          sessionId: "b69983",
          location: "app.js:ws.onmessage",
          message: "ws event",
          data: { type: msg.type, channel_id: msg.channel_id },
          timestamp: Date.now(),
          hypothesisId: "H4",
        }),
      }).catch(() => {});
      // #endregion
      if (msg.type === "subscribed" && msg.channel_id) {
        if (Array.isArray(msg.presence)) {
          applyPresenceList(msg.channel_id, msg.presence);
        } else {
          updatePresenceUi(msg.channel_id);
        }
      }
      if (msg.type === "message_created" && msg.payload) {
        const p = msg.payload;
        if (String(p.channel_id) !== String(state.currentChannelId)) {
          return;
        }
        cacheMessage(p);
        if (!p.parent_id) {
          appendMessage(p, true);
        } else if (
          String(state.currentThreadRootId) === String(p.parent_id)
        ) {
          appendThreadMessage(p, true);
        }
      }
      if (msg.type === "thread_updated" && msg.root_id != null) {
        if (String(msg.channel_id) === String(state.currentChannelId)) {
          updateReplyCountBadge(msg.root_id, msg.reply_count);
        }
      }
      if (msg.type === "channel_history_cleared" && msg.channel_id) {
        clearChannelFeedState(msg.channel_id);
      }
    } catch (_) {}
  };
  state.ws.onclose = () => {
    state.wsReady = false;
  };
}

function wsSubscribe(channelId) {
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
    return;
  }
  state.ws.send(
    JSON.stringify({ type: "subscribe", channel_id: channelId })
  );
}

function setView(name) {
  document.querySelectorAll(".nav-item").forEach((n) => {
    n.classList.toggle("active", n.dataset.view === name);
  });
  el("view-chat").classList.toggle("hidden", name !== "chat");
  el("view-admin").classList.toggle("hidden", name !== "admin");
  el("view-account").classList.toggle("hidden", name !== "account");
  const titles = { chat: "Channels", admin: "Admin", account: "Account" };
  el("page-heading").textContent = titles[name] || "Demo Chat";
}

function showApp() {
  el("login-view").classList.add("hidden");
  el("app-view").classList.remove("hidden");
}

function showLogin() {
  el("app-view").classList.add("hidden");
  el("login-view").classList.remove("hidden");
}

function formatTime(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

function cacheMessage(p) {
  if (p?.id) {
    state.messageCache.set(String(p.id), p);
  }
}

function bindReplyCountClick(countEl, rootId) {
  if (countEl.dataset.replyBound === "1") {
    return;
  }
  countEl.dataset.replyBound = "1";
  countEl.addEventListener("click", (ev) => {
    ev.stopPropagation();
    const cached = state.messageCache.get(String(rootId));
    openThread(rootId, cached);
  });
}

function renderMessageRow(p, options = {}) {
  const { showReplyActions = false, highlight = false } = options;
  const row = document.createElement("div");
  row.className = "msg-row" + (highlight ? " msg-row--thread-open" : "");
  row.dataset.id = p.id;
  row.innerHTML = `<div class="msg-meta"><strong>${escapeHtml(
    p.username
  )}</strong> · ${escapeHtml(formatTime(p.created_at))}</div><div class="msg-body">${escapeHtml(
    p.body
  )}</div>`;

  if (showReplyActions) {
    const actions = document.createElement("div");
    actions.className = "msg-row__actions";

    const replyBtn = document.createElement("button");
    replyBtn.type = "button";
    replyBtn.className = "btn btn-ghost msg-reply-btn";
    replyBtn.textContent = "Reply in thread";
    replyBtn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      openThread(p.id, p);
    });
    actions.appendChild(replyBtn);

    const countEl = document.createElement("span");
    countEl.className = "msg-reply-count";
    countEl.dataset.rootId = p.id;
    bindReplyCountClick(countEl, p.id);
    const count = p.reply_count || 0;
    if (count > 0) {
      countEl.textContent = `${count} ${count === 1 ? "reply" : "replies"}`;
    } else {
      countEl.classList.add("hidden");
    }
    actions.appendChild(countEl);
    row.appendChild(actions);
  }

  return row;
}

function updateReplyCountBadge(rootId, count) {
  const row = document.querySelector(`.msg-row[data-id="${rootId}"]`);
  if (!row) {
    return;
  }
  let countEl = row.querySelector(".msg-reply-count");
  if (!countEl) {
    const actions = row.querySelector(".msg-row__actions");
    if (!actions) {
      return;
    }
    countEl = document.createElement("span");
    countEl.className = "msg-reply-count";
    countEl.dataset.rootId = rootId;
    actions.appendChild(countEl);
  }
  bindReplyCountClick(countEl, rootId);
  const n = Number(count) || 0;
  if (n > 0) {
    countEl.classList.remove("hidden");
    countEl.textContent = `${n} ${n === 1 ? "reply" : "replies"}`;
  } else {
    countEl.classList.add("hidden");
    countEl.textContent = "";
  }
  const cached = state.messageCache.get(String(rootId));
  if (cached) {
    cached.reply_count = n;
  }
}

function resetThreadPanelDom() {
  state.threadMessageIds.clear();
  state.threadNextBeforeId = null;
  state.threadHasMore = false;
  el("thread-messages-inner").innerHTML = "";
  el("thread-parent").innerHTML = "";
  document.querySelectorAll(".msg-row--thread-open").forEach((n) => {
    n.classList.remove("msg-row--thread-open");
  });
}

function closeThread() {
  state.currentThreadRootId = null;
  state.threadRootMessage = null;
  resetThreadPanelDom();
  document.querySelector(".chat-layout")?.classList.remove("chat-layout--thread-open");
  el("thread-panel")?.classList.add("hidden");
  if (el("thread-msg-input")) {
    el("thread-msg-input").disabled = true;
    el("thread-msg-input").value = "";
  }
  if (el("thread-send-btn")) {
    el("thread-send-btn").disabled = true;
  }
  if (el("thread-load-older")) {
    el("thread-load-older").disabled = true;
  }
}

function clearChannelFeedState(channelId) {
  if (String(state.currentChannelId) !== String(channelId)) {
    return;
  }
  closeThread();
  state.messageIds.clear();
  state.messageCache.clear();
  state.nextBeforeId = null;
  state.hasMore = false;
  el("messages-inner").innerHTML = "";
  el("load-older").disabled = true;
}

async function clearChannelHistory() {
  const id = el("dlg-ch-id")?.value;
  const name = el("dlg-ch-name")?.value?.trim() || "this channel";
  if (!id) {
    return;
  }
  if (
    !window.confirm(
      `Clear all message history in #${name}?\n\nThis permanently deletes every message and thread reply in this channel. This cannot be undone.`
    )
  ) {
    return;
  }
  try {
    const result = await api(`/channels/${id}/messages`, { method: "DELETE" });
    clearChannelFeedState(id);
    el("dlg-channel")?.close();
    const count = result?.deleted_count ?? 0;
    alert(`Cleared ${count} message${count === 1 ? "" : "s"} from #${name}.`);
  } catch (e) {
    alert(e.message || String(e));
  }
}

async function openThread(rootId, rootMessage) {
  if (!state.currentChannelId) {
    return;
  }
  resetThreadPanelDom();
  state.currentThreadRootId = rootId;
  state.threadRootMessage =
    rootMessage || state.messageCache.get(String(rootId)) || null;

  document.querySelector(".chat-layout")?.classList.add("chat-layout--thread-open");
  el("thread-panel")?.classList.remove("hidden");

  document
    .querySelector(`.msg-row[data-id="${rootId}"]`)
    ?.classList.add("msg-row--thread-open");

  if (state.threadRootMessage) {
    el("thread-parent").appendChild(
      renderMessageRow(state.threadRootMessage, { showReplyActions: false })
    );
  }

  el("thread-msg-input").disabled = false;
  el("thread-send-btn").disabled = false;
  await loadThreadRepliesFirstPage();
}

function appendThreadMessage(p, dedupe) {
  if (dedupe && state.threadMessageIds.has(p.id)) {
    return;
  }
  state.threadMessageIds.add(p.id);
  cacheMessage(p);
  const inner = el("thread-messages-inner");
  inner.appendChild(renderMessageRow(p, { showReplyActions: false }));
  inner.scrollTop = inner.scrollHeight;
}

function prependThreadMessages(items) {
  const inner = el("thread-messages-inner");
  const frag = document.createDocumentFragment();
  items.forEach((p) => {
    if (!state.threadMessageIds.has(p.id)) {
      state.threadMessageIds.add(p.id);
      cacheMessage(p);
      frag.appendChild(renderMessageRow(p, { showReplyActions: false }));
    }
  });
  inner.insertBefore(frag, inner.firstChild);
}

async function loadThreadRepliesFirstPage() {
  if (!state.currentChannelId || !state.currentThreadRootId) {
    return;
  }
  const q = new URLSearchParams({ limit: "50" });
  const page = await api(
    `/channels/${state.currentChannelId}/messages/${state.currentThreadRootId}/replies?${q}`
  );
  state.threadHasMore = page.has_more;
  state.threadNextBeforeId = page.next_before_id;
  page.items.forEach((m) => appendThreadMessage(m, false));
  el("thread-load-older").disabled = !state.threadHasMore;
}

async function loadThreadOlder() {
  if (
    !state.currentChannelId ||
    !state.currentThreadRootId ||
    !state.threadNextBeforeId
  ) {
    return;
  }
  const q = new URLSearchParams({
    limit: "50",
    before_id: state.threadNextBeforeId,
  });
  const page = await api(
    `/channels/${state.currentChannelId}/messages/${state.currentThreadRootId}/replies?${q}`
  );
  state.threadHasMore = page.has_more;
  state.threadNextBeforeId = page.next_before_id;
  prependThreadMessages(page.items);
  el("thread-load-older").disabled = !state.threadHasMore;
}

async function sendThreadMessage() {
  const body = el("thread-msg-input").value.trim();
  if (!body || !state.currentChannelId || !state.currentThreadRootId) {
    return;
  }
  try {
    await api(`/channels/${state.currentChannelId}/messages`, {
      method: "POST",
      json: { body, parent_id: state.currentThreadRootId },
    });
    el("thread-msg-input").value = "";
  } catch (e) {
    alert(e.message);
  }
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function appendMessage(p, dedupe) {
  if (dedupe && state.messageIds.has(p.id)) {
    return;
  }
  state.messageIds.add(p.id);
  cacheMessage(p);
  const inner = el("messages-inner");
  inner.appendChild(renderMessageRow(p, { showReplyActions: true }));
  inner.scrollTop = inner.scrollHeight;
}

function prependMessages(items) {
  const inner = el("messages-inner");
  const frag = document.createDocumentFragment();
  items.forEach((p) => {
    if (!state.messageIds.has(p.id)) {
      state.messageIds.add(p.id);
      cacheMessage(p);
      frag.appendChild(renderMessageRow(p, { showReplyActions: true }));
    }
  });
  const anchor = inner.firstChild;
  inner.insertBefore(frag, anchor);
}

async function loadMe() {
  state.me = await api("/users/me");
  el("whoami").textContent = `${state.me.username}${state.me.is_admin ? " (admin)" : ""}`;
  el("nav-admin").classList.toggle("hidden", !state.me.is_admin);
}

function renderConnectedUsersPanel(list, errorMessage) {
  const ul = el("channel-connected-list");
  if (!ul) {
    return;
  }
  const heading = el("channel-connected-heading");
  if (heading && state.currentChannelId) {
    const ch = state.channels.find(
      (x) => String(x.id) === String(state.currentChannelId)
    );
    heading.textContent = ch ? `Connected · #${ch.name}` : "Connected now";
  } else if (heading) {
    heading.textContent = "Connected now";
  }
  ul.innerHTML = "";
  if (errorMessage) {
    const li = document.createElement("li");
    li.className = "connected-users-error";
    li.textContent = errorMessage;
    ul.appendChild(li);
    return;
  }
  if (list === null) {
    const li = document.createElement("li");
    li.className = "connected-users-placeholder";
    li.textContent = "Loading…";
    ul.appendChild(li);
    return;
  }
  if (!list.length) {
    const li = document.createElement("li");
    li.className = "connected-users-placeholder";
    li.textContent = "No one connected";
    ul.appendChild(li);
    return;
  }
  list.forEach((u) => {
    const li = document.createElement("li");
    li.textContent = u.username || "?";
    ul.appendChild(li);
  });
}

function applyPresenceList(channelId, list) {
  if (String(channelId) === String(state.currentChannelId)) {
    renderConnectedUsersPanel(list);
  }
}

async function updatePresenceUi(channelId) {
  if (!channelId || !state.token) {
    // #region agent log
    fetch("http://127.0.0.1:7820/ingest/612cfd04-c745-4042-ae99-3cc9373167a7", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Debug-Session-Id": "b69983",
      },
      body: JSON.stringify({
        sessionId: "b69983",
        location: "app.js:updatePresenceUi",
        message: "skip no token or id",
        data: {
          hasId: !!channelId,
          hasToken: !!state.token,
        },
        timestamp: Date.now(),
        hypothesisId: "H3",
      }),
    }).catch(() => {});
    // #endregion
    return;
  }
  try {
    // #region agent log
    fetch("http://127.0.0.1:7820/ingest/612cfd04-c745-4042-ae99-3cc9373167a7", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Debug-Session-Id": "b69983",
      },
      body: JSON.stringify({
        sessionId: "b69983",
        location: "app.js:updatePresenceUi",
        message: "presence GET start",
        data: { channelId: String(channelId) },
        timestamp: Date.now(),
        hypothesisId: "H1",
      }),
    }).catch(() => {});
    // #endregion
    const list = await api(`/channels/${channelId}/presence`);
    // #region agent log
    fetch("http://127.0.0.1:7820/ingest/612cfd04-c745-4042-ae99-3cc9373167a7", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Debug-Session-Id": "b69983",
      },
      body: JSON.stringify({
        sessionId: "b69983",
        location: "app.js:updatePresenceUi",
        message: "presence OK",
        data: { count: list?.length ?? -1 },
        timestamp: Date.now(),
        hypothesisId: "H1",
      }),
    }).catch(() => {});
    // #endregion
    applyPresenceList(channelId, list);
  } catch (e) {
    // #region agent log
    fetch("http://127.0.0.1:7820/ingest/612cfd04-c745-4042-ae99-3cc9373167a7", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Debug-Session-Id": "b69983",
      },
      body: JSON.stringify({
        sessionId: "b69983",
        location: "app.js:updatePresenceUi",
        message: "presence error",
        data: { err: String(e?.message || e) },
        timestamp: Date.now(),
        hypothesisId: "H2",
      }),
    }).catch(() => {});
    // #endregion
    if (e.message === "Unauthorized") {
      return;
    }
    if (String(channelId) === String(state.currentChannelId)) {
      renderConnectedUsersPanel(null, e.message);
    }
  }
}

function startPresencePolling() {
  stopPresencePolling();
  state.presenceInterval = setInterval(() => {
    if (state.currentChannelId && state.token) {
      updatePresenceUi(state.currentChannelId);
    }
  }, 4000);
}

async function resetInstance() {
  const ok = window.confirm(
    "Reset instance?\n\nThis will permanently delete:\n" +
      "• All channels and messages\n" +
      "• All channel memberships\n" +
      "• All users except the seed admin\n" +
      "• All server-side instance settings\n\n" +
      "The seed admin password will be reset to the default (changeme).\n\n" +
      "This cannot be undone."
  );
  if (!ok) {
    return;
  }
  try {
    const result = await api("/admin/reset", {
      method: "POST",
      json: { confirm: true },
    });
    closeThread();
    if (state.currentChannelId && state.ws?.readyState === WebSocket.OPEN) {
      state.ws.send(
        JSON.stringify({ type: "unsubscribe", channel_id: state.currentChannelId })
      );
    }
    state.currentChannelId = null;
    state.messageIds.clear();
    state.messageCache.clear();
    state.nextBeforeId = null;
    state.hasMore = false;
    el("messages-inner").innerHTML = "";
    el("msg-input").disabled = true;
    el("msg-input").value = "";
    el("send-btn").disabled = true;
    el("load-older").disabled = true;
    const title = el("channel-title-line");
    if (title) {
      title.textContent = "Select a channel";
    }
    renderConnectedUsersPanel([]);
    await refreshChannels();
    await refreshUsersTable();
    await refreshChannelsTable();
    await refreshMembersTable();
    alert(
      `Instance reset complete.\n\nSign in as "${result.admin_username}" with the default seed password if needed.`
    );
  } catch (e) {
    alert(e.message || String(e));
  }
}

async function refreshChannels() {
  state.channels = await api("/channels");
  const box = el("channel-list");
  box.innerHTML = "";
  state.channels.forEach((c) => {
    const wrap = document.createElement("div");
    wrap.className =
      "channel-item-wrap" +
      (c.id === state.currentChannelId ? " active" : "");
    wrap.dataset.id = c.id;
    const nameEl = document.createElement("div");
    nameEl.className = "channel-item-name";
    nameEl.textContent = c.name;
    wrap.appendChild(nameEl);
    wrap.onclick = () => selectChannel(c.id);
    box.appendChild(wrap);
  });
  const mc = el("member-channel-select");
  if (mc) {
    mc.innerHTML = "";
    state.channels.forEach((c) => {
      const o = document.createElement("option");
      o.value = c.id;
      o.textContent = c.name;
      mc.appendChild(o);
    });
  }
}

async function selectChannel(id) {
  closeThread();
  const prev = state.currentChannelId;
  if (state.ws && state.ws.readyState === WebSocket.OPEN && prev && prev !== id) {
    state.ws.send(
      JSON.stringify({ type: "unsubscribe", channel_id: prev })
    );
  }
  state.currentChannelId = id;
  state.messageIds.clear();
  state.messageCache.clear();
  el("messages-inner").innerHTML = "";
  el("msg-input").disabled = false;
  el("send-btn").disabled = false;
  const ch = state.channels.find((x) => x.id === id);
  const title = el("channel-title-line");
  if (title) {
    title.textContent = ch ? `# ${ch.name}` : "";
  }
  renderConnectedUsersPanel(null);
  document.querySelectorAll(".channel-item-wrap").forEach((n) => {
    n.classList.toggle("active", n.dataset.id === id);
  });
  await loadMessagesFirstPage();
  wsSubscribe(id);
  el("load-older").disabled = !state.hasMore;
  await updatePresenceUi(id);
  startPresencePolling();
}

async function loadMessagesFirstPage() {
  if (!state.currentChannelId) {
    return;
  }
  const q = new URLSearchParams({ limit: "50", root_only: "true" });
  const page = await api(
    `/channels/${state.currentChannelId}/messages?${q}`
  );
  state.hasMore = page.has_more;
  state.nextBeforeId = page.next_before_id;
  page.items.forEach((m) => appendMessage(m, false));
  el("load-older").disabled = !state.hasMore;
}

async function loadOlder() {
  if (!state.currentChannelId || !state.nextBeforeId) {
    return;
  }
  const q = new URLSearchParams({
    limit: "50",
    before_id: state.nextBeforeId,
    root_only: "true",
  });
  const page = await api(
    `/channels/${state.currentChannelId}/messages?${q}`
  );
  state.hasMore = page.has_more;
  state.nextBeforeId = page.next_before_id;
  prependMessages(page.items);
  el("load-older").disabled = !state.hasMore;
}

async function sendMessage() {
  const body = el("msg-input").value.trim();
  if (!body || !state.currentChannelId) {
    return;
  }
  try {
    await api(`/channels/${state.currentChannelId}/messages`, {
      method: "POST",
      json: { body },
    });
    el("msg-input").value = "";
  } catch (e) {
    alert(e.message);
  }
}

async function login() {
  const username = el("login-user").value.trim();
  const password = el("login-pass").value;
  showError(el("login-error"), "");
  try {
    const tok = await fetch(`${API}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    }).then(async (r) => {
      const t = await r.json().catch(() => ({}));
      if (!r.ok) {
        throw new Error(t.detail || r.statusText);
      }
      return t;
    });
    state.token = tok.access_token;
    sessionStorage.setItem("token", state.token);
    await loadMe();
    showApp();
    wsConnect();
    await refreshChannels();
    setView("chat");
    if (state.channels.length) {
      await selectChannel(state.channels[0].id);
    }
  } catch (e) {
    showError(el("login-error"), e.message);
  }
}

function logout() {
  sessionStorage.removeItem("token");
  state.token = null;
  state.me = null;
  stopPresencePolling();
  if (state.ws) {
    try {
      state.ws.close();
    } catch (_) {}
  }
  state.ws = null;
  showLogin();
}

async function refreshUsersTable() {
  if (!state.me?.is_admin) {
    return;
  }
  const users = await api("/users");
  const tb = el("users-table").querySelector("tbody");
  tb.innerHTML = "";
  users.forEach((u) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${escapeHtml(u.username)}</td><td>${
      u.is_admin
        ? '<span class="pill pill-admin">Admin</span>'
        : '<span class="pill pill-user">User</span>'
    }</td><td>${
      u.id === state.me.id
        ? ""
        : `<button type="button" class="btn btn-ghost" data-del-user="${u.id}">Remove</button>`
    }</td>`;
    tb.appendChild(tr);
  });
  tb.querySelectorAll("[data-del-user]").forEach((btn) => {
    btn.onclick = async () => {
      const id = btn.getAttribute("data-del-user");
      if (!confirm("Delete this user?")) {
        return;
      }
      await api(`/users/${id}`, { method: "DELETE" });
      await refreshUsersTable();
      await refreshMemberUserSelect();
    };
  });

  const sel = el("member-user-select");
  sel.innerHTML = "";
  users.forEach((u) => {
    const o = document.createElement("option");
    o.value = u.id;
    o.textContent = u.username;
    sel.appendChild(o);
  });

  const dlgUser = el("dlg-ch-user");
  dlgUser.innerHTML = "";
  const ph = document.createElement("option");
  ph.value = "";
  ph.textContent = "— Select user —";
  dlgUser.appendChild(ph);
  users.forEach((u) => {
    const o = document.createElement("option");
    o.value = u.id;
    o.textContent = u.username;
    dlgUser.appendChild(o);
  });
}

async function refreshChannelsTable() {
  if (!state.me?.is_admin) {
    return;
  }
  await refreshChannels();
  const tb = el("channels-table").querySelector("tbody");
  tb.innerHTML = "";
  state.channels.forEach((c) => {
    const tr = document.createElement("tr");
    const wh =
      c.allow_anonymous_webhook && c.anonymous_webhook_user_id
        ? '<span class="pill pill-warn">Anonymous ON</span>'
        : '<span class="pill pill-user">Auth required</span>';
    tr.innerHTML = `<td>${escapeHtml(c.name)}</td><td>${wh}</td><td><button type="button" class="btn btn-ghost" data-edit-ch="${c.id}">Edit</button> <button type="button" class="btn btn-ghost" data-del-ch="${c.id}">Delete</button></td>`;
    tb.appendChild(tr);
  });
  tb.querySelectorAll("[data-edit-ch]").forEach((btn) => {
    btn.onclick = async () => {
      await openChannelDlg(btn.getAttribute("data-edit-ch"));
    };
  });
  tb.querySelectorAll("[data-del-ch]").forEach((btn) => {
    btn.onclick = async () => {
      const id = btn.getAttribute("data-del-ch");
      if (!confirm("Delete this channel?")) {
        return;
      }
      await api(`/channels/${id}`, { method: "DELETE" });
      await refreshChannelsTable();
      if (state.currentChannelId === id) {
        state.currentChannelId = null;
        el("messages-inner").innerHTML = "";
        el("msg-input").disabled = true;
        el("send-btn").disabled = true;
      }
    };
  });
}

async function openChannelDlg(channelId) {
  const c = state.channels.find((x) => x.id === channelId);
  if (!c) {
    return;
  }
  await refreshUsersTable();
  el("dlg-ch-id").value = c.id;
  el("dlg-ch-name").value = c.name;
  el("dlg-ch-anon").checked = !!c.allow_anonymous_webhook;
  el("dlg-ch-warn").classList.toggle("hidden", !c.allow_anonymous_webhook);
  el("dlg-ch-user").value = c.anonymous_webhook_user_id
    ? String(c.anonymous_webhook_user_id)
    : "";
  el("dlg-ch-payload-format").value = c.webhook_payload_format || "body";
  el("dlg-ch-hook-url").textContent = `${window.location.origin}${API}/webhooks/channels/${c.id}/messages`;
  el("dlg-channel").showModal();
}

async function refreshMembersTable() {
  const sel = el("member-channel-select");
  const cid = sel.value;
  if (!cid) {
    el("members-table").querySelector("tbody").innerHTML = "";
    return;
  }
  const members = await api(`/channels/${cid}/members`);
  const tb = el("members-table").querySelector("tbody");
  tb.innerHTML = "";
  members.forEach((u) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${escapeHtml(u.username)}</td><td><button type="button" class="btn btn-ghost" data-rm-member="${u.id}">Remove</button></td>`;
    tb.appendChild(tr);
  });
  tb.querySelectorAll("[data-rm-member]").forEach((btn) => {
    btn.onclick = async () => {
      const uid = btn.getAttribute("data-rm-member");
      await api(`/channels/${cid}/members/${uid}`, { method: "DELETE" });
      await refreshMembersTable();
    };
  });
}

async function refreshMemberUserSelect() {
  await refreshUsersTable();
}

document.addEventListener("DOMContentLoaded", () => {
  loadSidebarThemeFromStorage();
  loadBrandingFromStorage();
  syncAdminLogoModeFromStorage();

  state.token = sessionStorage.getItem("token");
  if (state.token) {
    api("/users/me")
      .then(async (me) => {
        state.me = me;
        showApp();
        el("whoami").textContent = `${me.username}${me.is_admin ? " (admin)" : ""}`;
        el("nav-admin").classList.toggle("hidden", !me.is_admin);
        wsConnect();
        await refreshChannels();
        setView("chat");
        if (state.channels.length) {
          await selectChannel(state.channels[0].id);
        }
      })
      .catch(() => {
        logout();
      });
  }

  el("login-btn").onclick = login;
  el("logout-btn").onclick = logout;
  el("send-btn").onclick = sendMessage;
  el("msg-input").addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey) {
      ev.preventDefault();
      sendMessage();
    }
  });
  el("load-older").onclick = loadOlder;
  el("thread-close").onclick = closeThread;
  el("thread-send-btn").onclick = sendThreadMessage;
  el("thread-load-older").onclick = loadThreadOlder;
  el("thread-msg-input")?.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey) {
      ev.preventDefault();
      sendThreadMessage();
    }
  });

  document.querySelectorAll(".nav-item").forEach((n) => {
    n.onclick = () => {
      const v = n.dataset.view;
      if (v === "admin" && !state.me?.is_admin) {
        return;
      }
      setView(v);
      if (v === "admin") {
        populateAdminBrandingForm();
        refreshUsersTable();
        refreshChannelsTable();
        refreshMembersTable();
      }
    };
  });

  el("btn-new-user").onclick = () => el("dlg-user").showModal();
  el("dlg-cancel").onclick = () => el("dlg-user").close();
  el("dlg-save").onclick = async () => {
    const username = el("dlg-username").value.trim();
    const password = el("dlg-password").value;
    const is_admin = el("dlg-is-admin").checked;
    await api("/users", {
      method: "POST",
      json: { username, password, is_admin },
    });
    el("dlg-user").close();
    await refreshUsersTable();
  };

  el("btn-create-channel").onclick = async () => {
    const name = el("new-channel-name").value.trim();
    if (!name) {
      return;
    }
    await api("/channels", {
      method: "POST",
      json: { name, allow_anonymous_webhook: false },
    });
    el("new-channel-name").value = "";
    await refreshChannelsTable();
    if (state.currentChannelId) {
      await selectChannel(state.currentChannelId);
    }
  };

  el("btn-add-member").onclick = async () => {
    const cid = el("member-channel-select").value;
    const uid = el("member-user-select").value;
    await api(`/channels/${cid}/members`, {
      method: "POST",
      json: { user_id: uid },
    });
    await refreshMembersTable();
  };

  el("member-channel-select").onchange = refreshMembersTable;

  el("admin-logo-mode")?.addEventListener("change", syncAdminLogoCustomVisibility);

  el("btn-admin-title-apply")?.addEventListener("click", () => {
    const v = el("admin-app-title")?.value?.trim() || "";
    if (v) {
      localStorage.setItem(BRANDING_TITLE_KEY, v);
      applyAppTitle(v);
    } else {
      localStorage.removeItem(BRANDING_TITLE_KEY);
      applyAppTitle(DEFAULT_APP_TITLE);
    }
  });

  el("btn-admin-logo-apply")?.addEventListener("click", async () => {
    const mode = el("admin-logo-mode")?.value || "default";
    const fileIn = el("admin-logo-file");
    const file = fileIn?.files?.[0];
    let src = (el("admin-logo-url")?.value || "").trim();

    if (file) {
      if (file.size > LOGO_MAX_DATA_URL) {
        alert(`Image must be under ${LOGO_MAX_DATA_URL / 1024} KB.`);
        return;
      }
      try {
        src = await readFileAsDataURL(file);
      } catch (e) {
        alert(e?.message || String(e));
        return;
      }
    } else if (mode === "custom" && !src) {
      src = localStorage.getItem(BRANDING_LOGO_URL_KEY) || "";
    }

    if (mode === "custom" && !isValidLogoSrc(src)) {
      alert(
        "Enter a valid http(s) URL, a path starting with /, or upload an image (PNG, WebP, SVG, etc.)."
      );
      return;
    }

    localStorage.setItem(BRANDING_LOGO_MODE_KEY, mode);
    if (mode === "custom") {
      localStorage.setItem(BRANDING_LOGO_URL_KEY, src);
    } else {
      localStorage.removeItem(BRANDING_LOGO_URL_KEY);
    }
    applyLogoDisplay(mode, mode === "custom" ? src : "");
    if (fileIn) {
      fileIn.value = "";
    }
    populateAdminBrandingForm();
  });

  el("btn-admin-brand-reset")?.addEventListener("click", () => {
    resetBrandingTitleAndLogo();
  });

  el("btn-sidebar-apply")?.addEventListener("click", () => {
    const hex = el("admin-sidebar-color")?.value || DEFAULT_SIDEBAR_BG;
    const textHex =
      el("admin-sidebar-text-color")?.value || defaultAutoTextForBg(hex);
    applySidebarTheme(hex, { textOverride: textHex });
    persistSidebarTheme(hex);
    localStorage.setItem(SIDEBAR_TEXT_KEY, textHex);
  });
  el("btn-sidebar-reset")?.addEventListener("click", () => {
    resetSidebarTheme();
  });
  el("btn-admin-instance-reset")?.addEventListener("click", resetInstance);
  document.querySelectorAll(".sidebar-preset").forEach((btn) => {
    btn.addEventListener("click", () => {
      const hex = btn.getAttribute("data-hex");
      if (!hex) {
        return;
      }
      const picker = el("admin-sidebar-color");
      if (picker) {
        picker.value = hex;
      }
      const tx = storedSidebarTextOverride();
      applySidebarTheme(hex, tx ? { textOverride: tx } : {});
      persistSidebarTheme(hex);
      syncSidebarAdminPickers();
    });
  });

  el("dlg-ch-anon").onchange = () => {
    el("dlg-ch-warn").classList.toggle("hidden", !el("dlg-ch-anon").checked);
  };
  el("dlg-ch-cancel").onclick = () => el("dlg-channel").close();
  el("dlg-ch-clear-history")?.addEventListener("click", clearChannelHistory);
  el("dlg-ch-save").onclick = async () => {
    const id = el("dlg-ch-id").value;
    const name = el("dlg-ch-name").value.trim();
    const allow = el("dlg-ch-anon").checked;
    const uid = el("dlg-ch-user").value.trim();
    if (!name) {
      alert("Channel name is required.");
      return;
    }
    if (allow && !uid) {
      alert(
        "Choose which existing user anonymous webhook posts will appear as (must be a member of this channel)."
      );
      return;
    }
    const body = {
      name,
      allow_anonymous_webhook: allow,
      anonymous_webhook_user_id: allow && uid ? uid : null,
      webhook_payload_format: el("dlg-ch-payload-format").value || "body",
    };
    try {
      await api(`/channels/${id}`, { method: "PATCH", json: body });
      el("dlg-channel").close();
      await refreshChannelsTable();
      await refreshChannels();
    } catch (e) {
      alert(e.message || String(e));
    }
  };

  el("btn-save-password").onclick = async () => {
    const password = el("new-password").value;
    if (!password) {
      return;
    }
    try {
      await api("/users/me", { method: "PATCH", json: { password } });
      const node = el("account-msg");
      node.classList.remove("hidden");
      node.style.color = "var(--muted)";
      node.textContent = "Password updated.";
      el("new-password").value = "";
    } catch (e) {
      const node = el("account-msg");
      node.style.color = "";
      showError(node, e.message);
    }
  };
});
