#!/usr/bin/env node
"use strict";

/**
 * Version script: orchestrates changesets + VG for CalVer releases.
 *
 * Problem: Changesets applies semver bumps. VG handles CalVer.
 * Solution: Let changesets run first (consumes changeset files, writes
 * changelog), then VG overrides with correct CalVer and fixes formatting.
 *
 * Pipeline:
 * 1. changeset version  → Consume changesets into CHANGELOG (semver — will be overwritten)
 * 2. vg bump --apply    → Override with correct CalVer version in pyproject.toml
 *    (falls back to manual bump if vg bump fails — known VG bug #8)
 * 3. vg fix-changelog   → Repair changesets' CHANGELOG mangling
 * 4. vg sync            → Propagate CalVer to __init__.py, CHANGELOG
 * 5. package.json sync  → Set CalVer in package.json (VG regex can't distinguish keys)
 * 6. vg check           → Verify version is valid (not full validate — skips hooks)
 */

const { execFileSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const IS_CI = !!process.env.CI;

function run(cmd, args, { allowFail = false } = {}) {
  console.log(`  > ${cmd} ${args.join(" ")}`);
  try {
    execFileSync(cmd, args, { stdio: "inherit", cwd: ROOT });
  } catch (e) {
    if (allowFail) {
      console.log(`  > (non-fatal, continuing)`);
    } else {
      throw e;
    }
  }
}

function getManifestVersion() {
  const toml = fs.readFileSync(path.join(ROOT, "pyproject.toml"), "utf8");
  const match = toml.match(/version\s*=\s*"(.+?)"/);
  return match ? match[1] : null;
}

function setManifestVersion(version) {
  const tomlPath = path.join(ROOT, "pyproject.toml");
  let toml = fs.readFileSync(tomlPath, "utf8");
  toml = toml.replace(/version\s*=\s*"[^"]+"/, `version = "${version}"`);
  fs.writeFileSync(tomlPath, toml);
}

function syncPackageJson(version) {
  const pkgPath = path.join(ROOT, "package.json");
  const pkg = JSON.parse(fs.readFileSync(pkgPath, "utf8"));
  pkg.version = version;
  fs.writeFileSync(pkgPath, JSON.stringify(pkg, null, 2) + "\n");
  console.log(`  > package.json version set to ${version}`);
}

function calcNextCalVer(current) {
  // CalVer YYYY.M.MICRO — increment MICRO if same year.month, else new date
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth() + 1;
  const prefix = `${year}.${month}`;

  if (current.startsWith(prefix + ".")) {
    const micro = parseInt(current.split(".")[2], 10);
    return `${prefix}.${micro + 1}`;
  }
  return `${prefix}.0`;
}

function main() {
  console.log("version: Starting CalVer release pipeline...\n");

  // Step 1: Changesets consumes pending .changeset/*.md files
  console.log("Step 1: Changesets (consume changesets into CHANGELOG)");
  run("npx", ["changeset", "version"]);

  // Step 2: VG bump — try vg bump --apply, fall back to manual CalVer calc
  // (vg bump --apply has a known bug writing to pyproject.toml — VG issue #8)
  console.log("\nStep 2: VG bump (override with CalVer)");
  const currentVersion = getManifestVersion() || "0.0.0";
  try {
    run("vg", ["bump", "--apply"]);
  } catch (_) {
    // Fallback: calculate CalVer ourselves
    const next = calcNextCalVer(currentVersion);
    console.log(`  > vg bump failed, falling back to manual CalVer: ${next}`);
    setManifestVersion(next);
  }

  // Step 3: Fix changesets' CHANGELOG mangling
  console.log("\nStep 3: VG fix-changelog");
  run("vg", ["fix-changelog"], { allowFail: true });

  // Step 4: VG sync to __init__.py and CHANGELOG
  console.log("\nStep 4: VG sync");
  run("vg", ["sync"]);

  // Step 5: Sync package.json explicitly
  const version = getManifestVersion();
  if (!version) {
    console.error("ERROR: Could not read version from pyproject.toml");
    process.exit(1);
  }
  console.log(`\nStep 5: Sync package.json to ${version}`);
  syncPackageJson(version);

  // Step 6: Validate — use `vg check` (not `vg validate`) to skip hooks check in CI
  console.log("\nStep 6: VG check");
  run("vg", ["check"]);

  console.log("\nVersion pipeline complete.");
}

main();
