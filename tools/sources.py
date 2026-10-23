#!/usr/bin/env python3
"""Fetch exact audit inputs without changing existing work or following branches."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(path, *args, capture=True, check=True):
    return subprocess.run(
        ["git", "-C", str(path), *args], check=check, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def entries():
    lock = json.loads((ROOT / "sources.lock.json").read_text())
    if lock.get("schema") != 1:
        raise ValueError("Unsupported lock schema")
    seen = set()
    for entry in lock["sources"]:
        name = entry["name"]
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name) or name in seen:
            raise ValueError(f"Invalid or duplicate source name: {name}")
        seen.add(name)
        if not re.fullmatch(r"[0-9a-f]{40}", entry["commit"]):
            raise ValueError(f"Expected a full commit ID for {name}")
        if not (re.fullmatch(r"https://github\.com/[\w.-]+/[\w.-]+\.git", entry["url"])
                or entry["url"] == "https://git.yoctoproject.org/opkg"):
            raise ValueError(f"Unexpected source URL for {name}")
        for path in entry.get("sparse", []):
            if path.startswith("/") or any(p in ("..", ".") for p in path.split("/")):
                raise ValueError(f"Invalid sparse path: {path}")
    return lock["sources"]


def process(entry, fetch):
    source_root = ROOT / "sources"
    if source_root.is_symlink():
        raise ValueError("sources/ must not be a symlink")
    path = source_root / entry["name"]
    if path.is_symlink():
        raise ValueError(f"Refusing symlink: {path}")
    if not path.exists():
        if not fetch:
            raise ValueError(f"Missing {entry['name']}; run make sources")
        path.mkdir(parents=True)
        git(path, "init", "--quiet")
        git(path, "remote", "add", "origin", entry["url"])
    if not (path / ".git").is_dir():
        raise ValueError(f"Not a managed checkout: {path}")
    if git(path, "remote", "get-url", "origin").stdout.strip() != entry["url"]:
        raise ValueError(f"Unexpected origin in {path}")
    if git(path, "status", "--porcelain", "--untracked-files=all").stdout:
        raise ValueError(f"Local changes in {path}; leaving them intact")
    head = git(path, "rev-parse", "--verify", "HEAD", check=False)
    if head.returncode == 0:
        if head.stdout.strip() != entry["commit"]:
            raise ValueError(f"Different HEAD in {path}; refusing to reset it")
    elif fetch:
        print(f"Fetching {entry['name']} at {entry['commit'][:12]}", flush=True)
        git(path, "config", "remote.origin.promisor", "true")
        git(path, "config", "remote.origin.partialclonefilter", "blob:none")
        git(path, "fetch", "--quiet", "--depth=1", "--filter=blob:none", "--no-tags",
            "origin", entry["commit"], capture=False)
        if entry.get("sparse"):
            git(path, "sparse-checkout", "init", "--cone")
            git(path, "sparse-checkout", "set", "--", *entry["sparse"])
        git(path, "checkout", "--quiet", "--detach", entry["commit"], capture=False)
    else:
        raise ValueError(f"Incomplete checkout: {path}")
    if git(path, "rev-parse", "HEAD").stdout.strip() != entry["commit"]:
        raise ValueError(f"Revision verification failed: {path}")
    print(f"OK {entry['name']}: {entry['commit']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("fetch", "verify"))
    parser.add_argument("names", nargs="*", help="Selected names; default is all sources")
    args = parser.parse_args()
    sources = entries()
    unknown = set(args.names) - {e["name"] for e in sources}
    if unknown:
        parser.error(f"Unknown source names: {', '.join(sorted(unknown))}")
    failed = False
    for entry in sources:
        if args.names and entry["name"] not in args.names:
            continue
        try:
            process(entry, args.action == "fetch")
        except (ValueError, OSError, subprocess.CalledProcessError) as error:
            print(f"ERROR: {error}", file=sys.stderr)
            if isinstance(error, subprocess.CalledProcessError) and error.stderr:
                print(error.stderr, file=sys.stderr)
            failed = True
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
