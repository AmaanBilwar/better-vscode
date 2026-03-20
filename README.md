#### forked on Friday, 20th March 2026.

The goal of this fork is to try and debloat VSCode, make it relatively faster and useable, while solving a few bugs along the way.

## What the script does (fix-vs2026-build.ps1):
1. Cleans `node_modules/` and `package-lock.json`
2. `npm install --ignore-scripts` — installs deps without building
3. Patches node-gyp (system + local) for VS 2026 (version 18, toolset v145)
4. npm rebuild with env vars — compiles native modules against Electron headers
5. npm install — runs VS Code's postinstall scripts (build dirs, extensions)
## Usage:
`powershell -ExecutionPolicy Bypass -File .\fix-vs2026-build.ps1`
The npm rebuild step was the missing piece — the .npmrc Electron settings (disturl, target, runtime) aren't recognized at project level by newer npm, so they must be passed as env vars to compile native modules correctly.
