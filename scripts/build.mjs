import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
const source = "frontend/lightweight-status-badge.js";
const target =
  "custom_components/lightweight_status_badge/www/lightweight-status-badge.js";
const result = spawnSync(process.execPath, ["--check", source], {
  stdio: "inherit",
});
if (result.status !== 0) process.exit(1);
const content = readFileSync(source, "utf8");
if (process.argv.includes("--check")) {
  if (readFileSync(target, "utf8") !== content)
    throw new Error("Frontend artifact is stale. Run npm run build.");
} else {
  mkdirSync("custom_components/lightweight_status_badge/www", {
    recursive: true,
  });
  writeFileSync(target, content);
}
console.log(
  `Frontend ${process.argv.includes("--check") ? "verified" : "built"}: ${Buffer.byteLength(content)} bytes; no dependencies`,
);
