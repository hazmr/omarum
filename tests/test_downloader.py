import hashlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from omarum import catalog, downloader
from omarum.catalog import FileSpec, Model

BODY = b"a" * 3000


class Handler(BaseHTTPRequestHandler):
    ranges = True
    drop_after = None  # bytes; first request only
    seen_ranges: list = []

    def log_message(self, *a):
        pass

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(BODY)))
        self.end_headers()

    def do_GET(self):
        rng = self.headers.get("Range")
        Handler.seen_ranges.append(rng)
        start = 0
        if rng and Handler.ranges:
            start = int(rng.split("=")[1].split("-")[0])
            self.send_response(206)
        else:
            self.send_response(200)
        body = BODY[start:]
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if Handler.drop_after is not None:
            n, Handler.drop_after = Handler.drop_after, None
            self.wfile.write(body[:n])
            self.wfile.flush()
            self.connection.shutdown(2)
            return
        self.wfile.write(body)


@pytest.fixture
def server():
    Handler.ranges, Handler.drop_after, Handler.seen_ranges = True, None, []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def never():
    return False


def test_downloads_and_verifies(server, tmp_path):
    spec = FileSpec(url=server + "/f", path="f", size=3000, sha256=hashlib.sha256(BODY).hexdigest())
    downloader.fetch(spec, tmp_path / "f", on_bytes=lambda n: None, cancelled=never)
    assert (tmp_path / "f").read_bytes() == BODY and not (tmp_path / "f.part").exists()


def test_resume_after_interrupt(server, tmp_path):
    Handler.drop_after = 1000
    spec = FileSpec(url=server + "/f", path="f", size=3000)
    with pytest.raises(Exception):
        downloader.fetch(spec, tmp_path / "f", lambda n: None, never)
    assert (tmp_path / "f.part").stat().st_size == 1000
    downloader.fetch(spec, tmp_path / "f", lambda n: None, never)
    assert Handler.seen_ranges[-1] == "bytes=1000-" and (tmp_path / "f").read_bytes() == BODY


def test_server_without_range_restarts(server, tmp_path):
    Handler.ranges = False
    (tmp_path / "f.part").write_bytes(b"z" * 500)
    downloader.fetch(FileSpec(url=server + "/f", path="f", size=3000), tmp_path / "f", lambda n: None, never)
    assert (tmp_path / "f").read_bytes() == BODY


def test_bad_checksum_leaves_nothing(server, tmp_path):
    with pytest.raises(ValueError):
        downloader.fetch(FileSpec(url=server + "/f", path="f", size=3000, sha256="0" * 64),
                         tmp_path / "f", lambda n: None, never)
    assert not (tmp_path / "f").exists() and not (tmp_path / "f.part").exists()


def test_cancel_keeps_part(server, tmp_path):
    calls = iter([False])
    with pytest.raises(downloader.Cancelled):
        downloader.fetch(FileSpec(url=server + "/f", path="f", size=3000), tmp_path / "f",
                         lambda n: None, lambda: next(calls, True), chunk=1000)
    assert (tmp_path / "f.part").exists() and not (tmp_path / "f").exists()


def test_download_emits_progress_and_ready(server, tmp_path):
    m = Model(id="t", title="T", group="Voices", folder="t", files=(FileSpec(server + "/f", "f", 3000),),
              approx_bytes=3000)
    seen = []
    downloader.download(m, tmp_path, list(m.files), seen.append, never)
    assert seen[-1]["state"] == "ready" and catalog.state(m, tmp_path)["state"] == "ready"
    assert not catalog.state_path(m, tmp_path).exists()


def test_download_failure_is_recorded(server, tmp_path):
    Handler.drop_after = 10
    m = Model(id="t", title="T", group="Voices", folder="t", files=(FileSpec(server + "/f", "f", 3000),),
              approx_bytes=3000)
    seen = []
    with pytest.raises(Exception):
        downloader.download(m, tmp_path, list(m.files), seen.append, never)
    s = catalog.state(m, tmp_path)
    assert seen[-1]["state"] == "failed" and s["state"] == "failed" and s["error"]
