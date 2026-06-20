const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ""));
const bridgeToken = fragment.get("token") || "";

const state = {
  selectedId: null,
  activeTaskId: null,
  pollTimer: null,
  centralSession: null,
  pendingMaterialItem: null,
  contentPage: 1,
  contentPageSize: 12,
  contentPageCount: 1,
  multiSelectEnabled: false,
  selectedContentIds: new Set(),
  visibleContentIds: [],
  pendingBulkMaterialIds: [],
};

const el = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;");

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(bridgeToken ? { Authorization: `Bearer ${bridgeToken}` } : {}),
      ...(options.headers || {}),
    },
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || `请求失败 ${response.status}`);
  return payload;
}

async function establishBridgeSession() {
  if (!bridgeToken) return;
  const response = await fetch("/bridge/session", {
    method: "POST",
    headers: { Authorization: `Bearer ${bridgeToken}` },
  });
  if (!response.ok) throw new Error("本地工作台鉴权失败，请重新复制启动日志中的地址");
  window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
}

function toast(message) {
  el("toast").textContent = message;
  el("toast").hidden = false;
  window.setTimeout(() => { el("toast").hidden = true; }, 3200);
}

function formatNumber(value) {
  const number = Number(value || 0);
  if (number >= 10000) return `${(number / 10000).toFixed(number >= 100000 ? 0 : 1)}万`;
  return String(number);
}

function platformLabel(platform) {
  return platform === "douyin" ? "抖音" : "小红书";
}

function mediaUrl(url) {
  return url ? `/api/local/media?url=${encodeURIComponent(url)}` : "";
}

function statusLabel(status) {
  return { queued: "等待中", active: "定时中", running: "采集中", success: "完成", failed: "失败", paused: "已暂停" }[status] || status;
}

function processingStatusLabel(status) {
  return { pending: "待处理", discarded: "已废弃", material: "素材库" }[status] || "待处理";
}

function updateBatchToolbar() {
  el("batchToolbar").hidden = !state.multiSelectEnabled;
  el("toggleMultiSelect").textContent = state.multiSelectEnabled ? "退出多选" : "多选";
  const count = state.selectedContentIds.size;
  el("selectedCount").textContent = `已选 ${count} 条`;
  ["batchPending", "batchDiscard", "batchMaterial"].forEach((id) => {
    el(id).disabled = count === 0;
  });
  const visibleSelected = state.visibleContentIds.filter((id) => state.selectedContentIds.has(id)).length;
  el("selectPage").checked = state.visibleContentIds.length > 0 && visibleSelected === state.visibleContentIds.length;
  el("selectPage").indeterminate = visibleSelected > 0 && visibleSelected < state.visibleContentIds.length;
}

async function loadContents() {
  const params = new URLSearchParams();
  const keyword = el("localKeyword").value.trim();
  const platform = el("platformFilter").value;
  const source = el("sourceFilter").value;
  const processingStatus = el("statusFilter").value;
  if (keyword) params.set("keyword", keyword);
  if (platform) params.set("platform", platform);
  if (source) params.set("source_type", source);
  if (processingStatus) params.set("processing_status", processingStatus);
  params.set("limit", state.contentPageSize);
  params.set("offset", (state.contentPage - 1) * state.contentPageSize);
  const data = await api(`/api/local/contents?${params}`);
  const pageCount = Math.max(1, Math.ceil(data.total / state.contentPageSize));
  if (state.contentPage > pageCount) {
    state.contentPage = pageCount;
    return loadContents();
  }
  state.contentPageCount = pageCount;
  state.visibleContentIds = data.items.map((item) => item.id);
  el("resultCount").textContent = `${data.total} 条`;
  el("emptyState").hidden = data.items.length > 0;
  el("contentList").innerHTML = data.items.map((item) => {
    const cover = item.cover_url
      ? `<img class="cover" src="${escapeHtml(mediaUrl(item.cover_url))}" alt="">`
      : `<div class="cover cover-fallback">无封面</div>`;
    return `
      <div class="content-row ${state.selectedId === item.id ? "active" : ""} ${state.multiSelectEnabled ? "multi-select-active" : ""}">
        ${state.multiSelectEnabled ? `<label class="content-select" title="选择内容">
          <input type="checkbox" data-select-content="${item.id}" ${state.selectedContentIds.has(item.id) ? "checked" : ""}>
        </label>` : ""}
        <button class="content-open" data-id="${item.id}" type="button">
          ${cover}
          <div class="content-copy">
            <p class="content-title">${escapeHtml(item.title || "未命名内容")}</p>
            <div class="content-meta">${platformLabel(item.platform)} · ${escapeHtml(item.author_name || "未知作者")}</div>
          </div>
          <span class="processing-tag content-status-tag processing-${escapeHtml(item.processing_status || "pending")}">${processingStatusLabel(item.processing_status)}</span>
          <div class="metrics">
            <span>赞 ${formatNumber(item.like_count)}</span>
            <span>评 ${formatNumber(item.comment_count)}</span>
            ${item.acquisition_hit_count ? `<span>获客 ${item.acquisition_hit_count}</span>` : ""}
          </div>
        </button>
      </div>`;
  }).join("");
  document.querySelectorAll(".content-open").forEach((row) => {
    row.addEventListener("click", () => loadDetail(Number(row.dataset.id)));
  });
  document.querySelectorAll("[data-select-content]").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      const contentId = Number(checkbox.dataset.selectContent);
      if (checkbox.checked) state.selectedContentIds.add(contentId);
      else state.selectedContentIds.delete(contentId);
      updateBatchToolbar();
    });
  });
  el("contentPagination").hidden = data.total <= state.contentPageSize;
  el("pageInfo").textContent = `第 ${state.contentPage} / ${pageCount} 页`;
  el("previousPage").disabled = state.contentPage <= 1;
  el("nextPage").disabled = state.contentPage >= pageCount;
  el("statusText").textContent = `本地数据库 · ${data.total} 条内容`;
  updateBatchToolbar();
}

async function changeContentPage(page) {
  const nextPage = Math.max(1, Math.min(page, state.contentPageCount));
  if (nextPage === state.contentPage) return;
  state.contentPage = nextPage;
  await loadContents();
  el("contentList").scrollIntoView({ block: "start", behavior: "smooth" });
}

async function loadDetail(contentId) {
  state.selectedId = contentId;
  const item = await api(`/api/local/contents/${contentId}`);
  const imageUrls = item.image_urls?.length ? item.image_urls : (item.cover_url ? [item.cover_url] : []);
  const images = imageUrls.map((url, index) => `
    <div class="media-slide">
      <img src="${escapeHtml(mediaUrl(url))}" alt="图片 ${index + 1}" loading="${index ? "lazy" : "eager"}">
    </div>`).join("");
  const hits = (item.comment_hits || []).map((hit) =>
    `<div class="hit"><strong>${escapeHtml(hit.matched_keyword)}</strong><div>${escapeHtml(hit.comment_text)}</div></div>`
  ).join("");
  const creatorStats = [
    item.author_fans_count != null ? `粉丝 ${formatNumber(item.author_fans_count)}` : "",
    item.author_total_liked_collected != null ? `获赞收藏 ${formatNumber(item.author_total_liked_collected)}` : "",
    item.author_works_count != null ? `作品 ${formatNumber(item.author_works_count)}` : "",
    item.author_ip_location || "",
  ].filter(Boolean).join(" · ");
  const material = item.material_export;
  const materialStatus = material?.status === "synced"
    ? `<div class="material-synced">已加入中央素材库</div>`
    : material?.status === "failed"
      ? `<div class="material-failed">素材同步待重试</div>`
      : "";
  const originalLink = item.canonical_url
    ? `<a href="${escapeHtml(item.canonical_url)}" target="_blank" rel="noreferrer">打开平台原文</a>`
    : `<div class="preview-note">当前内容没有可用的平台原文地址。</div>`;
  el("detailPanel").innerHTML = `
    <button id="closeDetail" class="detail-close" type="button" aria-label="关闭详情" title="关闭详情">×</button>
    ${images ? `
      <div class="media-carousel">
        <div id="mediaTrack" class="media-track">${images}</div>
        ${imageUrls.length > 1 ? `
          <button id="mediaPrev" class="media-nav media-prev" type="button" aria-label="上一张">‹</button>
          <button id="mediaNext" class="media-nav media-next" type="button" aria-label="下一张">›</button>
          <div id="mediaCounter" class="media-counter">1 / ${imageUrls.length}</div>` : ""}
      </div>` : ""}
    <h2>${escapeHtml(item.title || "未命名内容")}</h2>
    <div class="detail-author">${escapeHtml(item.author_name || "未知作者")} · ${platformLabel(item.platform)}</div>
    ${creatorStats ? `<div class="creator-stats">${escapeHtml(creatorStats)}</div>` : ""}
    ${item.author_signature ? `<div class="creator-signature">${escapeHtml(item.author_signature)}</div>` : ""}
    ${materialStatus}
    <div class="detail-processing">
      状态：<span class="processing-tag processing-${escapeHtml(item.processing_status || "pending")}">${processingStatusLabel(item.processing_status)}</span>
    </div>
    <div class="detail-actions">
      <button id="acquisitionCheck" class="secondary" type="button">查获客信号</button>
      <button id="addMaterial" type="button">${material?.status === "synced" ? "更新素材" : "加入素材库"}</button>
      <button id="discardContent" class="danger-outline" type="button">${item.processing_status === "discarded" ? "已废弃" : "废弃"}</button>
    </div>
    <div class="detail-body">${escapeHtml(item.body_text || "尚未采集正文详情。")}</div>
    <div class="detail-section"><h3>获客信号 ${item.acquisition_hit_count || 0}</h3>${hits || "暂无命中"}</div>
    ${originalLink}
  `;
  el("closeDetail").addEventListener("click", closeDetail);
  el("acquisitionCheck").addEventListener("click", () => checkAcquisition(contentId));
  el("addMaterial").addEventListener("click", () => openMaterialDialog(item));
  el("discardContent").addEventListener("click", () => updateContentStatus([contentId], "discarded", true));
  setupMediaCarousel(imageUrls.length);
  await loadContents();
  if (!item.detail_fetched_at) {
    await fetchContentDetail(contentId);
  }
}

async function updateContentStatus(contentIds, status, reloadDetail = false) {
  await api("/api/local/contents/batch-status", {
    method: "POST",
    body: JSON.stringify({ content_ids: contentIds, status }),
  });
  contentIds.forEach((contentId) => state.selectedContentIds.delete(contentId));
  toast(status === "discarded" ? `已废弃 ${contentIds.length} 条` : `已设为待处理 ${contentIds.length} 条`);
  await loadContents();
  if (reloadDetail && state.selectedId) await loadDetail(state.selectedId);
}

async function addSelectedToMaterialLibrary(contentIds) {
  await loadCentralSession();
  if (!state.centralSession?.authenticated) {
    state.pendingBulkMaterialIds = [...contentIds];
    el("loginDialog").showModal();
    return;
  }
  let completed = 0;
  for (const contentId of contentIds) {
    const result = await api(`/api/local/contents/${contentId}/material`, {
      method: "POST",
      body: JSON.stringify({
        library_type: "uncategorized",
        rating: null,
        material_tags: [],
        note: null,
        selected_reason: "本地工作台批量精选",
      }),
    });
    if (result.status === "synced" || result.status === "failed") completed += 1;
  }
  contentIds.forEach((contentId) => state.selectedContentIds.delete(contentId));
  toast(`已提交 ${completed} 条到素材库`);
  await loadContents();
  if (state.selectedId && contentIds.includes(state.selectedId)) await loadDetail(state.selectedId);
}

function setupMediaCarousel(imageCount) {
  if (imageCount <= 1) return;
  const track = el("mediaTrack");
  const counter = el("mediaCounter");
  const updateCounter = () => {
    const index = Math.round(track.scrollLeft / Math.max(track.clientWidth, 1));
    counter.textContent = `${Math.min(index + 1, imageCount)} / ${imageCount}`;
  };
  const move = (direction) => track.scrollBy({ left: direction * track.clientWidth, behavior: "smooth" });
  el("mediaPrev").addEventListener("click", () => move(-1));
  el("mediaNext").addEventListener("click", () => move(1));
  track.addEventListener("scroll", updateCounter, { passive: true });
}

async function fetchContentDetail(contentId) {
  toast("正在补抓正文详情…");
  const result = await api(`/api/local/contents/${contentId}/detail-fetch`, {
    method: "POST",
    body: "{}",
  });
  if (!result.task_id) return;
  const finalStatus = await pollTask(result.task_id);
  if (finalStatus !== "success" || state.selectedId !== contentId) return;
  const refreshed = await api(`/api/local/contents/${contentId}`);
  if (refreshed.detail_fetched_at) {
    await loadDetail(contentId);
  }
}

async function checkAcquisition(contentId) {
  const button = el("acquisitionCheck");
  button.disabled = true;
  try {
    const result = await api(`/api/local/contents/${contentId}/acquisition-check`, {
      method: "POST",
      body: JSON.stringify({ max_comments: 30 }),
    });
    toast("评论采集已开始");
    await pollTask(result.task_id);
    await loadDetail(contentId);
  } catch (error) {
    toast(error.message);
  } finally {
    button.disabled = false;
  }
}

async function openMaterialDialog(item) {
  await loadCentralSession();
  if (!state.centralSession?.authenticated) {
    state.pendingMaterialItem = item;
    el("loginDialog").showModal();
    return;
  }
  state.pendingMaterialItem = null;
  showMaterialDialog(item);
}

function showMaterialDialog(item) {
  const material = item.material_export || {};
  el("materialContentId").value = item.id;
  el("libraryType").value = material.library_type || (item.acquisition_hit_count ? "lead" : "uncategorized");
  el("materialRating").value = material.rating || "";
  el("materialTags").value = (material.material_tags || []).join(", ");
  el("materialNote").value = material.note || "";
  el("materialDialog").showModal();
}

function closeDetail() {
  state.selectedId = null;
  el("detailPanel").innerHTML = `
    <div class="detail-placeholder">
      <strong>选择一条内容</strong>
      <span>查看正文、图片和获客信号。</span>
    </div>`;
  loadContents().catch((error) => toast(error.message));
}

async function loadTasks() {
  const data = await api("/api/local/tasks?limit=8");
  el("taskList").innerHTML = data.items.map((task) => {
    const effectiveStatus = task.status === "active" && task.latest_run?.status === "running"
      ? "running"
      : task.status;
    const isFinished = ["success", "failed", "paused"].includes(effectiveStatus);
    let actions = "";
    if (effectiveStatus === "running") {
      actions = `
        <button type="button" data-task-action="pause" data-task-id="${task.id}">暂停</button>
        <button type="button" class="task-cancel" data-task-action="cancel" data-task-id="${task.id}">取消</button>`;
    } else if (effectiveStatus === "queued") {
      actions = `<button type="button" class="task-cancel" data-task-action="cancel" data-task-id="${task.id}">取消</button>`;
    } else if (effectiveStatus === "paused") {
      actions = `<button type="button" data-task-action="resume" data-task-id="${task.id}">继续运行</button>`;
    } else if (effectiveStatus === "success" || effectiveStatus === "failed") {
      actions = `<button type="button" data-task-action="run" data-task-id="${task.id}">重新运行</button>`;
    } else if (effectiveStatus === "active") {
      actions = `
        <button type="button" data-task-action="run" data-task-id="${task.id}">立即运行</button>
        <button type="button" data-task-action="pause" data-task-id="${task.id}">暂停</button>`;
    }
    return `
    <div class="task-item ${isFinished ? "task-item-muted" : ""}">
      <div class="task-head">
        <strong>${escapeHtml(task.target || task.task_type)}</strong>
        ${task.new_content_count ? `<span class="unread-count">${task.new_content_count} 新</span>` : ""}
      </div>
      <span class="status-${escapeHtml(effectiveStatus)}">${statusLabel(effectiveStatus)}</span>
      <div class="task-actions">${actions}</div>
    </div>
  `}).join("") || `<span>暂无任务</span>`;
  document.querySelectorAll("[data-task-action]").forEach((button) => {
    button.addEventListener("click", () => taskAction(button.dataset.taskId, button.dataset.taskAction));
  });
}

async function loadCentralSession() {
  state.centralSession = await api("/api/local/central-session");
  el("centralServerUrl").value = state.centralSession.center_url || "";
  const user = state.centralSession.user;
  el("centralSessionButton").textContent = state.centralSession.authenticated
    ? user?.display_name || user?.username || "已登录"
    : "登录中央";
}

async function taskAction(taskId, action) {
  await api(`/api/local/tasks/${taskId}/${action}`, { method: "POST", body: "{}" });
  await loadTasks();
  const messages = {
    run: "任务已重新运行",
    resume: "任务已继续运行",
    pause: "任务已暂停",
    cancel: "任务已取消",
  };
  if (messages[action]) toast(messages[action]);
}

async function pollTask(taskId) {
  window.clearTimeout(state.pollTimer);
  const task = await api(`/api/local/tasks/${taskId}`);
  const effectiveStatus = task.status === "active" && task.latest_run
    ? task.latest_run.status
    : task.status;
  el("activeTask").hidden = false;
  const count = task.latest_run?.item_count || 0;
  el("activeTask").textContent = `“${task.target || task.task_type}” ${statusLabel(effectiveStatus)}${effectiveStatus === "success" ? `，采集 ${count} 条` : ""}`;
  await loadTasks();
  if (effectiveStatus === "success") {
    el("searchButton").disabled = false;
    state.activeTaskId = null;
    await loadContents();
    return effectiveStatus;
  }
  if (effectiveStatus === "failed") {
    el("searchButton").disabled = false;
    state.activeTaskId = null;
    const message = task.latest_run?.error_summary_json
      ? JSON.parse(task.latest_run.error_summary_json).message
      : "采集失败";
    toast(message || "采集失败");
    return effectiveStatus;
  }
  if (effectiveStatus === "paused") {
    el("searchButton").disabled = false;
    state.activeTaskId = null;
    toast("任务已暂停");
    return effectiveStatus;
  }
  await new Promise((resolve) => {
    state.pollTimer = window.setTimeout(resolve, 1200);
  });
  return pollTask(taskId);
}

el("searchForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const keyword = el("keyword").value.trim();
  if (!keyword) return;
  el("searchButton").disabled = true;
  state.contentPage = 1;
  try {
    const task = await api("/api/local/search", {
      method: "POST",
      body: JSON.stringify({ keyword, max_items: Number(el("maxItems").value), platform: "xhs" }),
    });
    state.activeTaskId = task.task_id;
    await pollTask(task.task_id);
  } catch (error) {
    el("searchButton").disabled = false;
    toast(error.message);
  }
});

el("monitorForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const target = el("creatorTarget").value.trim();
  if (!target) return;
  try {
    const task = await api("/api/local/tasks", {
      method: "POST",
      body: JSON.stringify({
        task_type: "creator_monitor",
        target,
        schedule_seconds: Number(el("monitorInterval").value),
        max_items: 20,
      }),
    });
    el("creatorTarget").value = "";
    await loadTasks();
    await pollTask(task.task_id);
  } catch (error) {
    toast(error.message);
  }
});

el("refreshRecommend").addEventListener("click", async () => {
  el("refreshRecommend").disabled = true;
  try {
    const task = await api("/api/local/tasks", {
      method: "POST",
      body: JSON.stringify({ task_type: "recommend", max_items: 30 }),
    });
    await loadTasks();
    await pollTask(task.task_id);
  } catch (error) {
    toast(error.message);
  } finally {
    el("refreshRecommend").disabled = false;
  }
});

el("scheduleRecommend").addEventListener("click", async () => {
  el("scheduleRecommend").disabled = true;
  try {
    const task = await api("/api/local/tasks", {
      method: "POST",
      body: JSON.stringify({
        task_type: "recommend",
        max_items: 30,
        schedule_seconds: Number(el("recommendInterval").value),
      }),
    });
    await loadTasks();
    await pollTask(task.task_id);
  } catch (error) {
    toast(error.message);
  } finally {
    el("scheduleRecommend").disabled = false;
  }
});

el("centralSessionButton").addEventListener("click", async () => {
  if (state.centralSession?.authenticated) {
    await api("/api/local/central-session/logout", { method: "POST", body: "{}" });
    await loadCentralSession();
    toast("已退出中央素材库");
  } else {
    el("loginDialog").showModal();
  }
});

el("loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const password = el("centralPassword").value;
  try {
    state.centralSession = await api("/api/local/central-session/login", {
      method: "POST",
      body: JSON.stringify({
        center_url: el("centralServerUrl").value.trim(),
        username: el("centralUsername").value.trim(),
        password,
      }),
    });
    el("centralPassword").value = "";
    el("loginDialog").close();
    await loadCentralSession();
    toast("中央素材库登录成功");
    const pendingItem = state.pendingMaterialItem;
    const pendingBulkIds = [...state.pendingBulkMaterialIds];
    state.pendingMaterialItem = null;
    state.pendingBulkMaterialIds = [];
    if (pendingItem) showMaterialDialog(pendingItem);
    else if (pendingBulkIds.length) await addSelectedToMaterialLibrary(pendingBulkIds);
  } catch (error) {
    el("centralPassword").value = "";
    toast(error.message);
  }
});

el("materialForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const contentId = Number(el("materialContentId").value);
  const tags = el("materialTags").value.split(/[,，]/).map((item) => item.trim()).filter(Boolean);
  const result = await api(`/api/local/contents/${contentId}/material`, {
    method: "POST",
    body: JSON.stringify({
      library_type: el("libraryType").value,
      rating: el("materialRating").value || null,
      material_tags: tags,
      note: el("materialNote").value.trim() || null,
      selected_reason: "本地工作台人工精选",
    }),
  });
  el("materialDialog").close();
  toast(result.status === "synced" ? "已加入中央素材库" : "收藏意图已保存，等待重试");
  await loadDetail(contentId);
});

document.querySelectorAll("[data-close-dialog]").forEach((button) => {
  button.addEventListener("click", () => {
    if (button.dataset.closeDialog === "loginDialog") {
      state.pendingMaterialItem = null;
      state.pendingBulkMaterialIds = [];
    }
    el(button.dataset.closeDialog).close();
  });
});

el("previousPage").addEventListener("click", () => changeContentPage(state.contentPage - 1).catch((error) => toast(error.message)));
el("nextPage").addEventListener("click", () => changeContentPage(state.contentPage + 1).catch((error) => toast(error.message)));
el("toggleMultiSelect").addEventListener("click", () => {
  state.multiSelectEnabled = !state.multiSelectEnabled;
  if (!state.multiSelectEnabled) state.selectedContentIds.clear();
  loadContents().catch((error) => toast(error.message));
});
el("selectPage").addEventListener("change", () => {
  state.visibleContentIds.forEach((contentId) => {
    if (el("selectPage").checked) state.selectedContentIds.add(contentId);
    else state.selectedContentIds.delete(contentId);
  });
  loadContents().catch((error) => toast(error.message));
});
el("batchPending").addEventListener("click", () => updateContentStatus([...state.selectedContentIds], "pending").catch((error) => toast(error.message)));
el("batchDiscard").addEventListener("click", () => updateContentStatus([...state.selectedContentIds], "discarded").catch((error) => toast(error.message)));
el("batchMaterial").addEventListener("click", () => addSelectedToMaterialLibrary([...state.selectedContentIds]).catch((error) => toast(error.message)));
el("applyFilters").addEventListener("click", () => {
  state.contentPage = 1;
  loadContents().catch((error) => toast(error.message));
});
el("refreshButton").addEventListener("click", () => Promise.all([loadContents(), loadTasks()]).catch((error) => toast(error.message)));
el("localKeyword").addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    state.contentPage = 1;
    loadContents().catch((error) => toast(error.message));
  }
});

establishBridgeSession()
  .then(() => Promise.all([loadContents(), loadTasks(), loadCentralSession()]))
  .catch((error) => toast(error.message));
