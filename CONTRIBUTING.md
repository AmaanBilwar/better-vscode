# Contributing

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

## Generating patches

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
3. If patches fail: fix in vscode, regenerate with `setup` -> edit -> `generate`

### In case applying a patch fails

When syncing with upstream, a patch can fail because file context changed (line moves, nearby edits).
Use this quick recovery flow to regenerate only the failing patch.

1. Identify the failing patch from `uv run utils/patches.py apply "..."`
2. Temporarily remove (or comment) that patch from `patches/series`
3. Create baseline without the failing patch:
   `uv run utils/patches.py setup --target "C:\...\coding\vscode"`
4. In the vscode tree, try applying the old patch to salvage non-conflicting hunks:
   `git apply --reject --whitespace=nowarn "C:\...\coding\better-vscode\patches\category\name.patch"`
5. Fix rejected hunks manually in vscode (for example, after upstream line shifts)
6. Regenerate the same patch name (overwrite):
   `uv run utils/patches.py generate --target "C:\...\coding\vscode" --name category/name --force`
7. Add the patch back to `patches/series` in its original position
8. Validate:
   `uv run utils/patches.py apply "C:\...\coding\vscode" --dry-run`

This keeps patch history clean and avoids rebuilding unrelated patches.

### Building
1. `uv run utils/patches.py apply "..."`
2. Build vscode as usual
3. `uv run utils/patches.py apply "..." --reverse` when done
