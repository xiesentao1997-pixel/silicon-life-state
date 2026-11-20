"""Resume an interrupted GitHub pre-release by uploading only verified, missing assets."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


def gh(*args):
    return subprocess.check_output(["gh", *map(str, args)])


def view(tag):
    fields = "tagName,isDraft,isPrerelease,assets,url"
    return json.loads(gh("release", "view", tag, "--json", fields))


def publish(tag, directory):
    sums = directory / "SHA256SUMS.txt"
    expected = {}
    for line in sums.read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        if Path(name).name != name or name in expected:
            raise ValueError(f"Invalid asset name in manifest: {name}")
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Local asset digest mismatch: {name}")
        expected[name] = digest
    expected[sums.name] = hashlib.sha256(sums.read_bytes()).hexdigest()
    if set(expected) != {p.name for p in directory.iterdir()}:
        raise ValueError("Release asset directory and manifest disagree")

    try:
        release = view(tag)
    except subprocess.CalledProcessError:
        # --verify-tag and GitHub's one-release-per-tag rule also protect retries
        # if a lookup or a previous create returned a transient network failure.
        gh("release", "create", tag, "--verify-tag", "--draft", "--prerelease",
           "--title", f"Silicon Life State {tag}", "--notes-file", directory / "RELEASE-NOTES.md")
        release = view(tag)

    def missing_assets(current):
        if current["tagName"] != tag:
            raise ValueError("Release tag mismatch")
        missing = dict(expected)
        for asset in current["assets"]:
            name = asset["name"]
            if name not in missing:
                raise ValueError(f"Unexpected remote asset: {name}")
            # Download and verify the exact bytes. This also works with GitHub CLI
            # versions that do not expose the server's optional asset digest.
            with tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp) / "asset"
                gh("release", "download", tag, "--pattern", name, "--output", target)
                if hashlib.sha256(target.read_bytes()).hexdigest() != missing.pop(name):
                    raise ValueError(f"Remote asset digest mismatch: {name}")
        return sorted(missing)

    missing = missing_assets(release)
    if not release["isDraft"]:
        if missing or not release["isPrerelease"]:
            raise ValueError(f"Existing published release does not match expected pre-release state or assets: {missing}")
        print("Verified existing release:", release["url"])
        return
    if missing:
        gh("release", "upload", tag, *(directory / name for name in missing))
        if missing_assets(view(tag)):
            raise ValueError("Remote upload incomplete")

    gh("release", "edit", tag, "--draft=false", "--prerelease", "--latest=false",
       "--verify-tag", "--notes-file", directory / "RELEASE-NOTES.md")
    result = view(tag)
    if result["isDraft"] or not result["isPrerelease"]:
        raise RuntimeError("GitHub did not confirm pre-release publication")
    print("Published verified pre-release:", result["url"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    if args.tag != "v1.0.4" or os.environ.get("GH_REPO") != "xiesentao1997-pixel/silicon-life-state":
        parser.error("This release targets v1.0.4 in xiesentao1997-pixel/silicon-life-state")
    publish(args.tag, args.directory.resolve())
