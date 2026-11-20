import zipfile

from omarum import gpupack


def _rel(name, size=10, sha="ab"):
    return {"filename": name, "url": f"https://files/{name}", "size": size,
            "digests": {"sha256": sha}, "packagetype": "bdist_wheel"}


FAKE = {"nvidia-cublas-cu12": {"releases": {
    "12.9.1.4": [_rel("nvidia_cublas_cu12-12.9.1.4-py3-none-manylinux_2_27_x86_64.whl"),
                 _rel("nvidia_cublas_cu12-12.9.1.4-py3-none-win_amd64.whl")],
    "12.4.5.8": [_rel("nvidia_cublas_cu12-12.4.5.8-py3-none-manylinux2014_x86_64.whl")],
    "13.0.0.1": [_rel("nvidia_cublas_cu12-13.0.0.1-py3-none-manylinux_2_27_x86_64.whl")],
}}}


def test_wheel_files_pick_the_newest_matching_linux_wheel():
    files = gpupack.wheel_files(fetch_json=lambda pkg: FAKE[pkg])
    assert [f.path for f in files] == ["nvidia_cublas_cu12-12.9.1.4-py3-none-manylinux_2_27_x86_64.whl"]
    assert files[0].sha256 == "ab" and files[0].size == 10


def test_unpack_keeps_only_shared_libs(tmp_path):
    whl = tmp_path / "w.whl"
    with zipfile.ZipFile(whl, "w") as z:
        z.writestr("nvidia/cublas/lib/libcublas.so.12", b"lib")
        z.writestr("nvidia/cublas/lib/libcublasLt.so.12", b"lib")
        z.writestr("nvidia/cublas/include/cublas.h", b"h")
        z.writestr("nvidia_cublas_cu12-12.9.dist-info/METADATA", b"m")
    names = gpupack.unpack(whl, tmp_path / "gpu")
    assert sorted(names) == ["libcublas.so.12", "libcublasLt.so.12"]
    assert not (tmp_path / "gpu" / "cublas.h").exists() and not whl.exists()
