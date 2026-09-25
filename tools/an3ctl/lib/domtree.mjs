// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Page-side JavaScript shared by the web and Android/WebView adapters.
// It produces a compact, LLM-sized semantic view of interactive UI instead of
// dumping raw HTML, and provides semantic locators (testid/id/role/name/text).

export const INTERACTIVE_SELECTOR =
  "a,button,input,select,textarea,[role],[data-testid],[onclick],[tabindex]";

// Returns a JSON string with { url, title, nodes: [...] }.
export function domTreeExpression(limit = 120) {
  return `(() => {
  const LIMIT = ${Number(limit)};
  const SIG = (el) => {
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (el.getAttribute('role')) return el.getAttribute('role');
    if (tag === 'a') return 'link';
    if (tag === 'button') return 'button';
    if (tag === 'select') return 'combobox';
    if (tag === 'textarea') return 'textbox';
    if (tag === 'input') {
      if (type === 'checkbox') return 'checkbox';
      if (type === 'radio') return 'radio';
      if (type === 'range') return 'slider';
      if (type === 'submit' || type === 'button') return 'button';
      return 'textbox';
    }
    if (tag === 'summary') return 'button';
    return tag;
  };
  const accName = (el) => {
    const aria = el.getAttribute('aria-label');
    if (aria) return aria.trim();
    const labelledby = el.getAttribute('aria-labelledby');
    if (labelledby) {
      const parts = labelledby.split(/\\s+/).map((id) => {
        const ref = document.getElementById(id);
        return ref ? (ref.innerText || ref.textContent || '').trim() : '';
      }).filter(Boolean);
      if (parts.length) return parts.join(' ');
    }
    const title = el.getAttribute('title');
    if (title) return title.trim();
    const placeholder = el.getAttribute('placeholder');
    if (placeholder) return placeholder.trim();
    const value = el.value;
    if (value && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') && value.length <= 60) return String(value).trim();
    const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
    return text.slice(0, 80);
  };
  const nodes = [];
  let truncated = false;
  for (const el of document.querySelectorAll(${JSON.stringify(INTERACTIVE_SELECTOR)})) {
    if (nodes.length >= LIMIT) { truncated = true; break; }
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    const visible = rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none' && Number(style.opacity) > 0;
    nodes.push({
      role: SIG(el),
      name: accName(el),
      testId: el.getAttribute('data-testid') || null,
      id: el.id || null,
      enabled: !el.disabled && el.getAttribute('aria-disabled') !== 'true',
      visible,
      checked: el.tagName === 'INPUT' && (el.type === 'checkbox' || el.type === 'radio') ? !!el.checked : null,
      value: el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' ? String(el.value).slice(0, 80) : null,
    });
  }
  return JSON.stringify({ url: location.href, title: document.title, truncated, nodes });
})()`;
}

// Locate one element (or the nth match) by a platform-neutral selector
// descriptor. Returns { found, count, index, node } where node is the same
// compact shape as the tree.
export function locateExpression(selector, opts = {}) {
  const nth = Number.isInteger(opts.nth) ? opts.nth : 0;
  const spec = JSON.stringify(selector);
  return `(() => {
  const selector = ${spec};
  const nth = ${nth};
  const SIG = (el) => {
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (el.getAttribute('role')) return el.getAttribute('role');
    if (tag === 'a') return 'link';
    if (tag === 'button') return 'button';
    if (tag === 'select') return 'combobox';
    if (tag === 'textarea') return 'textbox';
    if (tag === 'input') {
      if (type === 'checkbox') return 'checkbox';
      if (type === 'radio') return 'radio';
      if (type === 'range') return 'slider';
      if (type === 'submit' || type === 'button') return 'button';
      return 'textbox';
    }
    return tag;
  };
  const accName = (el) => {
    const aria = el.getAttribute('aria-label');
    if (aria) return aria.trim();
    const title = el.getAttribute('title');
    if (title) return title.trim();
    const placeholder = el.getAttribute('placeholder');
    if (placeholder) return placeholder.trim();
    const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
    if (text) return text.slice(0, 80);
    return String(el.value ?? '').slice(0, 80);
  };
  const all = Array.from(document.querySelectorAll(${JSON.stringify(INTERACTIVE_SELECTOR)}));
  let matches = [];
  if (selector.kind === 'testid') {
    matches = all.filter((el) => el.getAttribute('data-testid') === selector.value);
  } else if (selector.kind === 'id') {
    const el = document.getElementById(selector.value);
    matches = el ? [el] : [];
  } else if (selector.kind === 'css') {
    matches = Array.from(document.querySelectorAll(selector.value));
  } else if (selector.kind === 'role') {
    matches = all.filter((el) => SIG(el) === selector.value.role);
    if (selector.value.name) {
      const wanted = selector.value.name.toLowerCase();
      matches = matches.filter((el) => accName(el).toLowerCase().includes(wanted));
    }
  } else if (selector.kind === 'name') {
    const wanted = selector.value.toLowerCase();
    matches = all.filter((el) => accName(el).toLowerCase().includes(wanted));
  } else if (selector.kind === 'text') {
    const wanted = selector.value.toLowerCase();
    matches = all.filter((el) => ((el.innerText || el.textContent || '').toLowerCase().includes(wanted)));
  }
  if (!matches.length) return JSON.stringify({ found: false, count: 0, index: -1, node: null });
  const index = Math.min(Math.max(nth, 0), matches.length - 1);
  const el = matches[index];
  const rect = el.getBoundingClientRect();
  const style = getComputedStyle(el);
  return JSON.stringify({
    found: true,
    count: matches.length,
    matchIndex: index,
    // Global index into the full interactive element list so an action can
    // re-find the exact same element without re-deriving DOM paths.
    index: all.indexOf(el),
    node: {
      role: SIG(el),
      name: accName(el),
      testId: el.getAttribute('data-testid') || null,
      id: el.id || null,
      enabled: !el.disabled && el.getAttribute('aria-disabled') !== 'true',
      visible: rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none',
    },
  });
})()`;
}

// Assign every element matching a descriptor a deterministic handle in
// window.__an3ctl so subsequent action commands can target it without
// re-deriving DOM paths.
