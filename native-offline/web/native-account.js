// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Optional AN3 account session for installed apps. Guest mode never calls this
// module and never creates a server record.
(() => {
  "use strict";
  const origin = String(globalThis.AN3_ACCOUNT_ORIGIN || "https://example.com").replace(/\/+$/, "");
  const state = {loaded: false, user: null, csrf: "", error: ""};
  const request = async (path, options = {}) => {
    const response = await fetch(origin + path, Object.assign({credentials: "include", headers: {"Content-Type": "application/json"}}, options));
    let data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(data.error || `Account request failed (${response.status})`);
    return data;
  };
  const load = async () => {
    try {
      const data = await request("/api/account/session", {method: "GET", headers: {}});
      state.user = data.authenticated ? {id: data.userId, name: data.name || "AN3 account"} : null;
      state.csrf = data.authenticated ? String(data.csrf || "") : "";
      state.error = "";
    } catch (error) { state.error = error.message || String(error); }
    state.loaded = true;
    return state.user;
  };
  const login = async (name, password) => {
    if (!String(name || "").trim() || !String(password || "")) throw new Error("Enter your AN3 username and password.");
    await request("/api/login", {method: "POST", body: JSON.stringify({name: String(name).trim(), password: String(password), next: "/"})});
    await load();
    if (!state.user) throw new Error("The AN3 account session was not established.");
    return state.user;
  };
  const logout = async () => {
    await request("/api/logout", {method: "POST", headers: {"X-CSRF-Token": state.csrf}});
    state.user = null;
    state.csrf = "";
    return null;
  };
  const proof = async challenge => {
    if (!state.user) await load();
    if (!state.user) return null;
    const data = await request("/api/account/peer-proof", {method: "POST", body: JSON.stringify({challenge})});
    return data.proof || null;
  };
  const verify = async (challenge, remoteProof) => {
    if (!state.user) await load();
    if (!state.user || !remoteProof) return false;
    const data = await request("/api/account/peer-proof/verify", {method: "POST", body: JSON.stringify({challenge, proof: remoteProof})});
    return data.sameAccount === true;
  };
  globalThis.AN3Account = Object.freeze({origin, state, load, login, logout, proof, verify});
})();
