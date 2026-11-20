# Settings Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rum's settings window looks like Superwhisper's, has 13 rows instead of 22, and every model (speech to text, GPU support, voices) can be downloaded, cancelled, resumed and removed from a new Models tab; "Accurate" really runs Whisper Large v3 Turbo on the GPU.

**Architecture:** A stdlib-only model catalog and downloader (`omarum/catalog.py`, `omarum/downloader.py`) usable from both the GTK window (system Python) and the engine venv. A CLI (`omarum models …`) does downloads in a child process and prints JSON progress lines; the window runs it and redraws. GPU support is the NVIDIA cuBLAS/cuDNN wheels unpacked into `models/gpu/` and preloaded by the engine before CTranslate2. The window keeps its structure; rows come from a slimmer `settings_model.py`, and CSS plus three small widgets give the new look.

**Tech Stack:** Python 3.12 (stdlib: urllib, zipfile, hashlib, json), GTK4 via PyGObject (system Python), faster-whisper 1.2.1 / ctranslate2 4.9.0 (CUDA 12, cuDNN 9), pytest.

**Spec:** `docs/superpowers/specs/2026-11-20-settings-redesign-design.md`

## Global Constraints

- Text 12px, rows 28px tall, value column 180px from the window's left, section titles 11px bold in the foreground color, selected row: whole row tinted with the label in the accent color and no left bar.
- Switch drawn as a small switch, slider as a thin line with a tick handle and the value on the right, segmented buttons capitalized; no hint text on rows; the selected row's hint shows in the footer.
- Footer keys: `↑/↓ Select · ←/→ or Space Change · Enter Edit · Q Close` (per-tab variants in `FOOTERS`).
- Tabs exactly: `Settings`, `Models`, `Memory`, `Conversations`; brand `◉ omarum`.
- Removed rows keep their saved values untouched: `orb_colors`, `orb_size`, `vad_stop_secs`, `idle_timeout_secs`, `interrupt_min_words`, `mute_while_speaking`, `whisper_device` row (replaced by Processing), `record_audio`, Export.
- No sudo; nothing installed into the venv (uv sync removes it); every download lands under `~/.local/share/omarum/models/`.
- A model is never half there: download to `<file>.part`, verify size (and sha256 when known), then rename.
- Downloads never block the GTK main loop and continue when the window closes.
- `catalog.py` and `downloader.py` import only the standard library (the window runs on the system Python).
- Commit messages never include Claude attribution lines (Hazem's rule).

## Review Focus

1. Network drops mid-download → the row shows `✗ Failed: <why>  Enter to retry`, the `.part` stays, the next Enter resumes from its size (Task 2 test `test_resume_after_interrupt`).
2. The window is reopened while a download runs → the row still shows live progress from the state file, not `↓ Download` (Task 4 test `test_list_reports_running_download`).
3. A server that ignores `Range` (answers 200 to a ranged request) → the download restarts from zero instead of appending and corrupting (Task 2 test `test_server_without_range_restarts`).
4. Accurate chosen but GPU support missing or the GPU is full → Rum keeps speaking on the CPU model and the log says why (Task 3 test `test_pick_whisper_falls_back_when_gpu_pack_missing`).
5. Deleting the model Rum is using, or Base → refused with a reason, nothing removed (Task 4 test `test_remove_refuses_in_use_and_base`).

---

### Task 1: Model catalog and states

**Files:**
- Create: `omarum/catalog.py`
- Test: `tests/test_catalog.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class FileSpec: url: str; path: str; size: int = 0; sha256: str = ""` (`path` relative to the model's folder)
  - `@dataclass(frozen=True) class Model: id: str; title: str; group: str; folder: str; files: tuple[FileSpec, ...]; approx_bytes: int; removable: bool = True; resolver: str = ""` (`group` is `"Speech to text"` or `"Voices"`; `folder` relative to `MODELS_DIR`; `resolver == "pypi-wheels"` for GPU support, whose files are found at download time)
  - `CATALOG: tuple[Model, ...]` with ids `whisper-base`, `whisper-small`, `whisper-large-turbo`, `gpu`, `kokoro`, `piper-amy`
  - `def by_id(model_id: str) -> Model`
  - `def state(m: Model, models_dir: Path) -> dict` → `{"id", "title", "group", "state", "done", "total", "error"}`, `state` one of `ready | missing | partial | downloading | failed`
  - `def state_path(m: Model, models_dir: Path) -> Path` → `models_dir / ".state" / f"{m.id}.json"`
  - `def write_state(m, models_dir, **fields) -> None` (adds `"pid"` and `"at"`; atomic write)

Catalog values: `whisper-base` = folder `whisper/base.en`, repo `Systran/faster-whisper-base.en`, files `config.json, model.bin, tokenizer.json, vocabulary.txt`, approx 145_000_000, `removable=False`; `whisper-small` = `whisper/small.en`, `Systran/faster-whisper-small.en`, same files, approx 486_000_000; `whisper-large-turbo` = `whisper/large-v3-turbo`, `mobiuslabs/faster-whisper-large-v3-turbo`, files `config.json, model.bin, preprocessor_config.json, tokenizer.json, vocabulary.json`, approx 1_620_000_000; `gpu` = folder `gpu`, resolver `pypi-wheels`, approx 1_500_000_000; `kokoro` = folder `kokoro`, URLs from `setup.KOKORO_URL` + `kokoro-v1.0.onnx`, `voices-v1.0.bin`, approx 337_000_000; `piper-amy` = folder `piper`, `https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx` and `.onnx.json`, approx 63_000_000. Whisper URLs are `https://huggingface.co/{repo}/resolve/main/{file}`. Check the file names against the existing folders in `~/.local/share/omarum/models/whisper/` before committing (base.en uses `vocabulary.txt`, large-v3-turbo `vocabulary.json`).

Ready rule: every `FileSpec.path` exists and is non-empty (for `gpu`: `libcublas.so.12` and `libcudnn.so.9` exist in the folder). A state file with a live `pid` (`os.kill(pid, 0)` succeeds) → `downloading` with its `done/total`; with `error` → `failed`; any `*.part` in the folder → `partial` with `done` = summed `.part` sizes.

- [ ] **Step 1: Write the failing tests**

```python
def test_missing_then_ready(tmp_path):
    m = catalog.by_id("piper-amy")
    assert catalog.state(m, tmp_path)["state"] == "missing"
    for f in m.files:
        p = tmp_path / m.folder / f.path; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b"x")
    assert catalog.state(m, tmp_path)["state"] == "ready"

def test_partial_counts_part_bytes(tmp_path):
    m = catalog.by_id("kokoro")
    (tmp_path / "kokoro").mkdir(); (tmp_path / "kokoro" / "kokoro-v1.0.onnx.part").write_bytes(b"x" * 10)
    s = catalog.state(m, tmp_path)
    assert s["state"] == "partial" and s["done"] == 10

def test_live_pid_is_downloading_dead_pid_is_not(tmp_path):
    m = catalog.by_id("kokoro")
    catalog.write_state(m, tmp_path, done=5, total=9)          # our own pid: alive
    assert catalog.state(m, tmp_path)["state"] == "downloading"
    data = json.loads(catalog.state_path(m, tmp_path).read_text()); data["pid"] = 2**22 + 7
    catalog.state_path(m, tmp_path).write_text(json.dumps(data))
    assert catalog.state(m, tmp_path)["state"] != "downloading"

def test_failed_keeps_the_reason(tmp_path):
    m = catalog.by_id("kokoro")
    catalog.write_state(m, tmp_path, error="connection reset", pid=2**22 + 7)
    s = catalog.state(m, tmp_path)
    assert s["state"] == "failed" and s["error"] == "connection reset"

def test_catalog_ids_and_base_not_removable():
    assert [m.id for m in catalog.CATALOG] == ["whisper-base", "whisper-small", "whisper-large-turbo", "gpu", "kokoro", "piper-amy"]
    assert catalog.by_id("whisper-base").removable is False

def test_catalog_is_stdlib_only():
    src = Path(catalog.__file__).read_text()
    assert "import requests" not in src and "huggingface_hub" not in src and "omarum.models" not in src
```

- [ ] **Step 2: Run** `uv run pytest -q tests/test_catalog.py` — Expected: FAIL (`No module named 'omarum.catalog'`).
- [ ] **Step 3: Implement `omarum/catalog.py`** with the interfaces and values above. `MODELS_DIR` is passed in (don't import `omarum.models`; the window imports `omarum.paths` itself).
- [ ] **Step 4: Run** `uv run pytest -q tests/test_catalog.py` — Expected: PASS.
- [ ] **Step 5: Commit** `git add omarum/catalog.py tests/test_catalog.py && git commit -m "feat(models): catalog of every downloadable model and its state"`

---

### Task 2: Resumable, verified downloader

**Files:**
- Create: `omarum/downloader.py`
- Test: `tests/test_downloader.py` (serves files from a `http.server.ThreadingHTTPServer` on 127.0.0.1 in a thread; a handler flag turns Range support off and can drop the connection after N bytes)

**Interfaces:**
- Consumes: `catalog.FileSpec`, `catalog.Model`, `catalog.write_state`
- Produces:
  - `class Cancelled(Exception)`
  - `def fetch(spec: FileSpec, dest: Path, on_bytes: Callable[[int], None], cancelled: Callable[[], bool], opener=urllib.request.urlopen) -> None` — resume `dest.with_name(dest.name + ".part")` with `Range: bytes=<size>-`; a 200 reply to a ranged request truncates the `.part` and starts over; reads 1 MiB chunks, calls `on_bytes(n)` per chunk, raises `Cancelled` when `cancelled()` (keeping the `.part`); when complete checks size (`spec.size` or Content-Length) and `sha256` if set; mismatch deletes the `.part` and raises `ValueError("size/sha256 mismatch")`; success renames to `dest`.
  - `def download(m: Model, models_dir: Path, files: list[FileSpec], emit: Callable[[dict], None], cancelled: Callable[[], bool]) -> None` — skips files already present, totals sizes via `HEAD` (or `approx_bytes` when unknown), calls `emit({"id", "state": "downloading", "done", "total"})` at most every 0.25 s and `write_state` with the same numbers, ends with `emit({"state": "ready"})` and removes the state file; on error writes/emit `{"state": "failed", "error": str(e)[:160]}` and re-raises.

- [ ] **Step 1: Write the failing tests**

```python
def test_downloads_and_verifies(server, tmp_path):          # server serves b"a"*3000 at /f
    spec = FileSpec(url=server + "/f", path="f", size=3000, sha256=hashlib.sha256(b"a"*3000).hexdigest())
    downloader.fetch(spec, tmp_path / "f", on_bytes=lambda n: None, cancelled=lambda: False)
    assert (tmp_path / "f").read_bytes() == b"a"*3000 and not (tmp_path / "f.part").exists()

def test_resume_after_interrupt(server, tmp_path):          # first request drops after 1000 bytes
    server_drop_after(1000)
    spec = FileSpec(url=server + "/f", path="f", size=3000)
    with pytest.raises(Exception):
        downloader.fetch(spec, tmp_path / "f", lambda n: None, lambda: False)
    assert (tmp_path / "f.part").stat().st_size == 1000
    downloader.fetch(spec, tmp_path / "f", lambda n: None, lambda: False)
    assert last_range_header() == "bytes=1000-" and (tmp_path / "f").stat().st_size == 3000

def test_server_without_range_restarts(server, tmp_path):
    server_no_range(); (tmp_path / "f.part").write_bytes(b"z" * 500)
    downloader.fetch(FileSpec(url=server + "/f", path="f", size=3000), tmp_path / "f", lambda n: None, lambda: False)
    assert (tmp_path / "f").read_bytes() == b"a"*3000

def test_bad_checksum_leaves_nothing(server, tmp_path):
    with pytest.raises(ValueError):
        downloader.fetch(FileSpec(url=server + "/f", path="f", size=3000, sha256="0"*64), tmp_path / "f", lambda n: None, lambda: False)
    assert not (tmp_path / "f").exists() and not (tmp_path / "f.part").exists()

def test_cancel_keeps_part(server, tmp_path):
    calls = iter([False, True])
    with pytest.raises(downloader.Cancelled):
        downloader.fetch(FileSpec(url=server + "/f", path="f", size=3000), tmp_path / "f", lambda n: None, lambda: next(calls, True))
    assert (tmp_path / "f.part").exists() and not (tmp_path / "f").exists()

def test_download_emits_progress_and_ready(server, tmp_path):
    m = Model(id="t", title="T", group="Voices", folder="t", files=(FileSpec(server + "/f", "f", 3000),), approx_bytes=3000)
    seen = []
    downloader.download(m, tmp_path, list(m.files), seen.append, lambda: False)
    assert seen[-1]["state"] == "ready" and catalog.state(m, tmp_path)["state"] == "ready"
```

- [ ] **Step 2: Run** `uv run pytest -q tests/test_downloader.py` — Expected: FAIL (no module).
- [ ] **Step 3: Implement `omarum/downloader.py`** per the interfaces (stdlib only).
- [ ] **Step 4: Run** `uv run pytest -q tests/test_downloader.py` — Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(models): resumable, verified downloads"` (with both files added).

---

### Task 3: GPU support pack and the engine using it

**Files:**
- Create: `omarum/gpupack.py`
- Modify: `omarum/models.py` (`cuda_libs_loadable`, `pick_whisper`, new `preload_gpu_libs`), `omarum/pipeline.py` or wherever `make_stt` is first called (call `preload_gpu_libs()` before importing ctranslate2's CUDA path), `omarum/daemon.py` (preload at start, next to `preload_whisper`)
- Test: `tests/test_gpupack.py`, `tests/test_models.py`

**Interfaces:**
- Consumes: `downloader.fetch`, `catalog.by_id("gpu")`
- Produces:
  - `WHEELS = (("nvidia-cublas-cu12", "12."), ("nvidia-cudnn-cu12", "9."))`
  - `def wheel_files(fetch_json=…) -> list[FileSpec]` — for each package, read `https://pypi.org/pypi/<pkg>/json`, pick the newest release whose version starts with the prefix and has a `manylinux*_x86_64` wheel; FileSpec with that URL, `path` = the wheel file name, `size` and `sha256` from PyPI's `digests`.
  - `def unpack(wheel: Path, dest: Path) -> list[str]` — extract only members matching `nvidia/*/lib/*.so*` flat into `dest`; return names; delete the wheel afterwards.
  - `def preload_gpu_libs(models_dir: Path = MODELS_DIR, loader=ctypes.CDLL) -> bool` (in `models.py`) — if `models_dir/"gpu"/"libcublas.so.12"` exists, load `libcublasLt.so.12`, `libcublas.so.12`, then every `libcudnn*.so.9` (main `libcudnn.so.9` last) with `RTLD_GLOBAL`; True on success.
  - `cuda_libs_loadable()` returns True when `preload_gpu_libs()` succeeds or the system libs load (existing behavior).
  - `pick_whisper` logs `whisper: Accurate needs GPU support (Models tab); using <cpu model> on cpu` when `whisper_device == "auto"`, a CUDA device exists, and libs don't load.

- [ ] **Step 1: Write the failing tests**

```python
def test_wheel_files_pick_matching_versions():
    fake = {"nvidia-cublas-cu12": {"releases": {"12.9.1.4": [{"filename": "nvidia_cublas_cu12-12.9.1.4-py3-none-manylinux_2_27_x86_64.whl", "url": "https://x/a.whl", "size": 10, "digests": {"sha256": "ab"}, "packagetype": "bdist_wheel"}], "13.0.0": [...]}},
            "nvidia-cudnn-cu12": {"releases": {"9.10.2.21": [{... "filename": "nvidia_cudnn_cu12-9.10.2.21-py3-none-manylinux_2_27_x86_64.whl", ...}]}}}
    files = gpupack.wheel_files(fetch_json=lambda pkg: fake[pkg])
    assert [f.path for f in files] == ["nvidia_cublas_cu12-12.9.1.4-py3-none-manylinux_2_27_x86_64.whl", "nvidia_cudnn_cu12-9.10.2.21-py3-none-manylinux_2_27_x86_64.whl"]
    assert files[0].sha256 == "ab"

def test_unpack_keeps_only_shared_libs(tmp_path):   # build a zip with nvidia/cublas/lib/libcublas.so.12 and nvidia/cublas/include/x.h
    names = gpupack.unpack(make_wheel(tmp_path), tmp_path / "gpu")
    assert names == ["libcublas.so.12"] and not (tmp_path / "gpu" / "x.h").exists()

def test_preload_order(tmp_path):
    gpu = tmp_path / "gpu"; gpu.mkdir()
    for n in ("libcublas.so.12", "libcublasLt.so.12", "libcudnn.so.9", "libcudnn_ops.so.9"): (gpu / n).write_bytes(b"")
    loaded = []
    assert models.preload_gpu_libs(tmp_path, loader=lambda p, mode=0: loaded.append(Path(p).name))
    assert loaded[:2] == ["libcublasLt.so.12", "libcublas.so.12"] and loaded[-1] == "libcudnn.so.9"

def test_pick_whisper_falls_back_when_gpu_pack_missing():
    cfg = Config(whisper_device="auto")
    assert models.pick_whisper(cfg, cuda_devices=1, cuda_libs=False) == ("base.en", "cpu", "int8")
    assert models.pick_whisper(cfg, cuda_devices=1, cuda_libs=True)[1] == "cuda"
```

- [ ] **Step 2: Run** `uv run pytest -q tests/test_gpupack.py tests/test_models.py` — Expected: FAIL.
- [ ] **Step 3: Implement** `gpupack.py` and the `models.py` changes; call `preload_gpu_libs()` at daemon start before `preload_whisper`.
- [ ] **Step 4: Run** `uv run pytest -q` — Expected: all pass.
- [ ] **Step 5: Commit** `git commit -m "feat(models): GPU support pack (cuBLAS/cuDNN wheels unpacked, preloaded) so Accurate runs on the GPU"`

---

### Task 4: `omarum models` command and setup through it

**Files:**
- Create: `omarum/modelcmd.py`
- Modify: `omarum/cli.py` (add `models` subcommand), `omarum/setup.py` (download `whisper-base` and `kokoro` via `downloader.download`, keeping its JSON step lines)
- Test: `tests/test_modelcmd.py`, `tests/test_setup.py` if present (else extend `tests/test_integration.py` where setup is tested)

**Interfaces:**
- Consumes: Tasks 1–3
- Produces:
  - `omarum models list --json` → one JSON array of `catalog.state(...)` dicts plus `"size"` (bytes for display) and `"in_use": bool` (Base or the CPU model when Processing is Fast; large-turbo and gpu when Accurate is active; the engine of the current voice).
  - `omarum models download <id>` → prints JSON progress lines (`downloader.download`'s emits); for `gpu`, resolves `gpupack.wheel_files()`, downloads into `models/gpu/`, unpacks each wheel. Exit 0 on ready, 1 on failure, 2 on cancel. SIGTERM sets the cancel flag.
  - `omarum models cancel <id>` → SIGTERM to the pid in the state file; no-op when none.
  - `omarum models remove <id>` → refuses (exit 1, message on stderr) for `removable=False` or `in_use`; otherwise deletes the model's files (for `gpu` the whole folder) and its state file.
  - `def in_use(cfg) -> set[str]` in `modelcmd.py`.

- [ ] **Step 1: Write the failing tests**

```python
def test_list_reports_running_download(tmp_path, capsys):
    m = catalog.by_id("kokoro"); catalog.write_state(m, tmp_path, done=10, total=100)
    modelcmd.main(["list", "--json"], models_dir=tmp_path, cfg=Config())
    rows = {r["id"]: r for r in json.loads(capsys.readouterr().out)}
    assert rows["kokoro"]["state"] == "downloading" and rows["kokoro"]["done"] == 10

def test_remove_refuses_in_use_and_base(tmp_path):
    cfg = Config(whisper_device="auto")
    assert modelcmd.main(["remove", "whisper-base"], models_dir=tmp_path, cfg=cfg) == 1
    assert "whisper-large-turbo" in modelcmd.in_use(cfg)
    assert modelcmd.main(["remove", "whisper-large-turbo"], models_dir=tmp_path, cfg=cfg) == 1

def test_remove_deletes_files(tmp_path):
    m = catalog.by_id("piper-amy"); d = tmp_path / "piper"; d.mkdir()
    for f in m.files: (d / f.path).write_bytes(b"x")
    assert modelcmd.main(["remove", "piper-amy"], models_dir=tmp_path, cfg=Config(voice_primary="kokoro")) == 0
    assert catalog.state(m, tmp_path)["state"] == "missing"

def test_cancel_signals_the_downloader(tmp_path, monkeypatch):
    m = catalog.by_id("kokoro"); catalog.write_state(m, tmp_path, done=1, total=2)
    sent = []; monkeypatch.setattr(os, "kill", lambda pid, sig: sent.append(sig))
    modelcmd.main(["cancel", "kokoro"], models_dir=tmp_path, cfg=Config())
    assert signal.SIGTERM in sent
```

- [ ] **Step 2: Run** `uv run pytest -q tests/test_modelcmd.py` — Expected: FAIL.
- [ ] **Step 3: Implement** `modelcmd.main(argv, models_dir=MODELS_DIR, cfg=None) -> int` and wire `omarum models …` in `cli.py`; switch `setup.py` to `downloader.download` (its existing tests must keep passing with injected fakes).
- [ ] **Step 4: Run** `uv run pytest -q` — Expected: all pass.
- [ ] **Step 5: Commit** `git commit -m "feat(models): 'omarum models list|download|cancel|remove'; setup downloads through it"`

---

### Task 5: Slimmer rows

**Files:**
- Modify: `omarum/settings_model.py`
- Test: `tests/test_settings_model.py` (update the old row tests to the new tabs; delete tests of removed rows)

**Interfaces:**
- Produces:
  - `TABS = ("Settings", "Models", "Memory", "Conversations")`; `tab_index` unchanged in behavior (old names `companion`/`engine` map to `Settings`).
  - New row kinds: `voice` (merged list), `processing` (seg over `whisper_device` with options `("cpu", "auto")` and labels `(("cpu", "Fast"), ("auto", "Accurate"))`).
  - `def rows_for(tab, values: dict, brain_status=None, eleven_voices=None, eleven_status="", zonos3=False) -> list[Row]` — Settings tab in this order and groups: General (`Name`, `Your name`, `Brain`, `API key` only if the provider has `env_key`, `Model` only if `len(p.models) > 1`, `Endpoint` only for `custom`), Voice (`Voice`, `ElevenLabs key` only when `values["voice_primary"] == "elevenlabs"`, `Volume`), Speech to text (`Processing`), Talking (`Response speed`, `Talk key`), Orb (`Style`, `Position`), Screen (`Look when I ask` → `screen_look`, `See my code` → `screen_awareness`). Memory tab: `Keep conversations` only (facts/journal stay in the window).
  - `def voice_options(zonos3: bool, eleven_voices: list[tuple[str, str]], kokoro_voices=…, zonos3_voices=…) -> list[tuple[str, str]]` → `("elevenlabs:<id>", "ElevenLabs · <name>")`… then `("zonos3:<v>", "ZONOS3 · <v>")` only if `zonos3`, `("kokoro:<v>", "Kokoro · <Name>")`, `("piper:amy", "Piper · Amy")`.
  - `def voice_value(values) -> str` and `def voice_updates(choice: str) -> dict` (`"kokoro:af_bella"` → `{"voice_primary": "kokoro", "kokoro_voice": "af_bella"}`; elevenlabs → `elevenlabs_voice_id`; zonos3 → `zonos3_voice`; piper → `{"voice_primary": "piper"}`).
  - `display()` capitalizes seg/cycle values for the screen (`glow` → `Glow`, `top-right` → `Top right`, `fast` → `Fast`); stored values unchanged.
  - Every Row keeps a short `hint` (shown in the footer when selected): Processing `"Fast: small model on the CPU · Accurate: Large v3 Turbo on your GPU"`, Response speed `"Fast answers sooner · Patient waits longer · hold Space to always finish"`, Talk key `"double tap: open / close · hold: talk   (Enter to change)"`, Look when I ask `"\"look at my screen\": one screenshot, sent to your brain"`, See my code `"with IntelliJ or VS Code focused, Rum reads that file"`.
  - `FOOTERS["Settings"] = ["↑/↓ Select", "←/→ or Space Change", "Enter Edit", "Q Close"]`, `FOOTERS["Models"] = ["↑/↓ Select", "Enter Download / Cancel", "D Remove", "Q Close"]`.

- [ ] **Step 1: Write the failing tests**

```python
def test_settings_tab_has_13_rows_for_codex_with_zonos3_voice():
    labels = [r.label for r in sm.rows_for("Settings", {"brain": "codex", "voice_primary": "zonos3"})]
    assert len(labels) <= 13
    assert labels[:3] == ["Name", "Your name", "Brain"]
    assert labels[-8:] == ["Voice", "Volume", "Processing", "Response speed", "Talk key",
                           "Style", "Position", "Look when I ask", "See my code"][-8:]

def test_conditional_rows():
    labels = lambda v: [r.label for r in sm.rows_for("Settings", v)]
    assert "ElevenLabs key" in labels({"brain": "codex", "voice_primary": "elevenlabs"})
    assert "ElevenLabs key" not in labels({"brain": "codex", "voice_primary": "kokoro"})
    assert "API key" in labels({"brain": "anthropic", "voice_primary": "kokoro"})
    assert "API key" not in labels({"brain": "codex", "voice_primary": "kokoro"})

def test_removed_rows_are_gone():
    keys = {r.key for t in sm.TABS for r in sm.rows_for(t, {"brain": "codex", "voice_primary": "kokoro"})}
    assert keys.isdisjoint({"orb_colors", "orb_size", "vad_stop_secs", "idle_timeout_secs",
                            "interrupt_min_words", "mute_while_speaking", "record_audio"})

def test_voice_merge_and_updates():
    opts = sm.voice_options(zonos3=False, eleven_voices=[("abc", "Jessica")])
    assert opts[0] == ("elevenlabs:abc", "ElevenLabs · Jessica") and not any(o[0].startswith("zonos3:") for o in opts)
    assert sm.voice_updates("kokoro:af_bella") == {"voice_primary": "kokoro", "kokoro_voice": "af_bella"}
    assert sm.voice_value({"voice_primary": "kokoro", "kokoro_voice": "af_bella"}) == "kokoro:af_bella"

def test_processing_labels_and_display_capitalized():
    r = next(r for r in sm.rows_for("Settings", {"brain": "codex"}) if r.label == "Processing")
    assert sm.display(r, "auto") == "Accurate" and sm.display(r, "cpu") == "Fast"
    style = next(r for r in sm.rows_for("Settings", {"brain": "codex"}) if r.label == "Position")
    assert sm.display(style, "top-right") == "Top right"

def test_old_tab_names_open_settings():
    assert sm.tab_index("companion") == 0 and sm.tab_index("engine") == 0 and sm.tab_index("models") == 1
```

- [ ] **Step 2: Run** `uv run pytest -q tests/test_settings_model.py` — Expected: FAIL.
- [ ] **Step 3: Implement** the changes in `settings_model.py`; keep `SPEED_PRESETS`, `speed_of`, `once`, `edit_key`, `step`.
- [ ] **Step 4: Run** `uv run pytest -q` — Expected: all pass.
- [ ] **Step 5: Commit** `git commit -m "feat(settings): 13 rows in Superwhisper-like sections; one voice list; Processing Fast/Accurate"`

---

### Task 6: The new look and the Models tab in the window

**Files:**
- Modify: `settings/omarum_settings.py`
- Test: manual (GTK), plus `tests/test_settings_model.py` for any logic pulled out

**Interfaces:**
- Consumes: Task 5 (`rows_for(tab, values, …)`, `voice_options`, `voice_updates`, `FOOTERS`), Task 4 (`omarum models …` run with `~/.local/share/omarum/venv/bin/python -m omarum.cli models`), Task 1 (`catalog.state` for a first draw without waiting on the child).
- Produces: nothing other tasks use.

Changes:
- CSS per Global Constraints: `font-size: 12px`; `.row { min-height: 28px; padding: 0 15px; }` no left border; `.row.focus { background: alpha(selection, .45) } .row.focus .label { color: accent }`; `.group { font-size: 11px; font-weight: bold; color: foreground; padding: 16px 0 6px 0 }`; `.seg { padding: 1px 9px; font-size: 11px }`; label `set_size_request(165, -1)` so values start ~180px in.
- Toggle: a 28×14 `Gtk.DrawingArea` (outline box, filled square right when on, left when off, accent when on). Slider: 200×14 `Gtk.DrawingArea` (1px track, 2px×10px tick at the value) followed by the value label; no `‹ ›`. Cycle values keep `‹ value ›` with the value centered in 18 chars.
- Footer becomes a `Gtk.Box`: left label = selected row's hint (ellipsized, faded), right label = `FOOTERS[tab]` joined by `  ·  `; a flash replaces the left label.
- Hints no longer rendered inside rows.
- Voice row: `cycle` over `voice_options(...)`; changing saves every key of `voice_updates(choice)`; a local voice whose model isn't `ready` shows `(<size>)` after its name and picking it starts its download (Rum keeps the old voice until ready: save only after the download succeeds).
- Processing row: choosing Accurate when `gpu` or `whisper-large-turbo` isn't ready starts those downloads and shows `Accurate · downloading 42%` in the row; saves `whisper_device = "auto"` immediately (the engine falls back by itself, Task 3).
- Models tab: groups from `catalog.group`; row = title (label column), size (`1.6 GB` / `464 MB`), state text exactly as in the spec (`↓ Download` · `↓ 42%  680 MB of 1.6 GB` · `Paused  680 MB of 1.6 GB` for `partial` · `✓ Ready` · `✗ Failed: <why>  Enter to retry`); `(in use)` after Ready when `in_use`. ZONOS3 row is info only: `Installed` or `Not installed: build it, see README`. Enter on missing/partial/failed → `Gio.Subprocess` running `models download <id>`, read stdout lines with `read_line_async`, update that row; Enter while downloading → `models cancel <id>`. `D` arms (`flash("Press D again to remove <title>")`), second `D` → `models remove <id>`, showing its stderr if refused. While any download runs, refresh the tab every 1 s from `models list --json` so downloads started elsewhere show too.

- [ ] **Step 1: Implement** the CSS, widgets, footer, Voice/Processing behavior and Models tab as above.
- [ ] **Step 2: Syntax check** `python3 -c "import ast,sys; ast.parse(open('settings/omarum_settings.py').read())"` — Expected: no output.
- [ ] **Step 3: Run** `uv run pytest -q` — Expected: all pass.
- [ ] **Step 4: Open it** `python3 settings/omarum_settings.py &` and screenshot next to `superwhisper settings` at the same window size (grim, crop both windows). Expected: same text size, row spacing, value column, section titles; fix any visible difference once.
- [ ] **Step 5: Walk every Settings row** with ←/→/Enter and read `~/.config/omarum/config.toml` after each: every row writes its key (Voice writes two). Expected: values change as shown.
- [ ] **Step 6: Commit** `git commit -m "feat(settings): Superwhisper look, footer hints, Models tab with live downloads"`

---

### Task 7: Real downloads, Accurate on the GPU, docs

**Files:**
- Modify: `README.md` (Settings section: tabs, Models tab, Processing; remove rows no longer there; Troubleshooting "Rum mishears you: Settings → Processing → Accurate")
- Modify: `omarum/summary.py` if `ears_label` should read `Whisper · large-v3-turbo · GPU` when the pack loads (use `models.cuda_libs_loadable()` which now sees `models/gpu`).

- [ ] **Step 1: Download GPU support for real:** `~/.local/share/omarum/venv/bin/python -m omarum.cli models download gpu` — Expected: progress lines, then `{"state": "ready"}`; `ls ~/.local/share/omarum/models/gpu` shows `libcublas.so.12`, `libcudnn.so.9`.
- [ ] **Step 2: Cancel and resume once** with Piper (`remove piper-amy`, `download piper-amy`, cancel at ~30% from another shell, download again). Expected: second run's first progress line starts above 0; ends ready.
- [ ] **Step 3: Engine on the GPU:** with Hazem's go-ahead (Rum restarts), update the installed plugin and start a conversation. Expected in `~/.local/state/omarum/daemon.log`: `whisper: large-v3-turbo on cuda`.
- [ ] **Step 4: Update README**, run `uv run pytest -q` — Expected: all pass.
- [ ] **Step 5: Commit** `git commit -m "docs: new settings and Models tab; Accurate speech to text on the GPU"`
