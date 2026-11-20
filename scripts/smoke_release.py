"""Verify release checksums, component consistency, git bundle and a clean install from ZIP."""
import argparse
import hashlib
import http.client
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid
from urllib.parse import urlsplit
from zipfile import ZipFile


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def request(port, method, path, data=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.request(method, path, json.dumps(data).encode() if data is not None else None, headers)
        reply = conn.getresponse()
        result = reply.read()
        assert reply.status == 200, (path, reply.status)
        return json.loads(result) if path.startswith("/api/") else result
    finally:
        conn.close()


def check_tree(tree, temp):
    service = subprocess.Popen([sys.executable, "-I", str(tree / "apps/local-service/server.py"),
                                "--port", "0", "--data-dir", str(temp / "live"),
                                "--no-browser", "--json-ready"],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        startup = service.stdout.readline()
        if not startup:
            raise RuntimeError(service.stderr.read())
        ready = json.loads(startup)
        port = urlsplit(ready["base_url"]).port
        token = request(port, "POST", "/api/pair", {"code": ready["code"]})["token"]
        subject = request(port, "POST", "/api/subjects", {"name":"Release smoke", "idempotency_key":str(uuid.uuid4())}, token)
        snapshot = request(port, "GET", "/api/snapshot", token=token)
        assert snapshot["subjects"][0]["subject_id"] == subject["subject_id"]
        assert b'app.js' in request(port, "GET", "/")
        assert request(port, "GET", "/assets/life.webp")[:4] == b"RIFF"
    finally:
        service.terminate()
        service.communicate(timeout=10)


def verify_source_blobs(source_path, repo, revision):
    """Verify paths and exact release bytes against Git objects, independently of the ZIP manifest."""
    git = ["git", "-C", str(repo)]
    tree = subprocess.check_output([*git, "ls-tree", "-rz", revision])
    prefix = "SiliconLifeState/"
    expected = {"RELEASE.txt", "SOURCE-FILES.sha256"}
    counts = {"blobs": 0, "bytes": 0, "crlf_scripts": 0, "excluded_caches": 0}
    digests = {}
    with ZipFile(source_path) as source:
        members = source.namelist()
        if len(set(members)) != len(members):
            raise ValueError("Duplicate member in source ZIP")
        for row in tree.split(b"\0"):
            if not row:
                continue
            header, raw_path = row.split(b"\t", 1)
            mode, kind, oid = header.split()
            name = raw_path.decode("utf-8")
            if kind != b"blob" or mode not in (b"100644", b"100755"):
                raise ValueError(f"Unsupported release object: {name}")
            if name.startswith((".git/", ".work/", ".codex/", "dist/")):
                raise ValueError(f"Private path in release tree: {name}")
            if "__pycache__" in Path(name).parts or name.lower().endswith((".pyc", ".pyo")):
                counts["excluded_caches"] += 1
                continue
            if name in expected or name.lower().endswith((".sqlite3", ".db", ".token", ".env")):
                raise ValueError(f"Unexpected release input: {name}")
            expected.add(name)
            body = subprocess.check_output([*git, "cat-file", "blob", oid.decode("ascii")])
            if name.lower().endswith((".cmd", ".bat")):
                body = body.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
                counts["crlf_scripts"] += 1
            if source.read(prefix + name) != body:
                raise ValueError(f"Source ZIP differs from Git blob {oid.decode('ascii')}: {name}")
            counts["blobs"] += 1
            counts["bytes"] += len(body)
            digests[name] = sha256(body)
        paths = {prefix + name for name in expected}
        if set(members) != paths:
            raise ValueError(f"Source ZIP path mismatch: {sorted(set(members) ^ paths)}")
        digests["RELEASE.txt"] = sha256(source.read(prefix + "RELEASE.txt"))
        manifest = "".join(f"{digests[name]}  {name}\n" for name in sorted(digests)).encode()
        if source.read(prefix + "SOURCE-FILES.sha256") != manifest:
            raise ValueError("Source manifest differs from Git-derived checksums")
    return counts


def verify_component(archive_path, tree, listed, source_prefix, notice_dir=""):
    paths = {name.removeprefix(source_prefix): tree / name for name in listed if name.startswith(source_prefix)}
    paths[notice_dir + "LICENSE.txt"] = tree / "LICENSE"
    paths[notice_dir + "NOTICE"] = tree / "NOTICE"
    with ZipFile(archive_path) as archive:
        members = archive.namelist()
        if len(members) != len(set(members)) or set(members) != set(paths):
            raise ValueError(f"Incorrect file set or duplicate member in {archive_path.name}")
        for name, original in paths.items():
            if archive.read(name) != original.read_bytes():
                raise ValueError(f"Component differs from source: {archive_path.name}/{name}")
    return len(paths)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--tag", help="Require a tagged build of precisely this version")
    args = parser.parse_args()
    release = args.directory.resolve()
    sums = (release / "SHA256SUMS.txt").read_text().splitlines()
    for line in sums:
        digest, name = line.split("  ", 1)
        assert sha256((release / name).read_bytes()) == digest, name
    with tempfile.TemporaryDirectory(prefix="sls-release-smoke-") as tmp:
        tmp = Path(tmp)
        with ZipFile(next(release.glob("*-Windows-x64-Portable.zip"))) as archive:
            archive.extractall(tmp / "full")
        tree = tmp / "full/SiliconLifeState"
        for line in (tree / "SOURCE-FILES.sha256").read_text().splitlines():
            digest, name = line.split("  ", 1)
            assert sha256((tree / name).read_bytes()) == digest, name
        version = (tree / "VERSION").read_text().strip()
        prefix = f"SiliconLifeState-{version}"
        component_names = {prefix + suffix for suffix in ("-Desktop-Pet-Setup.zip", "-Source.zip", "-Chrome.zip", "-Skill.zip", "-Local-Service.zip", "-Windows-x64-Portable.zip")}
        assert component_names == {p.name for p in release.glob("*.zip")}, "Missing or mixed-version component ZIPs"
        with ZipFile(release / f"{prefix}-Source.zip") as source:
            members = set(source.namelist())
            listed = [row.split("  ", 1)[1] for row in (tree / "SOURCE-FILES.sha256").read_text().splitlines()]
            assert members == {"SiliconLifeState/" + name for name in [*listed, "SOURCE-FILES.sha256"]}
            for member in members:
                assert source.read(member) == (tmp / "full" / member).read_bytes(), member
        assert json.loads((tree / "apps/extension/manifest.json").read_text(encoding="utf-8"))["version"] == version
        for output, source in (("RELEASE-NOTES.md", f"RELEASE-{version}.md"), ("RELEASE-AUDIT.md", f"RELEASE-AUDIT-{version}.md")):
            assert (release / output).read_bytes() == (tree / "docs" / source).read_bytes(), output
        check_tree(tree, tmp / "first")
        with ZipFile(release / f"{prefix}-Desktop-Pet-Setup.zip") as pet:
            names = {name.removeprefix("apps/desktop-pet/") for name in listed if name.startswith("apps/desktop-pet/")}
            assert set(pet.namelist()) == names | {"SiliconLifePet.exe","LICENSE.txt","NOTICE"}
            for name in names | {"SiliconLifePet.exe"}:
                assert pet.read(name) == (tree / "apps/desktop-pet" / name).read_bytes()
            assert pet.read("LICENSE.txt") == (tree / "LICENSE").read_bytes() and pet.read("NOTICE") == (tree / "NOTICE").read_bytes()
        chrome_members = verify_component(release / f"{prefix}-Chrome.zip", tree, listed, "apps/extension/")
        skill_members = verify_component(release / f"{prefix}-Skill.zip", tree, listed, "packages/agent-skill/", "silicon-life-state/")
        with ZipFile(next(release.glob("*-Local-Service.zip"))) as archive:
            archive.extractall(tmp / "component")
        check_tree(tmp / "component/SiliconLifeState", tmp / "second")
        release_assets = tree / "release"
        for line in (release_assets / "SHA256SUMS.txt").read_text().splitlines():
            expected, name = line.split("  ", 1)
            component = (release_assets / name).read_bytes()
            assert sha256(component) == expected, name
            if name.endswith(".zip"):
                assert component == (release / name).read_bytes(), name
        bundle = release_assets / "SiliconLifeState.git.bundle"
        runtime = tree / "runtime"
        manifest = json.loads((runtime / "SLS-RUNTIME.json").read_text())
        assert (runtime / "python.exe").read_bytes()[:2] == b"MZ"
        assert (runtime / "LICENSE.txt").is_file() and (tree / "Reconnect-Windows.cmd").is_file()
        for name, digest in manifest["files_sha256"].items():
            assert sha256((runtime / name).read_bytes()) == digest, name
        git_dir = tmp / "git-test"
        subprocess.run(["git", "clone", "-q", str(bundle), str(git_dir)], check=True)
        prefix = ["git", "-C", str(git_dir)]
        assert subprocess.check_output(prefix + ["branch", "--show-current"]).decode().strip() == "main"
        tag = "v" + (tree / "VERSION").read_text().strip()
        actual_sha = subprocess.check_output(prefix + ["rev-parse", "HEAD"], text=True).strip()
        tag_sha = subprocess.check_output(prefix + ["rev-parse", tag + "^{commit}"], text=True).strip()
        metadata = (tree / "RELEASE.txt").read_text()
        if args.tag:
            assert tag == args.tag and "Build: tagged" in metadata.splitlines()
        if "Build: candidate" in metadata.splitlines():
            assert f"Historical tag: {tag} ({tag_sha})" in metadata.splitlines()
            subprocess.run(prefix + ["merge-base", "--is-ancestor", tag_sha, actual_sha], check=True)
        else:
            assert actual_sha == tag_sha and f"Release tag: {tag}" in metadata.splitlines()
        subprocess.run(prefix + ["merge-base", "--is-ancestor", "v1.0.0", tag], check=True)
        assert (git_dir / "Start-Windows.cmd").is_file()
        assert "Git commit: " + actual_sha in (tree / "RELEASE.txt").read_text()
        revision = actual_sha if "Build: candidate" in metadata.splitlines() else tag_sha
        verified = verify_source_blobs(release / f"SiliconLifeState-{version}-Source.zip", git_dir, revision)
    print(f"Source ZIP vs bundle commit {revision}: {verified['blobs']} Git blobs, "
          f"{verified['bytes']} bytes, {verified['crlf_scripts']} CRLF scripts, "
          f"{verified['excluded_caches']} excluded caches, 2 generated metadata files")
    print(f"PASS · {len(sums)} hashes · complete ZIP + standalone service cold starts · Chrome ({chrome_members}) + SKILL ({skill_members}) match including LICENSE and NOTICE · bundled x64 runtime integrity · git clone default main {actual_sha}")


if __name__ == "__main__":
    main()
