"""Fetch or inspect the pinned, unmodified Windows x64 embeddable CPython archive."""
import argparse
import hashlib
import io
import json
import os
import struct
import tempfile
import zipfile
from pathlib import Path
from urllib.request import urlopen


VERSION = "3.14.10"
FILENAME = f"python-{VERSION}-embed-amd64.zip"
URL = f"https://www.python.org/ftp/python/{VERSION}/{FILENAME}"
RELEASE_PAGE = "https://www.python.org/downloads/release/python-31410/"
SHA256 = "90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159"
ARCHIVE_SIZE = 12_619_664
DEFAULT_ARCHIVE = Path(__file__).resolve().parents[1] / ".work" / "portable" / FILENAME


def digest(data):
    return hashlib.sha256(data).hexdigest()


def check_x64_pe(data, name):
    if len(data) < 64 or data[:2] != b"MZ":
        raise ValueError(f"{name} does not contain a Windows executable header")
    pos = struct.unpack_from("<I", data, 60)[0]
    if pos + 26 > len(data) or data[pos:pos + 4] != b"PE\0\0":
        raise ValueError(f"Missing PE header in {name}")
    machine = struct.unpack_from("<H", data, pos + 4)[0]
    optional_header = struct.unpack_from("<H", data, pos + 24)[0]
    if (machine, optional_header) != (0x8664, 0x020B):
        raise ValueError(f"{name} is not an AMD64 PE32+ image")


def checked_archive(data):
    if len(data) != ARCHIVE_SIZE or digest(data) != SHA256:
        raise ValueError(f"Official {FILENAME} size or SHA-256 verification failed")
    return data


def fetch_archive(path):
    """Only accept the single official release. Publish a complete verified download atomically."""
    if path.exists():
        checked_archive(path.read_bytes())
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(URL, timeout=90) as response:
        if response.geturl() != URL:
            raise ValueError("The pinned Python.org URL changed; verify the release before updating it")
        data = checked_archive(response.read(ARCHIVE_SIZE + 1))
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".part", delete=False) as stage:
        stage_path = Path(stage.name)
        try:
            stage.write(data)
            stage.flush()
            os.fsync(stage.fileno())
        except BaseException:
            stage.close()
            stage_path.unlink(missing_ok=True)
            raise
    try:
        os.replace(stage_path, path)
    finally:
        stage_path.unlink(missing_ok=True)


def portable_files(archive):
    """Map runtime/ paths to exact official file bytes, plus local provenance metadata."""
    data = checked_archive(Path(archive).read_bytes())
    with zipfile.ZipFile(io.BytesIO(data)) as runtime:
        names = runtime.namelist()
        if len(set(names)) != len(names) or any(Path(n).name != n or "\\" in n or ":" in n for n in names):
            raise ValueError("Unexpected paths in embeddable release")
        required = {"python.exe", "pythonw.exe", "python314.dll", "python314.zip", "python314._pth",
                    "LICENSE.txt", "_sqlite3.pyd", "sqlite3.dll", "_ssl.pyd", "_socket.pyd", "python.cat"}
        if required - set(names):
            raise ValueError(f"Missing official runtime files: {sorted(required - set(names))}")
        blobs = {name: runtime.read(name) for name in names}
    for name, body in blobs.items():
        if name.lower().endswith((".dll", ".exe", ".pyd")):
            check_x64_pe(body, name)
    if b"PYTHON SOFTWARE FOUNDATION LICENSE" not in blobs["LICENSE.txt"].upper():
        raise ValueError("Missing official Python license")
    manifest = {"name": "CPython Windows embeddable package", "version": VERSION,
                "architecture": "AMD64", "archive": FILENAME, "archive_size": len(data),
                "archive_sha256": SHA256, "official_release": RELEASE_PAGE, "source_url": URL,
                "license_file": "LICENSE.txt", "files_sha256": {n: digest(blobs[n]) for n in sorted(blobs)}}
    files = {"runtime/" + n: b for n, b in blobs.items()}
    files["runtime/SLS-RUNTIME.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--fetch", action="store_true", help="download this exact version when the ZIP is missing")
    parser.add_argument("--stage", type=Path, help="create runtime/ under an empty installation staging path")
    args = parser.parse_args()
    if args.fetch:
        fetch_archive(args.archive)
    files = portable_files(args.archive)
    if args.stage:
        target = args.stage / "runtime"
        target.mkdir(parents=True, exist_ok=False)
        for name, body in files.items():
            (args.stage / name).write_bytes(body)
    print(f"PASS {FILENAME} · {SHA256} · {len(files) - 1} original files including license")


if __name__ == "__main__":
    main()
