/**
 * Проверка словаря: собирает все ключи t("…") из src/ и сообщает, каких переводов не хватает.
 *   node scripts/i18n-keys.cjs           — список недостающих ключей (код выхода 1, если есть)
 *   node scripts/i18n-keys.cjs --all     — вывести все ключи
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "src");
const keys = new Set();
(function walk(dir) {
  for (const f of fs.readdirSync(dir)) {
    const p = path.join(dir, f);
    if (fs.statSync(p).isDirectory()) { if (f !== "bank") walk(p); continue; }
    if (!/\.tsx?$/.test(f) || /^i18n/.test(f)) continue;
    const src = fs.readFileSync(p, "utf8");
    for (const m of src.matchAll(/\bt\(("(?:[^"\\]|\\.)*")/g)) keys.add(JSON.parse(m[1]));
  }
})(ROOT);

const all = [...keys];
if (process.argv.includes("--all")) {
  console.log(all.join("\n"));
  process.exit(0);
}
const dictSrc = fs.readFileSync(path.join(ROOT, "i18n-dict.ts"), "utf8");
const known = new Set([...dictSrc.matchAll(/("(?:[^"\\]|\\.)*"):\s*\[/g)].map((m) => JSON.parse(m[1])));
const missing = all.filter((k) => !known.has(k));
console.log(`ключей: ${all.length}, в словаре: ${known.size}, без перевода: ${missing.length}`);
missing.forEach((k) => console.log("  " + JSON.stringify(k)));
process.exit(missing.length ? 1 : 0);
