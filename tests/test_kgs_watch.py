"""라이브 KGS에 접속하지 않는 버전/실패/검색 회귀 검사."""
import contextlib
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.parse
import urllib.request

import pymupdf

import fetch_kgs_code
from ingest_kgs_code import extract_pdf, split_items
import kgs_watch as kw
import search


def pdf_bytes(code="GC205", body="Original requirement. " * 20):
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(40, 40, 550, 780),
                            f"KGS {code} 2026\n1.1 Scope\n{body}\n2.1 Test\n{body}", fontsize=10)
        return doc.tobytes()


def item(code="GC205"):
    return {"code": code, "year": "2026", "title": "Welding standard",
            "path": f"kgscode_pdf/{code}_2026.pdf", "revised_on": "2026-10-30"}


HTML = """<table><tr><th>코드번호</th><th>개정일</th></tr>
<tr><td>공통</td><td>KGS GC205 2026 <img src='new.png'><p>Welding &amp; testing</p></td>
<td>2026.10.30</td><td><a href='/download?file_nm=kgscode_pdf/GC205_2026.pdf&amp;file_folder=codeLink'>PDF</a></td></tr></table>"""


class FakeClient:
    def __init__(self, blob=None):
        self.blob = blob or pdf_bytes()
        self.fail_list = False
        self.fail_download = False

    def list_codes(self, wanted=None):
        if self.fail_list:
            raise OSError("HTTP 400: test failure")
        return [item()]

    def download(self, _item):
        if self.fail_download:
            raise TimeoutError("test timeout")
        return self.blob


class WatcherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.client = FakeClient()
        self.watch = kw.Watcher(self.root, self.client)
        self.baseline = [{"code": "GC205", "year": "2026", "title": "Welding standard",
                          "law": "KGS GC205", "item": "1.1", "content": "Old searchable requirement",
                          "source": "old.pdf"},
                         {"code": "FP216", "year": "2026", "title": "Other code",
                          "law": "KGS FP216", "item": "1.1", "content": "Other code stays unchanged"}]
        kw.atomic_write(self.watch.data, kw.encode_rows(self.baseline))
        self.original = self.watch.data.read_bytes()

    def tearDown(self):
        self.tmp.cleanup()

    def sync(self, **kwargs):
        return self.watch.sync(["GC205"], **kwargs)

    def latest(self):
        return self.watch.state()["codes"]["GC205"]["latest_sha256"]

    def test_same_year_same_url_change_gets_new_version_without_reusing_date(self):
        self.sync(apply=True)
        first = self.latest()
        self.watch.set_effective("GC205", first, "2026-01-01")
        self.client.blob = pdf_bytes(body="Changed within the same year. " * 20)
        report = self.sync(apply=True)
        second = self.latest()
        self.assertNotEqual(first, second)
        self.assertEqual(report["pending"][0]["reason"], "needs_effective_date")
        self.assertTrue(all(r.get("version_sha256") == first for r in kw.read_rows(self.watch.data)
                            if r["code"] == "GC205"))
        self.watch.set_effective("GC205", second, "2026-02-01")
        active = kw.read_rows(self.watch.data)
        self.assertTrue(all(r.get("version_sha256") == second for r in active if r["code"] == "GC205"))
        self.assertEqual([r for r in active if r["code"] == "FP216"], self.baseline[1:])
        self.assertTrue((self.watch.version_dir("GC205", first) / "document.pdf").exists())
        self.assertTrue(list((self.watch.work / "backups").glob("*.jsonl")))

    def test_unknown_date_stays_pending(self):
        report = self.sync(apply=True)
        self.assertFalse(report["applied"])
        self.assertEqual(self.watch.data.read_bytes(), self.original)
        self.assertEqual(report["pending"][0]["reason"], "needs_effective_date")

    def test_future_version_activates_on_date_even_when_source_is_offline(self):
        self.sync()
        sha = self.latest()
        result = self.watch.set_effective("GC205", sha, "2027-02-01", today=date(2027, 1, 31))
        self.assertFalse(result["applied"])
        self.assertEqual(self.watch.data.read_bytes(), self.original)
        self.client.fail_list = True
        report = self.sync(apply=True, today=date(2027, 2, 1))
        self.assertTrue(report["errors"])
        self.assertEqual(report["applied"][0]["sha256"], sha)

    def test_timeout_and_list_failure_preserve_active_and_last_version(self):
        self.sync()
        sha = self.latest()
        for attr in ("fail_download", "fail_list"):
            setattr(self.client, attr, True)
            report = self.sync(apply=True)
            self.assertTrue(report["errors"])
            self.assertEqual(self.watch.data.read_bytes(), self.original)
            self.assertEqual(self.latest(), sha)
            setattr(self.client, attr, False)

    def test_empty_catalog_and_missing_code_are_errors(self):
        for rows in ([], [item("FP216")]):
            with patch.object(self.client, "list_codes", return_value=rows):
                report = self.sync(apply=True)
                self.assertTrue(report["errors"])
                self.assertEqual(self.watch.data.read_bytes(), self.original)

    def test_wrong_code_pdf_and_html_download_do_not_replace_data(self):
        for blob in (b"<html>login</html>", pdf_bytes("FP216")):
            self.client.blob = blob
            report = self.sync(apply=True)
            self.assertTrue(report["errors"])
            self.assertEqual(self.watch.data.read_bytes(), self.original)

    def test_dry_run_writes_no_state_versions_or_corpus(self):
        report = self.sync(dry_run=True, apply=True)
        self.assertTrue(report["changed"])
        self.assertFalse(self.watch.state_file.exists())
        self.assertFalse((self.watch.work / "versions").exists())
        self.assertEqual(self.watch.data.read_bytes(), self.original)

    def test_repeat_run_is_idempotent(self):
        self.sync()
        sha = self.latest()
        self.watch.set_effective("GC205", sha, "2026-01-01")
        before = self.watch.data.read_bytes()
        report = self.sync(apply=True)
        self.assertEqual(report["changed"], [])
        self.assertEqual(report["applied"], [])
        self.assertEqual(self.watch.data.read_bytes(), before)

    def test_effective_confirmation_is_bound_to_exact_hash(self):
        self.sync()
        with self.assertRaises(ValueError):
            self.watch.set_effective("GC205", "0" * 64, "2026-01-01")
        self.assertEqual(self.watch.data.read_bytes(), self.original)

    def test_corrupt_snapshot_never_replaces_active(self):
        self.sync()
        sha = self.latest()
        folder = self.watch.version_dir("GC205", sha)
        (folder / "document.pdf").write_bytes(b"broken")
        with self.assertRaises(ValueError):
            self.watch.set_effective("GC205", sha, "2026-01-01")
        self.assertEqual(self.watch.data.read_bytes(), self.original)

    def test_atomic_replace_failure_keeps_previous_corpus(self):
        self.sync()
        sha = self.latest()
        replace = os.replace
        def fail_corpus(src, dst):
            if Path(dst) == self.watch.data:
                raise OSError("disk unavailable")
            return replace(src, dst)
        with patch("kgs_watch.os.replace", side_effect=fail_corpus), self.assertRaises(OSError):
            self.watch.set_effective("GC205", sha, "2026-01-01")
        self.assertEqual(self.watch.data.read_bytes(), self.original)
        self.assertFalse(list(self.watch.data.parent.glob(".kgs-*")))

    def test_second_writer_is_rejected(self):
        with kw.exclusive_lock(self.watch.work / "watch.lock"):
            with self.assertRaises(RuntimeError):
                self.sync()

    def test_search_and_answer_cache_reload_without_restart(self):
        import app
        import distance
        import facts
        with contextlib.ExitStack() as stack:
            for name, value in {"DATA": self.root / "data", "EMB": self.root / "data/embeddings.npy",
                                "HAVE": self.root / "data/embeddings_have.npy",
                                "EMB_META": self.root / "data/embeddings.json",
                                "_index": None, "_index_stamp": None}.items():
                stack.enter_context(patch.object(search, name, value))
            stack.enter_context(patch.object(app, "HERE", self.root))
            first = search.get_index()
            key = app._cache_key("welding", None, None, None, False)
            self.sync()
            sha = self.latest()
            self.watch.set_effective("GC205", sha, "2026-01-01")
            second = search.get_index()
            self.assertIsNot(first, second)
            self.assertNotEqual(key, app._cache_key("welding", None, None, None, False))
            self.assertTrue(second.search("Original requirement"))
            self.assertEqual(app.pdf_file_of("GC205"), self.watch.version_dir("GC205", sha) / "document.pdf")
            self.assertFalse(search.kgs_table_current({"law": "KGS GC205"}))
            self.assertTrue(search.kgs_table_current({"law": "KGS GC205", "version_sha256": sha}))
            self.assertEqual([r for r in second.docs if r["law"] == "KGS GC205"][0]["effective_date"], "2026-01-01")

    def test_read_only_status_endpoint_reports_active_version(self):
        import app
        self.sync()
        sha = self.latest()
        self.watch.set_effective("GC205", sha, "2026-01-01")
        server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.object(app, "HERE", self.root):
                url = f"http://127.0.0.1:{server.server_port}/api/kgs-updates"
                with urllib.request.urlopen(url, timeout=5) as response:
                    result = json.load(response)
                self.assertEqual(result["active"]["GC205"]["sha256"], sha)
                self.assertEqual(result["active"]["GC205"]["effective_on"], "2026-01-01")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


class CollectorTests(unittest.TestCase):
    def test_catalog_parse_includes_same_year_revision_and_entities(self):
        row = fetch_kgs_code.parse(HTML)[0]
        self.assertEqual(row["code"], "GC205")
        self.assertEqual(row["revised_on"], "2026-10-30")
        self.assertEqual(row["title"], "Welding & testing")

    def test_long_unspaced_text_terminates_and_preserves_content(self):
        text = "1.1 " + "x" * 5000
        pieces = split_items(text)
        self.assertGreater(len(pieces), 2)
        self.assertEqual("".join(b.replace(" ", "") for _, b in pieces), text.replace(" ", ""))

    def test_only_unambiguous_explicit_effective_date_is_accepted(self):
        self.assertEqual(kw.explicit_effective_date("이 기준은 2026년 11월 1일부터 시행한다."), "2026-11-01")
        for text in ("개정 2026년 11월 1일", "승인 2026년 11월 1일",
                     "이 기준은 2026년 11월 1일부터 시행한다. 경과조치", "이 기준은 2026년 13월 1일부터 시행"):
            self.assertIsNone(kw.explicit_effective_date(text))

    def test_real_http_session_listing_and_post_download_against_fixture(self):
        blob = pdf_bytes()
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(("GET", self.path, self.headers.get("Cookie")))
                self.send_response(200)
                self.send_header("Set-Cookie", "KGSSESSION=fixture; Path=/")
                self.end_headers()
                self.wfile.write(("<html>home</html>" if "Index.do" in self.path else HTML).encode())
            def do_POST(self):
                params = urllib.parse.parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
                requests.append(("POST", params, self.headers.get("Cookie")))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(blob)
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with patch.multiple(fetch_kgs_code, BASE=base, LIST=base + "/kgscode.list.do", DOWN=base + "/download"):
                client = fetch_kgs_code.KgsClient(pace=0)
                rows = client.list_codes()
                self.assertEqual(len(rows), 1)
                self.assertEqual(client.download(rows[0]), blob)
                self.assertEqual(requests[-1][1]["file_folder"], ["codeLink"])
                self.assertIn("KGSSESSION=fixture", requests[-1][2])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_stale_vectors_rejected_even_if_document_count_is_equal(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"BOT_LOCAL_EMBED": "0"}):
            root = Path(tmp)
            np.save(root / "v.npy", np.ones((1, 2)))
            np.save(root / "h.npy", np.ones(1, dtype=bool))
            (root / "m.json").write_text(json.dumps({"corpus_sha256": "old"}))
            docs = [{"law": "KGS GC205", "article": "[KGS GC205 1.1]", "title": "",
                     "content": "new content", "country": "한국", "kind": "상세기준"}]
            with patch.multiple(search, EMB=root / "v.npy", HAVE=root / "h.npy", EMB_META=root / "m.json"):
                self.assertIsNone(search.Index(docs).vecs)
                (root / "m.json").write_text(json.dumps({"corpus_sha256": search.docs_fingerprint(docs)}))
                self.assertIsNotNone(search.Index(docs).vecs)


if __name__ == "__main__":
    unittest.main()
