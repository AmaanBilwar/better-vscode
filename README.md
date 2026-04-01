# Better-VSCode

Opinionated vs code where i try to remove all the bs and keep things i like about vscode(there aren't very many left). The goal is to make it **private**, **relatively faster**, and **debloated**.

# how it works
Uses a patch system similar to [Helium](https://github/imputnet/helium), where i use patches to make changes to the vscode fork and dsitribute binaries

[AmaanBilwar/vscode](https://github.com/AmaanBilwar/vscode) - clean fork of microsoft/vscode(source code)

[AmaanBilwar/better-vscode](https://github.com/AmaanBilwar/better-vscode) - patches and tooling (no source code)

## Contributing

Contributing setup and workflows live in [`CONTRIBUTING.md`](CONTRIBUTING.md).

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

## Patch format

Standard unified diff. Patches go in `patches/` (subdirectories for organization, e.g. `patches/debloat/`). Order is defined in `patches/series`.
