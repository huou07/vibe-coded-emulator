// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Translate the existing CLI selector contract into Playwright locators.
// Browser role/name computation and actionability belong to Playwright.
export function locatorExpression(selector, nth = 0) {
  if (!selector) throw new Error("A selector is required");
  const value = JSON.stringify(selector.value);
  const name = (text) => `new RegExp(${JSON.stringify(String(text).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))}, "i")`;
  let locator;
  switch (selector.kind) {
    case "id":
      locator = `page.locator(${JSON.stringify(`[id=${JSON.stringify(selector.value)}]`)})`;
      break;
    case "testid": locator = `page.getByTestId(${value})`; break;
    case "css": locator = `page.locator(${value})`; break;
    case "text": locator = `page.getByText(${value}, { exact: false })`; break;
    case "role":
      locator = `page.getByRole(${JSON.stringify(selector.value.role)}, ${selector.value.name ? `{ name: ${name(selector.value.name)} }` : "{}"})`;
      break;
    case "name": {
      const match = name(selector.value);
      locator = `page.getByLabel(${match})`;
      for (const role of ["button", "link", "checkbox", "radio", "tab", "menuitem", "option", "switch", "slider", "combobox", "textbox"]) {
        locator += `.or(page.getByRole(${JSON.stringify(role)}, { name: ${match} }))`;
      }
      break;
    }
    default: throw new Error(`Unsupported selector kind: ${selector.kind}`);
  }
  if (!Number.isInteger(Number(nth)) || Number(nth) < 0) throw new Error("nth must be a nonnegative integer");
  return { all: locator, one: `(${locator}).nth(${Number(nth)})` };
}

export function queryScript(selector, nth = 0) {
  const { all, one } = locatorExpression(selector, nth);
  return `async (page) => {
    const count = await (${all}).count();
    const locator = ${one};
    if (count <= ${Number(nth)}) return { found: false, count, node: null };
    const ariaSnapshot = await locator.ariaSnapshot();
    const first = ariaSnapshot.match(/^- ([a-z]+)(?: "([^"]*)")?/);
    return { found: true, count, ariaSnapshot, node: {
      role: first?.[1] ?? "", name: first?.[2] ?? "",
      id: await locator.getAttribute("id"), testId: await locator.getAttribute("data-testid"),
      enabled: await locator.isEnabled(), visible: await locator.isVisible()
    }};
  }`;
}

export function actionScript(selector, action, opts = {}) {
  const { one } = locatorExpression(selector, opts.nth ?? 0);
  const timeout = Math.max(1, Math.min(Number(opts.timeout ?? 10000), 30000));
  const value = JSON.stringify(String(opts.value ?? ""));
  const key = JSON.stringify(String(opts.key ?? "Enter"));
  const actions = {
    click: `await locator.click({ timeout: ${timeout} });`,
    fill: `await locator.fill(${value}, { timeout: ${timeout} });`,
    press: `await locator.press(${key}, { timeout: ${timeout} });`,
    select: `await locator.selectOption(${value}, { timeout: ${timeout} });`,
    check: `await locator.setChecked(${opts.checked !== false}, { timeout: ${timeout} });`,
  };
  if (!actions[action]) throw new Error(`Unsupported action: ${action}`);
  return `async (page) => { const locator = ${one}; ${actions[action]} return { performed: true, action: ${JSON.stringify(action)} }; }`;
}
