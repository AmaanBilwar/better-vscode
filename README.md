# Better-VSCode

Uses a patch system similar to [Helium](https://github/imputnet/helium), where i use patches to make changes to the vscode fork and dsitribute binaries


[AmaanBilwar/vscode](https://github.com/AmaanBilwar/vscode) - clean fork of microsoft/vscode(source code)

[AmaanBilwar/better-vscode](https://github.com/AmaanBilwar/better-vscode) - patches and tooling (no source code)

## Requirements

- Python 3.8+
- GNU `patch` (Git for Windows includes it, or `scoop install patch`)
- Git

## First time setup

```bash
# Add upstream to your vscode fork (once)
git remote add upstream https://github.com/microsoft/vscode.git
git fetch upstream
```

## Commands

```bash
# Sync fork with upstream microsoft/vscode
python utils/patches.py sync --vscode-dir "C:\...\coding\vscode" --force-push

# Make changes in vscode, then generate a patch
python utils/patches.py generate --target "C:\...\coding\vscode" --name debloat/remove-telemetry

# Reset vscode back to clean state
git checkout -- . && git clean -fd

# Apply all patches to a clean vscode tree
python utils/patches.py apply "C:\...\coding\vscode"

# Dry run (check without applying)
python utils/patches.py apply "C:\...\coding\vscode" --dry-run

# Reverse applied patches
python utils/patches.py apply "C:\...\coding\vscode" --reverse

# List patches in series
python utils/patches.py list
```

## Workflows

### Adding a new change
1. Sync: `python utils/patches.py sync --vscode-dir "..."`
2. Edit files in vscode
3. Generate: `python utils/patches.py generate --target "..." --name category/name`
4. Clean: `git checkout -- . && git clean -fd` in vscode

### Upstream VS Code updates
1. Sync: `python utils/patches.py sync --vscode-dir "..."`
2. Apply: `python utils/patches.py apply "..."`
3. If patches fail: fix in vscode, regenerate with `generate`, clean again

### Building
1. `python utils/patches.py apply "..."`
2. Build vscode as usual
3. `python utils/patches.py apply "..." --reverse` when done

## Patch format

Standard unified diff. Patches go in `patches/` (subdirectories for organization, e.g. `patches/debloat/`). Order is defined in `patches/series`.
