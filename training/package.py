"""Package a trained model for release and compute its checksum (Task 2, steps 3-4).

    python training/package.py --run v1

Writes
  artifacts/model-<run>.tar.gz     deterministic archive of artifacts/<run>/ (the GitHub Release asset)
  artifacts/<run>/model.sha256     SHA-256 of that archive, in `sha256sum` format (uploaded to models/<run>/)
  artifacts/model-<run>.sha256     the same line, published next to the archive
The archive is deterministic (sorted names, fixed mtime/owner), so packaging twice gives the same hash.
"""
import argparse
import gzip
import hashlib
import io
import pathlib
import tarfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXCLUDE = {"model.sha256"}


def build_archive(model_dir, archive_path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for p in sorted(model_dir.iterdir()):
            if not p.is_file() or p.name in EXCLUDE:
                continue
            info = tarfile.TarInfo(name=p.name)
            info.size = p.stat().st_size
            info.mtime, info.uid, info.gid, info.uname, info.gname, info.mode = 0, 0, 0, "", "", 0o644
            with open(p, "rb") as f:
                tar.addfile(info, f)
    with open(archive_path, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, compresslevel=9) as gz:
        gz.write(buf.getvalue())


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="v1")
    ap.add_argument("--root", default=str(ROOT / "artifacts"))
    a = ap.parse_args()
    root = pathlib.Path(a.root)
    model_dir = root / a.run
    if not (model_dir / "model.safetensors").exists():
        raise SystemExit(f"{model_dir} has no model.safetensors; run `make train RUN={a.run}` first")
    archive = root / f"model-{a.run}.tar.gz"
    build_archive(model_dir, archive)
    line = f"{sha256_of(archive)}  {archive.name}\n"
    (model_dir / "model.sha256").write_text(line)
    (root / f"model-{a.run}.sha256").write_text(line)
    print(line.strip())


if __name__ == "__main__":
    main()
