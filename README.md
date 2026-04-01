# Better-VSCode

opinionated vs code where i try to remove all the bs and keep things i like about vscode(there aren't very many left). the goal is to make it private, relatively faster, and debloated.

# how it works
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
uv run utils/patches.py sync --vscode-dir "C:\...\coding\vscode" --force-push

# Apply all patches to a clean vscode tree
uv run utils/patches.py apply "C:\...\coding\vscode"

# Dry run (check without applying)
uv run utils/patches.py apply "C:\...\coding\vscode" --dry-run

# Reverse applied patches
uv run utils/patches.py apply "C:\...\coding\vscode" --reverse

# List patches in series
uv run utils/patches.py list
```

### Generating patches

```bash
# Step 1: Apply existing patches + commit as baseline
uv run utils/patches.py setup --target "C:\...\coding\vscode"

# Step 2: Make your changes in the vscode tree (edit files, etc.)

# Step 3: Generate patch (diffs your changes against the baseline, then resets tree)
uv run utils/patches.py generate --target "C:\...\coding\vscode" --name category/my-patch

# Or if something goes wrong, reset manually:
uv run utils/patches.py teardown --target "C:\...\coding\vscode"
```

`setup` applies all existing patches and commits them as a baseline. `generate` diffs only your new changes against that baseline, so patches never overlap with each other. The tree is automatically reset after generation.

## Workflows

### Adding a new change
1. Sync: `uv run utils/patches.py sync --vscode-dir "..."`
2. Setup: `uv run utils/patches.py setup --target "..."`
3. Edit files in vscode
4. Generate: `uv run utils/patches.py generate --target "..." --name category/name`
   (tree is auto-reset after generation)

### Upstream VS Code updates
1. Sync: `uv run utils/patches.py sync --vscode-dir "..."`
2. Apply: `uv run utils/patches.py apply "..."`
3. If patches fail: fix in vscode, regenerate with `setup` → edit → `generate`

### Building
1. `uv run utils/patches.py apply "..."`
2. Build vscode as usual
3. `uv run utils/patches.py apply "..." --reverse` when done

## Patch format

Standard unified diff. Patches go in `patches/` (subdirectories for organization, e.g. `patches/debloat/`). Order is defined in `patches/series`.
