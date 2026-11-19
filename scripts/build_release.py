"""Package a tagged commit without local databases, credentials or working files."""
import argparse
import hashlib
import io
from pathlib import Path
import subprocess
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from windows_runtime import DEFAULT_ARCHIVE, fetch_archive, portable_files

ROOT = Path(__file__).resolve().parents[1]


def git(*arguments):
    return subprocess.check_output(["git", "-C", str(ROOT), *arguments])


def archive(files, folder=""):
    stream = io.BytesIO()
    with ZipFile(stream, "w", compression=ZIP_DEFLATED, compresslevel=9) as out:
        for name, body in sorted(files.items()):
            entry = ZipInfo(folder + name, date_time=(2026, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = (0o100755 if name.endswith(".sh") else 0o100644) << 16
            entry.compress_type = ZIP_DEFLATED
            out.writestr(entry, body)
    return stream.getvalue()


def checksum(files):
    return "".join(f"{hashlib.sha256(body).hexdigest()}  {name}\n" for name, body in sorted(files.items())).encode()


def make_bundle(sha, target, temp_dir):
    """Export only the release ancestry, with a cloneable default main branch."""
    staging = Path(temp_dir) / "refs.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(staging)], check=True)
    tags = git("tag", "--merged", sha).decode().splitlines()
    refs = [f"refs/tags/{name}:refs/tags/{name}" for name in tags]
    staged = ["git", "-C", str(staging)]
    subprocess.run(staged + ["fetch", "-q", "--no-tags", str(ROOT),
                              f"{sha}:refs/heads/main", *refs], check=True)
    subprocess.run(staged + ["bundle", "create", str(target), "HEAD", "refs/heads/main", "--tags"], check=True)
    subprocess.run(staged + ["bundle", "verify", str(target)], check=True, stdout=subprocess.DEVNULL)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--windows-runtime", type=Path, default=DEFAULT_ARCHIVE,
                        help="Pinned official CPython Windows AMD64 embeddable ZIP")
    parser.add_argument("--fetch-runtime", action="store_true",
                        help="Fetch the pinned Python.org archive if absent")
    args = parser.parse_args()
    sha = git("rev-parse", "--verify", args.ref + "^{commit}").decode().strip()
    version = git("show", sha + ":VERSION").decode().strip()
    tag = "v" + version
    if git("rev-parse", tag + "^{commit}").decode().strip() != sha:
        parser.error(f"Tag {tag} must identify the requested commit")
    if args.fetch_runtime:
        fetch_archive(args.windows_runtime)
    if not args.windows_runtime.is_file():
        parser.error("Windows runtime missing. Pass --fetch-runtime or --windows-runtime PATH.")
    runtime = portable_files(args.windows_runtime)
    files = {}
    for line in git("ls-tree", "-rz", sha).split(b"\0"):
        if not line:
            continue
        header, path = line.split(b"\t", 1)
        mode, kind, object_id = header.split(b" ")
        if kind != b"blob" or mode not in (b"100644", b"100755"):
            raise ValueError("Unexpected Git object at " + path.decode())
        name = path.decode("utf-8")
        if name.startswith((".git/", ".work/", ".codex/", "dist/")):
            raise ValueError("Private path is not a release input")
        body = git("cat-file", "blob", object_id.decode())
        if name.lower().endswith((".cmd", ".bat")):
            body = body.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        files[name] = body
    for name in files:
        if name.lower().endswith((".sqlite3", ".db", ".token", ".env")):
            raise ValueError("Local data is not a release input")
    info = f"Silicon Life State {version}\n作者：岑衡川·沈回音\nGit commit: {sha}\nRelease tag: {tag}\n".encode()
    files["RELEASE.txt"] = info
    files["SOURCE-FILES.sha256"] = checksum(files)
    component_files = {}
    prefix = f"SiliconLifeState-{version}"
    component_files[f"{prefix}-Source.zip"] = archive(files, "SiliconLifeState/")
    extension = {k.removeprefix("apps/extension/"): v for k, v in files.items() if k.startswith("apps/extension/")}
    extension["LICENSE.txt"] = files["LICENSE"]
    component_files[f"{prefix}-Chrome.zip"] = archive(extension)
    skill = {k.removeprefix("packages/agent-skill/"): v for k, v in files.items() if k.startswith("packages/agent-skill/")}
    skill["silicon-life-state/LICENSE.txt"] = files["LICENSE"]
    component_files[f"{prefix}-Skill.zip"] = archive(skill)
    service = {k: v for k, v in files.items() if k.startswith(("apps/local-service/", "apps/dashboard/", "packages/", "docs/")) or
               k in ("Start-Windows.cmd", "Reconnect-Windows.cmd", "start.sh", "LICENSE", "README.md", "NOTICE", "VERSION", "RELEASE.txt", "docs/INSTALL.md", "docs/MCP.md")}
    service["README.md"] = (
        "# 硅基生命状态 · 本地服务与 MCP\n\n作者：岑衡川·沈回音\n\n"
        "此独立组件适合已有 Python 3.10+ 的环境。Windows x64 离线免安装请使用同版 Windows-x64-Portable.zip。\n\n"
        "Windows 双击 Start-Windows.cmd，macOS / Linux 使用 sh start.sh。"
        "首次配对后即可在仪表盘创建主体和分身。Chrome 扩展请从完整包或同版独立扩展包安装。\n\n"
        "[安装与恢复](docs/INSTALL.md) · [MCP 接入](docs/MCP.md) · "
        "[宿主示例](packages/agent-example/README.md)\n"
    ).encode()
    component_files[f"{prefix}-Local-Service.zip"] = archive(service, "SiliconLifeState/")
    with tempfile.TemporaryDirectory() as temp_dir:
        bundle = Path(temp_dir) / "SiliconLifeState.git.bundle"
        make_bundle(sha, bundle, temp_dir)
        kit = {**files, **runtime, **{f"release/{k}": v for k, v in component_files.items()}}
        kit["release/" + bundle.name] = bundle.read_bytes()
        kit["release/SHA256SUMS.txt"] = checksum({k.removeprefix("release/"):v for k,v in kit.items() if k.startswith("release/")})
        products = {f"{prefix}-Windows-x64-Portable.zip": archive(kit, "SiliconLifeState/"), **component_files}
    products["README.md"] = files["README.md"]
    products["TEST-REPORT.md"] = files["docs/TEST-REPORT.md"]
    products["SHA256SUMS.txt"] = checksum(products)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, body in products.items():
        path = args.output / name
        path.write_bytes(body)
        if path.suffix == ".zip":
            with ZipFile(path) as check:
                if check.testzip():
                    raise RuntimeError(f"Unreadable ZIP: {name}")
        print(f"{name}\t{len(body)} bytes")


if __name__ == "__main__":
    main()
