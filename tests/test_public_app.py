"""Public boundary and complete mocked-renderer productions with real media assembly."""
import shutil
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import oap
from fastapi.testclient import TestClient
from PIL import Image

from mmv import production, production_queue
from mmv import actors, media, render
from mmv.api_profiles import save_settings
from mmv.jobs import Jobs, BusyError
from mmv.setup import SessionLock, doctor, download_models
from mmv.storage import Storage, inside, read_json, write_json
from webapp.mondo_web import api_version, create_app, MGL_APP_VERSION


def picture():
    data = io.BytesIO()
    Image.new("RGB", (64, 80), "teal").save(data, "PNG")
    return data.getvalue()


from mock_comfy_v2 import ComfyV2Mixin, reset_v2


def mock_singing_body(job, shot, text):
    """Like the real writer: actors are `<Subject N>` (cast position); singing shots quote the words the job assigns them."""
    performance = job.get('instrument_performance') or {}
    actions = []
    for player in performance.get('performers', []):
        cue = next(c for c in player['shots'] if c['n'] == shot['n'])
        action = 'rests both hands without playing' if cue['paused'] else {
            'drums': 'strikes the snare with sticks', 'bass': 'plucks bass strings while fretting',
            'guitar': 'strums guitar strings while fretting', 'keyboards': 'presses keyboard keys with both hands'}[player['instrument']]
        actions.append(f"{player['subject']} {action} {player.get('instrument_picture_tag') or ''}.")
    text = ' '.join(actions) + ' ' + text if actions else text
    singing = job.get("singing")
    if not singing:
        return text * 3 + " Subject Rigging: lips firmly sealed shut, jaw completely relaxed, to prevent any facial babbling or lip-sync hallucinations."
    index = [i for i, member in enumerate(job["cast"]) if member["actor_id"] == singing["actor_id"]][0] + 1
    wanted = next((item for item in singing["shots"] if item["n"] == shot["n"]), {})
    if wanted.get("sung"):
        return f'<Subject {index}> sings "{wanted["words"]}" while lips and jaw shape each word. ' + text * 3
    return text * 3


class MockService(ComfyV2Mixin, BaseHTTPRequestHandler):
    requests = []
    video = b""
    # Clips returned before `video`, one per submission; lets tests stage a failing first render.
    queued_videos = []
    hold = False
    invalid_writer = False

    def log_message(self, *args):
        pass

    def reply(self, value):
        data = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.v2_post(data):
            return
        if self.path == "/media/upload/binary":
            self.reply({"data": {"download_url": "https://example.invalid/reference"}})
            return
        body = json.loads(data)
        type(self).requests.append((self.path, body))
        if self.path == "/prompt":
            graph = body["prompt"]
            prefix = graph["148"]["inputs"]["filename_prefix"]
            target = self.server.output / (prefix + "_00001.mp4")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(type(self).queued_videos.pop(0) if type(self).queued_videos else self.video)
            self.server.last_filename = target.name
            self.reply({"prompt_id": "local-test", "node_errors": {}})
        elif self.path == "/chat/completions":
            system = body["messages"][0].get("content", "") if len(body["messages"]) > 1 else ""
            user = body["messages"][-1]["content"]
            if isinstance(user, list):
                content = json.dumps({"style_card":"Soft teal light", "aesthetic_directives":"Soft teal light and textured paper, with patient camera movement."})
            elif user.startswith("TEXT:"):
                title = user.splitlines()[0][6:]
                content = 'The words "' + title + '" emerge in brushed metal with continuous motion, then hold motionless and legible. Silent scene, no musical score.'
            else:
                user_json = user.split("\n\nCorrect these validation failures", 1)[0]
                job = json.loads(user_json)
                text = "The fully clothed performer moves through warm light as wind lifts the fabric of a blue jacket. Reflections trace shifting patterns across nearby glass while the camera follows with deliberate rhythmic motion and the scene remains grounded in a coherent physical space. The subject stays recognizable and each movement carries the energy of the music through precise visible changes in posture and light. "
                content = json.dumps({"segment_id":job["segment_id"], "style_opening":"Cinematic daylight photography with expressive movement.",
                    "subject_definitions":[], "summary":"A fully clothed performer in sunlight.", "retention_analysis":[],
                    "shot_bodies":[(mock_singing_body(job, shot, text)) for shot in job["shots"]], "overall_soundscape":"Wind and quiet footsteps.", "non_diegetic_music":"N/A"})
            if self.invalid_writer: content = "{}"
            self.reply({"choices":[{"message":{"content":content}}]})
        elif self.path == "/queue":
            self.reply({})
        else:
            self.reply({"data": {"id": "hosted-test"}})

    def do_GET(self):
        if self.v2_get():
            return
        if self.path.startswith("/view") or self.path == "/video.mp4":
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(self.video)))
            self.end_headers()
            self.wfile.write(self.video)
        elif self.path.startswith("/object_info/"):
            self.reply(self.server.object_info.get(self.path.rsplit('/', 1)[-1], {}))
        elif self.path.startswith("/history/"):
            self.reply({} if self.hold else {"local-test": {"status": {"status_str": "success"},
                        "outputs": {"2": {"videos": [{"filename": self.server.last_filename, "subfolder": "", "type": "output"}]}}}})
        elif self.path.startswith("/predictions/"):
            self.reply({"data": {"status": "completed", "outputs": [f"http://127.0.0.1:{self.server.server_port}/video.mp4"]}})
        elif self.path == "/queue":
            # An idle ComfyUI, as the pre-prompt model release requires; the device reports no GPU memory to wait for.
            self.reply({"queue_running": [], "queue_pending": []})
        elif self.path == "/system_stats":
            self.reply({"devices": [{"name": "mock", "type": "cpu"}]})
        else:
            self.reply({})


class PublicAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media_temp = tempfile.TemporaryDirectory()
        directory = Path(cls.media_temp.name)
        video, song, score_path = directory / "test.mp4", directory / "test.wav", directory / "score.json"
        # Moving, detailed footage passes the motion/framing gate like a real render.
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i",
                        "testsrc2=s=128x72:r=24:d=6", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)], check=True)
        # A frozen, white-pillarboxed clip reproduces the real H3 failure the gate exists for.
        frozen = directory / "frozen.mp4"
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i",
                        "color=c=teal:s=96x72:r=24:d=6", "-vf", "noise=alls=6:allf=0,pad=128:72:16:0:white",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(frozen)], check=True)
        cls.frozen_video = frozen.read_bytes()
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i",
                        "sine=frequency=440:duration=1.1", str(song)], check=True)
        subprocess.run([sys.executable, "-m", "mmv.worker", "analyze", str(song), str(score_path), "4"], check=True)
        cls.song = song.read_bytes()
        cls.song_analysis_digest = hashlib.sha256(cls.song + b"4").hexdigest()
        cls.song_analysis_bytes = score_path.read_bytes()
        MockService.video = video.read_bytes()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), MockService)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.media_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.app = create_app(self.home, test_hosts=True)
        self.client = TestClient(self.app)
        self.store = self.app.state.store
        (self.home / "comfy-input").mkdir()
        (self.home / "comfy-output").mkdir()
        analysis_dir = self.home / "analysis"
        analysis_dir.mkdir(exist_ok=True)
        (analysis_dir / f"{self.song_analysis_digest}.json").write_bytes(self.song_analysis_bytes)
        self.server.output = self.home / "comfy-output"
        reset_v2(self.server)
        self.server.object_info = {}
        MockService.requests = []
        MockService.hold = False
        MockService.invalid_writer = False
        settings = self.store.settings()
        settings.update(comfy_url=self.url, comfy_input=str(self.home / "comfy-input"), comfy_output=str(self.home / "comfy-output"),
                        laya_model_dir=os.environ.get("MMV_TEST_LAYA_MODEL_DIR", str(self.home / "models/laya")), laya_device="cuda",
                        writer_url=self.url, writer_model="fixture-writer", vision_url=self.url, vision_model="fixture-vision",
                        writer_launch='["fixture-writer", "-ngl", "0"]')  # The HTTP fixture uses no GPU.
        if not os.environ.get("MMV_TEST_LAYA_MODEL_DIR"):
            model = self.home / "models/laya"
            (model / "tokenizer").mkdir(parents=True)
            (model / "encoder").mkdir()
            for name in ("model.safetensors", "rl_agent_config.json", "encoder/config.json"):
                (model / name).write_text("fixture")
            from mmv.jobs import JobContext
            original_command = JobContext.command
            def test_command(context, argv, **kwargs):
                if "mmv.worker" in argv and ("produce" in argv or "rewrite_prompt" in argv):
                    argv = ["mock_laya_worker" if x == "mmv.worker" else x for x in argv]
                    env = {**os.environ, **(kwargs.get("env") or {})}
                    env["PYTHONPATH"] = str(Path(__file__).parent) + os.pathsep + env.get("PYTHONPATH", "")
                    kwargs["env"] = env
                return original_command(context, argv, **kwargs)
            self.worker_patch = patch("mmv.jobs.JobContext.command",test_command)
            self.worker_patch.start()
        save_settings(self.store, settings)

    def tearDown(self):
        if hasattr(self,"worker_patch"): self.worker_patch.stop()
        if self.app.state.jobs.active:
            self.app.state.jobs.cancel()
            self.wait()
        self.client.close()
        self.temp.cleanup()

    def song_upload(self):
        response = self.client.post("/api/upload/song", files={"file": ("test.wav", self.song, "audio/wav")})
        response.raise_for_status()
        return response.json()["file"]

    def wait(self, timeout=90):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.client.get("/api/status").json()
            if status["state"] not in ("running", "cancelling") and self.app.state.jobs.active is None:
                if status["state"] == "failed":
                    print((self.home / "runs" / status["id"] / "operation.log").read_text())
                return status
            time.sleep(.05)
        self.fail("Operation did not finish")

    def start(self, request, consent=True):
        quote = self.client.post("/api/quote", json=request)
        quote.raise_for_status()
        start = self.client.post("/api/start", json={"quote_id": quote.json()["id"], "consent": consent})
        return quote, start

    def configure_sdk(self):
        settings = self.store.settings()
        settings.update(comfy_sdk_url=self.url, comfy_input='', comfy_output='')
        self.client.put('/api/settings', json=settings).raise_for_status()
        self.store.save_key('MMV_COMFY_API_KEY', 'fake-proxy-token')

    @unittest.skipUnless(importlib.util.find_spec('comfy_sdk'), 'optional official SDK not installed')
    def test_sdk_production_transfers_media_and_assembles(self):
        self.configure_sdk()
        actors.create_actor(self.store, 'blue', 'Blue', 'Blue jacket', picture())
        quote, started = self.start({'backend': 'comfy_sdk_h3', 'song': self.song_upload(), 'actors': ['blue']})
        started.raise_for_status()
        status = self.wait()
        self.assertEqual(status['state'], 'complete')
        self.assertEqual(quote.json()['estimate_usd'], 0)
        self.assertEqual(len(self.server.v2_submits), 1)
        headers, body = self.server.v2_submits[0]
        self.assertEqual(headers['Authorization'], 'Bearer fake-proxy-token')
        self.assertTrue(headers['Idempotency-Key'])
        graph = body['workflow']
        self.assertEqual(graph['124']['inputs']['steps'], 20)
        ref_node = graph['136']['inputs']
        image_loader = graph[ref_node['ref_images.ref_image_0'][0]]
        audio_loader = graph[ref_node['ref_audios.ref_audio_0'][0]]
        for loader, widget in [(image_loader, 'image'), (audio_loader, 'audio')]:
            asset_ref = loader['inputs'][widget]
            self.assertEqual(asset_ref['__type'], 'core/ASSET')
            self.assertIn(asset_ref['info']['id'], self.server.v2_assets)
        self.assertEqual(len(self.server.v2_assets), 2)
        run = self.home / 'runs' / status['id']
        self.assertRegex(status['id'], r'^test_\d{4}-\d{2}-\d{2}_\d{6}(?:-\d+)?$')
        self.assertTrue((run / 'music-video.mp4').is_file())
        self.assertAlmostEqual(media.duration(run / 'music-video.mp4'), 1.1, delta=.08)
        self.assertFalse((run / 'untrusted.mp4').exists())
        receipt = read_json(next((run / 'renders').glob('*/comfy-request.json')))
        self.assertEqual(receipt['job_id'], self.server.v2_ids[0])
        self.assertNotIn('fake-proxy-token', json.dumps(receipt))
        self.assertNotIn('fake-proxy-token', self.client.get('/api/settings').text)

    @unittest.skipUnless(importlib.util.find_spec('comfy_sdk'), 'optional official SDK not installed')
    def test_sdk_download_failure_resumes_without_generation_or_writer(self):
        self.configure_sdk()
        self.server.v2_download_fail = True
        _, started = self.start({'backend': 'comfy_sdk_h3', 'song': self.song_upload()})
        started.raise_for_status()
        status = self.wait()
        self.assertEqual(status['state'], 'failed')
        before = len(MockService.requests)
        self.server.v2_download_fail = False
        original = self.store.settings()
        changed = {**original, 'writer_model': 'changed-model'}
        self.client.put('/api/settings', json=changed).raise_for_status()
        stale = self.client.post('/api/resume/quote', json={'run_id': status['id']})
        self.assertEqual(stale.status_code, 400)
        self.client.put('/api/settings', json=original).raise_for_status()
        quote = self.client.post('/api/resume/quote', json={'run_id': status['id']})
        quote.raise_for_status()
        self.assertEqual(self.client.post('/api/start', json={'quote_id': quote.json()['id'], 'consent': False}).status_code, 400)
        resumed = self.client.post('/api/start', json={'quote_id': quote.json()['id'], 'consent': True})
        resumed.raise_for_status()
        self.assertEqual(resumed.json()['id'], status['id'])
        self.assertEqual(self.wait()['state'], 'complete')
        self.assertEqual(len(self.server.v2_submits), 1)
        self.assertEqual(len(MockService.requests), before)

    @unittest.skipUnless(importlib.util.find_spec('comfy_sdk'), 'optional official SDK not installed')
    def test_sdk_ambiguous_submission_is_never_retried(self):
        self.configure_sdk()
        self.server.v2_drop = True
        _, started = self.start({'backend': 'comfy_sdk_h3', 'song': self.song_upload()})
        started.raise_for_status()
        status = self.wait()
        self.assertEqual(status['state'], 'failed')
        self.assertEqual(len(self.server.v2_submits), 1)
        receipt = read_json(next((self.home / 'runs' / status['id'] / 'renders').glob('*/comfy-request.json')))
        self.assertEqual(receipt['state'], 'unknown')
        quote = self.client.post('/api/resume/quote', json={'run_id': status['id']})
        self.assertEqual(quote.status_code, 400)
        self.assertIn('unknown', quote.json()['detail'])
        self.assertEqual(len(self.server.v2_submits), 1)

    @unittest.skipUnless(importlib.util.find_spec('comfy_sdk'), 'optional official SDK not installed')
    def test_sdk_queue_full_does_not_trigger_hidden_sdk_retry(self):
        self.configure_sdk()
        self.server.v2_reject = True
        _, started = self.start({'backend': 'comfy_sdk_h3', 'song': self.song_upload()})
        started.raise_for_status()
        self.assertEqual(self.wait()['state'], 'failed')
        self.assertEqual(len(self.server.v2_submits), 1)

    @unittest.skipUnless(importlib.util.find_spec('comfy_sdk'), 'optional official SDK not installed')
    def test_sdk_cancels_only_recorded_job(self):
        self.configure_sdk()
        self.server.v2_hold = True
        _, started = self.start({'backend': 'comfy_sdk_h3', 'song': self.song_upload()})
        started.raise_for_status()
        deadline = time.monotonic() + 30
        receipt = self.home / 'runs' / started.json()['id'] / 'renders/seg000/comfy-request.json'
        while time.monotonic() < deadline:
            if read_json(receipt, {}).get('job_id'):
                break
            time.sleep(.05)
        self.assertTrue(read_json(receipt, {}).get('job_id'))
        self.client.post('/api/cancel').raise_for_status()
        self.assertEqual(self.wait()['state'], 'cancelled')
        self.assertEqual(self.server.v2_cancels, self.server.v2_ids)
        self.assertEqual(len(self.server.v2_submits), 1)

    @unittest.skipUnless(importlib.util.find_spec('comfy_sdk'), 'optional official SDK not installed')
    def test_sdk_oap_rejection_happens_before_upload_or_submit(self):
        self.configure_sdk()
        actors.create_actor(self.store, 'blue', 'Blue', '', picture())
        content = {key: 'none' for key in oap.CONTENT_ENUMS}
        content['nudity'] = 'explicit'
        response = self.client.post('/api/quote', json={'backend': 'comfy_sdk_h3',
            'song': self.song_upload(), 'actors': ['blue'], 'content': content})
        self.assertEqual(response.status_code, 400)
        self.assertIn('exceeds rider', response.json()['detail'])
        self.assertEqual(self.server.v2_assets, {})
        self.assertEqual(self.server.v2_submits, [])

    @unittest.skipUnless(importlib.util.find_spec('comfy_sdk'), 'optional official SDK not installed')
    def test_sdk_known_job_timeout_recovers_without_resubmission(self):
        from mmv.engine.backends.base import BackendError
        self.configure_sdk()
        self.server.v2_hold = True
        song = self.home / 'song.wav'
        song.write_bytes(self.song)
        backend = render.get_backend('comfy_sdk_h3')
        from mmv.pipeline import ENGINE
        backend.open_render(out_dir=self.home / 'recovery', comfy_sdk_url=self.url,
                            map_path=ENGINE / 'config/injection_map.json', root=ENGINE, timeout_s=.01)
        job = dict(segment_id='seg000', index=0, slug='timeout-test', prompt='A sunlit coast.',
                   gen_frames=39, duration_input=1.625, width=128, height=72, seed=0,
                   images=[], song=str(song), audio_start_s=0, audio_end_s=1.1)
        try:
            with self.assertRaisesRegex(BackendError, 'timed out'):
                backend.render_segment(**job)
            self.server.v2_hold = False
            result = backend.render_segment(**job)
            self.assertTrue(Path(result['video']).is_file())
            self.assertEqual(len(self.server.v2_submits), 1)
            # Even a changed seed cannot repurpose a saved receipt for a new submission.
            with self.assertRaisesRegex(BackendError, 'different inputs'):
                backend.render_segment(**{**job, 'seed': 1})
            self.assertEqual(len(self.server.v2_submits), 1)
        finally:
            backend.close_render()

    def test_local_h3_timeout_none_defaults_to_float(self):
        backend = render.get_backend('local_h3')
        from mmv.pipeline import ENGINE
        from mmv.engine.comfy import ComfyClient
        with tempfile.TemporaryDirectory() as tmp, patch.object(ComfyClient, 'is_up', return_value=True):
            backend.open_render(slug='slug', out_dir=Path(tmp) / 'renders',
                                map_path=ENGINE / 'config/injection_map.json', root=ENGINE,
                                timeout_s=None, comfy_host='127.0.0.1', comfy_port=8188,
                                comfy_input=Path(tmp) / 'in', comfy_output=Path(tmp) / 'out')
            self.assertEqual(backend._timeout, 7200.0)
            self.assertIsInstance(backend._timeout, float)

    @unittest.skipUnless(importlib.util.find_spec('comfy_sdk'), 'optional official SDK not installed')
    def test_sdk_rejects_followup_links_to_another_origin(self):
        from mmv.comfy_sdk import SdkSession
        session = SdkSession(self.url, 'fake-proxy-token')
        try:
            with self.assertRaisesRegex(ValueError, 'outside the configured local endpoint'):
                session.low.raw_request('GET', 'https://example.invalid/api/v2/jobs/fake')
        finally:
            session.close()

    def test_sdk_settings_refuse_nonlocal_or_credential_urls(self):
        for url in ['https://cloud.comfy.org', 'http://127.0.0.1:8189?token=secret',
                    'http://secret@localhost:8189', 'http://localhost:8189/path']:
            settings = self.store.settings()
            settings['comfy_sdk_url'] = url
            self.assertEqual(self.client.put('/api/settings', json=settings).status_code, 422)

    def test_sidebar_tab_order_and_numbering(self):
        import re
        html = (Path(__file__).resolve().parents[1] / "webapp" / "index.html").read_text()
        tabs = re.findall(r'<button class="nav[^"]*" data-panel="(\w+)".*?<span>(\d\d)</span>', html)
        self.assertEqual([k for k, _ in tabs], ["video", "idents", "actors", "styles", "harvest", "vocab", "worlds", "queue", "outputs", "settings"])
        self.assertEqual([n for _, n in tabs], ["%02d" % i for i in range(1, len(tabs) + 1)])
        eyebrows = dict(re.findall(r'<section id="panel-(\w+)"[^>]*><div[^>]*class="eyebrow"[^>]*>(\d\d) /', html))
        self.assertEqual(eyebrows, dict(tabs))

    def test_version_matches_package_and_readme(self):
        import tomllib
        root = Path(__file__).resolve().parents[1]
        project = tomllib.loads((root / "pyproject.toml").read_text())
        self.assertEqual(api_version()["version"], "1.12.2")
        self.assertEqual(project["project"]["version"], MGL_APP_VERSION)
        self.assertIn("1.12.2", (root / "README.md").read_text())
        self.assertEqual(self.client.get("/api/version").json(), api_version())

    def test_quick_start_button_dialog_and_endpoint(self):
        html = self.client.get("/").text
        self.assertIn('id="quick-start"', html)
        self.assertIn('id="quick-start-dialog"', html)
        self.assertIn("Select a song to begin", html)
        self.assertLess(html.index('id="quick-start"'), html.index('class="song-input"'))
        self.assertEqual(self.client.get("/js/quick_start.js").status_code, 200)
        self.assertIn('id="start-fresh"', html)
        self.assertIn('id="start-fresh-dialog"', html)
        plan = self.client.get("/api/quick-start").json()
        self.assertIn(plan["dance_mode"], ("off", "group"))
        self.assertEqual(plan["dancers"], plan["actors"] if plan["dance_mode"] == "group" else [])

    def test_frontend_es_modules_served_and_protected(self):
        app_res = self.client.get("/app.js")
        self.assertEqual(app_res.status_code, 200)
        self.assertIn("text/javascript", app_res.headers["content-type"])
        for mod in ("queue.js", "core.js", "tooltips.js", "project.js", "library.js", "outputs.js", "settings.js", "production.js", "guides.js", "vocab-model.js", "vocabulary.js", "component_labeling.js", "markdown.js"):
            res = self.client.get(f"/js/{mod}")
            self.assertEqual(res.status_code, 200, mod)
            self.assertIn("text/javascript", res.headers["content-type"])
        self.assertEqual(self.client.get("/js/nonexistent.js").status_code, 400)
        self.assertEqual(self.client.get("/js/index.html").status_code, 400)

    def test_favicons_served_and_linked(self):
        ico_res = self.client.get("/favicon.ico")
        self.assertEqual(ico_res.status_code, 200)
        self.assertIn("image/x-icon", ico_res.headers["content-type"])
        self.assertGreater(len(ico_res.content), 0)

        svg_res = self.client.get("/favicon.svg")
        self.assertEqual(svg_res.status_code, 200)
        self.assertIn("image/svg+xml", svg_res.headers["content-type"])
        self.assertIn("<svg", svg_res.text)

        html = self.client.get("/").text
        self.assertIn('href="/favicon.svg"', html)
        self.assertIn('href="/favicon.ico"', html)

    def test_uploaded_song_preview_endpoint(self):
        up = self.client.post("/api/upload/song", files={"file": ("track.wav", self.song, "audio/wav")})
        self.assertEqual(up.status_code, 200)
        uploaded_name = up.json()["file"]
        res = self.client.get(f"/api/uploads/song/{uploaded_name}")
        self.assertEqual(res.status_code, 200)
        self.assertIn("audio/wav", res.headers["content-type"])
        self.assertEqual(res.content, self.song)
        missing = self.client.get("/api/uploads/song/nonexistent.wav")
        self.assertEqual(missing.status_code, 400)

    def test_services_status_endpoint(self):
        res = self.client.get("/api/services/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("laya", data)
        self.assertIn("writer", data)
        self.assertIn("comfy", data)
        self.assertIn("vision", data)
        for key in ("laya", "writer", "comfy", "vision"):
            svc = data[key]
            self.assertIn("name", svc)
            self.assertIn("role", svc)
            self.assertIn("available", svc)
            self.assertIn("activity", svc)
            self.assertIn("detail", svc)
            self.assertIn(svc["activity"], ("processing", "sleeping", "offline", "missing"))

    def test_status_endpoint_includes_services(self):
        res = self.client.get("/api/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("services", data)
        self.assertIn("laya", data["services"])
        self.assertIn("writer", data["services"])
        self.assertIn("comfy", data["services"])

    def test_services_activity_evaluation(self):
        from mmv.services import _evaluate_service_activity
        probed = {
            "comfy": {"url": "http://127.0.0.1:8188", "available": True, "device": "RTX 4090", "queue_running": 0},
            "writer": {"mode": "local", "url": "http://127.0.0.1:8081", "model": "qwen3", "available": True, "slots_processing": 0},
            "laya": {"model_dir": "/mock/laya", "device": "cuda", "available": True},
            "vision": {"url": "http://127.0.0.1:8081", "model": "vision", "available": True},
        }
        # When idle: all available services should be sleeping
        idle_eval = _evaluate_service_activity(self.store, probed, {"state": "idle", "message": ""})
        self.assertEqual(idle_eval["comfy"]["activity"], "sleeping")
        self.assertEqual(idle_eval["writer"]["activity"], "sleeping")
        self.assertEqual(idle_eval["laya"]["activity"], "sleeping")
        self.assertEqual(idle_eval["vision"]["activity"], "sleeping")

        # When actively rendering in comfy:
        render_eval = _evaluate_service_activity(self.store, probed, {"state": "running", "message": "Rendering passage 1"})
        self.assertEqual(render_eval["comfy"]["activity"], "processing")
        self.assertEqual(render_eval["writer"]["activity"], "sleeping")

        # When actively writing prompts:
        writer_eval = _evaluate_service_activity(self.store, probed, {"state": "running", "message": "Writer developing passage direction"})
        self.assertEqual(writer_eval["writer"]["activity"], "processing")
        self.assertEqual(writer_eval["comfy"]["activity"], "sleeping")

        # When Laya is reviewing:
        laya_eval = _evaluate_service_activity(self.store, probed, {"state": "running", "message": "Laya reviewing passage 2"})
        self.assertEqual(laya_eval["laya"]["activity"], "processing")
        self.assertEqual(laya_eval["comfy"]["activity"], "sleeping")

    def test_each_video_renders_with_its_own_seed_while_the_variation_seed_keeps_the_plan(self):
        req = {"kind": "video", "backend": "local_h3", "song": self.song_upload()}
        quotes = [self.client.post("/api/quote", json=req).json() for _ in range(3)]
        self.assertEqual(len({q["render_seed"] for q in quotes}), 3, "videos must not share one built-in render seed")
        self.assertEqual({q["seed"] for q in quotes}, {0})
        self.assertEqual(quotes[0]["segments"], quotes[1]["segments"], "the same song and variation seed plan the same passages")
        chosen = self.client.post("/api/quote", json={**req, "seed": 9, "render_seed": 1234}).json()
        self.assertEqual((chosen["seed"], chosen["render_seed"]), (9, 1234))

    def test_service_logs_follow_the_operation_redoing_a_passage(self):
        from mmv.worker import service_logs
        production, job = self.home / "runs" / "song", self.home / "runs" / "reroll_song"
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MMV_SERVICE_LOG_DIR", None)
            self.assertEqual(service_logs(production), production)
            os.environ["MMV_SERVICE_LOG_DIR"] = str(job)
            self.assertEqual(service_logs(production), job)

    def test_offline_engines_guard_and_quote_reporting(self):
        original_settings = self.store.settings()
        # 1. Video request with offline writer
        bad_settings = {**original_settings, "writer_url": "http://127.0.0.1:9999", "writer_launch": ""}
        save_settings(self.store, bad_settings)
        req = {"kind": "video", "backend": "local_h3", "song": self.song_upload()}
        quote_res = self.client.post("/api/quote", json=req)
        self.assertEqual(quote_res.status_code, 200)
        quote_data = quote_res.json()
        self.assertIn("offline_engines", quote_data)
        self.assertTrue(any("Prompt Writer" in err for err in quote_data["offline_engines"]))

        # Attempting to start with offline writer must be blocked with HTTP 400
        start_res = self.client.post("/api/start", json={"quote_id": quote_data["id"], "consent": True})
        self.assertEqual(start_res.status_code, 400)
        self.assertIn("Prompt Writer", start_res.json()["detail"])

        # 2. Offline ComfyUI
        bad_comfy = {**original_settings, "comfy_url": "http://127.0.0.1:9998", "comfy_launch": ""}
        save_settings(self.store, bad_comfy)
        quote_res2 = self.client.post("/api/quote", json=req)
        quote_data2 = quote_res2.json()
        self.assertTrue(any("ComfyUI" in err for err in quote_data2["offline_engines"]))
        start_res2 = self.client.post("/api/start", json={"quote_id": quote_data2["id"], "consent": True})
        self.assertEqual(start_res2.status_code, 400)
        self.assertIn("ComfyUI", start_res2.json()["detail"])

        # 3. Harvest with offline Vision
        bad_vision = {**original_settings, "vision_url": "http://127.0.0.1:9997"}
        save_settings(self.store, bad_vision)
        ref_res = self.client.post("/api/upload/reference", files={"file": ("test.png", picture(), "image/png")})
        harvest_req = {"kind": "harvest", "style_id": "test_style", "references": [ref_res.json()["file"]]}
        quote_h = self.client.post("/api/quote", json=harvest_req)
        quote_h_data = quote_h.json()
        self.assertTrue(any("Vision" in err for err in quote_h_data["offline_engines"]))
        start_h = self.client.post("/api/start", json={"quote_id": quote_h_data["id"], "consent": True})
        self.assertEqual(start_h.status_code, 400)
        self.assertIn("Vision", start_h.json()["detail"])

        # Restore original settings
        save_settings(self.store, original_settings)

    def test_quality_vision_preview_and_start_do_not_need_the_style_harvest_endpoint(self):
        import socket
        from unittest.mock import Mock
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            free_port = probe.getsockname()[1]
        models = self.home / "vision-models"
        models.mkdir()
        (models / "qwen-Q4.gguf").write_bytes(b"")
        (models / "mmproj-qwen-f16.gguf").write_bytes(b"")
        settings = {**self.store.settings(), "vision_url": "http://127.0.0.1:1/v1", "vision_model": "harvest",
                    "writer_launch": json.dumps(["llama-server", "-m", str(models / "qwen-Q4.gguf"), "--port", "8081"])}
        save_settings(self.store, settings)
        request = {"kind": "video", "backend": "local_h3", "song": self.song_upload(), "vision_quality_check": True}
        started = Mock(return_value={"state": "running"})
        self.app.state.jobs.start = started
        with patch("mmv.vision_stage.VISION_PORT", free_port):
            quote = self.client.post("/api/quote", json=request)
            self.assertEqual(quote.status_code, 200, quote.text)
            self.assertEqual(quote.json()["offline_engines"], [])
            start = self.client.post("/api/start", json={"quote_id": quote.json()["id"], "consent": True})
            self.assertEqual(start.status_code, 200, start.text)
            started.assert_called_once()
            # The quality card is its own status entry; the harvester stays offline and separate.
            services = self.client.get("/api/status").json()["services"]
            self.assertEqual(services["vision_quality"]["role"], "Quality Check")
            self.assertTrue(services["vision_quality"]["has_launch"])
            self.assertFalse(services["vision"]["available"])
            # Without a launch command the same preview names the setting rather than the harvester.
            save_settings(self.store, {**settings, "writer_launch": ""})
            blocked = self.client.post("/api/quote", json=request)
        self.assertEqual(blocked.status_code, 400)
        self.assertIn("Vision quality check unavailable", blocked.json()["detail"])
        self.assertNotIn("8080", blocked.json()["detail"])

    def test_project_persistence_api(self):
        project = {
            "panel": "video",
            "forms": {"video-form": {"title": "My Track", "backend": "local_h3"}},
            "files": {"video-form": {"song": "test.wav", "references": []}},
            "details_open": True,
            "details_sections": {"director-camera": True, "director-render": False},
            "details_reviewed": {"director-render": True},
            "details_partial": {"card-track-direction": True},
            "log_open": False
        }
        res = self.client.put("/api/project", json=project)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["ok"])
        got = self.client.get("/api/project").json()
        self.assertEqual(got["panel"], "video")
        self.assertEqual(got["forms"]["video-form"]["title"], "My Track")
        self.assertTrue(got["details_open"])
        self.assertEqual(got["details_sections"], project["details_sections"])
        self.assertEqual(got["details_reviewed"], project["details_reviewed"])
        self.assertEqual(got["details_partial"], project["details_partial"])

    def test_actor_description_edit_keeps_signed_imports_immutable(self):
        actors.create_actor(self.store, "local_actor", "Local actor", "Blue jacket", picture())
        edited = self.client.patch("/api/actors/local_actor", json={"description": "Green coat"})
        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertEqual(self.store.actor("local_actor")["description"], "Green coat")
        self.assertEqual(self.client.patch("/api/actors/local_actor", json={"description": ""}).status_code, 400)
        (self.home / "actors/local_actor/original.oap").write_bytes(b"signed package placeholder")
        blocked = self.client.patch("/api/actors/local_actor", json={"description": "Different"})
        self.assertEqual(blocked.status_code, 400)
        self.assertIn("signed identity", blocked.json()["detail"])
        self.assertEqual(self.store.actor("local_actor")["description"], "Green coat")

    def test_panel_auto_collapse_setting_and_prop_guide(self):
        self.assertTrue(self.client.get("/api/settings").json()["settings"]["auto_collapse_panels"])
        changed = self.client.patch("/api/settings", json={"auto_collapse_panels": False})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertFalse(self.client.get("/api/settings").json()["settings"]["auto_collapse_panels"])
        guide = self.client.get("/api/props/guide")
        self.assertEqual(guide.status_code, 200)
        self.assertIn("Open Prop Protocol", guide.json()["markdown"])

    def test_every_sidebar_panel_can_be_saved_in_the_project(self):
        import re
        panels = set(re.findall(r'class="nav[^"]*" data-panel="([a-z]+)"', (Path(__file__).parents[1] / "webapp" / "index.html").read_text()))
        self.assertIn("worlds", panels)
        for panel in sorted(panels):
            res = self.client.put("/api/project", json={"panel": panel, "forms": {"world-form": {"title": "kept"}}})
            self.assertEqual(res.status_code, 200, f"{panel}: {res.text}")
        self.assertEqual(self.client.get("/api/project").json()["forms"]["world-form"]["title"], "kept")

    def test_clear_log_endpoint(self):
        studio_log = self.home / "studio.log"
        studio_log.write_text("historical error line\n", encoding="utf-8")
        self.assertIn("historical error", self.client.get("/api/log/latest").json()["log"])
        res = self.client.post("/api/log/clear")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "cleared"})
        self.assertEqual(self.client.get("/api/log/latest").json()["log"], "No operation or server log recorded yet.")
        self.assertEqual(studio_log.read_text(encoding="utf-8"), "")

    def test_sse_events_and_jobs_subscription(self):
        notifications = []
        unsub = self.app.state.jobs.subscribe(lambda st, log: notifications.append((st, log)))
        self.app.state.jobs.notify({"state": "test_state"}, log_line="test_line")
        unsub()
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0][0]["state"], "test_state")
        self.assertEqual(notifications[0][1], "test_line")

        with self.client.stream("GET", "/api/events?once=true") as response:
            self.assertEqual(response.status_code, 200)
            self.assertIn("text/event-stream", response.headers["content-type"])
            lines = [line for line in response.iter_lines() if line]
            self.assertEqual(lines[0], "event: status")
            self.assertIn('"state":', lines[1])

    def test_clear_cache_endpoint(self):
        cache_dir = self.home / "cache" / "prompts"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "test_prompt.json").write_text('{"prompt": "test"}', encoding="utf-8")
        self.assertTrue((cache_dir / "test_prompt.json").is_file())
        res = self.client.post("/api/cache/clear")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "cleared")
        self.assertEqual(res.json()["count"], 1)
        self.assertFalse((cache_dir / "test_prompt.json").exists())
        self.assertTrue((self.home / "cache_cleared.json").is_file())

    def test_empty_song_returns_friendly_error(self):
        res = self.client.post("/api/quote", json={"kind": "video", "song": "", "direction": "test"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("Upload a song first", res.json()["detail"])
        studio_log = (self.home / "studio.log").read_text(encoding="utf-8")
        self.assertIn("Preview failed (video): Upload a song first", studio_log)

    def test_passage_recovery_requires_matching_system(self):
        from types import SimpleNamespace
        from mmv.worker import find_cached_passage_prompt
        cache = self.home / "cache" / "prompts"
        cache.mkdir(parents=True, exist_ok=True)
        runs = self.home / "runs"
        previous = runs / "previous"
        (previous / "writer_jobs").mkdir(parents=True)
        job = {"segment_id": "seg000", "shots": []}
        write_json(previous / "writer_jobs/seg000.json", job)
        write_json(previous / "prompts.json", {"seg000": "validated old prompt"})
        (previous / "writer_system.md").write_text("old direction", encoding="utf-8")
        seg = SimpleNamespace(segment_id="seg000")
        self.assertIsNone(find_cached_passage_prompt(cache, runs, "new direction", job, seg, None))
        self.assertEqual(find_cached_passage_prompt(cache, runs, "old direction", job, seg, None),
                         "validated old prompt")
        # Matching saved prompts remain reusable after the fallback populated the cache.
        self.assertEqual(find_cached_passage_prompt(cache, None, "old direction", job, seg, None),
                         "validated old prompt")

    def test_compact_prompts_are_opt_in_and_default_keeps_full_ident_prompt(self):
        from mmv.engine import style
        self.assertFalse(self.client.post("/api/quote", json={"kind": "ident", "title": "Studio", "ident_seconds": 4}).json().get("request", {}).get("compact_prompts", False))
        full = style.compose_ident_prompt()
        sizes = {}
        for compact in (False, True):
            _, started = self.start({"kind": "ident", "title": "Studio", "ident_seconds": 4, "compact_prompts": compact})
            started.raise_for_status()
            self.assertEqual(self.wait()["state"], "complete")
            sizes[compact] = (self.home / "runs" / started.json()["id"] / "writer_system.md").read_text(encoding="utf-8")
        self.assertEqual(sizes[False], full)
        self.assertLess(len(sizes[True]), len(full))
        self.assertIn("Failure modes", sizes[True])

    def test_compact_prompts_default_sends_original_writer_message(self):
        import json as _json
        before = len([1 for path, _ in MockService.requests if path == "/chat/completions"])
        _, started = self.start({"song": self.song_upload(), "direction": "Coast", "title": "Coast", "reuse_prompts": False})
        started.raise_for_status()
        self.assertEqual(self.wait()["state"], "complete")
        bodies = [b for path, b in MockService.requests if path == "/chat/completions"][before:]
        user = [m for m in bodies[0]["messages"] if m["role"] == "user"][0]["content"]
        self.assertIn('\n  "', user)  # original indent=2 serialization, not compact separators

    def test_silent_mouths_default_applies_without_lyrics_and_natural_is_explicit(self):
        from mmv.engine.style import NATURAL_MOUTHS_RULE, SILENT_MOUTHS_RULE_V013
        rules = {}
        for natural in (False, True):
            _, started = self.start({"song": self.song_upload(), "direction": "Coast", "title": "Coast",
                                     "reuse_prompts": False, "silent_mouths": not natural})
            started.raise_for_status()
            self.assertEqual(self.wait()["state"], "complete")
            rules[natural] = (self.home / "runs" / started.json()["id"] / "writer_system.md").read_text(encoding="utf-8")
        self.assertEqual(self.client.get("/api/status").json().get("kind"), "video")
        self.assertIn(SILENT_MOUTHS_RULE_V013.strip(), rules[False])
        self.assertNotIn(NATURAL_MOUTHS_RULE.strip(), rules[False])
        self.assertIn(NATURAL_MOUTHS_RULE.strip(), rules[True])

    def test_production_supplies_public_actor_metadata(self):
        actors.create_actor(self.store, "blue", "Blue", "Distinctive blue jacket", picture())
        _, started = self.start({"song": self.song_upload(), "actors": ["blue"]})
        started.raise_for_status()
        self.assertEqual(self.wait()["state"], "complete")
        system = (self.home / "runs" / started.json()["id"] / "writer_system.md").read_text(encoding="utf-8")
        self.assertIn("CAST MEMBER: Blue", system)
        self.assertIn("Distinctive blue jacket", system)

    def test_prompt_caching_and_resumption(self):
        song = self.song_upload()
        quote, started = self.start({"song": song, "direction": "A sunlit coast", "title": "Coast", "seed": 11})
        started.raise_for_status()
        status = self.wait()
        self.assertEqual(status["state"], "complete")
        run_1 = self.home / "runs" / started.json()["id"]
        prompts_1 = read_json(run_1 / "prompts.json")
        self.assertTrue(bool(prompts_1))

        # Second production reuses cached prompts
        quote2, started2 = self.start({"song": song, "direction": "A sunlit coast", "title": "Coast", "seed": 11, "reuse_prompts": True})
        started2.raise_for_status()
        status2 = self.wait()
        self.assertEqual(status2["state"], "complete")
        run_2 = self.home / "runs" / started2.json()["id"]
        prompts_2 = read_json(run_2 / "prompts.json")
        self.assertEqual(prompts_1, prompts_2)
        log_text = (run_2 / "operation.log").read_text(encoding="utf-8")
        self.assertIn("resumed from cache", log_text)

    def test_passage_prompt_rewrite_and_checked_edit_use_the_production_prompt_stage(self):
        song = self.song_upload()
        _, started = self.start({"song": song, "direction": "A sunlit coast", "title": "Coast", "seed": 12})
        started.raise_for_status()
        self.assertEqual(self.wait()["state"], "complete")
        run_id = started.json()["id"]
        run = self.home / "runs" / run_id
        original = read_json(run / "prompts.json")["seg000"]
        original_job = read_json(run / "writer_jobs" / "seg000.json")
        original_prepared = read_json(run / "prepared.json")
        writer_files = sorted(p.name for p in run.glob("seg000.*.json"))
        base = f"/api/outputs/{run_id}/prompts/seg000"

        view = self.client.get(f"/api/outputs/{run_id}/prompts").json()
        self.assertFalse((run / "prompt_takes.json").exists(), "reading prompts must not write versions")
        self.assertEqual(view["segments"][0]["prompt_takes"][0]["id"], "prompt1")
        self.assertIsNone(view["prompt_blocked"])
        self.assertIn("Confirm", self.client.post(f"{base}/rewrite", json={}).text)
        self.assertIn("Confirm", self.client.post(f"{base}/edit", json={"prompt": original}).text)

        # A rewrite rolls fresh vocabulary and runs the worker's own writer, checks and Laya for this passage, keeping the earlier files aside.
        self.client.post(f"{base}/rewrite", json={"confirm": True, "seed": 4242}).raise_for_status()
        self.assertEqual(self.wait()["state"], "complete")
        rewritten_job = read_json(run / "writer_jobs" / "seg000.json")
        self.assertNotEqual(rewritten_job["shots"][0]["vocabulary"]["setting"], original_job["shots"][0]["vocabulary"]["setting"])
        self.assertNotEqual(rewritten_job["shots"][0]["vocabulary"]["mechanism"], original_job["shots"][0]["vocabulary"]["mechanism"])
        rewritten_prepared = read_json(run / "prepared.json")
        new_seg, old_seg = rewritten_prepared["plan"]["segments"][0], original_prepared["plan"]["segments"][0]
        self.assertEqual(rewritten_prepared["segments"][0], new_seg)
        self.assertEqual(read_json(run / "plan.json")["segments"][0], new_seg)
        self.assertEqual(rewritten_prepared["plan"]["slug"], original_prepared["plan"]["slug"])
        self.assertEqual(new_seg["rigging"], old_seg["rigging"])
        strip = lambda seg: {**seg, "thematic_anchor": 0, "footage_anchor": 0, "practical_effects": 0,
                             "shots": [{**shot, "vocab": 0} for shot in seg["shots"]]}
        self.assertEqual(strip(new_seg), strip(old_seg), "timing and cuts stay")
        versions = read_json(run / "prompt_takes.json")["segments"]["seg000"]
        self.assertEqual([v["id"] for v in versions["takes"]], ["prompt1", "prompt2"])
        self.assertEqual((versions["active_take"], versions["takes"][1]["validated"]), ("prompt2", True))
        self.assertEqual(versions["takes"][1]["variation_seed"], 4242)
        listed = self.client.get(f"/api/outputs/{run_id}/prompts").json()["segments"][0]["prompt_takes"]
        self.assertEqual((listed[1]["variation_seed"], listed[0]["vocabulary"]["shots"][0]), (4242, old_seg["shots"][0]["vocab"]))
        self.assertEqual(sorted(p.name for p in (run / "prompt_takes" / "seg000" / "before-prompt2").glob("*.json")), writer_files)
        self.assertIn("Writing musical passage 1 of 1", (run / "operation.log").read_text(encoding="utf-8"))

        # A hand edit that fails the checks is kept, marked, and never becomes the prompt.
        prompts_before = read_json(run / "prompts.json")
        self.client.post(f"{base}/edit", json={"prompt": "A short edit with no shots.", "confirm": True}).raise_for_status()
        self.assertEqual(self.wait()["state"], "failed")
        self.assertEqual(read_json(run / "prompts.json"), prompts_before)
        failed = read_json(run / "prompt_takes.json")["segments"]["seg000"]["takes"][-1]
        self.assertEqual((failed["id"], failed["validated"]), ("prompt3", False))
        self.assertTrue(failed["problems"])
        self.assertGreaterEqual(self.client.post(f"{base}/select", json={"prompt_take_id": "prompt3"}).status_code, 400)

        # A passing hand edit becomes the prompt; the original can be chosen again.
        self.client.post(f"{base}/edit", json={"prompt": original, "confirm": True}).raise_for_status()
        self.assertEqual(self.wait()["state"], "complete")
        self.assertEqual(read_json(run / "prompt_takes.json")["segments"]["seg000"]["active_take"], "prompt4")
        self.client.post(f"{base}/select", json={"prompt_take_id": "prompt1"}).raise_for_status()
        self.assertEqual(read_json(run / "prompts.json")["seg000"], original)
        # The original prompt comes back with the vocabulary it was written from, in every saved plan.
        self.assertEqual(read_json(run / "prepared.json")["plan"]["segments"][0], old_seg)
        self.assertEqual(read_json(run / "prepared.json")["segments"][0], old_seg)
        self.assertEqual(read_json(run / "plan.json")["segments"][0], old_seg)

        # An API writer needs the user's acceptance of the writer cost.
        prepared = read_json(run / "prepared.json")
        write_json(run / "prepared.json", {**prepared, "settings": {**prepared["settings"], "writer_mode": "api"}})
        refused = self.client.post(f"{base}/rewrite", json={"confirm": True})
        self.assertGreaterEqual(refused.status_code, 400)
        self.assertIn("accept the writer cost", refused.text)
        write_json(run / "prepared.json", prepared)

        # A worker that saved a prompt and then failed (e.g. GPU memory not released) leaves the prompt in use unchanged.
        prompts_before = (run / "prompts.json").read_bytes()
        def saves_then_fails(context, argv, **kwargs):
            write_json(run / "prompts.json", {"seg000": "half-finished"})
            raise RuntimeError("GPU memory was not released")
        with patch("mmv.jobs.JobContext.command", saves_then_fails):
            self.client.post(f"{base}/rewrite", json={"confirm": True}).raise_for_status()
            self.assertEqual(self.wait()["state"], "failed")
        self.assertEqual((run / "prompts.json").read_bytes(), prompts_before)

    def test_instrumental_and_lip_sync_validation(self):
        from mmv.engine.schema import validate_prompt, RIGGING_TAIL
        from mmv.engine.plan import Segment, Shot
        from mmv.engine.comfy import compute_ref_tags

        seg = Segment(
            index=0,
            song_start_frame=0,
            musical_frames=120,
            gen_frames=120,
            trim_frames=0,
            duration_input=5.0,
            montage_type="standard",
            section_index=0,
            section_label="mid",
            energy=0.5,
            thematic_anchor=None,
            ref_image_slots=0,
            footage_anchor="",
            practical_effects="",
            rigging="",
            audio_slice_start_s=0.0,
            audio_slice_end_s=5.0,
            shots=[Shot(n=1, start_frame=0, frames=120, cut_time=None, camera="static", shot_scale="medium", energy=0.5)],
        )
        tags = compute_ref_tags(0, 0, 1)

        from mmv.engine.schema import WriterResponse, assemble_prompt
        resp = WriterResponse(
            segment_id="seg000",
            style_opening="Cinematic daylight photography with expressive movement.",
            subject_definitions=[],
            summary="A performer in sunlight.",
            retention_analysis=[],
            shot_bodies=["The performer moves gracefully through a bright courtyard under sunlight. <Audio 1>"],
            overall_soundscape="Gentle instrumental music.",
            non_diegetic_music="N/A",
        )
        prompt_without_rigging = assemble_prompt(seg, resp, tags)

        # When silent_mouths is explicitly False (natural expressions), a missing rigging tail is permitted
        problems_instrumental = validate_prompt(prompt_without_rigging, seg, tags, strict_words=False, silent_mouths=False)
        self.assertEqual(problems_instrumental, [])

        # When silent_mouths is True, prompt without rigging tail triggers validation error
        problems_vocal = validate_prompt(prompt_without_rigging, seg, tags, strict_words=False, silent_mouths=True)
        self.assertIn("Subject Rigging block is missing (lip-sync suppression)", problems_vocal)

        # Auto-injection before overall_soundscape fixes the validation failure
        soundscape_pos = prompt_without_rigging.find("\noverall_soundscape:")
        remediated = prompt_without_rigging[:soundscape_pos].rstrip() + f" {RIGGING_TAIL}\n" + prompt_without_rigging[soundscape_pos:]
        problems_fixed = validate_prompt(remediated, seg, tags, strict_words=False, silent_mouths=True)
        self.assertEqual(problems_fixed, [])

        # End-to-end production run without lyrics completes cleanly
        quote, started = self.start({"song": self.song_upload(), "direction": "Warm light", "title": "Instrumental", "lyrics": ""})
        started.raise_for_status()
        status = self.wait()
        self.assertEqual(status["state"], "complete")
    def test_original_pipeline_real_assembly(self):
        quote, started = self.start({"song":self.song_upload(), "direction":"A sunlit coast", "title":"Coast"})
        started.raise_for_status()
        status = self.wait()
        self.assertEqual(status["state"], "complete", status)
        run = self.home / "runs" / started.json()["id"]
        self.assertTrue((run / "score.json").is_file())
        plan = read_json(run / "plan.json")
        self.assertEqual(quote.json()["analysis"]["shots"], sum(len(s["shots"]) for s in plan["segments"]))
        self.assertAlmostEqual(media.duration(run / "music-video.mp4"), plan["total_frames"]/24, delta=.08)
        prompts = read_json(run / "prompts.json")
        self.assertIn("subject_definitions:", next(iter(prompts.values())))
        self.assertIn("<Audio 1>", next(iter(prompts.values())))
        graph = next(b["prompt"] for path,b in MockService.requests if path == "/prompt")
        self.assertEqual(graph["124"]["inputs"]["steps"], 20)
        self.assertNotIn("115", graph)
        self.assertTrue(read_json(run / "consent.json")["accepted"])

    def test_ident_and_harvest(self):
        _, started = self.start({"kind":"ident", "title":"Studio", "ident_seconds":4})
        started.raise_for_status(); self.assertEqual(self.wait()["state"], "complete")
        image = self.client.post("/api/upload/reference", files={"file":("ref.png",picture())}).json()["file"]
        _, started = self.start({"kind":"harvest", "style_id":"teal", "title":"Teal", "references":[image]})
        started.raise_for_status(); status=self.wait(); self.assertEqual(status["state"], "complete", status)
        self.assertIn("Soft teal", self.store.style("teal")["style_card"])

    def test_deleted_timing_inputs_are_rejected(self):
        for name,value in (("bpm",120),("segment_seconds",8)):
            self.assertEqual(self.client.post("/api/quote",json={name:value}).status_code,422)
        html=self.client.get("/").text
        self.assertNotIn('name="bpm"',html)
        self.assertNotIn('name="segment_seconds"',html)

    def test_api_writer_requires_cost_and_no_implicit_render(self):
        settings=self.store.settings();settings.update(writer_mode="api",writer_call_estimate=0)
        self.client.put("/api/settings",json=settings).raise_for_status()
        response=self.client.post("/api/quote",json={"song":self.song_upload()})
        self.assertEqual(response.status_code,400)
        self.assertEqual(MockService.requests,[])

    def queue_quote(self, **changes):
        image = self.client.post("/api/upload/reference", files={"file": ("ref.png", picture())}).json()["file"]
        quote = self.client.post("/api/quote", json={"song": self.song_upload(), "backend": "local_h3", "references": [image], **changes})
        quote.raise_for_status()
        return quote.json()

    def paid_quote(self):
        self.store.save_key("WAVESPEED_API_KEY", "mock-only-key")
        return self.queue_quote(backend="wavespeed", resolution="768p")

    def wait_queue(self, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            queue = self.client.get("/api/queue").json()
            if not queue["running"] and self.app.state.jobs.active is None:
                return queue
            time.sleep(.02)
        self.fail("Queue did not finish")

    def test_queue_runs_free_tickets_in_order_without_consent(self):
        ran = []
        first = self.client.post("/api/queue", json={"quote_id": self.queue_quote(title="one")["id"]})
        second = self.client.post("/api/queue", json={"quote_id": self.queue_quote(title="two")["id"]})
        self.assertEqual((first.status_code, second.status_code), (200, 200), first.text)
        self.assertEqual(self.client.post(f"/api/queue/{second.json()['id']}/move", json={"delta": -1}).status_code, 200)
        self.assertEqual(self.client.get("/api/status").json()["queue"]["waiting"], 2)
        time.sleep(.1)
        self.assertEqual(self.app.state.jobs.active, None, "adding must not start anything")
        with patch("mmv.production.produce", side_effect=lambda store, request, prepared, context, resume=False: ran.append((request["title"], prepared["consent"]["accepted"])) or {}):
            self.client.post("/api/queue/start").raise_for_status()
            queue = self.wait_queue()
        self.assertEqual(ran, [("two", True), ("one", True)])
        self.assertEqual([t["state"] for t in queue["tickets"]], ["complete", "complete"])
        self.assertNotIn("request", queue["tickets"][0])
        self.assertEqual(self.client.post("/api/queue/clear-finished").json()["tickets"], [])

    def test_queue_paid_ticket_needs_consent_and_is_held_when_its_plan_changes(self):
        quote = self.paid_quote()
        self.assertGreater(quote["estimate_usd"], 0)
        refused = self.client.post("/api/queue", json={"quote_id": quote["id"]})
        self.assertEqual(refused.status_code, 400)
        self.assertIn("estimated charges", refused.json()["detail"])
        self.client.post("/api/queue", json={"quote_id": quote["id"], "consent": True}).raise_for_status()
        with patch("mmv.production.produce") as produce, patch("mmv.production.fingerprint", return_value="changed"):
            self.client.post("/api/queue/start").raise_for_status()
            queue = self.wait_queue()
        produce.assert_not_called()
        self.assertEqual(queue["tickets"][0]["state"], "held")
        self.assertIn("nothing was spent", queue["tickets"][0]["message"])

    def test_queue_paid_ticket_runs_on_its_approved_plan(self):
        quote = self.paid_quote()
        self.client.post("/api/queue", json={"quote_id": quote["id"], "consent": True}).raise_for_status()
        with patch("mmv.production.produce", return_value={}) as produce:
            self.client.post("/api/queue/start").raise_for_status()
            queue = self.wait_queue()
        self.assertEqual(queue["tickets"][0]["state"], "complete", queue["tickets"][0]["message"])
        self.assertEqual(produce.call_args.args[2]["consent"]["estimate_usd"], quote["estimate_usd"])

    def test_queue_free_ticket_that_became_paid_is_held(self):
        self.client.post("/api/queue", json={"quote_id": self.queue_quote()["id"]}).raise_for_status()
        real = production.prepare
        with patch("mmv.production.prepare", side_effect=lambda store, request: {**real(store, request), "estimate": 3.5}), \
                patch("mmv.production.produce") as produce:
            self.client.post("/api/queue/start").raise_for_status()
            queue = self.wait_queue()
        produce.assert_not_called()
        self.assertEqual(queue["tickets"][0]["state"], "held")

    def test_queue_failure_moves_on_and_cancel_pauses(self):
        for title in ("bad", "cancel me", "after"):
            self.client.post("/api/queue", json={"quote_id": self.queue_quote(title=title)["id"]}).raise_for_status()
        def produce(store, request, prepared, context, resume=False):
            if request["title"] == "bad":
                raise ValueError("mock failure")
            while True:
                context.wait(.02)
        with patch("mmv.production.produce", side_effect=produce):
            self.client.post("/api/queue/start").raise_for_status()
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                tickets = self.client.get("/api/queue").json()["tickets"]
                if tickets[1]["state"] == "running":
                    break
                time.sleep(.02)
            self.client.post("/api/cancel").raise_for_status()
            queue = self.wait_queue()
        self.assertEqual([t["state"] for t in queue["tickets"]], ["failed", "cancelled", "pending"])
        self.assertIn("mock failure", queue["tickets"][0]["message"])

    def test_queue_restart_interrupts_and_never_starts_by_itself(self):
        self.client.post("/api/queue", json={"quote_id": self.queue_quote()["id"]}).raise_for_status()
        running = self.client.post("/api/queue", json={"quote_id": self.queue_quote()["id"]}).json()["id"]
        path = self.home / "queue" / f"{running}.json"
        path.write_text(json.dumps({**json.loads(path.read_text()), "state": "running"}))
        reopened = TestClient(create_app(self.home, test_hosts=True))
        queue = reopened.get("/api/queue").json()
        self.assertFalse(queue["running"])
        self.assertEqual(sorted(t["state"] for t in queue["tickets"]), ["interrupted", "pending"])
        reopened.close()

    def test_queue_can_be_filled_during_an_operation_but_start_cannot_overlap(self):
        release = threading.Event()
        self.app.state.jobs.start("export", lambda context: release.wait(30))
        try:
            quote = self.queue_quote()
            self.assertEqual(self.client.post("/api/start", json={"quote_id": quote["id"], "consent": True}).status_code, 409)
            self.client.post("/api/queue", json={"quote_id": quote["id"]}).raise_for_status()
        finally:
            release.set()
        self.wait()
        self.assertEqual(self.client.get("/api/queue").json()["tickets"][0]["state"], "pending")

    def test_queue_again_replaces_a_stopped_ticket_at_its_place(self):
        first = self.client.post("/api/queue", json={"quote_id": self.queue_quote(title="one")["id"]}).json()
        second = self.client.post("/api/queue", json={"quote_id": self.queue_quote(title="two")["id"]}).json()["id"]
        self.assertEqual(self.client.post(f"/api/queue/{first['id']}/preview", json={}).status_code, 400)
        path = self.home / "queue" / f"{first['id']}.json"
        path.write_text(json.dumps({**json.loads(path.read_text()), "state": "failed"}))
        quote = self.client.post(f"/api/queue/{first['id']}/preview", json={})
        quote.raise_for_status()
        self.client.post("/api/queue", json={"quote_id": quote.json()["id"], "replaces": first["id"]}).raise_for_status()
        tickets = self.client.get("/api/queue").json()["tickets"]
        self.assertEqual([t["state"] for t in tickets], ["pending", "pending"])
        self.assertEqual(tickets[1]["id"], second)
        self.assertNotEqual(tickets[0]["id"], first["id"])

    def test_queue_treats_a_tiny_writer_cost_as_paid_and_shutdown_starts_nothing(self):
        self.assertGreater(production_queue.cost({"estimate": 0.0, "writer_estimate": 0.00001}), 0)
        self.client.post("/api/queue", json={"quote_id": self.queue_quote()["id"]}).raise_for_status()
        release = threading.Event()
        jobs = self.app.state.jobs
        jobs.start("export", lambda context: release.wait(30))
        self.client.post("/api/queue/start").raise_for_status()
        with TestClient(self.app):
            pass   # lifespan close: the same path the application takes when it stops
        release.set()
        self.wait()
        time.sleep(.2)
        self.assertEqual(self.client.get("/api/queue").json()["tickets"][0]["state"], "pending")

    def test_queue_makes_a_real_mocked_video_from_start_to_finish(self):
        self.client.post("/api/queue", json={"quote_id": self.queue_quote()["id"]}).raise_for_status()
        self.client.post("/api/queue/start").raise_for_status()
        queue = self.wait_queue(120)
        ticket = queue["tickets"][0]
        self.assertEqual(ticket["state"], "complete", ticket["message"])
        self.assertTrue((self.home / "runs" / ticket["run_id"] / "output.json").is_file())
        self.assertTrue(read_json(self.home / "runs" / ticket["run_id"] / "consent.json")["accepted"])
        self.assertEqual(self.client.get("/api/status").json()["state"], "complete")

    def mark_ticket(self, ticket_id, **fields):
        path = self.home / "queue" / f"{ticket_id}.json"
        path.write_text(json.dumps({**json.loads(path.read_text()), **fields}))

    @unittest.skipUnless(importlib.util.find_spec('comfy_sdk'), 'optional official SDK not installed')
    def test_queue_resume_keeps_finished_work_and_starting_the_queue_resumes_interrupted(self):
        self.configure_sdk()
        self.server.v2_download_fail = True
        quote = self.queue_quote(backend="comfy_sdk_h3")
        ticket = self.client.post("/api/queue", json={"quote_id": quote["id"]}).json()
        self.client.post("/api/queue/start").raise_for_status()
        stopped = self.wait_queue(120)["tickets"][0]
        self.assertEqual(stopped["state"], "failed", stopped["message"])
        self.assertTrue(stopped["resumable"])
        self.server.v2_download_fail = False
        self.mark_ticket(ticket["id"], state="interrupted")   # as a restart would leave it
        self.assertEqual(self.client.get("/api/queue").json()["waiting"], 1)
        self.client.post("/api/queue/start").raise_for_status()
        finished = self.wait_queue(120)["tickets"][0]
        self.assertEqual(finished["state"], "complete", finished["message"])
        self.assertEqual(finished["run_id"], stopped["run_id"], "must continue in the same run")
        self.assertEqual(len(self.server.v2_submits), 1, "nothing is rendered twice")

    def test_queue_resume_before_prompts_finished_starts_over_and_paid_is_never_resumed(self):
        free = self.client.post("/api/queue", json={"quote_id": self.queue_quote()["id"]}).json()
        self.mark_ticket(free["id"], state="interrupted", run_id="never_got_far")
        with patch("mmv.production.produce", return_value={}) as produce:
            self.client.post("/api/queue/start").raise_for_status()
            queue = self.wait_queue()
        self.assertEqual(queue["tickets"][0]["state"], "complete", queue["tickets"][0]["message"])
        self.assertFalse(produce.call_args.kwargs["resume"])
        self.assertNotEqual(queue["tickets"][0]["run_id"], "never_got_far")
        paid = self.client.post("/api/queue", json={"quote_id": self.paid_quote()["id"], "consent": True}).json()
        self.mark_ticket(paid["id"], state="interrupted", run_id="paid_run")
        self.assertEqual(self.client.post(f"/api/queue/{paid['id']}/resume").status_code, 400)
        with patch("mmv.production.produce") as produce:
            self.client.post("/api/queue/start").raise_for_status()
            queue = self.wait_queue()
        produce.assert_not_called()
        self.assertEqual(queue["tickets"][-1]["state"], "interrupted")

    def test_queue_resume_that_would_recharge_a_writer_is_held(self):
        ticket = self.client.post("/api/queue", json={"quote_id": self.queue_quote()["id"]}).json()
        self.mark_ticket(ticket["id"], state="interrupted", run_id="writer_stopped")
        real = production.prepare
        with patch("mmv.production.prepare", side_effect=lambda store, request: {**real(store, request), "estimate": 1.0}), \
                patch("mmv.production.produce") as produce:
            self.client.post("/api/queue/start").raise_for_status()
            queue = self.wait_queue()
        produce.assert_not_called()
        self.assertEqual(queue["tickets"][0]["state"], "held")

    def test_stem_work_waits_for_a_free_gpu_then_goes_before_the_next_ticket(self):
        from mmv import stems
        control, jobs = production_queue.new_control(), self.app.state.jobs
        release, ran, active_at_run = threading.Event(), [], []
        def record(*args, **kwargs):
            active_at_run.append(jobs.active is not None)
            ran.append(True)
            raise ValueError("mock separation stops here")
        def preview():
            with control["prepare_lock"], production_queue.preview_gpu_gate(self.store, jobs, control):
                stems.separate(self.store, self.home / "song.wav", "digest", "htdemucs")
        jobs.start("export", lambda context: release.wait(30))
        with patch("mmv.stems.subprocess.run", side_effect=record), patch.object(production_queue, "GPU_POLL_SECONDS", .02), \
                patch("mmv.stems.pick_device", return_value="cpu"):
            worker = threading.Thread(target=lambda: self.assertRaises(ValueError, preview))
            worker.start()
            deadline = time.monotonic() + 5
            while not control["gpu_waiters"] and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertEqual(control["gpu_waiters"], 1)
            control["running"] = True
            self.assertIsNone(production_queue._claim_next(self.store, jobs, control), "the next ticket lets the preview go first")
            self.assertTrue(control["running"])
            self.assertEqual(ran, [], "nothing touches the GPU during the operation")
            with control["prepare_lock"]:
                pass   # other previews are not held up while it waits
            release.set()
            worker.join(10)
        self.assertEqual(active_at_run, [False])
        self.assertEqual(control["gpu_waiters"], 0)

    def test_queue_refuses_non_productions_and_running_removal(self):
        self.assertEqual(self.client.post("/api/queue", json={"quote_id": "fabricated"}).status_code, 400)
        first = self.client.post("/api/queue", json={"quote_id": self.queue_quote()["id"]}).json()
        path = self.home / "queue" / f"{first['id']}.json"
        path.write_text(json.dumps({**json.loads(path.read_text()), "state": "running"}))
        self.assertEqual(self.client.delete(f"/api/queue/{first['id']}").status_code, 400)

    def test_preview_returns_editable_score_and_edits_change_the_plan(self):
        self.store.save_key("WAVESPEED_API_KEY","mock-only-key")
        image=self.client.post("/api/upload/reference",files={"file":("ref.png",picture())}).json()["file"]
        song=self.song_upload()
        base={"song":song,"backend":"wavespeed","resolution":"768p","references":[image]}
        plain=self.client.post("/api/quote",json=base)
        plain.raise_for_status()
        score=plain.json()["score"]
        self.assertTrue(score["beats"] and score["passages"] and "tempo_bpm" in score)
        edited=self.client.post("/api/quote",json={**base,"score_edits":{"bar_one_beat":1,"beat_nudge_ms":50,"muted_beats":[0]}})
        edited.raise_for_status()
        self.assertNotEqual(plain.json()["id"],edited.json()["id"])
        self.assertEqual(len(edited.json()["score"]["beats"]),len(score["beats"])-1)
        invalid=self.client.post("/api/quote",json={**base,"score_edits":{"muted_beats":[99999]}})
        self.assertEqual(invalid.status_code,400)
        self.assertEqual(self.client.post("/api/quote",json={**base,"score_edits":{"beat_nudge_ms":9999}}).status_code,422)
        self.assertEqual(self.client.post("/api/quote",json={**base,"score_edits":{"unknown":1}}).status_code,422)
        peaks=self.client.get("/api/waveform",params={"song":song})
        peaks.raise_for_status()
        self.assertTrue(peaks.json()["peaks"])
        self.assertNotEqual(self.client.get("/api/waveform",params={"song":"../../etc/passwd"}).status_code,200)

    def test_instrument_driver_needs_the_addon_and_model_then_drives_energy(self):
        from mmv import stems
        self.store.save_key("WAVESPEED_API_KEY","mock-only-key")
        image=self.client.post("/api/upload/reference",files={"file":("ref.png",picture())}).json()["file"]
        song=self.song_upload()
        base={"song":song,"backend":"wavespeed","resolution":"768p","references":[image]}
        report=self.client.get("/api/stems").json()
        self.assertIn("install_command",report)
        self.assertFalse(any(model["ready"] for model in report["models"].values()))
        with patch.object(stems,"installed",return_value=False):
            missing=self.client.post("/api/quote",json={**base,"analysis_driver":"drums"})
            self.assertEqual(missing.status_code,400)
            self.assertIn("Demucs add-on",missing.json()["detail"])
        with patch.object(stems,"installed",return_value=True):
            self.assertIn("stem model first",self.client.post("/api/quote",json={**base,"analysis_driver":"drums"}).json()["detail"])
            self.assertEqual(self.client.post("/api/stems/prepare",json={"model":"htdemucs"}).status_code,400)
            self.assertEqual(MockService.requests,[])
            calls=[]
            def fake_prepare(store,model,context):
                calls.append(model)
                (store.home/"analysis"/"stems").mkdir(parents=True,exist_ok=True)
                write_json(store.home/"analysis"/"stems"/(model+".ready"),{"model":model})
                return {"model":model}
            with patch.object(stems,"prepare_model",side_effect=fake_prepare):
                self.client.post("/api/stems/prepare",json={"model":"htdemucs","consent":True}).raise_for_status()
                self.wait()
            self.assertEqual(calls,["htdemucs"])
            self.assertTrue(self.client.get("/api/stems").json()["models"]["htdemucs"]["ready"])
            def fake_separate(store,path,digest,model):
                folder=store.home/"analysis"/"stems"/"fake"
                folder.mkdir(parents=True,exist_ok=True)
                for stem in stems.MODELS[model]:
                    shutil.copy(path,folder/(stem+".wav"))
                return folder
            with patch.object(stems,"separate",side_effect=fake_separate):
                driven=self.client.post("/api/quote",json={**base,"analysis_driver":"drums"})
                driven.raise_for_status()
                self.assertTrue(driven.json()["score"]["beats"])
                self.assertEqual(self.client.post("/api/quote",json={**base,"analysis_driver":"banjo"}).status_code,422)
                self.assertEqual(self.client.post("/api/quote",json={**base,"analysis_driver":"drums","stem_quality":"ultra"}).status_code,422)
                not_ready=self.client.post("/api/quote",json={**base,"analysis_driver":"drums","stem_quality":"high"})
                self.assertEqual(not_ready.status_code,400)
                self.assertIn("htdemucs_ft",not_ready.json()["detail"])
                with patch.object(stems,"prepare_model",side_effect=fake_prepare):
                    self.client.post("/api/stems/prepare",json={"model":"htdemucs_ft","consent":True}).raise_for_status()
                    self.wait()
                high=self.client.post("/api/quote",json={**base,"analysis_driver":"drums","stem_quality":"high"})
                high.raise_for_status()
                self.assertTrue(high.json()["score"]["beats"])

    def test_hosted_original_adapters_and_consent(self):
        self.store.save_key("WAVESPEED_API_KEY","mock-only-key")
        image=self.client.post("/api/upload/reference",files={"file":("ref.png",picture())}).json()["file"]
        song=self.song_upload()
        with patch.dict(os.environ,{"WAVESPEED_BASE_URL":self.url}):
            for backend,resolution,cost in (("wavespeed","768p",.4),("seedance_2_5","480p",.72)):
                MockService.requests=[]
                quote,rejected=self.start({"song":song,"backend":backend,"resolution":resolution,"references":[image]},consent=False)
                self.assertEqual(rejected.status_code,400)
                self.assertEqual(MockService.requests,[])
                self.assertEqual(quote.json()["estimate_usd"],cost)
                started=self.client.post("/api/start",json={"quote_id":quote.json()["id"],"consent":True})
                started.raise_for_status();status=self.wait();self.assertEqual(status["state"],"complete",status)
                submissions=[body for path,body in MockService.requests if path.endswith("/reference-to-video") or path.endswith("/text-to-video")]
                self.assertEqual(len(submissions),1)
                self.assertIn("subject_definitions:",read_json(self.home/"runs"/started.json()["id"]/"prompts.json")["seg000"])
                receipt=read_json(self.home/"runs"/started.json()["id"]/"renders.json")["seg000"]
                self.assertEqual(receipt["request_id"],"hosted-test")

    def test_lyrics_detection_needs_the_addon_and_model_and_never_downloads_unasked(self):
        from mmv import lyrics
        song = self.song_upload()
        report = self.client.get('/api/lyrics').json()
        self.assertIn('install_command', report)
        self.assertEqual(self.client.post('/api/lyrics/prepare', json={'model': 'small'}).status_code, 400)       # no consent
        with patch.object(lyrics, 'available', return_value=False):
            missing = self.client.post('/api/lyrics/detect', json={'song': song})
            self.assertEqual(missing.status_code, 400)
            self.assertIn('Whisper add-on', missing.json()['detail'])
        self.assertEqual(self.client.post('/api/lyrics/detect', json={'song': song, 'model': 'huge'}).status_code, 422)
        self.assertNotEqual(self.client.post('/api/lyrics/detect', json={'song': '../../etc/passwd'}).status_code, 200)
        self.assertIn('Detect the lyrics first', self.client.post('/api/lyrics/align', json={'song': song, 'text': 'hello'}).json()['detail'])
        fake = {'words': [{'word': 'hello', 'start': 1.0, 'end': 1.4}, {'word': 'there', 'start': 1.5, 'end': 1.9}],
                'lines': [{'start': 1.0, 'end': 1.9, 'text': 'hello there'}], 'source': 'vocals stem', 'language': 'en'}
        with patch.object(lyrics, 'require_ready'), patch.object(lyrics, 'transcribe', return_value=fake) as transcribe:
            started = self.client.post('/api/lyrics/detect', json={'song': song, 'model': 'small'})
            started.raise_for_status()
            status = self.wait()
            self.assertEqual(status['state'], 'complete')
            self.assertEqual(status['result']['lines'], fake['lines'])
            self.assertEqual(status['result']['source'], 'vocals stem')
            self.assertEqual(transcribe.call_args.args[3], 'small')
        with patch.object(lyrics, 'cached_words', return_value={'words': fake['words'], 'source': 'vocals stem'}):
            aligned = self.client.post('/api/lyrics/align', json={'song': song, 'text': 'Hello there'})
            aligned.raise_for_status()
            self.assertEqual(aligned.json()['lines'][0]['timing'], 'matched')
        with patch.object(lyrics, 'available', return_value=True), patch.object(lyrics, 'prepare_model', return_value={'model': 'small'}) as prepare:
            self.client.post('/api/lyrics/prepare', json={'model': 'small', 'consent': True}).raise_for_status()
            self.assertEqual(self.wait()['state'], 'complete')
            self.assertEqual(prepare.call_args.args[1], 'small')

    def test_lip_sync_mode_sings_only_the_passages_with_lyrics_and_keeps_the_others_sealed(self):
        from mmv.engine.schema import RIGGING_TAIL
        actors.create_actor(self.store, 'blue', 'Blue', 'Blue jacket', picture())
        song = self.song_upload()
        base = {'song': song, 'actors': ['blue']}
        sealed = self.client.post('/api/quote', json=base)
        sealed.raise_for_status()
        self.assertIsNone(sealed.json().get('lipsync'))
        lines = [{'start': 0.0, 'end': 1.1, 'text': 'Interdimensional lover'}]
        silent = self.client.post('/api/quote', json={**base, 'mouth_mode': 'lip_sync', 'lyric_lines': []})
        silent.raise_for_status()
        self.assertFalse(any(p['singing'] for p in silent.json()['lipsync']['passages'].values()))
        self.assertEqual(self.client.post('/api/quote', json={**base, 'mouth_mode': 'lip_sync', 'lyric_lines': [{'start': 3, 'end': 1, 'text': 'x'}]}).status_code, 400)
        guessed = self.client.post('/api/quote', json={**base, 'mouth_mode': 'lip_sync', 'singers': ['blue'],
                                                       'lyric_lines': [{**lines[0], 'timing': 'interpolated'}]})
        guessed.raise_for_status()
        self.assertFalse(guessed.json()['lipsync']['passages']['seg000']['singing'])      # guessed timing never unseals a passage
        self.assertEqual(guessed.json()['lipsync']['unconfirmed_lines'], 1)
        self.assertEqual(self.client.post('/api/quote', json={**base, 'mouth_mode': 'lip_sync', 'lyric_lines': [{**lines[0], 'timing': 'bogus'}]}).status_code, 422)
        quote, started = self.start({**base, 'mouth_mode': 'lip_sync', 'lyric_lines': lines, 'singers': ['blue']})
        plan = quote.json()['lipsync']
        self.assertTrue(plan['passages']['seg000']['singing'])
        self.assertEqual(plan['singer'], 'blue')
        started.raise_for_status()
        status = self.wait()
        self.assertEqual(status['state'], 'complete', status)
        run = self.home / 'runs' / started.json()['id']
        self.assertIn('This passage contains singing', (run / 'writer_system_singing.md').read_text(encoding="utf-8"))
        self.assertNotIn('This passage contains singing', (run / 'writer_system.md').read_text(encoding="utf-8"))
        job = read_json(run / 'writer_jobs' / 'seg000.json')
        self.assertEqual(job['cast'][0]['lines'], ['Interdimensional lover'])
        self.assertEqual(job['singing']['actor_id'], 'blue')
        self.assertNotIn('rigging', job)
        prompt = read_json(run / 'prompts.json')['seg000']
        self.assertIn('Interdimensional', prompt)
        self.assertEqual([s['sung'] for s in job['singing']['shots']][:1], [True])
        self.assertIn('follow the sung vocal', prompt)
        self.assertNotIn(RIGGING_TAIL.rstrip('.').lower(), prompt.lower())
        # the same song in the default mode still seals every mouth
        quote, started = self.start(base)
        started.raise_for_status()
        self.assertEqual(self.wait()['state'], 'complete')
        run = self.home / 'runs' / started.json()['id']
        self.assertFalse((run / 'writer_system_singing.md').exists())
        self.assertIn(RIGGING_TAIL.rstrip('.').lower(), read_json(run / 'prompts.json')['seg000'].lower())

    def test_a_finished_production_exports_as_an_editing_package_through_the_api(self):
        actors.create_actor(self.store, 'blue', 'Blue', 'Blue jacket', picture())          # not a public starter actor
        self.store.save_key('MMV_COMFY_API_KEY', 'export-test-key-9876543210')
        quote, started = self.start({'song': self.song_upload(), 'actors': ['blue']})
        started.raise_for_status()
        self.assertEqual(self.wait()['state'], 'complete')
        run_id = started.json()['id']
        refused = self.client.post(f'/api/outputs/{run_id}/package', json={})
        self.assertEqual(refused.status_code, 400)
        self.assertIn('PRIVATE_ACTORS', refused.json()['detail'])
        self.assertEqual(self.client.post('/api/outputs/not-a-run/package', json={'allow_private_actors': True}).status_code, 400)
        self.assertEqual(self.client.post(f'/api/outputs/{run_id}/package', json={'bogus': 1}).status_code, 422)
        exported = self.client.post(f'/api/outputs/{run_id}/package', json={'allow_private_actors': True, 'zip': True})
        exported.raise_for_status()
        status = self.wait()
        self.assertEqual(status['state'], 'complete', status)
        result = status['result']
        package = Path(result['path'])
        self.assertEqual(package.parent.resolve(), (self.home / 'exports').resolve())

        self.assertRegex(package.name, r'^[A-Za-z0-9_]+_\d{4}-\d\d-\d\d_\d{4}$')           # title and date-time, not a random id
        self.assertEqual(result['private_actors'], ['blue'])
        self.assertTrue(Path(result['zip']).is_file())
        for name in ('README.md', 'MANIFEST.json', '01_final/music-video.mp4', '05_receipts/request.json'):
            self.assertTrue((package / name).is_file(), name)
        self.assertIn('PRIVATE_ACTORS_WARNING', (package / 'README.md').read_text())
        self.assertTrue(any((package / '02_raw_clips').glob('seg000_*_raw.mp4')))
        everything = ' '.join(p.read_text(errors='ignore') for p in package.rglob('*') if p.is_file() and p.suffix in ('.json', '.md', '.txt', '.log'))
        self.assertNotIn('export-test-key-9876543210', everything)
        self.assertNotIn(str(Path.home()), everything)
        self.assertFalse((package / '07_actor_references').exists())                         # no private reference images
        self.assertTrue(list((package / '06_stills').glob('*.png')))                         # stills come from the clips

    @unittest.skipUnless(importlib.util.find_spec('comfy_sdk'), 'optional official SDK not installed')
    def test_studio_clip_quality_saves_the_studio_file_names_it_by_type_and_still_assembles(self):
        self.configure_sdk()
        actors.create_actor(self.store, 'blue', 'Blue', 'Blue jacket', picture())
        song = self.song_upload()
        standard = self.start({'backend': 'comfy_sdk_h3', 'song': song, 'actors': ['blue']})[1]
        standard.raise_for_status()
        self.assertEqual(self.wait()['state'], 'complete')
        plain_graph = self.server.v2_submits[-1][1]['workflow']
        self.assertEqual(plain_graph['148']['inputs']['crf'], 6)                       # standard keeps the shipped workflow
        plain_run = self.home / 'runs' / standard.json()['id']
        self.assertTrue(next((plain_run / 'renders').glob('*/video.mp4')).is_file())   # and the old names
        for quality, fmt, suffix in (('prores', 'video/ProRes', '.mov'), ('lossless', 'video/ffv1-mkv', '.mkv')):
            quote, started = self.start({'backend': 'comfy_sdk_h3', 'song': song, 'actors': ['blue'], 'clip_quality': quality})
            started.raise_for_status()
            status = self.wait()
            self.assertEqual(status['state'], 'complete', status)
            node = self.server.v2_submits[-1][1]['workflow']['148']['inputs']
            self.assertEqual(node['format'], fmt)
            self.assertNotIn('crf', node)
            self.assertNotIn('pix_fmt', node)
            run = self.home / 'runs' / started.json()['id']
            clip = next((run / 'renders').glob('*/video' + suffix))
            self.assertTrue(clip.is_file(), clip)
            self.assertEqual(read_json(next((run / 'renders').glob('*/result.json')))['clip_quality'], quality)
            self.assertTrue((run / 'music-video.mp4').is_file())                          # the final video is still the encoded mp4
            self.assertAlmostEqual(media.duration(run / 'music-video.mp4'), 1.1, delta=.08)
        # if the job does not return the studio file, the standard clip is used and the run says so
        self.server.v2_no_studio = True
        _, started = self.start({'backend': 'comfy_sdk_h3', 'song': song, 'actors': ['blue'], 'clip_quality': 'prores'})
        started.raise_for_status()
        self.assertEqual(self.wait()['state'], 'complete')
        fallback = read_json(next((self.home / 'runs' / started.json()['id'] / 'renders').glob('*/result.json')))
        self.assertIn('Studio-quality clip was not returned', fallback['clip_quality_note'])
        self.assertTrue(fallback['video'].endswith('video.mp4'))
        output = read_json(self.home / 'runs' / started.json()['id'] / 'output.json')
        self.assertTrue(any('Studio-quality clip not delivered' in w for w in output['quality_warnings']), output)
        self.assertEqual((output['clip_quality'], output['clip_quality_requested']), ('standard', 'prores'))     # delivered vs requested
        outputs = self.client.get('/api/outputs').json()
        self.assertTrue(any('Studio-quality clip not delivered' in ' '.join(o.get('quality_warnings', [])) for o in outputs))

    def test_studio_clips_are_refused_where_they_cannot_work_and_graphs_are_switched_cleanly(self):
        from mmv import comfy_sdk
        from mmv.engine.comfy import WorkflowBuilder
        song = self.song_upload()
        refused = self.client.post('/api/quote', json={'song': song, 'clip_quality': 'prores'})            # local H3, not the SDK path
        self.assertEqual(refused.status_code, 400)
        self.assertIn('Comfy SDK renderer only', refused.json()['detail'])
        self.assertEqual(self.client.post('/api/quote', json={'song': song, 'clip_quality': 'raw'}).status_code, 422)
        root = Path(__file__).resolve().parents[1] / 'mmv/engine'
        builder = WorkflowBuilder.load(root / 'config/injection_map.json', root)
        base = json.loads(json.dumps(builder.base))
        self.assertIs(comfy_sdk.studio_graph(base, builder.map, 'standard'), base)
        studio = comfy_sdk.studio_graph(base, builder.map, 'prores')
        self.assertEqual(studio['148']['inputs']['format'], 'video/ProRes')
        self.assertEqual(studio['148']['inputs']['profile'], '4444')
        self.assertEqual(base['148']['inputs']['format'], 'video/h264-mp4')                                  # the input graph is untouched
        self.assertEqual(comfy_sdk.studio_graph(base, builder.map, 'lossless')['148']['inputs']['format'], 'video/ffv1-mkv')
        broken = {k: v for k, v in base.items() if k != '148'}
        with self.assertRaises(comfy_sdk.BackendError):
            comfy_sdk.studio_graph(broken, builder.map, 'prores')
        make = lambda ct, name: type('O', (), {'content_type': ct, 'name': name})()
        self.assertEqual(comfy_sdk.media_suffix(make('video/quicktime', 'x'), '.mp4'), '.mov')
        self.assertEqual(comfy_sdk.media_suffix(make('audio/flac', 'x'), '.wav'), '.flac')
        self.assertEqual(comfy_sdk.media_suffix(make('application/octet-stream', 'clip.webm'), '.mp4'), '.webm')
        self.assertEqual(comfy_sdk.media_suffix(make('', ''), '.mp4'), '.mp4')

    def test_bundled_props_preview_validation_and_mock_render_reference_order(self):
        from mmv import instrument_assets
        for actor_id in ('guitar_actor', 'keys_actor'):
            actors.create_actor(self.store, actor_id, actor_id, 'Overview', picture())
        self.assertTrue(next(i for i in self.client.get('/api/instruments').json() if i['id'] == 'guitar')['available'])
        self.assertEqual(self.client.get('/api/props/mmv-guitar/reference').status_code, 200)
        self.assertEqual(self.client.post('/api/instruments/guitar').status_code, 404)
        song = self.song_upload()
        request = {'song': song, 'actors': ['guitar_actor', 'keys_actor'], 'on_screen': 2, 'ensemble_mode': 'always',
                   'instrument_mode': 'perform', 'instrument_assignments': {'guitar_actor': 'guitar', 'keys_actor': 'keyboards'}}
        quote, started = self.start(request)
        started.raise_for_status()
        performance = quote.json()['instruments']
        self.assertNotIn('notice', performance)
        self.assertEqual(set(performance['assets']), {'guitar', 'keyboards'})
        self.assertTrue(all(s['ref_image_slots'] == 4 for s in quote.json()['segments']))
        self.assertTrue(all(p['source'] == 'mix' for v in performance['passages'].values() for p in v['performers']))
        self.assertEqual(self.wait()['state'], 'complete')
        directory = self.home / 'runs' / started.json()['id']
        graph = read_json(directory / 'render-graph.json')
        image_files = [v['inputs']['image'] for v in graph.values() if v.get('class_type') == 'LoadImage']
        self.assertEqual(len(set(image_files)), 4)
        self.assertTrue(all(':' not in filename for filename in image_files))
        prompts = read_json(directory / 'prompts.json')
        self.assertTrue(all('<Picture 3>' in p and '<Picture 4>' in p for p in prompts.values()))
        jobs = [read_json(p) for p in (directory / 'writer_jobs').glob('*.json')]
        self.assertNotIn('private test provenance', json.dumps(jobs))
        self.assertTrue(read_json(directory / 'prepared.json')['passage_plan_binding'])
        # The same requests remain fully guarded; off removes all instrument fields.
        bad = self.client.post('/api/quote', json={**request, 'instrument_assignments': {'missing': 'guitar'}})
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.client.post('/api/quote', json={**request, 'instrument_assignments': {'guitar_actor': 'flute'}}).status_code, 422)
        danced = self.client.post('/api/quote', json={**request, 'dance_mode': 'group'}).json()
        self.assertIsNone(danced['dance'])  # Both actors' hands are busy.
        self.assertIsNone(self.client.post('/api/quote', json={'song': song}).json()['instruments'])
        # Resume replays the saved instrument decisions even if stem analysis would change now.
        from mmv.pipeline import prepare_resume
        saved_request = read_json(directory / 'request.json')
        with patch('mmv.instruments.cached_scores', side_effect=AssertionError('must replay saved cues')):
            resumed = prepare_resume(self.store, saved_request, directory)
        self.assertEqual(resumed['instruments'], read_json(directory / 'prepared.json')['instruments'])
        self.assertTrue(all(s['ref_image_slots'] == 4 for s in resumed['segments']))
        fresh_quote = self.client.post('/api/quote', json=request).json()
        asset_path = Path(resumed['instruments']['assets']['guitar']['path'])
        asset_path.write_bytes(b'changed synthetic fixture')
        with self.assertRaisesRegex(ValueError, 'reference changed'):
            prepare_resume(self.store, saved_request, directory)
        refused = self.client.post('/api/start', json={'quote_id': fresh_quote['id'], 'consent': True})
        self.assertEqual(refused.status_code, 400)
        self.assertIsNone(self.app.state.jobs.active)

    def test_independent_preview_parts_fallback_and_validation(self):
        from mmv import actors
        actors.create_actor(self.store, 'dance_actor', 'Dance Actor', 'Overview', picture())
        song = self.song_upload()
        request = {'song': song, 'actors': ['dance_actor'], 'dance_mode': 'independent',
                   'dance_parts': {'dance_actor': 'bass'}}
        response = self.client.post('/api/quote', json=request)
        response.raise_for_status()
        plan = response.json()['dance']
        self.assertEqual(plan['parts'], {'dance_actor': 'bass'})
        self.assertIsNone(plan['lead'])
        dancers = [d for passage in plan['passages'].values() for d in passage['dancers']]
        self.assertTrue(dancers)
        self.assertTrue(all(d['source'] == 'mix' and d['fallback'] for d in dancers))
        self.assertEqual(self.client.post('/api/quote', json={**request, 'dance_parts': {'dance_actor': 'invalid'}}).status_code, 422)
        self.assertEqual(self.client.post('/api/quote', json={**request, 'dance_parts': {'missing': 'bass'}}).status_code, 400)

    def test_dance_is_planned_in_the_preview_and_requests_without_dancing_are_unchanged(self):
        song = self.song_upload()
        plan = self.client.post('/api/quote', json={'song': song, 'dance_mode': 'group', 'dance_direction': ' gentle   swaying '})
        plan.raise_for_status()
        dance = plan.json()['dance']
        self.assertEqual((dance['mode'], dance['direction']), ('group', 'gentle swaying'))
        self.assertTrue(dance['passages'] and dance['digest'] and dance['tempo_bpm'] > 0)
        off = self.client.post('/api/quote', json={'song': song, 'dance_mode': 'off', 'dance_direction': 'ignored', 'dancers': ['x']})
        off.raise_for_status()
        self.assertIsNone(off.json()['dance'])
        self.assertEqual(off.json()['id'] and self.client.post('/api/quote', json={'song': song}).json()['dance'], None)
        for bad, code in (({'dance_mode': 'wild'}, 422), ({'dance_mode': 'group', 'dance_direction': 'x' * 201}, 422),
                          ({'dance_mode': 'group', 'dancers': ['nobody_here']}, 400), ({'dance_mode': 'group', 'dance_lead': 'nobody_here'}, 400)):
            with self.subTest(bad=bad):
                self.assertEqual(self.client.post('/api/quote', json={'song': song, **bad}).status_code, code)

    def test_lyric_captions_are_planned_burned_after_the_flash_and_downloadable(self):
        song = self.song_upload()
        lines = [{'start': 0.2, 'end': 0.9, 'text': 'Honk {honk}', 'timing': 'matched'}, {'start': 1.0, 'end': 1.5, 'text': 'guess', 'timing': 'interpolated'}]
        plan = self.client.post('/api/quote', json={'song': song, 'lyric_lines': lines, 'captions': {'mode': 'burned'}})
        plan.raise_for_status()
        self.assertEqual(plan.json()['captions']['cues'], [[0.2, 0.9, 'Honk {honk}']])
        self.assertEqual(plan.json()['lipsync'], None)                                       # captions never switch lip sync on
        self.assertIsNone(self.client.post('/api/quote', json={'song': song, 'lyric_lines': lines}).json()['captions'])
        nothing = self.client.post('/api/quote', json={'song': song, 'captions': {'mode': 'burned'}}).json()['captions']
        self.assertEqual((nothing['cues'], bool(nothing['note'])), ([], True))                  # previewable, so lines can be added in the editor
        for bad, code in (({'captions': {'mode': 'neon'}, 'lyric_lines': lines}, 422), ({'lyric_lines': [{'start': 3, 'end': 1, 'text': 'x'}], 'captions': {'mode': 'sidecar'}}, 400)):
            with self.subTest(bad=bad):
                self.assertEqual(self.client.post('/api/quote', json={'song': song, **bad}).status_code, code)
        fonts = self.client.get('/api/captions/fonts')
        self.assertEqual(fonts.status_code, 200)
        self.assertIsInstance(fonts.json()['fonts'], list)
        for bad in ({'color': 'red'}, {'outline_color': '#12'}, {'font': 'Comic, Sans'}, {'font': 'x' * 41}):
            with self.subTest(bad=bad):
                self.assertEqual(self.client.post('/api/quote', json={'song': song, 'lyric_lines': lines, 'captions': {'mode': 'burned', **bad}}).status_code, 422)
                self.assertEqual(self.client.post('/api/captions', json={'source': 'x/music-video.mp4', **bad}).status_code, 422)
        plan = self.client.post('/api/quote', json={'song': song, 'lyric_lines': lines, 'captions': {'mode': 'burned', 'color': '#FF8800', 'font': ''}})
        self.assertEqual((plan.status_code, plan.json()['captions']['color']), (200, '#ff8800'))
        quote, started = self.start({'song': song, 'lyric_lines': lines, 'captions': {'mode': 'burned'},
                                     'subliminal': {'mode': 'text', 'text': 'GOOSE', 'times': [0.5], 'frames': 2}})
        started.raise_for_status()
        status = self.wait()
        self.assertEqual(status['state'], 'complete', status)
        run = self.home / 'runs' / started.json()['id']
        output = read_json(run / 'output.json')
        self.assertEqual(output['captions'], {'mode': 'burned', 'cues': 1, 'srt': 'lyrics.srt', 'style': 'classic', 'position': 'bottom', 'size': 'medium',
                                              'uncaptioned_copy': 'music-video-uncaptioned.mp4'})
        self.assertEqual(output['subliminal']['clean_copy'], 'music-video-clean.mp4')
        self.assertNotIn('quality_warnings', output)
        from mmv.engine.assemble import probe_frames
        self.assertEqual(probe_frames(run / 'music-video.mp4'), probe_frames(run / 'music-video-uncaptioned.mp4'))
        for name, kind in (('lyrics.srt', 'application/x-subrip'), ('music-video-uncaptioned.mp4', 'video/mp4'), ('music-video-clean.mp4', 'video/mp4')):
            served = self.client.get(f'/api/media/{run.name}/{name}')
            self.assertEqual((served.status_code, served.headers['content-type']), (200, kind), name)
        self.assertIn('Honk {honk}', self.client.get(f'/api/media/{run.name}/lyrics.srt').text)
        self.assertNotEqual(self.client.get(f'/api/media/{run.name}/operation.log').status_code, 200)     # only recorded files are served

    def test_a_finished_video_can_be_captioned_later_as_a_new_output_leaving_the_original_alone(self):
        song = self.song_upload()
        lines = [{'start': 0.2, 'end': 0.9, 'text': 'Honk honk', 'timing': 'matched'}]
        _, started = self.start({'song': song, 'lyric_lines': lines})
        started.raise_for_status()
        self.assertEqual(self.wait()['state'], 'complete')
        run = self.home / 'runs' / started.json()['id']
        original = (run / 'music-video.mp4').read_bytes()
        self.assertNotIn('captions', read_json(run / 'output.json'))
        done = self.client.post('/api/captions', json={'source': run.name + '/music-video.mp4'})
        done.raise_for_status()
        status = self.wait()
        self.assertEqual(status['state'], 'complete', status)
        new = self.home / 'runs' / done.json()['id']
        self.assertRegex(new.name, r'^.+_captions_classic_\d{4}-\d{2}-\d{2}_\d{6}$')            # readable like productions, not random
        record = read_json(new / 'output.json')
        self.assertEqual((record['kind'], record['file'], record['captions']['cues']), ('captioned', 'captioned.mp4', 1))
        self.assertEqual((run / 'music-video.mp4').read_bytes(), original)                    # the original is untouched
        from mmv.engine.assemble import probe_frames
        self.assertEqual(probe_frames(new / 'captioned.mp4'), probe_frames(run / 'music-video.mp4'))
        self.assertNotEqual((new / 'captioned.mp4').read_bytes(), original)
        self.assertEqual(self.client.get(f'/api/media/{new.name}/lyrics.srt').status_code, 200)
        self.assertIn(new.name + '/captioned.mp4', [item['file'] for item in self.client.get('/api/outputs').json()])
        # things that are not completed music videos are refused (the busy guard is the shared jobs.require_idle)
        for source in (new.name + '/captioned.mp4', 'nobody/music-video.mp4'):
            with self.subTest(source=source):
                self.client.post('/api/captions', json={'source': source})
                self.assertEqual(self.wait()['state'], 'failed')

    def test_captioning_a_video_made_with_captions_starts_from_original_clips_and_needs_lines(self):
        song = self.song_upload()
        lines = [{'start': 0.2, 'end': 0.9, 'text': 'Honk honk', 'timing': 'matched'}]
        _, started = self.start({'song': song, 'lyric_lines': lines, 'captions': {'mode': 'burned'}})
        started.raise_for_status()
        self.assertEqual(self.wait()['state'], 'complete')
        run = self.home / 'runs' / started.json()['id']
        from unittest import mock
        from mmv import final_assembly as caption_module
        with mock.patch.object(caption_module, 'render', wraps=caption_module.render) as spy:
            self.client.post('/api/captions', json={'source': run.name + '/music-video.mp4'}).raise_for_status()
            self.assertEqual(self.wait()['state'], 'complete')
        recipe = spy.call_args.args[0]
        self.assertTrue(recipe['clips'])
        self.assertTrue(all(Path(c['path']).name not in ('music-video.mp4', 'music-video-uncaptioned.mp4') for c in recipe['clips']))
        _, bare = self.start({'song': song})
        bare.raise_for_status()
        self.assertEqual(self.wait()['state'], 'complete')
        self.client.post('/api/captions', json={'source': bare.json()['id'] + '/music-video.mp4'}).raise_for_status()
        failed = self.wait()
        self.assertEqual(failed['state'], 'failed')
        self.assertIn('no timed lyric lines', failed['message'])

    def test_missing_ident_originals_are_refused_during_preview(self):
        directory = self.home / 'runs' / 'lost-ident'
        directory.mkdir()
        (directory / 'ident.mp4').write_bytes(b'finished output is not a source')
        write_json(directory / 'output.json', {'kind': 'ident', 'file': 'ident.mp4', 'duration': 1})
        song = self.song_upload()
        for key in ('start_ident', 'end_ident'):
            response = self.client.post('/api/quote', json={'song': song, key: 'lost-ident/ident.mp4'})
            self.assertEqual(response.status_code, 400)
            self.assertIn('Original assembly sources', response.json()['detail'])

    def test_subliminal_flashes_are_planned_in_the_preview_and_applied_to_the_finished_video_keeping_a_clean_copy(self):
        song = self.song_upload()
        plan = self.client.post('/api/quote', json={'song': song, 'subliminal': {'mode': 'text', 'text': 'GOOSE', 'times': [0.5], 'frames': 2}})
        plan.raise_for_status()
        flash = plan.json()['subliminal']
        self.assertEqual((flash['starts'], flash['times'], flash['mode']), ([12], [0.5], 'text'))
        self.assertIn('flashing', flash['notice'])
        self.assertIsNone(self.client.post('/api/quote', json={'song': song}).json()['subliminal'])
        self.assertIsNone(self.client.post('/api/quote', json={'song': song, 'subliminal': {'mode': 'off', 'frames': 5}}).json()['subliminal'])
        for bad, code in (({'mode': 'text', 'text': 'x', 'times': [0.2, 0.4]}, 400),                  # flashes too close together
                          ({'mode': 'text', 'text': 'x', 'times': [60]}, 400),                           # outside the video
                          ({'mode': 'image', 'image': 'missing.png', 'times': [0.5]}, 400),
                          ({'mode': 'text', 'text': '', 'times': [0.5]}, 400),
                          ({'mode': 'text', 'text': 'x', 'times': [0.5], 'frames': 99}, 422),
                          ({'mode': 'text', 'text': 'x', 'times': [0.5], 'mystery': 1}, 422)):
            with self.subTest(bad=bad):
                self.assertEqual(self.client.post('/api/quote', json={'song': song, 'subliminal': bad}).status_code, code)
        quote, started = self.start({'song': song, 'subliminal': {'mode': 'text', 'text': 'GOOSE', 'times': [0.5], 'frames': 2}})
        started.raise_for_status()
        status = self.wait()
        self.assertEqual(status['state'], 'complete', status)
        run = self.home / 'runs' / started.json()['id']
        self.assertTrue((run / 'music-video-clean.mp4').is_file())
        output = read_json(run / 'output.json')
        self.assertEqual(output['subliminal'], {'mode': 'text', 'frames': 2, 'times': [0.5], 'clean_copy': 'music-video-clean.mp4'})
        self.assertNotIn('quality_warnings', output)                                       # nothing went wrong
        from mmv import subliminal as flash_module
        self.assertEqual(flash_module._count_frames(run / 'music-video.mp4')[0], flash_module._count_frames(run / 'music-video-clean.mp4')[0])
        self.assertAlmostEqual(media.duration(run / 'music-video.mp4'), media.duration(run / 'music-video-clean.mp4'), delta=.05)
        from PIL import Image, ImageChops
        def frame(path, index):
            png = run / f'{path.stem}-{index}.png'
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(path), '-vf', f'select=eq(n\\,{index})', '-frames:v', '1', str(png)], check=True)
            return Image.open(png).convert('L')
        def difference(index):
            histogram = ImageChops.difference(frame(run / 'music-video.mp4', index), frame(run / 'music-video-clean.mp4', index)).histogram()
            return sum(value * count for value, count in enumerate(histogram))
        self.assertGreater(difference(12), 20 * difference(5) + 1000)                    # the flash frame differs, the others barely do
        self.assertGreater(difference(13), 20 * difference(5) + 1000)
        exported = self.client.post(f'/api/outputs/{run.name}/package', json={'allow_private_actors': True})
        self.assertEqual(exported.status_code, 200)
        self.wait()

    def test_failed_writer_never_renders(self):
        MockService.invalid_writer=True
        _,started=self.start({"song":self.song_upload()});started.raise_for_status()
        status=self.wait();self.assertEqual(status["state"],"failed")
        self.assertFalse(any(path=="/prompt" for path,body in MockService.requests))
        self.assertEqual(sum(path=="/chat/completions" for path,body in MockService.requests),3)
        self.assertTrue(status['can_retry_prompts'])
        self.assertFalse(status['can_resume'])
        self.app.state.jobs.last['message'] = (self.app.state.jobs.last['message'].removesuffix(' Nothing rendered.')
                                               + ' Note: Incomplete responses, JSON formatting errors, or shot-count mismatches'
                                                 ' often indicate your local writer context allocation size is too small. Nothing rendered.')
        self.assertNotIn('context allocation size', self.client.get('/api/status').json()['message'])
        self.assertEqual(self.client.post('/api/retry-prompts/quote', json={'run_id': 'unknown'}).status_code, 400)
        fresh = self.client.post('/api/retry-prompts/quote', json={'run_id': status['id']})
        fresh.raise_for_status()
        self.assertEqual(fresh.json()['kind'], 'video')
        self.assertEqual(fresh.json()['request']['song'], read_json(self.home / 'runs' / status['id'] / 'request.json')['song'])
        self.assertNotEqual(fresh.json()['id'], started.json()['id'])
        self.assertEqual(self.client.post('/api/start', json={'quote_id': fresh.json()['id'], 'consent': False}).status_code, 400)
        self.assertEqual(self.client.get('/api/status').json()['state'], 'failed')
        self.assertEqual(sum(path=="/chat/completions" for path,body in MockService.requests),3)
        renders = self.home / 'runs' / status['id'] / 'renders'
        renders.mkdir()
        (renders / 'already-submitted').mkdir()
        self.assertFalse(self.client.get('/api/status').json()['can_retry_prompts'])
        self.assertEqual(self.client.post('/api/retry-prompts/quote', json={'run_id': status['id']}).status_code, 400)

    def test_cancel_own_render_and_no_overlapping_start(self):
        MockService.hold=True
        _,started=self.start({"song":self.song_upload()});started.raise_for_status()
        deadline=time.monotonic()+15
        while time.monotonic()<deadline and not any(path=="/prompt" for path,body in MockService.requests): time.sleep(.05)
        self.assertTrue(any(path=="/prompt" for path,body in MockService.requests))
        self.assertEqual(self.client.post("/api/start",json={"quote_id":"anything","consent":True}).status_code,409)
        self.client.post("/api/cancel").raise_for_status()
        self.assertEqual(self.wait()["state"],"cancelled")
        self.assertTrue(any(path=="/queue" and body=={"delete":["local-test"]} for path,body in MockService.requests))

    def test_stale_preview_rejected(self):
        quote = self.client.post("/api/quote", json={"song": self.song_upload()}).json()
        settings = self.store.settings()
        settings["vision_model"] = "changed"
        self.client.put("/api/settings", json=settings).raise_for_status()
        rejected = self.client.post("/api/start", json={"quote_id": quote["id"], "consent": True})
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("changed", rejected.json()["detail"])

    def test_actor_signed_oap_round_trip_and_no_overwrite(self):
        response = self.client.post("/api/actors", data={"actor_id": "blue", "name": "Blue", "description": "Blue jacket"},
                                    files={"reference": ("ref.png", picture())})
        response.raise_for_status()
        package = self.client.post("/api/actors/blue/export")
        package.raise_for_status()
        uploaded = self.client.post("/api/upload/oap", files={"file": ("blue.oap", package.content)}).json()["file"]
        inspection = self.client.get("/api/oap/inspect/" + uploaded).json()
        self.assertTrue(inspection["verification"]["signature_valid"])
        self.assertFalse(inspection["verification"]["agent_known"])
        data = {"filename": uploaded, "actor_id": "blue_copy"}
        self.assertEqual(self.client.post("/api/oap/import", data=data).status_code, 400)
        data["accept_unknown"] = "true"
        imported = self.client.post("/api/oap/import", data=data)
        imported.raise_for_status()
        self.assertEqual(self.client.post("/api/actors/blue_copy/export").content, package.content)
        self.assertEqual(self.client.post("/api/oap/import", data=data).status_code, 400)
        self.assertNotIn("voice", imported.json())

    def test_oap_tamper_and_unsafe_archive_rejected(self):
        actor = actors.create_actor(self.store, "blue", "Blue", "", picture())
        path = actors.export_actor(self.store, "blue")
        corrupt = self.home / "corrupt.oap"
        with zipfile.ZipFile(path) as source, zipfile.ZipFile(corrupt, "w") as target:
            for member in source.infolist():
                target.writestr(member, b"tampered" if member.filename.endswith(".png") else source.read(member))
        with self.assertRaises(ValueError):
            actors.package_info(corrupt)
        with zipfile.ZipFile(corrupt, "w") as target:
            target.writestr("../escape", "unsafe")
            target.writestr("manifest.json", "{}")
        with self.assertRaisesRegex(ValueError, "unsafe"):
            actors.package_info(corrupt)

    def test_actor_rider_conflict_blocks_preview(self):
        actors.create_actor(self.store, "blue", "Blue", "", picture())
        content = {key: "none" for key in oap.CONTENT_ENUMS}
        content["nudity"] = "explicit"
        response = self.client.post("/api/quote", json={"song": self.song_upload(), "actors": ["blue"], "content": content})
        self.assertEqual(response.status_code, 400)
        self.assertIn("exceeds rider", response.json()["detail"])

    def test_credentials_not_returned_or_copied_into_settings(self):
        self.client.put("/api/key", json={"name": "WAVESPEED_API_KEY", "value": "private-example"}).raise_for_status()
        self.assertNotIn("private-example", self.client.get("/api/settings").text)
        if os.name != "nt":
            self.assertEqual((self.home / "secrets.json").stat().st_mode & 0o777, 0o600)

    def test_image_metadata_removed(self):
        data = io.BytesIO()
        image = Image.new("RGB", (20, 20), "teal")
        exif = Image.Exif()
        exif[0x010E] = "private metadata"
        image.save(data, "JPEG", exif=exif)
        destination = self.home / "clean.png"
        actors.clean_image(data.getvalue(), destination)
        with Image.open(destination) as clean:
            self.assertFalse(clean.getexif())


    def test_topaz_direct_export_command_and_original_preserved(self):
        _, started = self.start({"song": self.song_upload()})
        started.raise_for_status()
        self.assertEqual(self.wait()["state"], "complete")
        source = self.client.get("/api/outputs").json()[0]["file"]
        original = (self.home / "runs" / source).read_bytes()
        executable = self.home / "topaz-ffmpeg"
        executable.write_text("test fixture")
        models = self.home / "topaz-models"
        models.mkdir()
        (models / "ahq-12.json").write_text("{}")
        settings = self.store.settings()
        settings.update(topaz_executable=str(executable), topaz_models=str(models))
        self.client.put("/api/settings", json=settings).raise_for_status()
        commands = []

        def fake_command(context, argv, **kwargs):
            commands.append(argv)
            Path(argv[-1]).write_bytes(MockService.video)

        with patch("mmv.jobs.JobContext.command", fake_command):
            self.client.post("/api/upscale", json={"source": source, "model": "ahq-12", "scale": 2}).raise_for_status()
            result = self.wait()
        self.assertEqual(result["state"], "complete", result)
        self.assertTrue(any("tvai_up=model=ahq-12:scale=2" in str(x) for x in commands[0]))
        self.assertEqual((self.home / "runs" / source).read_bytes(), original)
        self.assertEqual(self.client.get("/api/outputs").json()[0]["kind"], "upscale")

    def test_topaz_cloud_estimate_consent_and_download(self):
        _, started = self.start({"song": self.song_upload()})
        started.raise_for_status()
        self.assertEqual(self.wait()["state"], "complete")
        source = self.client.get("/api/outputs").json()[0]["file"]
        original = (self.home / "runs" / source).read_bytes()
        settings = self.store.settings()
        settings.update(topaz_backend="cloud")
        self.client.put("/api/settings", json=settings).raise_for_status()
        self.assertEqual(self.client.post("/api/upscale/estimate", json={"source": source}).status_code, 400)
        self.client.put("/api/key", json={"name": "MMV_TOPAZ_API_KEY", "value": "topaz-test-key-123"}).raise_for_status()
        self.assertTrue(self.client.get("/api/settings").json()["keys"]["MMV_TOPAZ_API_KEY"])
        calls, state = [], {"price": 3, "status": "complete"}

        def send(method, url, headers, body):
            calls.append((method, url.split("topazlabs.com")[-1], headers.get("X-API-Key"), body))
            path = calls[-1][1]
            if method == "POST" and path == "/video/":
                return 200, {}, json.dumps({"requestId": "req-1", "estimates": {"cost": [2, state["price"]], "time": [10, 20]}}).encode()
            if path.endswith("/accept"):
                return 202, {}, json.dumps({"uploadId": "u", "urls": ["https://upload.invalid/part"]}).encode()
            if method == "PUT":
                return 200, {"ETag": '"abc"'}, b""
            if path.endswith("/complete-upload"):
                return 202, {}, b"{}"
            if path.endswith("/status"):
                return 200, {}, json.dumps({"status": state["status"], "progress": 100,
                                            "download": {"url": "https://download.invalid/out.mp4"}}).encode()
            return 200, {}, b"{}"

        def fetch(url, destination):
            Path(destination).write_bytes(MockService.video)

        with patch("mmv.topaz_api.send_http", send), patch("mmv.topaz_api.download_http", fetch):
            quote = self.client.post("/api/upscale/estimate", json={"source": source, "model": "prob-4", "scale": 2})
            quote.raise_for_status()
            self.assertEqual(quote.json()["credits"], [2, 3])
            self.assertFalse(any(c[0] in ("PATCH", "PUT") for c in calls), "an estimate must not reserve or upload")
            for credits in (None, 1000000):
                refused = self.client.post("/api/upscale", json={"source": source, "model": "prob-4", "scale": 2,
                                                                 **({"max_credits": credits} if credits else {})})
                self.assertEqual(refused.status_code, 400, "approval must match a displayed estimate")
            self.assertFalse(any(c[0] == "PATCH" for c in calls))
            state["price"] = 9
            self.client.post("/api/upscale", json={"source": source, "model": "prob-4", "scale": 2, "max_credits": 3}).raise_for_status()
            self.assertEqual(self.wait()["state"], "failed", "a price above the approved credits must stop before reserving")
            self.assertFalse(any(c[0] == "PATCH" for c in calls))
            state["price"] = 3
            self.client.post("/api/upscale", json={"source": source, "model": "prob-4", "scale": 2, "max_credits": 3}).raise_for_status()
            result = self.wait()
            motion = {"source": source, "model": "none", "scale": 1,
                      "options": {"interpolation": {"model": "apo-8", "fps": 60}}}
            self.client.post("/api/upscale/estimate", json=motion).raise_for_status()
            sent = json.loads([c for c in calls if c[1] == "/video/"][-1][3])
            self.assertEqual(sent["filters"], [{"model": "apo-8", "fps": 60}])
            self.assertEqual(self.client.post("/api/upscale", json={**motion, "max_credits": 3,
                             "options": {"interpolation": {"model": "apo-8", "fps": 24}}}).status_code, 400,
                             "approval is bound to the exact options estimated")
            self.assertEqual(self.client.post("/api/upscale/estimate", json={**motion, "options": {"tuning": {"x": 1}}}).status_code, 422)
        self.assertEqual(result["state"], "complete", result)
        self.assertEqual([c[0] for c in calls if c[1].startswith("/video/req-1")].count("PATCH"), 2)
        self.assertTrue(all(c[2] == "topaz-test-key-123" for c in calls if "topazlabs" not in c[1] and c[1].startswith("/video")))
        create = json.loads([c for c in calls if c[1] == "/video/" and b"prob-4" in c[3]][-1][3])
        self.assertEqual(create["filters"], [{"model": "prob-4"}])
        self.assertEqual((self.home / "runs" / source).read_bytes(), original)
        self.assertEqual(self.client.get("/api/outputs").json()[0]["kind"], "upscale")

    def test_security_and_private_features_absent(self):
        self.assertEqual(self.client.post("/api/cancel", headers={"Origin": "https://other.invalid"}).status_code, 403)
        for endpoint in ("/api/vault/status", "/api/film", "/api/micro-drama/new", "/mondo_web.py"):
            self.assertEqual(self.client.get(endpoint).status_code, 404)
        response = self.client.get("/")
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        self.assertEqual(self.client.get("/", headers={"Host": "other.invalid"}).status_code, 400)
        self.assertEqual(self.client.get("/api/media/abc/secrets.json").status_code, 400)

    def test_invalid_settings_and_nonfinite_input(self):
        settings = self.store.settings()
        settings["vision_url"] = "file:///etc/passwd"
        self.assertEqual(self.client.put("/api/settings", json=settings).status_code, 422)
        self.assertEqual(self.client.post("/api/quote", json={"bpm": 0}).status_code, 422)
        self.assertEqual(self.client.post("/api/quote", json={"content": {"nudity": "invented"}}).status_code, 422)
        self.assertEqual(self.client.post("/api/quote", json={"kind": "film"}).status_code, 422)

    def install_test_h3_models(self):
        for category, name in [('vae', 'test_video_vae.safetensors'),
                               ('diffusion_models', 'test_diffusion.safetensors')]:
            folder = self.home / 'models' / category
            folder.mkdir(parents=True, exist_ok=True)
            (folder / name).write_text('test fixture; not real weights')

    def custom_h3_workflow(self):
        from mmv.pipeline import ENGINE
        graph = read_json(ENGINE / 'workflows/h3_ref2video_audionodeadded.json')
        graph['127']['inputs']['unet_name'] = 'my-current-model.safetensors'
        graph['127']['inputs']['weight_dtype'] = 'operator-precision'
        graph['custom-node'] = {'class_type': 'OperatorCustomNode', 'inputs': {'note': 'preserve me'}}
        # Loader IDs are not required to match the bundled graph.
        graph['527'] = graph.pop('127')
        for node in graph.values():
            for key, value in node['inputs'].items():
                if isinstance(value, list) and value and value[0] == '127':
                    node['inputs'][key] = ['527', *value[1:]]
        path = self.home / 'operator-graph.json'
        write_json(path, graph)
        mapping = read_json(ENGINE / 'config/injection_map.json')
        mapping.update(workflow=str(path), operator_note='preserve bindings too')
        map_path = self.home / 'operator-map.json'
        write_json(map_path, mapping)
        return graph, mapping, map_path

    def test_model_change_preserves_active_custom_graph_and_map(self):
        self.install_test_h3_models()
        graph, mapping, map_path = self.custom_h3_workflow()
        settings = self.store.settings()
        settings['workflow_map_path'] = str(map_path)
        self.client.put('/api/settings', json=settings).raise_for_status()
        response = self.client.get('/api/settings').json()
        self.assertEqual(response['settings']['h3_models']['diffusion_model'], 'my-current-model.safetensors')
        # A normal settings save must retain the selected map and model.
        self.client.put('/api/settings', json=response['settings']).raise_for_status()
        self.assertEqual(self.store.settings()['workflow_map_path'], str(map_path))
        settings = response['settings']
        settings['h3_models'] = {'diffusion_model': 'test_diffusion.safetensors'}
        self.client.put('/api/settings', json=settings).raise_for_status()
        saved_map = read_json(Path(self.store.settings()['workflow_map_path']))
        saved_graph = read_json(Path(saved_map['workflow']))
        expected = json.loads(json.dumps(graph))
        expected['527']['inputs']['unet_name'] = 'test_diffusion.safetensors'
        self.assertEqual(saved_graph, expected)
        self.assertEqual({**saved_map, 'workflow': mapping['workflow']}, mapping)
        # Keep the operator-owned sources intact, including precision and added nodes.
        self.assertEqual(read_json(Path(mapping['workflow'])), graph)
        self.assertEqual(read_json(map_path), mapping)

    def test_bundled_diffusion_model_brings_its_own_workflow_and_steps(self):
        from mmv.workflow_presets import map_steps, preset_path
        standard_unet, fast_unet = 'minimax_h3_ref2va_pruned_bf16.safetensors', 'fasth3_omniref_8step_pruned_bf16.safetensors'
        for category, name in [('diffusion_models', standard_unet), ('diffusion_models', fast_unet),
                               ('text_encoders', 'my_encoder.safetensors')]:
            folder = self.home / 'models' / category
            folder.mkdir(parents=True, exist_ok=True)
            (folder / name).write_text('test fixture; not real weights')
        settings = {**self.store.settings(), 'workflow_map_path': preset_path('fasth3_bf16')}
        self.client.put('/api/settings', json={**settings, 'h3_models': {'text_encoder': 'my_encoder.safetensors'}}).raise_for_status()
        self.assertEqual(self.client.get('/api/settings').json()['workflow_steps'], 8)
        # The 20-step model chosen on the 8-step FastH3 workflow switches to the standard workflow.
        settings = self.store.settings()
        self.client.put('/api/settings', json={**settings, 'h3_models': {'diffusion_model': standard_unet}}).raise_for_status()
        body = self.client.get('/api/settings').json()
        self.assertEqual((body['workflow_steps'], map_steps(self.store.settings()['workflow_map_path'])), (20, 20))
        self.assertEqual(body['settings']['h3_models']['diffusion_model'], standard_unet)
        self.assertEqual(body['settings']['h3_models']['text_encoder'], 'my_encoder.safetensors')
        saved = read_json(Path(read_json(Path(self.store.settings()['workflow_map_path']))['workflow']))
        self.assertEqual([n['inputs']['steps'] for n in saved.values() if 'steps' in n['inputs']], [20])
        # And back: the FastH3 model brings the 8-step workflow.
        settings = self.store.settings()
        self.client.put('/api/settings', json={**settings, 'h3_models': {'diffusion_model': fast_unet}}).raise_for_status()
        body = self.client.get('/api/settings').json()
        self.assertEqual((body['workflow_steps'], body['settings']['h3_models']['diffusion_model']), (8, fast_unet))
        self.assertEqual(body['settings']['h3_models']['text_encoder'], 'my_encoder.safetensors')

    def test_ambiguous_model_loaders_are_not_silently_selected(self):
        self.install_test_h3_models()
        graph, mapping, map_path = self.custom_h3_workflow()
        graph['another-loader'] = {'class_type': 'UNETLoader', 'inputs': {'unet_name': 'second-model.safetensors'}}
        write_json(Path(mapping['workflow']), graph)
        settings = {**self.store.settings(), 'workflow_map_path': str(map_path)}
        self.client.put('/api/settings', json=settings).raise_for_status()
        self.assertNotIn('diffusion_model', self.client.get('/api/settings').json()['settings']['h3_models'])
        settings['h3_models'] = {'diffusion_model': 'test_diffusion.safetensors'}
        response = self.client.put('/api/settings', json=settings)
        self.assertEqual(response.status_code, 400)
        self.assertIn('unambiguous', response.json()['detail'])
        self.assertEqual(read_json(Path(mapping['workflow'])), graph)

    def test_new_workflow_path_is_not_overridden_on_save(self):
        _, _, map_path = self.custom_h3_workflow()
        settings = self.client.get('/api/settings').json()['settings']
        settings.pop('h3_models')  # Browser submits only explicit model changes.
        settings['workflow_map_path'] = str(map_path)
        self.client.put('/api/settings', json=settings).raise_for_status()
        self.assertEqual(self.store.settings()['workflow_map_path'], str(map_path))

    def test_model_discovery_falls_back_per_category(self):
        self.install_test_h3_models()
        self.server.object_info = {'VAELoader': {'VAELoader': {'input': {'required': {
            'vae_name': [['live-video-vae.safetensors']]}}}}}
        info = self.client.get('/api/settings').json()['h3_models_installed']
        self.assertEqual(info['video_vae'], ['live-video-vae.safetensors'])
        self.assertIn('test_diffusion.safetensors', info['diffusion_model'])

    def test_unavailable_or_unsafe_model_selections_do_not_change_settings(self):
        before = self.store.settings()
        for models, status in [({'diffusion_model': 'not-installed.safetensors'}, 400),
                               ({'diffusion_model': '../private.safetensors'}, 422),
                               ({'unknown_role': 'test.safetensors'}, 422)]:
            request = {**before, 'h3_models': models}
            self.assertEqual(self.client.put('/api/settings', json=request).status_code, status)
            self.assertEqual(self.store.settings(), before)

    def test_h3_model_settings_roundtrip(self):
        self.install_test_h3_models()
        res = self.client.get("/api/settings")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("settings", body)
        self.assertIn("h3_models", body["settings"])
        self.assertIn("h3_models_installed", body)
        self.assertIn("video_vae", body["settings"]["h3_models"])
        self.assertIn("diffusion_model", body["settings"]["h3_models"])

        settings = self.store.settings()
        settings["h3_models"] = {
            "video_vae": "test_video_vae.safetensors",
            "diffusion_model": "test_diffusion.safetensors",
        }
        self.client.put("/api/settings", json=settings).raise_for_status()

        updated = self.client.get("/api/settings").json()
        self.assertEqual(updated["settings"]["h3_models"]["video_vae"], "test_video_vae.safetensors")
        self.assertEqual(updated["settings"]["h3_models"]["diffusion_model"], "test_diffusion.safetensors")

    def test_browse_fs(self):
        res = self.client.get("/api/fs/browse")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("current", data)
        self.assertIn("drives", data)
        self.assertIn("folders", data)

        sub = self.home / "subfolder_test"
        sub.mkdir()
        file_path = sub / "test.json"
        file_path.write_text("{}")

        res_folder = self.client.get(f"/api/fs/browse?path={self.home}&mode=folder")
        self.assertEqual(res_folder.status_code, 200)
        folder_names = [f["name"] for f in res_folder.json()["folders"]]
        self.assertIn("subfolder_test", folder_names)

        res_file = self.client.get(f"/api/fs/browse?path={sub}&mode=file&ext=.json")
        self.assertEqual(res_file.status_code, 200)
        file_names = [f["name"] for f in res_file.json()["files"]]
        self.assertIn("test.json", file_names)


class QueueRuleTests(unittest.TestCase):
    def ticket(self, estimate=0, fingerprint="f", **fields):
        return {**production_queue.new_ticket({"kind": "video"}, "x", 1, estimate=estimate, fingerprint=fingerprint), **fields}

    def test_free_work_is_never_held(self):
        self.assertIsNone(production_queue.hold_reason(self.ticket(), [self.ticket(5, state="failed")], 0, "other"))

    def test_paid_work_needs_the_approved_plan_and_a_clean_paid_record(self):
        approved = self.ticket(5)
        self.assertIsNone(production_queue.hold_reason(approved, [approved], 5, "f"))
        self.assertIn("changed", production_queue.hold_reason(approved, [approved], 5, "g"))
        self.assertIn("never approved", production_queue.hold_reason(self.ticket(), [], 5, "f"))
        self.assertIn("earlier paid", production_queue.hold_reason(approved, [self.ticket(5, state="failed", finished=approved["created"] + 1)], 5, "f"))
        self.assertIsNone(production_queue.hold_reason(approved, [self.ticket(5, state="failed", finished=approved["created"] - 1)], 5, "f"))
        self.assertIsNone(production_queue.hold_reason(approved, [self.ticket(0, state="failed")], 5, "f"))

    def test_a_paid_failure_put_back_in_line_still_holds_older_approvals(self):
        approved = self.ticket(5)
        failed = self.ticket(5, state="failed", finished=approved["created"] + 1)
        requeued = {**failed, "state": "held", "finished": approved["created"] + 2, "stopped_at": failed["finished"]}
        self.assertIn("earlier paid", production_queue.hold_reason(approved, [requeued], 5, "f"))
        self.assertIsNone(production_queue.hold_reason(approved, [{**requeued, "state": "complete"}], 5, "f"))

    def test_moved_swaps_waiting_neighbours_only(self):
        first, second = self.ticket(position=1), self.ticket(position=2)
        swapped = production_queue.moved([first, second], first["id"], 1)
        self.assertEqual({t["id"]: t["position"] for t in swapped}, {first["id"]: 2, second["id"]: 1})
        self.assertEqual(production_queue.moved([first, second], first["id"], -1), [])
        with self.assertRaises(ValueError):
            production_queue.moved([self.ticket(state="running", id="r")], "r", 1)


class UtilityTests(unittest.TestCase):

    def test_windows_json_read_retries_only_permission_errors(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        path = Mock()
        path.exists.return_value = True
        path.read_text.side_effect = [PermissionError('transient lock'), '{"ok": true}']
        with patch('mmv.storage.os', SimpleNamespace(name='nt')), patch('mmv.storage.time.sleep'):
            self.assertEqual(read_json(path), {'ok': True})
        self.assertEqual(path.read_text.call_count, 2)
        path.read_text.side_effect = PermissionError('not transient on POSIX')
        with patch('mmv.storage.os', SimpleNamespace(name='posix')):
            with self.assertRaises(PermissionError):
                read_json(path)


    def test_single_session_and_interrupted_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Storage(temp)
            with SessionLock(store.home):
                with self.assertRaises(ValueError):
                    with SessionLock(store.home):
                        pass
            write_json(store.home / "operation.json", {"state": "running", "id": "old"})
            jobs = Jobs(store)
            self.assertEqual(jobs.status()["state"], "interrupted")

    def test_model_download_consent_integrity_and_path_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Storage(temp)
            manifest = store.home / "manifest.json"
            data = b"small fixture, not an AI model"
            entry = {"name": "Test fixture", "url": "https://example.invalid/model", "license_url": "https://example.invalid/license",
                     "sha256": hashlib.sha256(data).hexdigest(), "destination": "test/model.gguf", "size_bytes": len(data)}
            write_json(manifest, {"models": [entry]})
            with patch("builtins.input", return_value="no"), patch("urllib.request.urlopen") as network:
                download_models(store, manifest)
                network.assert_not_called()
            response = io.BytesIO(data)
            response.url = entry["url"]
            with patch("builtins.input", return_value="yes"), patch("urllib.request.urlopen", return_value=response):
                download_models(store, manifest)
            self.assertEqual((store.home / "models/test/model.gguf").read_bytes(), data)
            entry["destination"] = "../../escape"
            write_json(manifest, {"models": [entry]})
            with self.assertRaises(ValueError):
                download_models(store, manifest)

    def test_inside_rejects_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                inside(Path(temp), "../secrets")

    def test_corrupt_model_download_never_activated(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Storage(temp)
            manifest = store.home / "manifest.json"
            write_json(manifest, {"models": [{"name": "Corrupt fixture", "url": "https://example.invalid/model",
                       "license_url": "https://example.invalid/license", "sha256": "0" * 64,
                       "destination": "model.gguf"}]})
            response = io.BytesIO(b"not matching the checksum")
            response.url = "https://example.invalid/model"
            with patch("builtins.input", return_value="yes"), patch("urllib.request.urlopen", return_value=response):
                with self.assertRaisesRegex(ValueError, "integrity"):
                    download_models(store, manifest)
            self.assertFalse((store.home / "models/model.gguf").exists())
            self.assertTrue((store.home / "models/model.gguf.partial").exists())

    def test_invalid_manifest_rejected_before_any_download(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Storage(temp)
            manifest = store.home / "manifest.json"
            write_json(manifest, {"models": [{"name": "Invalid", "url": "http://example.invalid/file"}]})
            with patch("urllib.request.urlopen") as network:
                with self.assertRaises(ValueError):
                    download_models(store, manifest)
                network.assert_not_called()

    def test_service_error_reporting_identifies_comfyui_and_launch_key(self):
        from mmv import runtime
        with patch.object(runtime, "http_ok", return_value=False):
            with self.assertRaises(ValueError) as ctx:
                runtime.start_service("", "", "http://127.0.0.1:8188/system_stats", Path("/tmp/comfy-service.log"))
            msg = str(ctx.exception)
            self.assertIn("ComfyUI service is not running", msg)
            self.assertIn("http://127.0.0.1:8188/system_stats", msg)
            self.assertIn("comfy_launch", msg)

    def test_service_error_reporting_identifies_llama_and_launch_key(self):
        from mmv import runtime
        with patch.object(runtime, "http_ok", return_value=False):
            with self.assertRaises(ValueError) as ctx:
                runtime.start_service("", "", "http://127.0.0.1:8080/v1/models", Path("/tmp/writer-service.log"))
            msg = str(ctx.exception)
            self.assertIn("llama.cpp", msg)
            self.assertIn("http://127.0.0.1:8080/v1/models", msg)
            self.assertIn("writer_launch", msg)

    def test_service_identification_vision_and_laya(self):
        from mmv import runtime
        name, key = runtime.identify_service(health_url="http://127.0.0.1:8080/v1/chat/completions", log="/tmp/vision.log")
        self.assertIn("Vision", name)
        name, key = runtime.identify_service(health_url=None, log="/tmp/laya.log")
        self.assertIn("Laya", name)

    def test_operation_log_endpoint_includes_comfy_log(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Storage(temp)
            run_dir = store.home / "runs" / "test_run"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "operation.log").write_text("Starting pipeline\n", encoding="utf-8")
            (run_dir / "comfy-service.log").write_text("ComfyUI startup output log", encoding="utf-8")
            (run_dir / "writer-service.log").write_text("llama-server output log", encoding="utf-8")
            app = create_app(store.home, test_hosts=True)
            client = TestClient(app)
            res = client.get("/api/log/test_run")
            self.assertEqual(res.status_code, 200)
            log_text = res.json()["log"]
            self.assertIn("--- ComfyUI Service Output ---", log_text)
            self.assertIn("ComfyUI startup output log", log_text)
            self.assertIn("--- Writer Service Output (llama.cpp) ---", log_text)
            self.assertIn("llama-server output log", log_text)

    def test_token_reduction_helpers_and_ident_pruning(self):
        from mmv.worker import _compact_writer_job, _compact_ident_prompt
        from mmv.engine import style
        job = {
            "segment_id": "seg000",
            "cast": [{"actor_id": "a1", "display_name": "Actor 1", "part": "", "lines": [], "direction": ""}],
            "shots": [{"n": 1, "vocabulary": {"setting": "alley", "lighting": "neon"}}],
        }
        pretty = json.dumps(job, indent=2)
        compact = _compact_writer_job(job)
        self.assertLess(len(compact), len(pretty) * 0.75)
        parsed = json.loads(compact)
        self.assertEqual(parsed["segment_id"], "seg000")
        self.assertNotIn("lines", parsed["cast"][0])
        self.assertNotIn("direction", parsed["cast"][0])
        self.assertNotIn("part", parsed["cast"][0])

        full_ident = style.compose_ident_prompt()
        std_ident = _compact_ident_prompt(full_ident, "standard")
        harvest_ident = _compact_ident_prompt(full_ident, "harvest")
        sceno_ident = _compact_ident_prompt(full_ident, "scenographic")
        self.assertLess(len(std_ident), len(full_ident) * 0.6)
        self.assertNotIn("Scenographic mode\n", std_ident)
        self.assertNotIn("Reading a reference image\n", std_ident)
        self.assertIn("Reading a reference image\n", harvest_ident)
        self.assertNotIn("Scenographic mode\n", harvest_ident)
        self.assertIn("Scenographic mode\n", sceno_ident)
        self.assertNotIn("IMAGE-TO-VIDEO IDENT (SCENOGRAPHIC)", sceno_ident)

    def test_vocabulary_customization_and_api_endpoints(self):
        from mmv.pipeline import load_vocabulary
        with tempfile.TemporaryDirectory() as temp:
            store = Storage(temp)
            # Test 1: load_vocabulary defaults
            full_vocab = load_vocabulary("full")
            self.assertIn("settings", full_vocab)
            self.assertGreater(len(full_vocab["settings"]), 200)

            # Test 2: custom_vocabulary overrides (append & replace)
            custom_overrides = {
                "settings": {"mode": "append", "add": ["custom_cyberpunk_neon_alley"], "exclude": [full_vocab["settings"][0]]},
                "lighting": {"mode": "replace", "add": ["monochrome laser beam", "candlelight"], "exclude": []},
            }
            custom_vocab = load_vocabulary("full", store=store, custom=custom_overrides)
            self.assertIn("custom_cyberpunk_neon_alley", custom_vocab["settings"])
            self.assertNotIn(full_vocab["settings"][0], custom_vocab["settings"])
            self.assertEqual(custom_vocab["lighting"], ["monochrome laser beam", "candlelight"])

            # Test 3: empty category error guard
            with self.assertRaises(ValueError) as ctx:
                load_vocabulary("full", store=store, custom={"lighting": {"mode": "replace", "add": []}})
            self.assertIn("lighting' cannot be empty", str(ctx.exception))

            # Test 4: API endpoints for vocabulary
            app = create_app(store.home, test_hosts=True)
            client = TestClient(app)

            # GET /api/vocabulary
            res = client.get("/api/vocabulary")
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertIn("categories", data)
            self.assertIn("settings", data["categories"])
            self.assertIn("base", data)
            self.assertIn("profiles", data)

            # POST /api/vocabularies (save preset)
            preset_payload = {
                "id": "my_synthwave_preset",
                "name": "My Synthwave Preset",
                "description": "80s retro neon aesthetic",
                "base_profile": "full",
                "tables": {
                    "lighting": {"mode": "replace", "add": ["magenta neon grid", "cyan laser glow"], "exclude": []}
                }
            }
            res = client.post("/api/vocabularies", json=preset_payload)
            self.assertEqual(res.status_code, 200)

            # Verify preset loaded via store
            saved_preset_vocab = load_vocabulary("my_synthwave_preset", store=store)
            self.assertEqual(saved_preset_vocab["lighting"], ["magenta neon grid", "cyan laser glow"])

            # GET /api/vocabularies
            res = client.get("/api/vocabularies")
            self.assertEqual(res.status_code, 200)
            self.assertEqual(len(res.json()), 1)
            self.assertEqual(res.json()[0]["id"], "my_synthwave_preset")

            # DELETE /api/vocabularies/my_synthwave_preset
            res = client.delete("/api/vocabularies/my_synthwave_preset")
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json(), {"deleted": "my_synthwave_preset"})

            # Cannot delete built-in profile
            res = client.delete("/api/vocabularies/full")
            self.assertEqual(res.status_code, 400)

            # GET /api/vocabulary/guide
            res = client.get("/api/vocabulary/guide")
            self.assertEqual(res.status_code, 200)
            guide_data = res.json()
            self.assertIn("markdown", guide_data)
            self.assertIn("Visual Vocabulary", guide_data["markdown"])
            self.assertIn("title", guide_data)

    def test_project_vocab_random_key_persistence(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Storage(temp)
            app = create_app(store.home, test_hosts=True)
            client = TestClient(app)

            # Save project with a pseudo-random vocabulary key
            payload = {
                "panel": "video",
                "forms": {"video": {"title": "Neon Dreams"}},
                "vocab_random_key": "482910:5",
                "custom_vocabulary": {
                    "lighting": {"mode": "append", "add": [], "exclude": ["strobe lights"]}
                }
            }
            res = client.put("/api/project", json=payload)
            self.assertEqual(res.status_code, 200)

            # Retrieve project and verify vocab_random_key persists
            get_res = client.get("/api/project")
            self.assertEqual(get_res.status_code, 200)
            data = get_res.json()
            self.assertEqual(data.get("vocab_random_key"), "482910:5")
            self.assertEqual(data.get("forms", {}).get("video", {}).get("title"), "Neon Dreams")
            self.assertIn("lighting", data.get("custom_vocabulary", {}))

    def test_style_carries_validated_optional_vocabulary(self):
        with tempfile.TemporaryDirectory() as temp:
            client = TestClient(create_app(Storage(temp).home, test_hosts=True))
            vocab = {"settings": {"mode": "append", "add": ["rain-slick archive"], "exclude": []}}
            base = {"id": "vocab_style", "name": "Vocab Style", "direction": "Cold archive light."}
            saved = client.post("/api/styles/import", json={**base, "vocabulary": vocab, "overwrite": False})
            self.assertEqual(saved.status_code, 200, saved.text)
            self.assertEqual(saved.json()["vocabulary"]["settings"]["add"], ["rain-slick archive"])
            listed = next(s for s in client.get("/api/styles").json() if s["id"] == "vocab_style")
            self.assertEqual(listed["vocabulary"]["settings"]["add"], ["rain-slick archive"])
            self.assertEqual(client.get("/api/styles/vocab_style/export").json()["vocabulary"], saved.json()["vocabulary"])
            for bad in ({"nonsense": {"add": ["x"]}}, {"settings": {"mode": "replace", "add": []}}):
                refused = client.post("/api/styles/import", json={**base, "vocabulary": bad, "overwrite": True})
                self.assertEqual(refused.status_code, 400, refused.text)
            long = {"settings": {"mode": "append", "add": ["x" * 301], "exclude": []}}
            self.assertEqual(client.post("/api/styles/import", json={**base, "vocabulary": long, "overwrite": True}).status_code, 400)
            plain = client.post("/api/styles/import", json={**base, "overwrite": True})
            self.assertNotIn("vocabulary", plain.json())

    def test_world_contrast_resolves_pools_and_stays_out_of_defaults(self):
        from mmv import worlds
        from webapp.mondo_web import ProductionRequest, request_dict, with_world
        with tempfile.TemporaryDirectory() as temp:
            store = Storage(temp)
            for wid, place in (("home", "salt pan"), ("away", "glass atrium")):
                worlds.create(store, wid, {"id": wid, "name": wid.title(), "pools": {"settings": {"include": [place], "exclude": []}}})
            plain = request_dict(ProductionRequest(song="s.wav", direction="d", world_id="home", world_contrast={"tangent": "away"}, world_contrast_strength=80))
            self.assertEqual(plain["world_contrast"], {"tangent": "away"})
            resolved = with_world(store, plain)
            self.assertEqual(resolved["world_departures"], {"tangent": {"settings": ["glass atrium"]}})
            self.assertEqual(ProductionRequest(**resolved).world_departures, resolved["world_departures"])   # resume and retry re-validate the stored request
            self.assertNotIn("world_contrast", request_dict(ProductionRequest(song="s.wav", direction="d", world_id="home", world_contrast={"tangent": "away"}, world_contrast_strength=0)))
            with self.assertRaises(ValueError):
                ProductionRequest(song="s.wav", direction="d", world_id="home", world_contrast={"mirror": "home"})
            off = request_dict(ProductionRequest(song="s.wav", direction="d", world_id="home"))
            self.assertNotIn("world_contrast", off)
            self.assertNotIn("world_departures", with_world(store, off))
            self.assertNotIn("world_contrast", request_dict(ProductionRequest(song="s.wav", direction="d", world_contrast={"tangent": "away"})))

    def test_style_export_import_and_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Storage(temp)
            app = create_app(store.home, test_hosts=True)
            client = TestClient(app)

            # Create an initial style with an 11-axis style card
            create_payload = {
                "id": "cyberpunk_neon",
                "name": "Cyberpunk Neon",
                "direction": "High contrast neon cyan and magenta lighting with heavy film grain.",
                "style_card": "Color Palette: Neon cyan, magenta\nLighting: Hard directional neon\nCamera: Anamorphic lens flare",
            }
            res = client.post("/api/styles", json=create_payload)
            self.assertEqual(res.status_code, 200)
            created = res.json()
            self.assertEqual(created["id"], "cyberpunk_neon")
            self.assertEqual(created["style_card"], create_payload["style_card"])

            # Export style
            export_res = client.get("/api/styles/cyberpunk_neon/export")
            self.assertEqual(export_res.status_code, 200)
            self.assertIn("application/json", export_res.headers["content-type"])
            self.assertIn("cyberpunk_neon.json", export_res.headers.get("content-disposition", ""))
            exported_data = export_res.json()
            self.assertEqual(exported_data["id"], "cyberpunk_neon")
            self.assertEqual(exported_data["name"], "Cyberpunk Neon")
            self.assertEqual(exported_data["style_card"], create_payload["style_card"])

            # Export nonexistent style
            self.assertEqual(client.get("/api/styles/missing_style/export").status_code, 400)

            # Import existing style without overwrite -> should fail 400
            import_collision = {
                "id": "cyberpunk_neon",
                "name": "Cyberpunk Collision",
                "direction": "Attempting overwrite without flag.",
                "overwrite": False,
            }
            res_coll = client.post("/api/styles/import", json=import_collision)
            self.assertEqual(res_coll.status_code, 400)
            self.assertIn("already exists", res_coll.json()["detail"])

            # Import existing style with overwrite=True -> succeeds and updates
            import_overwrite = {
                "id": "cyberpunk_neon",
                "name": "Cyberpunk 2099",
                "direction": "Updated rain-slicked concrete aesthetic.",
                "style_card": "Axis 1: Rain-slicked reflections",
                "overwrite": True,
            }
            res_over = client.post("/api/styles/import", json=import_overwrite)
            self.assertEqual(res_over.status_code, 200)
            self.assertEqual(res_over.json()["name"], "Cyberpunk 2099")

            # Verify exported version matches updated data
            updated_export = client.get("/api/styles/cyberpunk_neon/export").json()
            self.assertEqual(updated_export["name"], "Cyberpunk 2099")
            self.assertEqual(updated_export["style_card"], "Axis 1: Rain-slicked reflections")
            self.assertNotIn("overwrite", updated_export)

            # Import new style
            import_new = {
                "id": "vintage_sepia",
                "name": "Vintage Sepia",
                "direction": "1920s orthochromatic film look with warm sepia toning.",
                "overwrite": False,
            }
            res_new = client.post("/api/styles/import", json=import_new)
            self.assertEqual(res_new.status_code, 200)

            # Style list contains both
            styles_list = client.get("/api/styles").json()
            ids = [s["id"] for s in styles_list]
            self.assertIn("cyberpunk_neon", ids)
            self.assertIn("vintage_sepia", ids)

            # Validation failures:
            # 1. Invalid ID pattern
            bad_id = {"id": "Invalid ID!", "name": "Bad", "direction": "Some text"}
            self.assertEqual(client.post("/api/styles/import", json=bad_id).status_code, 422)

            # 2. Path traversal attempt in ID
            traversal_id = {"id": "../traversal", "name": "Bad", "direction": "Some text"}
            self.assertEqual(client.post("/api/styles/import", json=traversal_id).status_code, 422)

            # 3. Empty direction
            empty_dir = {"id": "valid_id", "name": "Valid", "direction": ""}
            self.assertEqual(client.post("/api/styles/import", json=empty_dir).status_code, 422)

            # 4. Undeclared fields (StrictModel enforcement)
            extra_field = {"id": "valid_id_2", "name": "Valid", "direction": "Look", "hack": 123}
            self.assertEqual(client.post("/api/styles/import", json=extra_field).status_code, 422)


if __name__ == "__main__":
    unittest.main()


