#!/usr/bin/env node
"use strict";

const { execFileSync } = require("child_process");
const path = require("path");
const fs = require("fs");

const ROOT = path.resolve(__dirname, "..");
const VENV = path.join(ROOT, ".venv");
const IS_WIN = process.platform === "win32";
const PYTHON = IS_WIN
  ? path.join(VENV, "Scripts", "python.exe")
  : path.join(VENV, "bin", "python");

function ensureVenv() {
  if (!fs.existsSync(PYTHON)) {
    console.error(
      "openclawdocs: Python venv not found. Run: npm run postinstall"
    );
    process.exit(1);
  }
}

function main() {
  ensureVenv();
  const args = process.argv.slice(2);
  try {
    execFileSync(PYTHON, ["-m", "openclaw_docs", ...args], {
      stdio: "inherit",
      cwd: ROOT,
    });
  } catch (e) {
    process.exit(e.status || 1);
  }
}

main();
