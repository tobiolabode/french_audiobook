import { spawnSync } from "node:child_process";
import process from "node:process";

const args = process.argv.slice(2);
const result = spawnSync(process.execPath, ["node_modules/vitest/vitest.mjs", ...args], {
  stdio: "inherit",
  shell: false,
});

if (result.error) {
  console.error(result.error.message);
  process.exit(1);
}

process.exit(result.status ?? 1);
