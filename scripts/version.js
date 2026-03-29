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
 * 3. vg fix-changelog   → Repair changesets' CHANGELOG mangling
 * 4. vg sync            → Propagate CalVer to __init__.py, CHANGELOG
 * 5. npm version (sync) → Set CalVer in package.json (can't use VG regex — ambiguous key)
 * 6. vg validate        → Verify everything is consistent
 */

const { execFileSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");

function run(cmd, args) {
  console.log(`  > ${cmd} ${args.join(" ")}`);
  execFileSync(cmd, args, { stdio: "inherit", cwd: ROOT });
}

function getManifestVersion() {
  // Read version from pyproject.toml (VG manifest source)
  const toml = fs.readFileSync(path.join(ROOT, "pyproject.toml"), "utf8");
  const match = toml.match(/version\s*=\s*"(.+?)"/);
  return match ? match[1] : null;
}

function syncPackageJson(version) {
  // Set package.json version directly (avoids VG regex ambiguity with scripts.version)
  const pkgPath = path.join(ROOT, "package.json");
  const pkg = JSON.parse(fs.readFileSync(pkgPath, "utf8"));
  pkg.version = version;
  fs.writeFileSync(pkgPath, JSON.stringify(pkg, null, 2) + "\n");
  console.log(`  > package.json version set to ${version}`);
}

function main() {
  console.log("version: Starting CalVer release pipeline...\n");

  // Step 1: Changesets consumes pending .changeset/*.md files
  console.log("Step 1: Changesets (consume changesets into CHANGELOG)");
  run("npx", ["changeset", "version"]);

  // Step 2: VG overrides with correct CalVer
  console.log("\nStep 2: VG bump (override with CalVer)");
  run("vg", ["bump", "--apply"]);

  // Step 3: Fix changesets' CHANGELOG mangling
  console.log("\nStep 3: VG fix-changelog");
  run("vg", ["fix-changelog"]);

  // Step 4: VG sync to __init__.py and CHANGELOG
  console.log("\nStep 4: VG sync (pyproject.toml, __init__.py, CHANGELOG)");
  run("vg", ["sync"]);

  // Step 5: Sync package.json explicitly
  const version = getManifestVersion();
  if (!version) {
    console.error("ERROR: Could not read version from pyproject.toml");
    process.exit(1);
  }
  console.log(`\nStep 5: Sync package.json to ${version}`);
  syncPackageJson(version);

  // Step 6: Validate
  console.log("\nStep 6: VG validate");
  run("vg", ["validate"]);

  console.log("\nVersion pipeline complete.");
}

main();
