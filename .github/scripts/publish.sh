#!/usr/bin/env bash
set -euo pipefail

PKG_NAME=$(node -p "require('./package.json').name")
PKG_VERSION=$(node -p "require('./package.json').version")

if npm view "${PKG_NAME}@${PKG_VERSION}" version \
  --registry=https://registry.npmjs.org/ >/dev/null 2>&1; then
  echo "::notice title=Publish skipped::${PKG_NAME}@${PKG_VERSION} is already on npm"
  exit 0
fi

echo "::notice title=Publishing::${PKG_NAME}@${PKG_VERSION}"
npm publish --access public --provenance
