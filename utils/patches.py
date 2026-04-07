#!/usr/bin/env python3
"""better-vscode patch management tooling."""

import argparse
import os
import re
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


def _slugify(text):
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip()).strip("-").lower()
    return slug or "patch"


def _split_diff_sections(diff_text):
    lines = diff_text.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.startswith("diff --git ")]
    if not starts:
        return []

    starts.append(len(lines))
    sections = []
    for i in range(len(starts) - 1):
        sections.append(lines[starts[i] : starts[i + 1]])
    return sections


def _section_path(section_lines):
    if not section_lines:
        return "unknown"

    first = section_lines[0].strip()
    # Example: diff --git a/src/foo.ts b/src/foo.ts
    if first.startswith("diff --git "):
        parts = first.split()
        if len(parts) >= 4 and parts[3].startswith("b/"):
            return parts[3][2:]
    return "unknown"


def _split_section_hunks(section_lines):
    hunk_starts = [
        i
        for i, line in enumerate(section_lines)
        if line.startswith("@@ ") or line.startswith("@@@ ")
    ]
    if not hunk_starts:
        return [section_lines]

    prefix = section_lines[: hunk_starts[0]]
    hunks = []
    for i, start in enumerate(hunk_starts):
        end = hunk_starts[i + 1] if i + 1 < len(hunk_starts) else len(section_lines)
        hunks.append(prefix + section_lines[start:end])
    return hunks


def _build_split_patches(diff_text, base_name, split_mode):
    sections = _split_diff_sections(diff_text)
    if not sections:
        return []

    entries = []
    counter = 1
    for section in sections:
        rel_path = _section_path(section)
        rel_slug = _slugify(rel_path)

        parts = [section] if split_mode == "file" else _split_section_hunks(section)
        part_total = len(parts)
        for part_index, part_lines in enumerate(parts, 1):
            if split_mode == "hunk":
                suffix = (
                    f"{counter:03d}-{rel_slug}-h{part_index:02d}-of-{part_total:02d}"
                )
            else:
                suffix = f"{counter:03d}-{rel_slug}"

            patch_name = f"{base_name}-{suffix}.patch"
            entries.append((patch_name, "".join(part_lines)))
            counter += 1

    return entries


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


def _check_clean_tree(target):
    """Ensure working tree has no uncommitted changes."""
    result = subprocess.run(
        ["git", "status", "--porcelain"], cwd=target, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise SystemExit(f"Not a git repo: {target}")
    if result.stdout.strip():
        log("Working tree has uncommitted changes. Commit or stash first.", "red")
        sys.exit(1)


def _apply_baseline(target, series):
    """Apply existing patches and commit as baseline. Returns True if baseline was created."""
    if not series:
        return False

    log("Applying existing patches as baseline...", "cyan")
    failed = []
    for i, patch_rel in enumerate(series, 1):
        patch_file = PATCHES_DIR / patch_rel
        if not patch_file.exists():
            log(f"  [{i}/{len(series)}] MISSING: {patch_rel}", "red")
            failed.append(patch_rel)
            continue
        log(f"  [{i}/{len(series)}] {patch_rel}", "dim")
        rc, _, _ = run_patch(patch_file, target, fuzz=True)
        if rc != 0:
            log(f"  FAILED: {patch_rel}", "red")
            failed.append(patch_rel)
    if failed:
        log("Baseline patches failed. Fix them first.", "red")
        sys.exit(1)

    subprocess.run(["git", "add", "-A"], cwd=target, capture_output=True, text=True)
    subprocess.run(
        ["git", "commit", "-m", "temp: baseline for patch generation", "--no-verify"],
        cwd=target,
        capture_output=True,
        text=True,
    )
    log("Baseline committed.", "green")
    return True


def _reset_baseline(target, series):
    """Revert baseline commit and reverse patches to restore original state."""
    log("Resetting to original state...", "dim")
    subprocess.run(
        ["git", "reset", "--hard", "HEAD~1"], cwd=target, capture_output=True, text=True
    )
    for patch_rel in reversed(series):
        patch_file = PATCHES_DIR / patch_rel
        if patch_file.exists():
            run_patch(patch_file, target, reverse=True)
    subprocess.run(
        ["git", "checkout", "--", "."], cwd=target, capture_output=True, text=True
    )
    subprocess.run(["git", "clean", "-fd"], cwd=target, capture_output=True, text=True)
    log("Tree reset to original state.", "green")


def cmd_setup(args):
    """Apply existing patches and commit as baseline for patch generation."""
    target = Path(args.target).resolve()
    if not target.is_dir():
        raise SystemExit(f"Target directory not found: {target}")

    _check_clean_tree(target)

    series = parse_series()
    if not series:
        log("No patches in series. Nothing to set up.", "yellow")
        return

    _apply_baseline(target, series)
    log("\nReady. Make your changes, then run:", "cyan")
    log(
        f'  uv run utils/patches.py generate --target "{args.target}" --name <name>',
        "dim",
    )


def cmd_teardown(args):
    """Reset tree back to original state (undo setup)."""
    target = Path(args.target).resolve()
    if not target.is_dir():
        raise SystemExit(f"Target directory not found: {target}")

    series = parse_series()
    _reset_baseline(target, series)


def cmd_generate(args):
    """Generate a patch from working changes against the baseline."""
    target = Path(args.target).resolve()
    if not target.is_dir():
        raise SystemExit(f"Target directory not found: {target}")

    name = args.name
    split_mode = args.split
    if any(c in name for c in "\\ :"):
        raise SystemExit(f"Invalid patch name: {name}")

    # Check we're on the baseline commit (i.e., setup was run)
    log_result = subprocess.run(
        ["git", "log", "-1", "--format=%s"], cwd=target, capture_output=True, text=True
    )
    on_baseline = "temp: baseline for patch generation" in log_result.stdout

    if not on_baseline:
        log("No baseline commit found. Run setup first:", "red")
        log(f'  uv run utils/patches.py setup --target "{args.target}"', "yellow")
        sys.exit(1)

    # Generate diff from baseline
    diff_result = subprocess.run(
        ["git", "diff", "HEAD"], cwd=target, capture_output=True, text=True
    )
    if not diff_result.stdout.strip():
        log("No changes detected. Nothing to generate.", "yellow")
        series = parse_series()
        _reset_baseline(target, series)
        return

    patches_to_write = []
    if split_mode == "none":
        final_name = name if name.endswith(".patch") else f"{name}.patch"
        patches_to_write = [(final_name, diff_result.stdout)]
    else:
        base_name = name[:-6] if name.endswith(".patch") else name
        patches_to_write = _build_split_patches(
            diff_result.stdout, base_name, split_mode
        )
        if not patches_to_write:
            log("No split patches were produced.", "yellow")
            series = parse_series()
            _reset_baseline(target, series)
            return

    existing = []
    for patch_name, _ in patches_to_write:
        patch_path = PATCHES_DIR / patch_name
        if patch_path.exists():
            existing.append(patch_name)

    if existing and not args.force:
        log("Patch file(s) already exist. Use --force to overwrite:", "red")
        for patch_name in existing:
            log(f"  - {patch_name}", "red")
        series = parse_series()
        _reset_baseline(target, series)
        sys.exit(1)

    generated_names = []
    for patch_name, patch_text in patches_to_write:
        patch_path = PATCHES_DIR / patch_name
        patch_path.parent.mkdir(parents=True, exist_ok=True)
        patch_path.write_text(patch_text, encoding="utf-8")
        generated_names.append(patch_name)
        log(f"Generated: {patch_path}", "green")

    # Update series file
    series = parse_series()
    with open(SERIES_FILE, "a") as f:
        for patch_name in generated_names:
            if patch_name not in series:
                f.write(patch_name + "\n")
                log(f"Added to series: {patch_name}", "green")
            else:
                log(f"Already in series: {patch_name}", "yellow")

    # Show summary
    stat = subprocess.run(
        ["git", "diff", "--stat", "HEAD"], cwd=target, capture_output=True, text=True
    )
    log("\nChanges in patch:", "cyan")
    print(stat.stdout)

    # Reset tree
    _reset_baseline(target, series)


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

    # setup
    p_setup = sub.add_parser(
        "setup", help="Apply patches and commit as baseline for generating a new patch"
    )
    p_setup.add_argument("--target", required=True, help="VS Code source tree")

    # generate
    p_gen = sub.add_parser(
        "generate",
        help="Generate a patch from working changes (run after 'setup', before 'teardown')",
    )
    p_gen.add_argument("--target", required=True, help="VS Code source tree")
    p_gen.add_argument(
        "--name",
        required=True,
        help="Patch name or prefix (e.g., 'ai/remove-telemetry')",
    )
    p_gen.add_argument(
        "--split",
        choices=["none", "file", "hunk"],
        default="none",
        help="Split generated output into separate patches by file or hunk",
    )
    p_gen.add_argument("--force", action="store_true", help="Overwrite existing patch")

    # teardown
    p_teardown = sub.add_parser(
        "teardown", help="Reset tree back to original state (undo setup)"
    )
    p_teardown.add_argument("--target", required=True, help="VS Code source tree")

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

    {
        "apply": cmd_apply,
        "setup": cmd_setup,
        "generate": cmd_generate,
        "teardown": cmd_teardown,
        "sync": cmd_sync,
        "list": cmd_list,
    }[args.command](args)


if __name__ == "__main__":
    main()
