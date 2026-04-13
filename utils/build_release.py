#!/usr/bin/env python3
"""Build patched VS Code for one platform and collect release artifacts.

Usage:
  python utils/build_release.py --vscode-dir ./vscode-src --platform windows-x64 --artifact-dir ./artifacts/windows-x64

Notes:
- Applies patches from this repo to provided vscode dir.
- Runs npm install + platform build command.
- Copies produced archives into artifact-dir.
"""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path


BUILD_COMMANDS = {
    "windows-x64": "npm run gulp vscode-win32-x64-min",
    "linux-x64": "npm run gulp vscode-linux-x64-min",
    "darwin-arm64": "npm run gulp vscode-darwin-arm64-min",
}

ARTIFACT_GLOBS = {
    "windows-x64": [".build/win32-*/archive/*.zip"],
    "linux-x64": [".build/linux-*/archive/*.tar.gz", ".build/linux-*/archive/*.deb", ".build/linux-*/archive/*.rpm"],
    "darwin-arm64": [".build/darwin-*/archive/*.zip", ".build/darwin-*/archive/*.dmg"],
}

FALLBACK_OUTPUT_DIRS = {
    "windows-x64": "../VSCode-win32-x64",
    "linux-x64": "../VSCode-linux-x64",
    "darwin-arm64": "../VSCode-darwin-arm64",
}


def run(cmd: str, cwd: Path, env: dict[str, str] | None = None) -> None:
    print(f"\n==> {cmd}")
    subprocess.run(cmd, cwd=cwd, env=env, shell=True, check=True)


def patch_copilot_shims_guard(vscode_dir: Path) -> None:
    """Make built-in copilot shim step non-fatal when copilot extension/sdk is absent.

    better-vscode can hide/remove copilot surfaces. Newer vscode build pipeline always
    executes prepareBuiltInCopilotExtensionShims() and throws if sdk folder is missing.
    For debloated builds we skip that hard failure.
    """
    target = vscode_dir / "build" / "lib" / "copilot.ts"
    if not target.exists():
        print(f"[patch] skip copilot guard (missing file): {target}")
        return

    content = target.read_text(encoding="utf-8")
    old = (
        "\tconst copilotBase = path.join(extensionNodeModules, '@github', 'copilot');\n"
        "\tconst copilotSdkBase = path.join(copilotBase, 'sdk');\n"
        "\tif (!fs.existsSync(copilotSdkBase)) {\n"
        "\t\tthrow new Error(`[prepareBuiltInCopilotExtensionShims] Copilot SDK directory not found at ${copilotSdkBase}`);\n"
        "\t}\n"
    )
    new = (
        "\tconst copilotBase = path.join(extensionNodeModules, '@github', 'copilot');\n"
        "\tlet copilotSdkBase = path.join(copilotBase, 'sdk');\n"
        "\tif (!fs.existsSync(copilotSdkBase)) {\n"
        "\t\tconst fallback = path.join(copilotBase, 'copilot-sdk');\n"
        "\t\tif (fs.existsSync(fallback)) {\n"
        "\t\t\tcopilotSdkBase = fallback;\n"
        "\t\t\tconsole.warn(`[prepareBuiltInCopilotExtensionShims] Using fallback copilot SDK dir: ${fallback}`);\n"
        "\t\t} else {\n"
        "\t\t\tconsole.warn(`[prepareBuiltInCopilotExtensionShims] Copilot SDK directory not found at ${copilotSdkBase}. Skipping shim materialization.`);\n"
        "\t\t\treturn;\n"
        "\t\t}\n"
        "\t}\n"
    )

    if old not in content:
        print("[patch] copilot shim guard already patched or upstream changed; skipping")
        return

    target.write_text(content.replace(old, new), encoding="utf-8")
    print(f"[patch] applied copilot shim guard: {target}")


def collect_artifacts(vscode_dir: Path, platform: str, artifact_dir: Path) -> None:
    patterns = ARTIFACT_GLOBS[platform]
    matches: list[Path] = []
    for pattern in patterns:
        found = [Path(p) for p in glob.glob(str(vscode_dir / pattern))]
        matches.extend(found)

    artifact_dir.mkdir(parents=True, exist_ok=True)

    if matches:
        for src in matches:
            dst = artifact_dir / src.name
            shutil.copy2(src, dst)
            print(f"Collected: {src} -> {dst}")
        return

    # Fallback: some builds only produce unpacked app folder (e.g. ../VSCode-win32-x64)
    fallback_rel = FALLBACK_OUTPUT_DIRS.get(platform)
    fallback_dir = (vscode_dir / fallback_rel).resolve() if fallback_rel else None
    if fallback_dir and fallback_dir.exists():
        archive_base = artifact_dir / f"better-vscode-{platform}"
        archive_path = shutil.make_archive(str(archive_base), "zip", root_dir=str(fallback_dir))
        print(f"Collected fallback folder archive: {fallback_dir} -> {archive_path}")
        return

    raise RuntimeError(
        f"No artifacts found for {platform}. Checked patterns: {patterns}. "
        f"Fallback dir checked: {fallback_dir}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build patched VS Code and collect artifacts")
    parser.add_argument("--vscode-dir", required=True, help="Path to vscode checkout")
    parser.add_argument("--platform", choices=sorted(BUILD_COMMANDS.keys()), required=True)
    parser.add_argument("--artifact-dir", required=True, help="Where release artifacts are copied")
    parser.add_argument("--skip-apply", action="store_true", help="Skip applying patches")
    parser.add_argument("--install-command", default="npm install --ignore-scripts && npm install", help="Command used to install dependencies")
    parser.add_argument("--build-command", help="Override platform build command")

    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    vscode_dir = Path(args.vscode_dir).resolve()
    artifact_dir = Path(args.artifact_dir).resolve()

    if not vscode_dir.exists():
        raise FileNotFoundError(f"vscode-dir not found: {vscode_dir}")

    if not args.skip_apply:
        run(f'uv run "{repo_root / "utils" / "patches.py"}" apply "{vscode_dir}"', cwd=repo_root)

    env = os.environ.copy()
    env.setdefault("VSCODE_SKIP_NODE_VERSION_CHECK", "1")
    env["SKIP_WIN32_DEPS_PATCH"] = "1"

    run(args.install_command, cwd=vscode_dir, env=env)

    patch_copilot_shims_guard(vscode_dir)

    build_cmd = args.build_command or BUILD_COMMANDS[args.platform]
    run(build_cmd, cwd=vscode_dir, env=env)

    collect_artifacts(vscode_dir, args.platform, artifact_dir)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"\nCommand failed: {exc.cmd}", file=sys.stderr)
        raise
