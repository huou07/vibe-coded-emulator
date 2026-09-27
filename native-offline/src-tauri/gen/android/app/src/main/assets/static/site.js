// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
(() => {
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

  addEventListener("keydown", event => {
    if (event.key === "Escape" && navToggle?.getAttribute("aria-expanded") === "true") {
      setNavOpen(false);
      navToggle.focus();
    }
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

})();
