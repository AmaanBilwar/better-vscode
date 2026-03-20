#!/usr/bin/env python3
"""better-vscode patch management tooling."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
PATCHES_DIR = REPO_DIR / "patches"
SERIES_FILE = PATCHES_DIR / "series"


def log(msg, color=None):
    colors = {
        "cyan": "\033[96m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "red": "\033[91m",
        "dim": "\033[90m",
        "reset": "\033[0m",
    }
    prefix = colors.get(color, "")
    suffix = colors.get("reset", "") if color else ""
    print(f"{prefix}{msg}{suffix}")


def find_patch_binary():
    env = os.environ.get("PATCH_BIN")
    if env:
        p = Path(env)
        if p.exists():
            return str(p)
        which = shutil.which(env)
        if which:
            return which

    which = shutil.which("patch")
    if which:
        return which
    raise SystemExit("GNU patch not found. Install it or set PATCH_BIN env var.")


def parse_series():
    if not SERIES_FILE.exists():
        raise SystemExit(f"Series file not found: {SERIES_FILE}")
    lines = SERIES_FILE.read_text().splitlines()
    return [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]


def run_patch(patch_path, tree_path, reverse=False, dry_run=False, fuzz=True):
    patch_bin = find_patch_binary()
    cmd = [
        patch_bin,
        "-p1",
        "--ignore-whitespace",
        "-i",
        str(patch_path),
        "-d",
        str(tree_path),
        "--no-backup-if-mismatch",
    ]
    if reverse:
        cmd.append("--reverse")
    else:
        cmd.append("--forward")
    if dry_run:
        cmd.append("--dry-run")
    if not fuzz:
        cmd.append("--fuzz=0")

    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def cmd_apply(args):
    target = Path(args.target).resolve()
    if not target.is_dir():
        raise SystemExit(f"Target directory not found: {target}")

    series = parse_series()
    if args.reverse:
        series = list(reversed(series))

    total = len(series)
    failed = []

    for i, patch_rel in enumerate(series, 1):
        patch_path = PATCHES_DIR / patch_rel
        verb = "Reversing" if args.reverse else "Applying"
        dry = " (dry run)" if args.dry_run else ""

        if not patch_path.exists():
            log(f"[{i}/{total}] PATCH NOT FOUND: {patch_rel}", "red")
            failed.append(patch_rel)
            continue

        log(f"[{i}/{total}] {verb} {patch_rel}{dry}", "cyan")
        rc, stdout, stderr = run_patch(
            patch_path,
            target,
            reverse=args.reverse,
            dry_run=args.dry_run,
            fuzz=args.fuzz,
        )

        if rc != 0:
            log(f"  FAILED: {patch_rel}", "red")
            if not args.dry_run and (stdout or stderr):
                log(f"  Output:\n{stdout}{stderr}", "yellow")
            failed.append(patch_rel)

    if failed:
        log(f"\nFAILED PATCHES ({len(failed)}/{total}):", "red")
        for f in failed:
            log(f"  - {f}", "red")
        log(
            f'\nRun: python utils/patches.py apply --reverse "{target}" to undo applied patches.',
            "yellow",
        )
        sys.exit(1)
    else:
        log(f"\nAll {total} patches applied successfully.", "green")


def cmd_generate(args):
    target = Path(args.target).resolve()
    if not target.is_dir():
        raise SystemExit(f"Target directory not found: {target}")

    name = args.name
    if not name.endswith(".patch"):
        name += ".patch"

    if any(c in name for c in "\\ :"):
        raise SystemExit(f"Invalid patch name: {name}")

    patch_path = PATCHES_DIR / name
    if patch_path.exists() and not args.force:
        resp = (
            input(f"Patch '{name}' already exists. Overwrite? (y/N) ").strip().lower()
        )
        if resp != "y":
            return

    # Check git repo
    result = subprocess.run(
        ["git", "status", "--porcelain"], cwd=target, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise SystemExit(f"Not a git repo: {target}")

    if result.stdout.strip() == "":
        log("No changes detected. Nothing to generate.", "yellow")
        return

    # Generate diff
    diff_result = subprocess.run(
        ["git", "diff", "HEAD"], cwd=target, capture_output=True, text=True
    )
    if not diff_result.stdout.strip():
        log("No changes to generate.", "yellow")
        return

    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(diff_result.stdout, encoding="utf-8")
    log(f"Generated: {patch_path}", "green")

    # Update series file
    series = parse_series()
    if name not in series:
        with open(SERIES_FILE, "a") as f:
            f.write(name + "\n")
        log(f"Added to series: {name}", "green")
    else:
        log(f"Already in series: {name}", "yellow")

    # Show summary
    stat = subprocess.run(
        ["git", "diff", "--stat", "HEAD"], cwd=target, capture_output=True, text=True
    )
    log("\nChanges in patch:", "cyan")
    print(stat.stdout)


def cmd_sync(args):
    target = Path(args.vscode_dir).resolve()
    if not target.is_dir():
        raise SystemExit(f"VS Code directory not found: {target}")

    branch = args.branch

    # Check upstream remote
    remotes = subprocess.run(
        ["git", "remote"], cwd=target, capture_output=True, text=True
    )
    if "upstream" not in remotes.stdout:
        raise SystemExit(
            "No 'upstream' remote. Run:\n"
            "  git remote add upstream https://github.com/microsoft/vscode.git"
        )

    log("Fetching upstream...", "cyan")
    subprocess.run(["git", "fetch", "upstream"], cwd=target, check=True)

    log(f"Resetting {branch} to upstream/{branch}...", "cyan")
    subprocess.run(["git", "checkout", branch], cwd=target, check=True)
    subprocess.run(
        ["git", "reset", "--hard", f"upstream/{branch}"], cwd=target, check=True
    )

    if args.force_push:
        log("Pushing to origin...", "cyan")
        subprocess.run(
            ["git", "push", "origin", branch, "--force"], cwd=target, check=True
        )
    else:
        log("Skipped push to origin. Run manually if needed:", "yellow")
        log(f"  git push origin {branch} --force", "dim")

    log("\nFork synced with upstream.", "green")
    log("Now apply patches:", "cyan")
    log(f'  python utils/patches.py apply "{target}"', "dim")
    log("\nIf patches fail, fix them in the vscode dir, then regenerate:", "yellow")
    log('  python utils/patches.py generate --target "..." --name <name>', "dim")


def cmd_list(args):
    series = parse_series()
    if not series:
        log("No patches in series.", "yellow")
        return

    for i, patch in enumerate(series, 1):
        path = PATCHES_DIR / patch
        status = "ok" if path.exists() else "MISSING"
        color = "green" if path.exists() else "red"
        log(f"  {i:3d}. [{status}] {patch}", color)


def main():
    parser = argparse.ArgumentParser(description="better-vscode patch tooling")
    sub = parser.add_subparsers(dest="command")

    # apply
    p_apply = sub.add_parser("apply", help="Apply patches from series to target tree")
    p_apply.add_argument("target", help="Directory tree to patch")
    p_apply.add_argument("--reverse", action="store_true", help="Reverse patches")
    p_apply.add_argument("--dry-run", action="store_true", help="Dry run only")
    p_apply.add_argument("--fuzz", action=argparse.BooleanOptionalAction, default=True)

    # generate
    p_gen = sub.add_parser("generate", help="Generate a patch from working changes")
    p_gen.add_argument("--target", required=True, help="VS Code source tree")
    p_gen.add_argument(
        "--name", required=True, help="Patch name (e.g., 'remove-telemetry')"
    )
    p_gen.add_argument("--force", action="store_true", help="Overwrite existing patch")

    # sync
    p_sync = sub.add_parser("sync", help="Sync fork with upstream microsoft/vscode")
    p_sync.add_argument("--vscode-dir", required=True, help="Path to vscode fork")
    p_sync.add_argument("--branch", default="main", help="Branch name (default: main)")
    p_sync.add_argument(
        "--force-push", action="store_true", help="Push to origin after reset"
    )

    # list
    p_list = sub.add_parser("list", help="List patches in series")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    {"apply": cmd_apply, "generate": cmd_generate, "sync": cmd_sync, "list": cmd_list}[
        args.command
    ](args)


if __name__ == "__main__":
    main()
