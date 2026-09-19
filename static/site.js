// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
(() => {
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const toast = document.getElementById("toast");
  const notify = (message, error = false) => {
    if (!toast) return;
    toast.textContent = message;
    toast.className = error ? "show error" : "show";
    clearTimeout(notify.timer);
    notify.timer = setTimeout(() => { toast.className = ""; }, 3500);
  };
  const api = async (url, options = {}) => {
    const response = await fetch(url, {
      credentials: "same-origin",
      headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf, ...(options.headers || {})},
      ...options
    });
    const data = await response.json().catch(() => ({error: response.statusText}));
    if (!response.ok) throw new Error(data.error || "Request failed");
    return data;
  };

  if ("serviceWorker" in navigator) {
    addEventListener("load", () => {
      const manifest = document.querySelector('link[rel="manifest"]')?.href;
      const version = manifest ? new URL(manifest).searchParams.get("v") || "1" : "1";
      navigator.serviceWorker.register(`/service-worker.js?v=${version}`).catch(() => {});
    });
  }

  const navToggle = document.getElementById("navToggle");
  const siteNav = document.getElementById("siteNav");
  const setNavOpen = open => {
    if (!navToggle || !siteNav) return;
    navToggle.setAttribute("aria-expanded", String(open));
    siteNav.classList.toggle("open", open);
  };
  navToggle?.addEventListener("click", () => setNavOpen(navToggle.getAttribute("aria-expanded") !== "true"));
  siteNav?.addEventListener("click", event => {
    if (event.target.closest("a,button")) setNavOpen(false);
  });

  const guide = document.getElementById("welcomeGuide");
  const guideCloseButton = document.getElementById("closeGuide");
  let guideReturnFocus = null;
  const guideFocusable = () => guide ? [...guide.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])')] : [];
  const closeGuide = () => {
    if (!guide) return;
    clearTimeout(openGuide.timer);
    guide.classList.remove("show");
    setTimeout(() => {
      guide.hidden = true;
      guideReturnFocus?.focus();
      guideReturnFocus = null;
    }, 180);
  };
  const openGuide = () => {
    if (!guide) return;
    guideReturnFocus = navToggle && matchMedia("(max-width: 820px)").matches ? navToggle : document.activeElement;
    guide.hidden = false;
    requestAnimationFrame(() => {
      guide.classList.add("show");
      guideCloseButton?.focus();
    });
  };
  document.getElementById("guideButton")?.addEventListener("click", openGuide);
  guideCloseButton?.addEventListener("click", closeGuide);
  if (guide) {
    guide.addEventListener("click", event => {
      if (event.target === guide) closeGuide();
    });
    guide.addEventListener("keydown", event => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeGuide();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = guideFocusable();
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });
    try {
      if (!localStorage.getItem("an3-welcome-v1")) {
        localStorage.setItem("an3-welcome-v1", "1");
        setTimeout(openGuide, 120);
      }
    } catch (_) {}
  }

  addEventListener("keydown", event => {
    if (event.key !== "Escape") return;
    if (guide && !guide.hidden) closeGuide();
    else if (navToggle?.getAttribute("aria-expanded") === "true") {
      setNavOpen(false);
      navToggle.focus();
    }
  });

  document.querySelector('[data-action="logout"]')?.addEventListener("click", async () => {
    try { await api("/api/logout", {method: "POST", body: "{}"}); location.href = "/"; }
    catch (error) { notify(error.message, true); }
  });

  const authForm = document.getElementById("authForm");
  authForm?.addEventListener("submit", async event => {
    event.preventDefault();
    if (authForm.classList.contains("is-loading")) return;
    const form = new FormData(authForm);
    const kind = authForm.dataset.kind;
    const payload = Object.fromEntries(form.entries());
    const errorBox = document.getElementById("formError");
    const submit = authForm.querySelector('button[type="submit"]');
    const progress = document.getElementById("authProgress");
    const progressLabel = document.getElementById("authProgressLabel");
    const fields = [...authForm.querySelectorAll("input:not([type=hidden])")];
    const vietnamese = document.documentElement.lang !== "en";
    errorBox.textContent = "";
    errorBox.hidden = true;
    fields.forEach(field => field.removeAttribute("aria-invalid"));
    authForm.classList.add("is-loading");
    authForm.setAttribute("aria-busy", "true");
    submit.disabled = true;
    progress.hidden = false;
    progressLabel.textContent = kind === "register"
      ? (vietnamese ? "Đang tạo tài khoản..." : "Creating account...")
      : (vietnamese ? "Đang đăng nhập..." : "Signing in...");
    try {
      const data = await api(`/api/${kind}`, {method: "POST", body: JSON.stringify(payload)});
      progress.classList.add("complete");
      location.href = data.redirect || "/";
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.hidden = false;
      fields.forEach(field => field.setAttribute("aria-invalid", "true"));
      authForm.classList.remove("is-loading");
      authForm.removeAttribute("aria-busy");
      submit.disabled = false;
      progress.hidden = true;
      progress.classList.remove("complete");
      errorBox.focus();
    }
  });
  authForm?.querySelectorAll("input:not([type=hidden])").forEach(field => field.addEventListener("input", () => {
    field.removeAttribute("aria-invalid");
    const errorBox = document.getElementById("formError");
    if (errorBox) { errorBox.hidden = true; errorBox.textContent = ""; }
  }));

  const displayNameForm = document.getElementById("displayNameForm");
  displayNameForm?.addEventListener("submit", async event => {
    event.preventDefault();
    const status = document.getElementById("displayNameStatus");
    try {
      const data = await api("/api/account/display-name", {method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(displayNameForm).entries()))});
      document.querySelector(".site-header .account")?.replaceChildren(document.createTextNode(data.display_name));
      if (status) status.textContent = document.documentElement.lang === "en" ? "Nickname saved." : "Đã lưu nickname.";
      notify(document.documentElement.lang === "en" ? "Nickname saved" : "Đã lưu nickname");
    } catch (error) { if (status) status.textContent = error.message; notify(error.message, true); }
  });

  const search = document.getElementById("gameSearch");
  const clearSearch = document.getElementById("clearSearch");
  const resetLibrary = document.getElementById("resetLibrary");
  const libraryStatus = document.getElementById("libraryStatus");
  const libraryNoResults = document.getElementById("libraryNoResults");
  const libraryCards = [...document.querySelectorAll("#gameGrid .game-card")];
  const librarySections = [...document.querySelectorAll("#gameGrid .game-system-section")];
  const librarySearchText = new WeakMap();
  libraryCards.forEach(card => librarySearchText.set(card, card.textContent.toLocaleLowerCase()));
  let activeSystem = "all";
  const filterLibrary = () => {
    const query = search?.value.trim().toLocaleLowerCase() || "";
    const visibleGames = new Set();
    libraryCards.forEach(card => {
      const matchesSystem = activeSystem === "all" || card.dataset.system === activeSystem;
      const matchesSearch = !query || (librarySearchText.get(card) || "").includes(query);
      card.hidden = !(matchesSystem && matchesSearch);
      if (!card.hidden) visibleGames.add(card.dataset.gameSlug || card.textContent);
    });
    librarySections.forEach(section => {
      section.hidden = !section.querySelector(".game-card:not([hidden])");
    });
    if (clearSearch) clearSearch.hidden = !query;
    if (libraryNoResults) libraryNoResults.hidden = visibleGames.size > 0;
    if (libraryStatus) {
      const vietnamese = document.documentElement.lang !== "en";
      libraryStatus.textContent = vietnamese
        ? `${visibleGames.size} trò chơi phù hợp`
        : `${visibleGames.size} matching ${visibleGames.size === 1 ? "game" : "games"}`;
    }
  };
  let libraryFilterFrame = 0;
  const scheduleLibraryFilter = () => {
    if (libraryFilterFrame) return;
    libraryFilterFrame = requestAnimationFrame(() => {
      libraryFilterFrame = 0;
      filterLibrary();
    });
  };
  search?.addEventListener("input", scheduleLibraryFilter);
  document.querySelectorAll("[data-system-filter]").forEach(button => button.addEventListener("click", () => {
    activeSystem = button.dataset.systemFilter || "all";
    document.querySelectorAll("[data-system-filter]").forEach(item => {
      const selected = item === button;
      item.classList.toggle("active", selected);
      item.setAttribute("aria-pressed", String(selected));
    });
    filterLibrary();
  }));
  clearSearch?.addEventListener("click", () => {
    search.value = "";
    filterLibrary();
    search.focus();
  });
  const resetLibraryState = () => {
    activeSystem = "all";
    if (search) search.value = "";
    document.querySelectorAll("[data-system-filter]").forEach(item => {
      const selected = item.dataset.systemFilter === "all";
      item.classList.toggle("active", selected);
      item.setAttribute("aria-pressed", String(selected));
    });
    filterLibrary();
    search?.focus();
  };
  resetLibrary?.addEventListener("click", resetLibraryState);
  document.querySelectorAll("[data-library-reset]").forEach(button => button.addEventListener("click", resetLibraryState));
  const gameGrid = document.getElementById("gameGrid");
  const libraryRefreshKey = "an3-library-refresh-state-v1";
  let libraryRestore = null;
  if (gameGrid) {
    try {
      libraryRestore = JSON.parse(sessionStorage.getItem(libraryRefreshKey) || "null");
      sessionStorage.removeItem(libraryRefreshKey);
    } catch (_) {}
  }
  if (libraryRestore && search) {
    search.value = String(libraryRestore.query || "");
    activeSystem = String(libraryRestore.system || "all");
    document.querySelectorAll("[data-system-filter]").forEach(item => {
      const selected = item.dataset.systemFilter === activeSystem;
      item.classList.toggle("active", selected);
      item.setAttribute("aria-pressed", String(selected));
    });
  }
  if (search) filterLibrary();
  if (libraryRestore && Number.isFinite(Number(libraryRestore.scrollY))) {
    requestAnimationFrame(() => scrollTo({top: Math.max(0, Number(libraryRestore.scrollY)), behavior: "auto"}));
  }

  if (gameGrid) {
    const currentVersion = gameGrid.dataset.libraryVersion;
    let libraryUpdateAvailable = false;
    let libraryVersionTimer = null;
    const showLibraryUpdate = () => {
      if (document.getElementById("libraryUpdateNotice")) return;
      const notice = document.createElement("aside");
      const message = document.createElement("span");
      const refresh = document.createElement("button");
      const english = document.documentElement.lang === "en";
      notice.id = "libraryUpdateNotice";
      notice.className = "library-update-notice";
      notice.setAttribute("role", "status");
      message.textContent = english ? "New library content is available." : "Có nội dung thư viện mới.";
      refresh.type = "button";
      refresh.className = "button";
      refresh.textContent = english ? "Refresh when ready" : "Làm mới khi sẵn sàng";
      refresh.addEventListener("click", () => {
        try {
          sessionStorage.setItem(libraryRefreshKey, JSON.stringify({
            query: search?.value || "",
            system: activeSystem,
            scrollY: scrollY
          }));
        } catch (_) {}
        location.reload();
      });
      notice.append(message, refresh);
      const target = document.querySelector(".library-head") || gameGrid.parentElement;
      target?.prepend(notice);
    };
    const checkLibraryVersion = async () => {
      if (document.hidden || libraryUpdateAvailable) return;
      try {
        const response = await fetch("/api/library-version", {cache: "no-store"});
        const data = await response.json();
        if (response.ok && data.version && data.version !== currentVersion) {
          libraryUpdateAvailable = true;
          showLibraryUpdate();
        }
      } catch (_) {}
    };
    const stopLibraryVersionPolling = () => {
      if (libraryVersionTimer) clearTimeout(libraryVersionTimer);
      libraryVersionTimer = null;
    };
    const scheduleLibraryVersionCheck = (delay = 60000) => {
      stopLibraryVersionPolling();
      if (document.hidden || libraryUpdateAvailable) return;
      libraryVersionTimer = setTimeout(async () => {
        await checkLibraryVersion();
        scheduleLibraryVersionCheck();
      }, delay);
    };
    const onLibraryVisibilityChange = () => {
      if (document.hidden) {
        stopLibraryVersionPolling();
        return;
      }
      checkLibraryVersion().finally(() => scheduleLibraryVersionCheck());
    };
    scheduleLibraryVersionCheck();
    addEventListener("visibilitychange", onLibraryVisibilityChange);
    addEventListener("pagehide", () => {
      stopLibraryVersionPolling();
      removeEventListener("visibilitychange", onLibraryVisibilityChange);
    }, {once: true});
  }

  const monitoring = document.getElementById("adminMonitoring");
  if (monitoring) {
    const english = document.documentElement.lang === "en";
    const unavailable = english ? "Unavailable" : "Không khả dụng";
    const labels = {
      normal: english ? "Normal" : "Bình thường",
      warning: english ? "Warning" : "Cảnh báo",
      unavailable,
      error: english ? "Error" : "Lỗi",
      stale: english ? "Stale data" : "Dữ liệu cũ",
      loading: english ? "Loading…" : "Đang tải…"
    };
    let monitorTimer = null;
    let freshnessTimer = null;
    let requestController = null;
    let requestInFlight = false;
    let stopped = false;
    let failures = 0;
    let lastSuccessAt = 0;
    const finiteNumber = value => {
      if (value === null || value === undefined || value === "") return null;
      const number = Number(value);
      return Number.isFinite(number) ? number : null;
    };
    const formatBytes = value => {
      const units = ["B", "KB", "MB", "GB", "TB"];
      let number = finiteNumber(value);
      if (number === null) return unavailable;
      let index = 0;
      while (number >= 1024 && index < units.length - 1) {
        number /= 1024;
        index += 1;
      }
      return number.toFixed(index ? 1 : 0) + " " + units[index];
    };
    const formatUptime = seconds => {
      const number = finiteNumber(seconds);
      if (number === null) return unavailable;
      const total = Math.max(0, Math.floor(number));
      const days = Math.floor(total / 86400);
      const hours = Math.floor(total % 86400 / 3600);
      const minutes = Math.floor(total % 3600 / 60);
      return english
        ? String(days) + "d " + String(hours) + "h " + String(minutes) + "m"
        : String(days) + " ngày " + String(hours) + " giờ " + String(minutes) + " phút";
    };
    const setCard = (name, value, status, statusText = "") => {
      const card = monitoring.querySelector('[data-metric-card="' + name + '"]');
      if (!card) return;
      card.querySelector("[data-metric-value]").textContent = value;
      card.querySelector("[data-metric-status]").textContent = statusText || labels[status] || labels.error;
      card.dataset.status = status;
    };
    const updateFreshness = () => {
      const updated = document.getElementById("monitoringUpdated");
      if (!updated || !lastSuccessAt) return;
      const seconds = Math.max(0, Math.floor((Date.now() - lastSuccessAt) / 1000));
      if (seconds < 5) {
        updated.textContent = english ? "Updated just now" : "Vừa cập nhật";
      } else {
        updated.textContent = english
          ? "Updated " + String(seconds) + "s ago"
          : "Cập nhật " + String(seconds) + " giây trước";
      }
    };
    const startFreshness = () => {
      clearInterval(freshnessTimer);
      freshnessTimer = setInterval(updateFreshness, 1000);
      updateFreshness();
    };
    const scheduleMonitoring = delay => {
      clearTimeout(monitorTimer);
      if (!stopped && !document.hidden) monitorTimer = setTimeout(refreshMonitoring, delay);
    };
    const markMonitoringFailure = () => {
      const stale = Boolean(lastSuccessAt);
      monitoring.querySelectorAll("[data-metric-card]").forEach(card => {
        card.dataset.status = stale ? "stale" : "error";
        card.querySelector("[data-metric-status]").textContent = stale ? labels.stale : labels.error;
      });
      if (stale) updateFreshness();
      else {
        const updated = document.getElementById("monitoringUpdated");
        if (updated) updated.textContent = labels.error;
      }
    };
    const formatPercent = metric => {
      const number = finiteNumber(metric?.used_percent);
      return number === null ? unavailable : number.toFixed(1) + "%";
    };
    const refreshMonitoring = async () => {
      if (stopped || document.hidden || requestInFlight) return;
      requestInFlight = true;
      requestController = new AbortController();
      const timeout = setTimeout(() => requestController?.abort(), 6000);
      try {
        const response = await fetch("/api/admin/system-metrics", {
          credentials: "same-origin",
          cache: "no-store",
          signal: requestController.signal
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data || typeof data !== "object") throw new Error("metrics unavailable");
        setCard("cpu", formatPercent(data.cpu), data.cpu?.status || "unavailable");
        setCard("ram", data.ram?.used_percent == null
          ? unavailable
          : formatBytes(data.ram.used_bytes) + " / " + formatBytes(data.ram.total_bytes) + " (" + formatPercent(data.ram) + ")",
        data.ram?.status || "unavailable");
        setCard("disk", data.disk?.used_percent == null
          ? unavailable
          : formatBytes(data.disk.used_bytes) + " / " + formatBytes(data.disk.total_bytes) + " (" + formatPercent(data.disk) + ")",
        data.disk?.status || "unavailable");
        const temperature = finiteNumber(data.temperature?.celsius);
        const power = finiteNumber(data.power?.watts);
        setCard("temperature", temperature === null ? unavailable : temperature.toFixed(1) + " °C", data.temperature?.status || "unavailable");
        setCard("power", power === null ? unavailable : power.toFixed(2) + " W", data.power?.status || "unavailable");
        setCard("uptime", formatUptime(data.uptime_seconds), data.uptime_seconds == null ? "unavailable" : "normal");
        setCard("app", data.app?.ok ? (english ? "Healthy" : "Bình thường") : (english ? "Unhealthy" : "Lỗi"), data.app?.status || "error");
        const generatedAt = finiteNumber(data.updated_at);
        lastSuccessAt = generatedAt === null ? Date.now() : generatedAt * 1000;
        failures = 0;
        updateFreshness();
      } catch (_) {
        failures = Math.min(failures + 1, 3);
        markMonitoringFailure();
      } finally {
        clearTimeout(timeout);
        requestController = null;
        requestInFlight = false;
        const delay = Math.min(30000, 7000 * (2 ** failures));
        scheduleMonitoring(delay);
      }
    };
    let begun = false;
    const beginMonitoring = () => {
      if (begun) return;
      begun = true;
      startFreshness();
      refreshMonitoring();
    };
    // Server status is a collapsed secondary panel. Do not poll until the
    // administrator actually opens it.
    if (monitoring.tagName === "DETAILS" && !monitoring.open) {
      monitoring.addEventListener("toggle", () => {
        if (monitoring.open) beginMonitoring();
      }, {once: true});
    } else {
      beginMonitoring();
    }
    document.addEventListener("visibilitychange", () => {
      if (!begun) return;
      if (document.hidden) {
        clearTimeout(monitorTimer);
        clearInterval(freshnessTimer);
        requestController?.abort();
      } else {
        startFreshness();
        refreshMonitoring();
      }
    });
    addEventListener("pagehide", () => {
      stopped = true;
      clearTimeout(monitorTimer);
      clearInterval(freshnessTimer);
      requestController?.abort();
    }, {once: true});
  }

  document.querySelectorAll("[data-rate]").forEach(button => button.addEventListener("click", async () => {
    const box = button.closest("[data-game]");
    if (!csrf) { location.href = "/login"; return; }
    try {
      const value = Number(button.dataset.rate);
      await api(`/api/games/${box.dataset.game}/rating`, {method: "POST", body: JSON.stringify({value})});
      box.querySelectorAll("[data-rate]").forEach(star => {
        const selected = Number(star.dataset.rate) <= value;
        star.classList.toggle("active", selected);
        star.setAttribute("aria-pressed", String(selected));
      });
      notify("Đã lưu đánh giá");
    } catch (error) { notify(error.message, true); }
  }));

  document.getElementById("favoriteButton")?.addEventListener("click", async event => {
    const button = event.currentTarget;
    try {
      const data = await api(`/api/games/${button.dataset.game}/favorite`, {method: "POST", body: "{}"});
      button.setAttribute("aria-pressed", String(data.favorited));
      button.textContent = data.favorited
        ? (document.documentElement.lang === "en" ? "Remove favorite" : "Bỏ yêu thích")
        : (document.documentElement.lang === "en" ? "Add favorite" : "Thêm yêu thích");
      notify(data.favorited ? (document.documentElement.lang === "en" ? "Added to favorites" : "Đã thêm yêu thích") : (document.documentElement.lang === "en" ? "Removed from favorites" : "Đã bỏ yêu thích"));
    } catch (error) { notify(error.message, true); }
  });

  const commentForm = document.getElementById("commentForm");
  commentForm?.addEventListener("submit", async event => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(commentForm).entries());
    try {
      await api(`/api/games/${commentForm.dataset.game}/comments`, {method: "POST", body: JSON.stringify(values)});
      location.reload();
    } catch (error) { notify(error.message, true); }
  });

  const reportForm = document.getElementById("reportForm");
  reportForm?.addEventListener("submit", async event => {
    event.preventDefault();
    try {
      await api(`/api/games/${reportForm.dataset.game}/reports`, {method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(reportForm).entries()))});
      reportForm.reset();
      notify(document.documentElement.lang === "en" ? "Issue report sent" : "Đã gửi báo lỗi");
    } catch (error) { notify(error.message, true); }
  });

  document.querySelectorAll("[data-comment-delete]").forEach(button => button.addEventListener("click", async () => {
    if (!confirm("Delete this comment?")) return;
    try {
      await api(`/admin/api/comments/${button.dataset.commentDelete}/delete`, {method: "POST", body: "{}"});
      button.closest(".comment").remove();
    } catch (error) { notify(error.message, true); }
  }));

  document.querySelectorAll("[data-delete-game]").forEach(button => button.addEventListener("click", async event => {
    if (!confirm("Delete this game, cover, comments and ratings?")) return;
    try {
      await api(`/admin/api/games/${event.currentTarget.dataset.deleteGame}`, {method: "DELETE", body: null});
      const row = event.currentTarget.closest("tr");
      if (row) row.remove(); else location.href = "/admin";
    } catch (error) { notify(error.message, true); }
  }));

  const batchStatusForm = document.getElementById("batchStatusForm");
  const batchPreview = document.getElementById("batchPreview");
  const batchConfirmation = document.getElementById("batchConfirmation");
  const batchApply = document.getElementById("batchApply");
  let batchPlan = null;
  const batchIds = () => [...document.querySelectorAll("[data-batch-game]:checked")].map(input => Number(input.value));
  const clearBatchPlan = () => {
    batchPlan = null;
    if (batchPreview) batchPreview.textContent = "";
    if (batchConfirmation) { batchConfirmation.value = ""; batchConfirmation.disabled = true; batchConfirmation.closest("label")?.setAttribute("hidden", ""); }
    if (batchApply) batchApply.disabled = true;
  };
  document.querySelectorAll("[data-batch-game]").forEach(input => input.addEventListener("change", clearBatchPlan));
  batchStatusForm?.querySelector("select[name=status]")?.addEventListener("change", clearBatchPlan);
  batchStatusForm?.addEventListener("submit", async event => {
    event.preventDefault();
    const ids = batchIds();
    const status = new FormData(batchStatusForm).get("status");
    if (!ids.length) { batchPreview.textContent = "Select at least one game."; return; }
    try {
      const preview = await api("/admin/api/games/batch-status/preview", {method: "POST", body: JSON.stringify({ids, status})});
      batchPlan = {ids: [...ids].sort((a, b) => a - b), status, confirmation: preview.confirmation};
      batchPreview.textContent = `${preview.games.length} game(s) will become ${preview.target_label}. Type: ${preview.confirmation}`;
      batchConfirmation.closest("label")?.removeAttribute("hidden");
      batchConfirmation.disabled = false;
      batchConfirmation.focus();
    } catch (error) { clearBatchPlan(); batchPreview.textContent = error.message; notify(error.message, true); }
  });
  batchConfirmation?.addEventListener("input", () => { batchApply.disabled = !batchPlan || batchConfirmation.value !== batchPlan.confirmation; });
  batchApply?.addEventListener("click", async () => {
    const ids = batchIds().sort((a, b) => a - b);
    const status = new FormData(batchStatusForm).get("status");
    if (!batchPlan || status !== batchPlan.status || ids.join(",") !== batchPlan.ids.join(",")) { clearBatchPlan(); notify("Selection changed. Preview again.", true); return; }
    try {
      batchApply.disabled = true;
      const result = await api("/admin/api/games/batch-status/apply", {method: "POST", body: JSON.stringify({ids, status, confirmation: batchConfirmation.value})});
      batchPreview.textContent = `${result.changed} game(s) updated to ${result.target}.`;
      location.reload();
    } catch (error) { batchApply.disabled = false; notify(error.message, true); }
  });

  document.getElementById("adminCreateForm")?.addEventListener("submit", async event => {
    event.preventDefault();
    const form = event.currentTarget;
    try {
      await api("/admin/api/users", {method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(form).entries()))});
      location.reload();
    } catch (error) { notify(error.message, true); }
  });

  document.querySelectorAll(".user-display-name").forEach(form => form.addEventListener("submit", async event => {
    event.preventDefault();
    try {
      await api(`/admin/api/users/${form.dataset.userId}`, {method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(form).entries()))});
      notify("Saved.");
    } catch (error) { notify(error.message, true); }
  }));

  document.querySelectorAll("[data-report-status]").forEach(select => select.addEventListener("change", async event => {
    const report = event.currentTarget.closest("[data-report-id]");
    try {
      await api(`/admin/api/reports/${report.dataset.reportId}`, {method: "POST", body: JSON.stringify({status: event.currentTarget.value})});
    } catch (error) { notify(error.message, true); }
  }));

  document.getElementById("siteSettingsForm")?.addEventListener("submit", async event => {
    event.preventDefault();
    try {
      await api("/admin/api/site-settings", {method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(event.currentTarget).entries()))});
      notify("Contact saved.");
    } catch (error) { notify(error.message, true); }
  });
})();
