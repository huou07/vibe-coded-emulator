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

  const guide = document.getElementById("welcomeGuide");
  const closeGuide = () => {
    if (!guide) return;
    guide.classList.remove("show");
    setTimeout(() => { guide.hidden = true; }, 180);
  };
  const openGuide = (automatic = false) => {
    if (!guide) return;
    guide.hidden = false;
    requestAnimationFrame(() => guide.classList.add("show"));
    clearTimeout(openGuide.timer);
    if (automatic) openGuide.timer = setTimeout(closeGuide, 5000);
  };
  document.getElementById("guideButton")?.addEventListener("click", () => openGuide(false));
  document.getElementById("closeGuide")?.addEventListener("click", closeGuide);
  if (guide) {
    try {
      if (!localStorage.getItem("an3-welcome-v1")) {
        localStorage.setItem("an3-welcome-v1", "1");
        setTimeout(() => openGuide(true), 120);
      }
    } catch (_) {}
  }

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
    const vietnamese = document.documentElement.lang !== "en";
    errorBox.textContent = "";
    authForm.classList.add("is-loading");
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
      authForm.classList.remove("is-loading");
      submit.disabled = false;
      progress.hidden = true;
      progress.classList.remove("complete");
    }
  });

  const displayNameForm = document.getElementById("displayNameForm");
  displayNameForm?.addEventListener("submit", async event => {
    event.preventDefault();
    try {
      const data = await api("/api/account/display-name", {method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(displayNameForm).entries()))});
      document.querySelector(".site-header .account")?.replaceChildren(document.createTextNode(data.display_name));
      notify(document.documentElement.lang === "en" ? "Nickname saved" : "Đã lưu nickname");
    } catch (error) { notify(error.message, true); }
  });

  const search = document.getElementById("gameSearch");
  let activeSystem = "all";
  const filterLibrary = () => {
    const query = search?.value.trim().toLocaleLowerCase() || "";
    document.querySelectorAll("#gameGrid .game-card").forEach(card => {
      const matchesSystem = activeSystem === "all" || card.dataset.system === activeSystem;
      const matchesSearch = !query || card.textContent.toLocaleLowerCase().includes(query);
      card.hidden = !(matchesSystem && matchesSearch);
    });
    document.querySelectorAll("#gameGrid .game-system-section").forEach(section => {
      const recommended = section.dataset.sectionKind === "recommended";
      section.hidden = (recommended && activeSystem !== "all") || !section.querySelector(".game-card:not([hidden])");
    });
  };
  search?.addEventListener("input", filterLibrary);
  document.querySelectorAll("[data-system-filter]").forEach(button => button.addEventListener("click", () => {
    activeSystem = button.dataset.systemFilter || "all";
    document.querySelectorAll("[data-system-filter]").forEach(item => item.classList.toggle("active", item === button));
    filterLibrary();
  }));

  const gameGrid = document.getElementById("gameGrid");
  if (gameGrid) {
    const currentVersion = gameGrid.dataset.libraryVersion;
    setInterval(async () => {
      if (document.hidden || search?.value) return;
      try {
        const response = await fetch("/api/library-version", {cache: "no-store"});
        const data = await response.json();
        if (response.ok && data.version !== currentVersion) location.reload();
      } catch (_) {}
    }, 15000);
  }

  document.querySelectorAll("[data-rate]").forEach(button => button.addEventListener("click", async () => {
    const box = button.closest("[data-game]");
    if (!csrf) { location.href = "/login"; return; }
    try {
      const value = Number(button.dataset.rate);
      await api(`/api/games/${box.dataset.game}/rating`, {method: "POST", body: JSON.stringify({value})});
      box.querySelectorAll("[data-rate]").forEach(star => star.classList.toggle("active", Number(star.dataset.rate) <= value));
      notify("Đã lưu đánh giá");
    } catch (error) { notify(error.message, true); }
  }));

  document.getElementById("favoriteButton")?.addEventListener("click", async event => {
    const button = event.currentTarget;
    try {
      const data = await api(`/api/games/${button.dataset.game}/favorite`, {method: "POST", body: "{}"});
      button.setAttribute("aria-pressed", String(data.favorited));
      button.textContent = `${data.favorited ? "♥" : "♡"} ${document.documentElement.lang === "en" ? "Favorite" : "Yêu thích"}`;
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

  const uploadRaw = (url, file, onProgress) => new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", `${url}?name=${encodeURIComponent(file.name)}`);
    xhr.setRequestHeader("X-CSRF-Token", csrf);
    xhr.upload.onprogress = event => { if (event.lengthComputable) onProgress(event.loaded / event.total); };
    xhr.onload = () => {
      const data = (() => { try { return JSON.parse(xhr.responseText); } catch (_) { return {}; } })();
      if (xhr.status >= 200 && xhr.status < 300) resolve(data);
      else reject(new Error(data.error || `Upload failed (${xhr.status})`));
    };
    xhr.onerror = () => reject(new Error("Network error"));
    xhr.send(file);
  });

  const DIRECT_UPLOAD_LIMIT = 48 * 1024 * 1024;
  const putChunk = (url, blob, offset, onProgress) => new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.setRequestHeader("X-CSRF-Token", csrf);
    xhr.setRequestHeader("X-Upload-Offset", String(offset));
    xhr.upload.onprogress = event => { if (event.lengthComputable) onProgress(event.loaded / event.total); };
    xhr.onload = () => {
      const data = (() => { try { return JSON.parse(xhr.responseText); } catch (_) { return {}; } })();
      if (xhr.status >= 200 && xhr.status < 300) resolve(data);
      else reject(new Error(data.error || `Upload failed (${xhr.status})`));
    };
    xhr.onerror = () => reject(new Error("Network error"));
    xhr.send(blob);
  });

  const uploadChunkedRom = async (gameId, file, onProgress) => {
    let uploadId = "";
    try {
      const session = await api(`/admin/api/games/${gameId}/uploads`, {
        method: "POST", body: JSON.stringify({kind: "rom", name: file.name, size: file.size})
      });
      uploadId = session.upload_id;
      const chunkSize = Math.max(1024 * 1024, Number(session.chunk_size) || 8 * 1024 * 1024);
      for (let offset = 0; offset < file.size; offset += chunkSize) {
        const end = Math.min(file.size, offset + chunkSize);
        await putChunk(`/admin/api/uploads/${uploadId}`, file.slice(offset, end), offset, ratio => {
          onProgress((offset + (end - offset) * ratio) / file.size);
        });
      }
      const completed = await api(`/admin/api/uploads/${uploadId}/complete`, {method: "POST", body: "{}"});
      uploadId = "";
      return completed;
    } catch (error) {
      if (uploadId) {
        try { await api(`/admin/api/uploads/${uploadId}`, {method: "DELETE", body: null}); } catch (_) {}
      }
      throw error;
    }
  };

  const uploadRom = (gameId, file, onProgress) => file.size > DIRECT_UPLOAD_LIMIT
    ? uploadChunkedRom(gameId, file, onProgress)
    : uploadRaw(`/admin/api/games/${gameId}/rom`, file, onProgress);

  const gameForm = document.getElementById("gameForm");
  const titleFromFilename = value => String(value || "").replace(/^.*[\\/]/, "").replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim().slice(0, 120) || "Game";
  const assignFile = (input, file) => {
    const transfer = new DataTransfer();
    transfer.items.add(file);
    input.files = transfer.files;
    input.dispatchEvent(new Event("change", {bubbles: true}));
  };
  const coverInput = document.getElementById("coverInput");
  const coverPasteTarget = document.getElementById("coverPasteTarget");
  const coverPasteStatus = document.getElementById("coverPasteStatus");
  const setCoverFromClipboard = file => {
    if (!file || !String(file.type || "").startsWith("image/")) {
      coverPasteStatus.textContent = document.documentElement.lang === "en" ? "Clipboard does not contain an image." : "Clipboard chưa có ảnh.";
      return;
    }
    const extension = {"image/png":"png", "image/jpeg":"jpg", "image/webp":"webp"}[file.type] || "png";
    const named = new File([file], `pasted-cover.${extension}`, {type:file.type || "image/png"});
    assignFile(coverInput, named);
    coverPasteStatus.textContent = `${document.documentElement.lang === "en" ? "Cover ready" : "Đã chọn cover"}: ${named.name}`;
  };
  coverPasteTarget?.addEventListener("click", () => coverPasteTarget.focus());
  coverPasteTarget?.addEventListener("keydown", event => {
    if (event.key === "Enter" || event.key === " ") { event.preventDefault(); coverPasteTarget.focus(); }
  });
  coverPasteTarget?.addEventListener("paste", event => {
    const item = [...(event.clipboardData?.items || [])].find(candidate => candidate.type.startsWith("image/"));
    if (!item) return;
    event.preventDefault();
    setCoverFromClipboard(item.getAsFile());
  });
  coverInput?.addEventListener("change", () => {
    const file = coverInput.files?.[0];
    if (file) coverPasteStatus.textContent = `${document.documentElement.lang === "en" ? "Cover ready" : "Đã chọn cover"}: ${file.name}`;
  });

  gameForm?.addEventListener("submit", async event => {
    event.preventDefault();
    const form = new FormData(gameForm);
    const id = gameForm.dataset.id;
    const rom = form.get("rom");
    const cover = form.get("cover");
    const screenshots = [...form.getAll("screenshots")].filter(file => file?.size);
    const status = document.getElementById("adminStatus");
    const bar = document.getElementById("adminProgress");
    if (!id && (!rom || !rom.size)) { status.textContent = "Chọn file game trước khi lưu."; return; }
    const shouldPublish = form.get("published") === "on";
    const title = form.get("title_en");
    const description = form.get("description_vi");
    const payload = {
      title_vi: title, title_en: title, system: form.get("system"),
      rom_name: rom?.name || "",
      description_vi: description, description_en: description,
      published: id ? shouldPublish : false, experimental: form.get("experimental") === "on",
      update_note: form.get("update_note") || ""
    };
    try {
      status.textContent = "Saving metadata…";
      const data = await api(id ? `/admin/api/games/${id}` : "/admin/api/games", {method: "POST", body: JSON.stringify(payload)});
      const gameId = data.id;
      if (rom?.size) {
        status.textContent = `Uploading ${rom.name}…`;
        const upload = await uploadRom(gameId, rom, ratio => { bar.style.width = `${ratio * 80}%`; });
        payload.system = upload.system || payload.system;
      }
      if (cover?.size) {
        status.textContent = `Uploading ${cover.name}…`;
        await uploadRaw(`/admin/api/games/${gameId}/cover`, cover, ratio => { bar.style.width = `${80 + ratio * 20}%`; });
      }
      for (let index = 0; index < screenshots.length; index += 1) {
        const image = screenshots[index];
        status.textContent = `Uploading screenshot ${index + 1}/${screenshots.length}…`;
        await uploadRaw(`/admin/api/games/${gameId}/screenshot`, image, ratio => { bar.style.width = `${80 + ratio * 20}%`; });
      }
      if (!id && shouldPublish) {
        status.textContent = "Publishing…";
        await api(`/admin/api/games/${gameId}`, {
          method: "POST",
          body: JSON.stringify({...payload, published: true})
        });
      }
      bar.style.width = "100%";
      status.textContent = "Saved.";
      location.href = `/admin/game/${gameId}`;
    } catch (error) { status.textContent = error.message; notify(error.message, true); }
  });

  const bulkGameForm = document.getElementById("bulkGameForm");
  bulkGameForm?.addEventListener("submit", async event => {
    event.preventDefault();
    const files = [...new FormData(bulkGameForm).getAll("roms")].filter(file => file?.size);
    const status = document.getElementById("bulkStatus");
    const bar = document.getElementById("bulkProgress");
    if (!files.length) { status.textContent = "Chọn ít nhất một file game."; return; }
    const successes = [], failures = [];
    for (let index = 0; index < files.length; index += 1) {
      const rom = files[index];
      const title = titleFromFilename(rom.name);
      let gameId = null;
      try {
        status.textContent = `(${index + 1}/${files.length}) Đang tạo ${rom.name}…`;
        const created = await api("/admin/api/games", {method:"POST", body:JSON.stringify({
          title_vi:title, title_en:title, system:"auto", rom_name:rom.name,
          description_vi:"", description_en:"", published:false, experimental:false,
          update_note:""
        })});
        gameId = created.id;
        status.textContent = `(${index + 1}/${files.length}) Đang upload ${rom.name}…`;
        await uploadRom(gameId, rom, ratio => {
          bar.style.width = `${Math.round(((index + ratio) / files.length) * 100)}%`;
        });
        successes.push({title, slug:created.slug});
      } catch (error) {
        if (gameId) { try { await api(`/admin/api/games/${gameId}`, {method:"DELETE", body:null}); } catch (_) {} }
        failures.push(`${rom.name}: ${error.message}`);
      }
    }
    bar.style.width = "100%";
    if (failures.length) {
      status.textContent = `Đã upload ${successes.length}/${files.length}. ${failures.join(" | ")}`;
      notify(status.textContent, true);
      return;
    }
    status.textContent = `Đã tạo ${successes.length} game nháp. Đang mở thư viện…`;
    setTimeout(() => { location.href = "/admin"; }, 650);
  });

  document.querySelectorAll("[data-delete-game]").forEach(button => button.addEventListener("click", async event => {
    if (!confirm("Delete this game, cover, comments and ratings?")) return;
    try {
      await api(`/admin/api/games/${event.currentTarget.dataset.deleteGame}`, {method: "DELETE", body: null});
      const row = event.currentTarget.closest("tr");
      if (row) row.remove(); else location.href = "/admin";
    } catch (error) { notify(error.message, true); }
  }));

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
