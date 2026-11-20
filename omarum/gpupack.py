"""GPU support for speech to text: NVIDIA's cuBLAS from its PyPI wheel. Stdlib only.

CTranslate2 (faster-whisper) loads `libcublas.so.12` to run Whisper on an NVIDIA GPU; the driver
alone doesn't have it. We download the official wheel and keep only its shared libraries in
`models/gpu/`. Nothing goes into the venv (uv sync would remove it); the engine preloads them
(omarum.models.preload_gpu_libs).
"""

from __future__ import annotations

import json
import urllib.request
import zipfile
from pathlib import Path

from omarum.catalog import FileSpec

WHEELS = (("nvidia-cublas-cu12", "12."),)


def _pypi(pkg: str) -> dict:
    req = urllib.request.Request(f"https://pypi.org/pypi/{pkg}/json", headers={"User-Agent": "omarum-downloader"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def _version_key(v: str) -> tuple:
    return tuple(int(p) if p.isdigit() else 0 for p in v.split("."))


def wheel_files(fetch_json=_pypi) -> list[FileSpec]:
    """The newest Linux x86_64 wheel of each package whose version starts with its prefix."""
    out = []
    for pkg, prefix in WHEELS:
        releases = fetch_json(pkg)["releases"]
        for version in sorted((v for v in releases if v.startswith(prefix)), key=_version_key, reverse=True):
            wheel = next((f for f in releases[version] if f.get("packagetype") == "bdist_wheel"
                          and "linux" in f["filename"] and f["filename"].endswith("x86_64.whl")), None)
            if wheel:
                out.append(FileSpec(wheel["url"], wheel["filename"], int(wheel.get("size") or 0),
                                    wheel.get("digests", {}).get("sha256", "")))
                break
        else:
            raise RuntimeError(f"no Linux wheel of {pkg} {prefix}x on PyPI")
    return out


def unpack(wheel: Path, dest: Path) -> list[str]:
    """Keep only nvidia/*/lib/*.so* from the wheel, flat in `dest`; delete the wheel."""
    dest.mkdir(parents=True, exist_ok=True)
    names = []
    with zipfile.ZipFile(wheel) as z:
        for info in z.infolist():
            parts = info.filename.split("/")
            if len(parts) == 4 and parts[0] == "nvidia" and parts[2] == "lib" and ".so" in parts[3]:
                tmp = dest / (parts[3] + ".part")
                with z.open(info) as src, open(tmp, "wb") as out:
                    while block := src.read(1 << 20):
                        out.write(block)
                tmp.replace(dest / parts[3])
                names.append(parts[3])
    Path(wheel).unlink(missing_ok=True)
    return names
