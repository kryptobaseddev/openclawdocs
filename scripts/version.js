#!/usr/bin/env node
"use strict";

/**
 * Version script: orchestrates changesets + VG for CalVer releases.
 *
 * Why this exists instead of just `changeset version && vg bump --apply && vg sync`:
 * - Changesets applies semver bumps (doesn't understand CalVer)
 * - vg bump --apply has a bug (#9) that picks option 1 in non-interactive mode,
 *   which can DOWNGRADE the version. Using calcNextCalVer() as workaround.
 *
 * Once VG #9 is fixed, this script can be replaced with:
 *   changeset version && vg bump --type patch --apply && vg fix-changelog && vg sync
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
    if (!allowFail) throw e;
    console.log(`  > (non-fatal, continuing)`);
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

function calcNextCalVer(current) {
  // YYYY.M.MICRO — increment MICRO if same year.month, else reset to 0
  const now = new Date();
  const prefix = `${now.getFullYear()}.${now.getMonth() + 1}`;
  if (current.startsWith(prefix + ".")) {
    return `${prefix}.${parseInt(current.split(".")[2], 10) + 1}`;
  }
  return `${prefix}.0`;
}

function main() {
  console.log("version: CalVer release pipeline\n");

  // 1. Changesets consumes .changeset/*.md into CHANGELOG
  console.log("1. Consume changesets");
  run("npx", ["changeset", "version"]);

  // 2. Calculate correct CalVer (workaround for VG #9)
  const current = getManifestVersion() || "0.0.0";
  const next = calcNextCalVer(current);
  console.log(`\n2. CalVer: ${current} -> ${next}`);
  setManifestVersion(next);

  // 3. Fix changesets CHANGELOG mangling
  console.log("\n3. Fix changelog");
  run("vg", ["fix-changelog"], { allowFail: true });

  // 4. VG sync propagates to package.json, __init__.py, CHANGELOG
  console.log("\n4. VG sync");
  run("vg", ["sync"]);

  // 5. Verify
  console.log("\n5. VG check");
  run("vg", ["check"]);

  console.log(`\nDone: ${next}`);
}

main();
