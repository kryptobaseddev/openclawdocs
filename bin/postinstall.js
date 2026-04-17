#!/usr/bin/env node
"use strict";

const { execFileSync } = require("child_process");
const path = require("path");
const fs = require("fs");

const ROOT = path.resolve(__dirname, "..");
const VENV = path.join(ROOT, ".venv");
const IS_WIN = process.platform === "win32";
const PIP = IS_WIN
  ? path.join(VENV, "Scripts", "pip.exe")
  : path.join(VENV, "bin", "pip");

function isSupportedPython(cmd) {
  try {
    const v = execFileSync(cmd, ["--version"], { encoding: "utf8" }).trim();
    const match = v.match(/Python (\d+)\.(\d+)/);
    return !!(match && parseInt(match[1]) >= 3 && parseInt(match[2]) >= 12);
  } catch (_) {
    return false;
  }
}

function findPython() {
  const explicit = process.env.OPENCLAWDOCS_PYTHON || process.env.PYTHON;
  if (explicit && isSupportedPython(explicit)) {
    return explicit;
  }

  for (const cmd of ["python3.13", "python3.12", "python3", "python"]) {
    if (isSupportedPython(cmd)) {
      return cmd;
    }
  }
  return null;
}

function main() {
  const python = findPython();
  if (!python) {
    console.error("openclawdocs: Python 3.12+ is required but not found.");
    console.error("Install Python 3.12+ and re-run: npm run postinstall");
    console.error("You can also set OPENCLAWDOCS_PYTHON=/path/to/python3.12");
    process.exit(1);
  }

  console.log(`openclawdocs: Using ${python}`);

  // Create venv
  if (!fs.existsSync(VENV)) {
    console.log("openclawdocs: Creating Python virtual environment...");
    execFileSync(python, ["-m", "venv", VENV], { stdio: "inherit", cwd: ROOT });
  }

  // Install Python package
  console.log("openclawdocs: Installing Python dependencies...");
  execFileSync(PIP, ["install", "--upgrade", "pip"], {
    stdio: "inherit",
    cwd: ROOT,
  });
  execFileSync(PIP, ["install", "-e", "."], { stdio: "inherit", cwd: ROOT });

  // Auto-sync documentation on first install
  const PYTHON_BIN = IS_WIN
    ? path.join(VENV, "Scripts", "python.exe")
    : path.join(VENV, "bin", "python");
  console.log("openclawdocs: Downloading documentation (first sync)...");
  try {
    execFileSync(PYTHON_BIN, ["-m", "openclaw_docs", "sync"], {
      stdio: "inherit",
      cwd: ROOT,
    });
  } catch (_) {
    console.log("openclawdocs: Auto-sync failed (no network?). Run: openclawdocs sync");
  }

  console.log("openclawdocs: Setup complete. Try: openclawdocs search 'getting started'");
}

main();
