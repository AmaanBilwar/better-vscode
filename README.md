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

## Build + Release automation

- Cross-platform builder script: `utils/build_release.py`
- GitHub workflow: `.github/workflows/release.yml`

### Local build (no release)

```bash
python utils/build_release.py \
  --vscode-dir "C:\...\coding\vscode" \
  --platform windows-x64 \
  --artifact-dir "./artifacts/windows-x64"
```

Platforms: `windows-x64`, `linux-x64`, `darwin-arm64`

### Create release

1. Commit/push changes.
2. Tag version and push tag:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```
3. GitHub Actions builds all platforms and publishes release with attached artifacts.

### Manual CI build

Run **Build and Release** workflow from Actions tab (`workflow_dispatch`) to test build without tag.
