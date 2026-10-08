// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// External Game Settings + shared Application settings for the offline shell.
// It renders the canonical model (native-settings.js) and persists through the
// one Android settings adapter, so the library and the in-game menu can never
// hold conflicting copies. A renderer that crashes the game process is edited
// here, outside that process, which is what makes a bad choice recoverable.
(() => {
  const model = window.NativeSettingsModel;
  const bridge = window.AN3AndroidSettings;

  const parse = value => { try { return JSON.parse(value || "{}"); } catch (_) { return {}; } };

  const start = () => {
    const appCard = document.getElementById("nativeApplicationSettingsBody");
    const systemsRow = document.getElementById("nativeGameSettingsSystems");
    const card = document.getElementById("nativeGameSettingsCard");
    if (!model || !card || !systemsRow || !appCard) return;

    const body = document.getElementById("nativeGameSettingsBody");
    const status = document.getElementById("nativeGameSettingsStatus");
    let snapshot = bridge ? parse(bridge.all()) : {global: {}, systems: {}};
    let system = model.systems[0];
    let category = "graphics";

    const setStatus = text => { if (status) status.textContent = text; };

    const readStored = (definition, scope) => {
      const values = scope == null ? (snapshot.global || {}) : ((snapshot.systems || {})[scope] || {});
      return values[definition.id];
    };

    const control = (definition, value, onChange) => {
      const wrap = document.createElement("label");
      wrap.className = "native-field native-settings-field";
      const caption = document.createElement("span");
      caption.textContent = definition.label;
      wrap.appendChild(caption);
      if (definition.type === "enum") {
        const select = document.createElement("select");
        for (const option of model.valuesOf(definition)) {
          const choice = document.createElement("option");
          choice.value = option;
          choice.textContent = model.labelOf(definition, option);
          select.appendChild(choice);
        }
        select.value = model.coerce(definition, value);
        select.addEventListener("change", () => onChange(select.value));
        wrap.appendChild(select);
      } else if (definition.type === "bool") {
        const input = document.createElement("input");
        input.type = "checkbox";
        input.checked = model.coerce(definition, value) === "true";
        input.addEventListener("change", () => onChange(input.checked ? "true" : "false"));
        wrap.appendChild(input);
      } else if (definition.type === "int") {
        const input = document.createElement("input");
        input.type = "number";
        if (definition.min != null) input.min = String(definition.min);
        if (definition.max != null) input.max = String(definition.max);
        input.value = model.coerce(definition, value);
        input.addEventListener("input", () => onChange(input.value));
        wrap.appendChild(input);
      }
      return wrap;
    };

    const renderGroup = (container, definitions, scope) => {
      container.textContent = "";
      const draft = {};
      const editable = definitions.filter(definition => definition.editable !== false);
      const pinned = definitions.filter(definition => definition.editable === false);
      if (editable.length === 0 && pinned.length === 0) {
        const empty = document.createElement("p");
        empty.className = "native-muted";
        empty.textContent = scope == null
          ? "No shared settings in this group."
          : "This system has no configurable options in this build.";
        container.appendChild(empty);
      }
      for (const definition of editable) {
        const value = readStored(definition, scope);
        draft[definition.id] = model.coerce(definition, value);
        const field = control(definition, value, next => { draft[definition.id] = next; });
        if (definition.note) {
          const note = document.createElement("small");
          note.className = "native-muted";
          note.textContent = definition.note;
          wrapHint(field, note);
        }
        container.appendChild(field);
      }
      if (pinned.length > 0) {
        const managed = document.createElement("p");
        managed.className = "native-muted";
        managed.dataset.gsPinned = scope == null ? "global" : scope;
        managed.textContent = `Managed automatically on this platform: ${pinned.map(definition => definition.label).join(", ")}.`;
        container.appendChild(managed);
      }
      if (scope == null) {
        const globalGroup = document.createElement("div");
        globalGroup.className = "native-settings-actions";
        globalGroup.appendChild(action("Save application settings", () => saveDefinitions(editable, scope, draft)));
        container.appendChild(globalGroup);
        return globalGroup;
      }
      const actions = document.createElement("div");
      actions.className = "native-settings-actions";
      actions.appendChild(action("Save settings", () => saveDefinitions(editable, scope, draft)));
      if (definitions.some(definition => definition.category === "graphics")) {
        actions.appendChild(action("Reset Graphics to Defaults", () => {
          if (!bridge) return;
          bridge.resetGraphics(scope);
          reload();
          setStatus(`Graphics defaults restored for ${model.systemLabels[scope]} only.`);
        }));
      }
      container.appendChild(actions);
      return actions;
    };

    const wrapHint = (field, hint) => {
      const holder = document.createElement("span");
      holder.className = "native-settings-hint";
      holder.appendChild(hint);
      field.appendChild(holder);
    };

    const action = (label, handler, primary = false) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = primary ? "button primary" : "button";
      button.textContent = label;
      button.addEventListener("click", handler);
      return button;
    };

    const saveDefinitions = (definitions, scope, draft) => {
      if (!bridge) { setStatus("Settings are read-only in this build."); return; }
      const edits = {};
      for (const definition of definitions) {
        const edit = model.buildEdit(definition, scope, draft[definition.id]);
        if (!edit) { setStatus(`Unsupported value for ${definition.label}.`); return; }
        edits[edit.key] = edit.value;
      }
      const result = parse(bridge.save(JSON.stringify(edits)));
      if (result.ok === false && Array.isArray(result.rejected) && result.rejected.length > 0) {
        setStatus(`Rejected: ${result.rejected.join(", ")}`);
      } else {
        setStatus(`Saved ${model.systemLabels[scope] || "application"} settings. Renderer changes apply on the next launch.`);
      }
      reload();
    };

    const renderSystems = () => {
      systemsRow.textContent = "";
      for (const id of model.systems) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "native-system-tab";
        button.dataset.gsSystem = id;
        button.textContent = model.systemLabels[id] || id.toUpperCase();
        button.setAttribute("aria-pressed", String(id === system));
        if (id === system) button.classList.add("active");
        button.addEventListener("click", () => { system = id; render(); });
        systemsRow.appendChild(button);
      }
    };

    const render = () => {
      renderSystems();
      body.textContent = "";
      if (!bridge) {
        const note = document.createElement("p");
        note.className = "native-muted";
        note.textContent = "Game settings are available in the packaged Android app. This build has no settings adapter.";
        body.appendChild(note);
        return;
      }
      const reason = model.unavailableReason(system);
      if (reason) {
        const note = document.createElement("p");
        note.className = "native-status";
        note.dataset.gsAvailability = system;
        note.textContent = reason;
        body.appendChild(note);
      }
      const tabs = document.createElement("div");
      tabs.className = "native-settings-tabs";
      for (const [id, label] of [["graphics", "Graphics"], ["emulation", "Emulation"]]) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "native-settings-tab";
        button.dataset.gsCategory = id;
        button.textContent = label;
        button.setAttribute("aria-pressed", String(category === id));
        if (category === id) button.classList.add("active");
        button.addEventListener("click", () => { category = id; render(); });
        tabs.appendChild(button);
      }
      body.appendChild(tabs);
      const group = document.createElement("div");
      group.className = "native-settings-group";
      group.dataset.gsGroup = category;
      body.appendChild(group);
      const definitions = category === "graphics" ? model.graphics[system] : model.emulation[system];
      renderGroup(group, definitions || [], system);
    };

    const renderApplication = () => {
      appCard.textContent = "";
      if (!bridge) {
        const note = document.createElement("p");
        note.className = "native-muted";
        note.textContent = "Application settings are edited in the in-game menu in this build.";
        appCard.appendChild(note);
        return;
      }
      renderGroup(appCard, model.externalGlobal(), null);
    };

    const reload = () => {
      if (!bridge) return;
      snapshot = parse(bridge.all());
      renderApplication();
      render();
    };

    renderApplication();
    render();
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once: true});
  else start();
})();
