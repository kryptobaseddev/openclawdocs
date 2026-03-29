#!/usr/bin/env node
"use strict";

/**
 * Version script: orchestrates changesets + VG for CalVer releases.
 *
 * Problem: Changesets applies semver bumps. VG's `bump --apply` auto-picks
 * the wrong option in non-interactive CI (always picks option 1, which can
 * downgrade the version).
 *
 * Solution: Calculate CalVer ourselves (always correct), use VG only for
 * changelog fixing and file sync.
 *
 * Pipeline:
 * 1. changeset version  → Consume changesets into CHANGELOG
 * 2. calcNextCalVer()   → Calculate correct YYYY.M.MICRO (always increments)
 * 3. Set manifest       → Write to pyproject.toml
 * 4. vg fix-changelog   → Repair changesets' CHANGELOG mangling
 * 5. vg sync            → Propagate to __init__.py, CHANGELOG
 * 6. Sync package.json  → Direct write (VG regex can't distinguish JSON keys)
 * 7. vg check           → Verify version is valid CalVer
 */

const { execFileSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");

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
  console.log(`  > package.json set to ${version}`);
}

function calcNextCalVer(current) {
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
  console.log("version: CalVer release pipeline\n");

  // Step 1: Changesets consumes .changeset/*.md files into CHANGELOG
  console.log("Step 1: Consume changesets");
  run("npx", ["changeset", "version"]);

  // Step 2: Calculate correct CalVer (don't trust vg bump in non-interactive)
  const current = getManifestVersion() || "0.0.0";
  const next = calcNextCalVer(current);
  console.log(`\nStep 2: CalVer ${current} → ${next}`);
  setManifestVersion(next);

  // Step 3: Fix changesets' CHANGELOG mangling
  console.log("\nStep 3: Fix changelog");
  run("vg", ["fix-changelog"], { allowFail: true });

  // Step 4: Sync to __init__.py, CHANGELOG
  console.log("\nStep 4: VG sync");
  run("vg", ["sync"]);

  // Step 5: Sync package.json
  console.log("\nStep 5: Sync package.json");
  syncPackageJson(next);

  // Step 6: Verify
  console.log("\nStep 6: VG check");
  run("vg", ["check"]);

  console.log(`\nDone: ${next}`);
}

main();
