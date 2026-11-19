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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    release = args.directory.resolve()
    sums = (release / "SHA256SUMS.txt").read_text().splitlines()
    for line in sums:
        digest, name = line.split("  ", 1)
        assert sha256((release / name).read_bytes()) == digest, name
    with tempfile.TemporaryDirectory(prefix="sls-release-smoke-") as tmp:
        tmp = Path(tmp)
        with ZipFile(next(release.glob("*-All-in-One.zip"))) as archive:
            archive.extractall(tmp / "full")
        tree = tmp / "full/SiliconLifeState"
        for line in (tree / "SOURCE-FILES.sha256").read_text().splitlines():
            digest, name = line.split("  ", 1)
            assert sha256((tree / name).read_bytes()) == digest, name
        check_tree(tree, tmp / "first")
        for suffix, base in (("-Chrome.zip","apps/extension"),("-Skill.zip","packages/agent-skill")):
            with ZipFile(next(release.glob("*"+suffix))) as archive:
                for name in archive.namelist():
                    if Path(name).name != "LICENSE.txt":
                        assert archive.read(name) == (tree / base / name).read_bytes(), name
        with ZipFile(next(release.glob("*-Local-Service.zip"))) as archive:
            archive.extractall(tmp / "component")
        check_tree(tmp / "component/SiliconLifeState", tmp / "second")
        bundle = tree / "release/SiliconLifeState.git.bundle"
        git_dir = tmp / "git-test"
        subprocess.run(["git","init","-q",str(git_dir)],check=True)
        prefix = ["git","-C",str(git_dir)]
        subprocess.run(prefix+["bundle","verify",str(bundle)],check=True,stdout=subprocess.DEVNULL)
        tag = "v" + (tree / "VERSION").read_text().strip()
        subprocess.run(prefix+["fetch","-q",str(bundle),f"refs/tags/{tag}:refs/tags/{tag}"],check=True)
        actual_sha = subprocess.check_output(prefix+["rev-parse",tag+"^{commit}"]).decode().strip()
        assert "Git commit: " + actual_sha in (tree / "RELEASE.txt").read_text()
    print(f"PASS · {len(sums)} hashes · complete ZIP + standalone service cold starts · extension + SKILL match · Git bundle/tag {actual_sha}")


if __name__ == "__main__":
    main()
