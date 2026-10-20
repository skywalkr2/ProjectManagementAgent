// Re-review capture: every view at several widths, plus measurements no unit test makes.
import { createRequire } from "module";
const require = createRequire(process.env.WEB_DIR + "/package.json");
const { chromium } = require("@playwright/test");
const fs = require("fs");
const OUT = process.env.OUT; fs.mkdirSync(OUT + "/shots", { recursive: true });
const BASE = process.env.BASE || "http://127.0.0.1:8798/";
const M = {}; const log = [];
const b = await chromium.launch();

const VIEWS = ["today","work/changed","work/since","work/followups","work/open","work/outgoing","work/stages",
  "records/projects","records/people","records/files","records/knowledge","records/rules-review",
  "sources","addons","settings","settings/you","settings/ai","settings/ai-compare","settings/backups","settings/today",
  "settings/appearance","settings/lists","settings/advanced","setup","quality","styleguide"];

async function newPage(w, h, scheme = "light") {
  const c = await b.newContext({ viewport: { width: w, height: h }, colorScheme: scheme, permissions: ["clipboard-read","clipboard-write"] });
  const p = await c.newPage();
  p.on("pageerror", (e) => log.push(`pageerror ${w} ${e}`));
  p.on("console", (m) => { if (m.type() === "error") log.push(`console ${w} ${m.text().slice(0,200)}`); });
  return [c, p];
}
const go = async (p, v) => { await p.goto(BASE + "?token=e2e-token#" + v); await p.waitForTimeout(2200); };
const safe = (s) => s.replace(/[^a-z0-9]+/gi, "-");
const T = async (label, f) => { try { return await f(); } catch (e) { log.push(`FAIL ${label}: ${String(e).split("\n")[0]}`); } };

// Page metrics computed in the browser.
const metrics = () => {
  const vis = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none"; };
  const main = document.querySelector("main") || document.body;
  const header = document.querySelector("header");
  const text = main.innerText;
  const ids = [...new Set((text.match(/\b(PER|ORG|TEAM|PRJ|ACT|Q|DEC|FACT|SRC|CHG|EVT|SER|REQ|NOTE)-\d+\b/g) || []))];
  const enums = [...new Set((text.match(/\b[a-z]+_[a-z_]+\b/g) || []))].slice(0, 10);
  const loading = (text.match(/Loading…|Loading\.\.\./g) || []).length;
  const glyphs = [...new Set((text.match(/[✓✔✗✕✖⚠→←↑↓↻★☐☑•]/g) || []))].join("");
  let upper = 0; const sizes = new Set(), weights = new Set(), fams = new Set();
  let maxDepth = 0, deepest = "";
  const bordered = (el) => { const s = getComputedStyle(el); const n = ["Top","Right","Bottom","Left"].filter((k) => parseFloat(s["border" + k + "Width"]) > 0 && s["border" + k + "Style"] !== "none").length; return n >= 3; };
  for (const el of main.querySelectorAll("*")) {
    if (!vis(el)) continue;
    const s = getComputedStyle(el);
    const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (own) { sizes.add(s.fontSize); weights.add(s.fontWeight); fams.add(s.fontFamily.split(",")[0]); if (s.textTransform === "uppercase") upper++; }
    if (own) { let d = 0, a = el; while (a && a !== main.parentElement) { if (a.nodeType === 1 && a !== el && bordered(a) && !a.matches("button,input,select,textarea,[role=button]")) d++; a = a.parentElement; } if (d > maxDepth) { maxDepth = d; deepest = el.textContent.trim().slice(0, 50); } }
  }
  const small = [];
  for (const el of document.querySelectorAll("a[href],button,input,select,textarea,[role=button],[role=menuitem],[role=tab],[role=checkbox]")) {
    if (!vis(el)) continue; const r = el.getBoundingClientRect();
    if ((r.width < 24 || r.height < 24) && !(el.tagName === "A" && getComputedStyle(el).display === "inline")) small.push(`${Math.round(r.width)}x${Math.round(r.height)} ${(el.getAttribute("aria-label") || el.textContent || el.tagName).trim().slice(0, 30)}`);
  }
  const mr = main.getBoundingClientRect();
  const side = document.querySelector("nav[aria-label] , aside");
  const inner = [];
  for (const el of main.querySelectorAll("*")) { const s = getComputedStyle(el); if (/(auto|scroll)/.test(s.overflowY) && el.scrollHeight > el.clientHeight + 4 && el.clientHeight > 80) inner.push(`${el.className.toString().slice(0, 40)} ${el.clientHeight}/${el.scrollHeight}`); }
  // content extent: union of direct children of main
  let minL = Infinity, maxR = -Infinity;
  for (const ch of main.querySelectorAll(":scope > *, :scope > * > *")) { if (!vis(ch)) continue; const r = ch.getBoundingClientRect(); if (r.width < 40) continue; minL = Math.min(minL, r.left); maxR = Math.max(maxR, r.right); }
  return {
    headerH: header ? Math.round(header.getBoundingClientRect().height) : null,
    mainL: Math.round(mr.left), mainW: Math.round(mr.width), contentL: Math.round(minL), contentR: Math.round(maxR), vw: innerWidth,
    hscroll: document.documentElement.scrollWidth > innerWidth + 1,
    ids, enums, loading, glyphs, upper, fontSizes: [...sizes].sort(), weights: [...weights].sort(), families: [...fams],
    borderDepth: maxDepth, deepest, small: small.slice(0, 12), smallCount: small.length, inner: inner.slice(0, 6),
    h1: (document.querySelector("main h1") || {}).textContent || null,
  };
};

// ---------- 1. Populate the demo ----------
let [c, p] = await newPage(1440, 900);
await go(p, "today");
const cases = await (await fetch(new URL("/__e2e/cases", BASE))).json();
for (const id of ["production-checkin","printer-proof-date","shared-first-name","decision-for-pm","only-the-named-action-moves","question-asked-of-me-nothing-holds-it"]) {
  const cs = cases.find((x) => x.id === id); if (!cs) { log.push("no case " + id); continue; }
  await T("handin " + id, async () => {
    await p.getByRole("button", { name: /Hand (something )?in/ }).first().click(); await p.waitForTimeout(400);
    await p.getByLabel(/Paste or type/).first().fill(cs.pasted ?? cs.note);
    if (cs.pasted && cs.note) { const n = p.getByLabel(/Anything to do with it/); if (await n.count()) await n.fill(cs.note); }
    await p.getByRole("button", { name: "Hand in", exact: true }).click(); await p.waitForTimeout(4000);
    await p.keyboard.press("Escape").catch(() => {});
  });
}
const projects = await (await p.request.get(BASE + "api/projects")).json().catch(() => []);
const people = await (await p.request.get(BASE + "api/people")).json().catch(() => []);
log.push("projects " + JSON.stringify(projects.map((x) => x.id)) + " people " + people.length);
if (projects[0]) VIEWS.push(`records/project/${projects[0].id}`);
if (people[1]) VIEWS.push(`records/person/${people[1].id}`);
await c.close();

// ---------- 2. Every view at 1440, 390, 1920 with metrics ----------
for (const [w, h, tag] of [[1440, 900, "1440"], [390, 844, "390"], [1920, 1080, "1920"]]) {
  [c, p] = await newPage(w, h);
  for (const v of VIEWS) {
    await T(`view ${tag} ${v}`, async () => {
      await go(p, v);
      M[`${tag} ${v}`] = await p.evaluate(metrics);
      await p.screenshot({ path: `${OUT}/shots/${tag}-${safe(v)}.png`, fullPage: tag !== "1920" });
    });
  }
  await c.close();
}

// ---------- 3. Today and key views at more sizes and dark ----------
for (const [w, h, tag, scheme] of [[1024, 768, "1024", "light"], [1280, 720, "1280", "light"], [2560, 1440, "2560", "light"], [1440, 900, "1440-dark", "dark"], [390, 844, "390-dark", "dark"], [1100, 800, "1100", "light"], [800, 900, "800", "light"], [1300, 800, "1300", "light"]]) {
  [c, p] = await newPage(w, h, scheme);
  for (const v of ["today", "work/followups", "settings/ai", "records/people", "work/stages"]) {
    await T(`more ${tag} ${v}`, async () => { await go(p, v); M[`${tag} ${v}`] = await p.evaluate(metrics); await p.screenshot({ path: `${OUT}/shots/${tag}-${safe(v)}.png` }); });
  }
  await c.close();
}

// ---------- 4. Today specifics ----------
for (const [w, h, tag] of [[1280, 720, "1280"], [390, 844, "390"], [1440, 900, "1440"], [1920, 1080, "1920"]]) {
  [c, p] = await newPage(w, h);
  await go(p, "today");
  M[`today-queue ${tag}`] = await p.evaluate(() => {
    const lines = [...document.querySelectorAll("[data-queue-line]")];
    const vh = innerHeight; const r0 = lines[0]?.getBoundingClientRect();
    const titles = lines.map((l) => (l.querySelector("strong, [class*=title], [class*=Title]")?.textContent || l.textContent).trim().slice(0, 70));
    const visible = lines.filter((l) => { const r = l.getBoundingClientRect(); return r.bottom <= vh && r.top >= 0; }).length;
    const ins = document.querySelector("[data-queue-inspector]");
    const todo = [...document.querySelectorAll("input[type=checkbox]")].map((cb) => { const row = cb.closest("li,div"); const t = row?.querySelector("[class*=title], strong, span"); const r = t?.getBoundingClientRect(); const lh = t ? parseFloat(getComputedStyle(t).lineHeight) || 20 : 20; return r ? Math.round(r.height / lh) : null; });
    return { firstTop: r0 ? Math.round(r0.top) : null, count: lines.length, visible, titles, inspector: ins ? ins.innerText.slice(0, 160) : null, todoLines: todo, focused: document.activeElement?.closest("[data-queue-line]")?.innerText.slice(0, 60) || document.activeElement?.tagName };
  });
  if (tag === "1920") {
    await T("j and inspector", async () => {
      await p.keyboard.press("j"); await p.waitForTimeout(500);
      M["today-j 1920"] = await p.evaluate(() => ({ focused: document.activeElement?.closest("[data-queue-line]")?.innerText.slice(0, 80), inspector: document.querySelector("[data-queue-inspector]")?.innerText.slice(0, 120) }));
      await p.screenshot({ path: `${OUT}/shots/today-1920-after-j.png` });
    });
  }
  await c.close();
}

// ---------- 5. Toasts vs Tab on Today ----------
[c, p] = await newPage(1440, 900);
await go(p, "today");
await T("toasts", async () => {
  let made = 0;
  for (let i = 0; i < 6 && made < 3; i++) {
    const btn = p.locator("[data-queue-line] button", { hasText: /^(Looks good|All looks good)$/ }).first();
    if (await btn.count()) { await btn.click(); made++; await p.waitForTimeout(700); }
  }
  const cb = p.locator("main input[type=checkbox]").first(); if (made < 3 && await cb.count()) { await cb.click(); made++; await p.waitForTimeout(600); }
  log.push("toasts made " + made);
  await p.screenshot({ path: `${OUT}/shots/toasts-1440.png` });
  const covered = [];
  await p.locator("body").focus();
  for (let i = 0; i < 160; i++) {
    await p.keyboard.press("Tab");
    const r = await p.evaluate(() => {
      const el = document.activeElement; if (!el || el === document.body) return null;
      const b = el.getBoundingClientRect(); if (b.width === 0) return null;
      const pts = [[b.left + b.width / 2, b.top + b.height / 2], [b.left + 3, b.top + 3], [b.right - 3, b.bottom - 3]];
      const hits = pts.map(([x, y]) => { const t = document.elementFromPoint(x, y); return !t || el === t || el.contains(t) || t.contains(el); });
      const name = (el.getAttribute("aria-label") || el.textContent || el.tagName).trim().slice(0, 40);
      return { name, all: hits.every((h) => !h), center: !hits[0] };
    });
    if (r && r.all) covered.push("ENTIRE " + r.name); else if (r && r.center) covered.push("center " + r.name);
  }
  M["toast-tab 1440"] = { covered };
});
await c.close();

// ---------- 6. Send back, Follow-ups copy, settings/ai, compare ----------
[c, p] = await newPage(1440, 900);
await go(p, "work/changed");
await T("send back", async () => {
  await p.getByRole("button", { name: /More actions/ }).first().click(); await p.waitForTimeout(300);
  await p.getByRole("menuitem", { name: /Send back/ }).first().click(); await p.waitForTimeout(600);
  const sub = p.getByRole("button", { name: /^Send back/ }).last();
  const r = await sub.boundingBox(); M["sendback"] = { box: r, vh: 900, inView: !!r && r.y >= 0 && r.y + r.height <= 900 };
  await p.screenshot({ path: `${OUT}/shots/sendback-1440.png` });
});
await go(p, "work/followups");
await T("copy", async () => {
  await p.evaluate(() => navigator.clipboard.writeText("EMPTY"));
  const copy = p.getByRole("button", { name: /^Copy/ }).first(); await copy.click(); await p.waitForTimeout(700);
  M["copy-first-press"] = { clipboard: (await p.evaluate(() => navigator.clipboard.readText())).slice(0, 60) };
  await p.screenshot({ path: `${OUT}/shots/followups-after-copy-1440.png` });
  const tbl = p.getByRole("button", { name: /^Table$/ }).first(); if (await tbl.count()) { await tbl.click(); await p.waitForTimeout(500); }
  const tab = p.getByRole("tab", { name: /Table/ }).first(); if (await tab.count()) { await tab.click(); await p.waitForTimeout(500); }
  await p.screenshot({ path: `${OUT}/shots/followups-table-1440.png`, fullPage: true });
});
await go(p, "today");
await T("row menu today", async () => { await p.locator("[data-queue-line]").first().getByRole("button", { name: /More/ }).first().click(); await p.waitForTimeout(300); await p.screenshot({ path: `${OUT}/shots/today-menu-1440.png` }); await p.keyboard.press("Escape"); });
await T("handin drawer", async () => { await p.getByRole("button", { name: /Hand (something )?in/ }).first().click(); await p.waitForTimeout(500); await p.screenshot({ path: `${OUT}/shots/handin-1440.png` }); M["handin"] = await p.evaluate(() => { const t = document.querySelector("textarea"); const r = t?.getBoundingClientRect(); const cw = t ? parseFloat(getComputedStyle(t).fontSize) * 0.5 : 8; return { w: r && Math.round(r.width), approxChars: r && Math.round(r.width / cw) }; }); await p.keyboard.press("Escape"); });
await T("ask", async () => { await p.keyboard.press("/"); await p.waitForTimeout(500); await p.screenshot({ path: `${OUT}/shots/ask-1440.png` }); await p.keyboard.press("Escape"); });
await T("status", async () => { await p.locator("header").getByRole("button").filter({ hasText: /Backup|Live|Offline/ }).first().click(); await p.waitForTimeout(300); await p.screenshot({ path: `${OUT}/shots/status-1440.png` }); await p.keyboard.press("Escape"); });
await T("usermenu", async () => { await p.locator("header").getByRole("button", { name: /menu|AL/i }).last().click(); await p.waitForTimeout(300); await p.screenshot({ path: `${OUT}/shots/usermenu-1440.png` }); await p.keyboard.press("Escape"); });
await T("people drawer", async () => { await go(p, "records/people"); await p.getByRole("button", { name: /Add a person/ }).first().click(); await p.waitForTimeout(500); await p.screenshot({ path: `${OUT}/shots/people-add-1440.png` }); await p.keyboard.press("Escape"); });
await T("people detail", async () => { await go(p, "records/people"); await p.locator("main tbody tr").nth(1).click(); await p.waitForTimeout(600); await p.screenshot({ path: `${OUT}/shots/people-detail-1440.png` }); });
await T("project edit", async () => { await go(p, "records/projects"); await p.locator("main tbody tr").first().click(); await p.waitForTimeout(600); await p.screenshot({ path: `${OUT}/shots/projects-detail-1440.png` }); });
await c.close();

fs.writeFileSync(`${OUT}/metrics.json`, JSON.stringify(M, null, 1));
fs.writeFileSync(`${OUT}/log.txt`, log.join("\n"));
console.log(log.join("\n")); await b.close();
