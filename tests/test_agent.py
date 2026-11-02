"""Exercise agent calls against an actual local app and MCP over stdio."""
import asyncio
import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import uvicorn

from mmv.agent import AgentClient
import test_public_app as public_fixtures
from tests.test_opp_props import package as make_opp_package


class LiveAppFixture:
    @classmethod
    def setUpClass(cls):
        public_fixtures.PublicAppTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        public_fixtures.PublicAppTests.tearDownClass()

    def setUp(self):
        self.fixture = public_fixtures.PublicAppTests("test_version_matches_package_and_readme")
        self.fixture.setUp()
        self.home = self.fixture.home
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        self.url = "http://127.0.0.1:" + str(sock.getsockname()[1])
        self.server = uvicorn.Server(uvicorn.Config(self.fixture.app, log_level="error", lifespan="on"))
        self.thread = threading.Thread(target=self.server.run, kwargs={"sockets": [sock]}, daemon=True)
        self.thread.start()
        for _ in range(100):
            if self.server.started:
                break
            time.sleep(.02)
        if not self.server.started:
            self.fail("Test app did not start")
        self.agent = AgentClient(self.url)
        self.song = self.home / "song.wav"
        self.song.write_bytes(public_fixtures.PublicAppTests.song)
        self.reference = self.home / "reference.png"
        self.reference.write_bytes(public_fixtures.picture())

    def tearDown(self):
        self.server.should_exit = True
        self.thread.join(timeout=15)
        self.fixture.tearDown()

    def wait(self):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            status = self.agent.inspect("status")
            if status["state"] not in ("running", "cancelling"):
                return status
            time.sleep(.05)
        self.fail("Operation did not complete")


class AgentTests(LiveAppFixture, unittest.TestCase):
    def test_opp_import_and_instrument_preview(self):
        source = make_opp_package(self.home, signed=True)
        uploaded = self.agent.upload("opp", str(source))["file"]
        inspected = self.agent.inspect_opp(uploaded)
        self.assertTrue(inspected["verification"]["signature_valid"])
        with self.assertRaisesRegex(ValueError, "accept this signer"):
            self.agent.import_opp(uploaded)
        imported = self.agent.import_opp(uploaded, accept_signer=inspected['manifest']['prop']['owner']['public_key'])
        self.assertEqual(imported["id"], "blue-guitar")
        self.assertEqual(self.agent.inspect("props")[0]["id"], "blue-guitar")
        self.assertEqual(self.agent.select_opp_sheet('blue-guitar', 'strumming strings')['sheet_kind'], 'interaction')
        self.agent.create_actor("blue", "Blue", "A blue jacket", str(self.reference))
        song = self.agent.upload("song", str(self.song))["file"]
        quote = self.agent.preview({"song": song, "actors": ["blue"], "instrument_mode": "perform",
            "instrument_assignments": {"blue": "guitar"}, "instrument_props": {"guitar": "blue-guitar"},
            "instrument_prop_uses": {"guitar": "strumming strings"}})
        asset = quote["instruments"]["assets"]["guitar"]
        self.assertEqual(asset["prop_id"], "blue-guitar")
        self.assertEqual(asset["sheet_kind"], "interaction")
        self.assertNotIn('path', asset)
        self.assertNotIn('bundle_path', asset)
        self.assertNotEqual(quote['instruments']['passages'][next(iter(quote['instruments']['passages']))]['performers'][0]['description'],
                            imported['description'])
        self.assertEqual(quote["instruments"]["passages"][next(iter(quote["instruments"]["passages"]))]["references"], ["guitar"])

    def test_preview_start_and_download(self):
        uploaded = self.agent.upload("song", str(self.song))
        self.assertEqual(uploaded["name"], self.song.name)
        song = uploaded["file"]
        independent = self.agent.preview({"song": song, "dance_mode": "independent", "dance_parts": {}})
        self.assertEqual(independent["dance"]["mode"], "independent")
        self.assertEqual(independent["dance"]["version"], 3)
        preview = self.agent.preview({"song": song, "title": "Agent Coast", "direction": "A sunlit coast"})
        with self.assertRaisesRegex(ValueError, "authorization"):
            self.agent.start(preview["id"])
        self.agent.start(preview["id"], consent=True)
        status = self.wait()
        self.assertEqual(status["state"], "complete", status)
        output = self.agent.inspect("outputs")[0]
        score = self.agent.music_score(output["file"])
        self.assertTrue(score["beats"] and score["passages"])
        self.assertTrue(all(shot["cut"] in ("passage", "downbeat", "beat", "split")
                            for passage in score["passages"] for shot in passage["shots"]))
        self.assertTrue(output["play_url"].startswith(self.url + "/api/media/"))
        passages = self.agent.output_prompts(output["file"])["segments"]
        self.assertTrue(passages and all(p["prompt"] for p in passages))
        self.assertTrue(all(p["clip_url"].startswith(self.url + "/api/outputs/") for p in passages if p["has_clip"]))
        self.assertIn("Quality Vision", self.agent.inspect("vision-guide")["markdown"])
        destination = self.home / "download.mp4"
        receipt = self.agent.download(output["file"], str(destination))
        self.assertGreater(receipt["bytes"], 0)
        before = destination.read_bytes()
        with self.assertRaises(FileExistsError):
            self.agent.download(output["file"], str(destination))
        self.assertEqual(before, destination.read_bytes())

    def test_oap_workflow_through_agent(self):
        record = self.agent.create_actor("blue", "Blue", "A blue jacket", str(self.reference))
        self.assertEqual(record["id"], "blue")
        package = self.home / "blue.oap"
        self.agent.export_oap("blue", str(package))
        upload = self.agent.upload("oap", str(package))["file"]
        report = self.agent.inspect_oap(upload)
        self.assertTrue(report["verification"]["signature_valid"])
        self.assertFalse(report["verification"]["agent_known"])
        with self.assertRaises(ValueError):
            self.agent.import_oap(upload, "blue_copy")
        self.assertEqual(self.agent.import_oap(upload, "blue_copy", accept_unknown=True)["id"], "blue_copy")

    def test_audition_export_and_role_agreement_through_agent(self):
        self.agent.create_actor("blue", "Blue", "A blue jacket", str(self.reference))
        receipt = self.agent.export_oap("blue", str(self.home / "blue-audition.oap"), tier="audition")
        self.assertGreater(receipt["bytes"], 0)
        drafted = self.agent.create_agreement("blue", "agent_role", "Neon Rain", "150.00", "USD")
        self.assertFalse(drafted["complete"])
        with self.assertRaisesRegex(ValueError, "authorization"):
            self.agent.sign_agreement("agent_role", "director")
        self.agent.sign_agreement("agent_role", "director", confirm=True)
        self.agent.sign_agreement("agent_role", "agent", confirm=True)
        self.assertTrue(self.agent.verify_agreement("agent_role")["complete"])
        self.assertEqual([x["id"] for x in self.agent.inspect("agreements")], ["agent_role"])
        bundle = self.home / "agreement.zip"
        self.agent.export_agreement("agent_role", str(bundle))
        with zipfile.ZipFile(bundle) as archive:
            signed = self.home / "returned.json"
            signed.write_bytes(archive.read("agreement.json"))
        upload = self.agent.upload("agreement", str(signed))["file"]
        self.assertTrue(self.agent.import_agreement(upload)["complete"])

    def test_cli_json_and_rejected_missing_consent(self):
        env = {**os.environ, "MMV_URL": self.url,
               "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
        result = subprocess.run([sys.executable, "-m", "mmv.agent", "version"], env=env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["version"], "1.12.3")
        result = subprocess.run([sys.executable, "-m", "mmv.agent", "start", "unknown"], env=env,
                                capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("authorization", result.stderr)

    def test_world_editing_previews_then_needs_confirmation_through_client_and_cli(self):
        self.agent.create_world({"id": "salt", "name": "Salt Archive", "core_laws": ["The record outlives the person"]})
        world = self.agent.get_world("salt")
        world["core_laws"] = ["Nothing leaves unfiled"]
        preview = self.agent.preview_world_edit("salt", world)
        self.assertEqual(preview["changes"][0]["added"], ["Nothing leaves unfiled"])
        self.assertEqual(self.agent.get_world("salt")["version"], 1)
        with self.assertRaisesRegex(ValueError, "reviewed the changes"):
            self.agent.edit_world("salt", world)
        with self.assertRaisesRegex(ValueError, "base_version"):
            self.agent.edit_world("salt", {"name": "x"}, confirm=True)
        self.assertEqual(self.agent.edit_world("salt", world, confirm=True)["version"], 2)
        with self.assertRaises(ValueError):
            self.agent.edit_world("salt", world, confirm=True)
        edited = {**self.agent.get_world("salt"), "locations": ["The lamplit registry"]}
        (self.home / "edit.json").write_text(json.dumps(edited))
        env = {**os.environ, "MMV_URL": self.url, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
        run = lambda *args: subprocess.run([sys.executable, "-m", "mmv.agent", *args], env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(json.loads(run("world-edit-preview", "salt", str(self.home / "edit.json")).stdout)["changes"][0]["added"],
                         ["The lamplit registry"])
        refused = run("edit-world", "salt", str(self.home / "edit.json"))
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("reviewed", refused.stderr)
        self.assertEqual(json.loads(run("edit-world", "salt", str(self.home / "edit.json"), "--confirm").stdout)["version"], 3)
        self.assertEqual(self.agent.rollback_world("salt", 1)["version"], 4)

    def test_proxy_environment_is_not_used_for_local_calls(self):
        with patch.dict(os.environ, {"HTTP_PROXY": "http://example.invalid:1", "NO_PROXY": "", "no_proxy": ""}):
            self.assertEqual(AgentClient(self.url).inspect("version")["version"], "1.12.3")

    def test_world_management_guards_and_cli(self):
        ledger = {"id": "salt", "name": "Salt Archive", "core_laws": ["The record outlives the person"],
                  "pools": {"settings": {"include": ["a basement archive"]}}}
        self.assertEqual(self.agent.create_world(ledger)["version"], 1)
        self.assertEqual([w["id"] for w in self.agent.inspect("worlds")], ["salt"])
        self.assertEqual(self.agent.get_world("salt", 1)["name"], "Salt Archive")
        self.assertEqual(self.agent.export_world("salt")["id"], "salt")
        saved = self.agent.export_world("salt", self.home)
        self.assertTrue(Path(saved["saved"]).is_file())
        self.assertEqual(self.agent.world_proposals(), [])
        from mmv import worlds
        proposed = {**worlds.normalize(ledger), "id": "salt", "core_laws": ["Nothing leaves unfiled"]}
        worlds.write_proposal(self.fixture.store, "grow-one", "salt", "grow", 1, proposed, [("lore", "a.md")], {"vision": "m"})
        self.assertEqual(self.agent.world_proposal("grow-one")["changes"][0]["added"], ["Nothing leaves unfiled"])
        with self.assertRaises(ValueError) as refused:
            self.agent.accept_world_proposal("grow-one")
        self.assertIn("reviewed", str(refused.exception))
        self.assertEqual(self.agent.get_world("salt")["version"], 1)
        self.assertEqual(self.agent.accept_world_proposal("grow-one", confirm=True)["version"], 2)
        self.assertEqual(self.agent.rollback_world("salt", 1)["version"], 3)
        self.assertEqual([v["version"] for v in self.agent.world_versions("salt")], [1, 2, 3])
        with self.assertRaises(ValueError):
            self.agent.delete_world("salt")
        env = {**os.environ, "MMV_URL": self.url, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
        run = lambda *args: subprocess.run([sys.executable, "-m", "mmv.agent", *args], env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(json.loads(run("world", "salt", "--version", "2").stdout)["version"], 2)
        self.assertEqual(json.loads(run("world-versions", "salt").stdout)[-1]["version"], 3)
        refused = run("delete-world", "salt")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("authorization", refused.stderr)
        self.assertEqual(json.loads(run("delete-world", "salt", "--confirm").stdout), {"deleted": "salt"})
        (self.home / "a.md").write_bytes(b"The archive never closes.")
        (self.home / "a.mp4").write_bytes(b"x")
        (self.home / "a.exe").write_bytes(b"x")
        with self.assertRaises(ValueError):
            self.agent.upload("video", str(self.home / "a.exe"))
        self.assertEqual(self.agent.upload("video", str(self.home / "a.mp4"))["name"], "media.mp4")
        self.assertEqual(self.agent.upload("lore", str(self.home / "a.md"))["name"], "media.md")

    def test_create_style_and_upload_reference(self):
        style = self.agent.create_style("cool", "Cool", "Cool blue light", style_card="Forensic test card")
        self.assertEqual(style["id"], "cool")
        self.assertEqual(style.get("style_card"), "Forensic test card")
        exported = self.agent.export_style("cool")
        self.assertEqual(exported["id"], "cool")
        self.assertEqual(exported["name"], "Cool")
        self.assertEqual(exported["style_card"], "Forensic test card")

        # Test import without overwrite fails
        with self.assertRaises(ValueError):
            self.agent.import_style("cool", "Cool 2", "Updated light", overwrite=False)

        # Test import with overwrite succeeds
        imported = self.agent.import_style("cool", "Cool 2", "Updated light", overwrite=True)
        self.assertEqual(imported["name"], "Cool 2")

        self.assertTrue(self.agent.upload("reference", str(self.reference))["file"].endswith(".png"))


class ClientBoundaryTests(unittest.TestCase):
    def test_actor_edit_and_panel_setting_use_local_api(self):
        client = AgentClient()
        with patch.object(client, '_json', return_value={'ok': True}) as request:
            client.update_actor('local_actor', 'Green coat')
            request.assert_called_once_with('PATCH', '/api/actors/local_actor', {'description': 'Green coat'})
        with patch.object(client, '_json', return_value={'ok': True}) as request:
            client.update_settings({'auto_collapse_panels': False})
            request.assert_called_once_with('PATCH', '/api/settings', {'auto_collapse_panels': False})
        with patch.object(client, '_json', return_value={'actors': []}) as request:
            client.check_oap_collection()
            request.assert_called_once_with('GET', '/api/oap-collection')
        with patch.object(client, '_json', return_value={'filename': 'checked.oap'}) as request:
            client.stage_oap_collection('human_female_baker_01', 'a' * 64)
            request.assert_called_once_with('POST', '/api/oap-collection/stage',
                                            {'actor_id': 'human_female_baker_01', 'index_sha256': 'a' * 64})

    def test_prompt_retry_preview_uses_quote_route_without_starting(self):
        client = AgentClient()
        with patch.object(client, '_json', return_value={'id': 'fresh-quote'}) as request:
            self.assertEqual(client.preview_retry_prompts('failed-run')['id'], 'fresh-quote')
            request.assert_called_once_with('POST', '/api/retry-prompts/quote', {'run_id': 'failed-run'})

    def test_destructive_actions_and_executable_settings_require_boundaries(self):
        client = AgentClient()
        with patch.object(client, '_json') as request:
            for operation in (lambda: client.delete_actor('example'), lambda: client.delete_style('example'),
                              lambda: client.remove_api_profile('example'),
                              lambda: client.update_settings({'writer_launch': '["arbitrary"]'})):
                with self.assertRaises(ValueError):
                    operation()
            request.assert_not_called()

    def test_remote_or_ambiguous_targets_are_rejected(self):
        for url in ("https://example.com", "http://127.0.0.1.example.com", "http://127.0.0.1/private",
                    "http://user:password@localhost", "file:///tmp/app", "http://localhost:99999",
                    "http://localhost?redirect=https://example.com", "http://localhost/#fragment"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                AgentClient(url)

    def test_non_application_route_is_rejected(self):
        client = AgentClient()
        for route in ("/secrets.json", "https://example.com", "/api/../secrets.json"):
            with self.assertRaises(ValueError):
                client._open("GET", route)


@unittest.skipUnless(importlib.util.find_spec("mcp"), "Install the optional mcp extra to test the MCP transport")
class MCPTests(LiveAppFixture, unittest.TestCase):
    def test_stdio_discovery_and_app_calls(self):
        async def check():
            from mcp import Client, StdioServerParameters
            try:
                from mcp.client.stdio import stdio_client
            except ImportError:
                stdio_client = lambda p: p
            root = str(Path(__file__).resolve().parents[1])
            transport = StdioServerParameters(command=sys.executable, args=["-m", "mmv.mcp_server"],
                                              env={"MMV_URL": self.url, "PYTHONPATH": root})
            async with Client(stdio_client(transport)) as client:
                tools = await client.list_tools()
                names = {tool.name for tool in tools.tools}
                self.assertEqual(len(names), 76)
                self.assertTrue({'check_oap_collection', 'stage_oap_collection', 'oap_recipient_key'} <= names)
                self.assertTrue({'create_role_agreement', 'sign_role_agreement', 'verify_role_agreement',
                    'export_role_agreement', 'import_role_agreement', 'read_music_score', 'read_output_prompts'} <= names)
                self.assertTrue({'detect_lyrics', 'align_lyrics', 'export_production_package'} <= names)
                self.assertIn('inspect_storyboard', names)
                from mmv.storage import write_json
                board_dir = self.home / 'runs' / 'agent-board'
                board_dir.mkdir()
                write_json(board_dir / 'storyboard.json', {'enabled': True, 'mode': 'narrative', 'images': [], 'panels': [{'image': '', 'direction': 'Walk'}]})
                board = await client.call_tool('inspect_storyboard', {'run_id': 'agent-board'})
                self.assertEqual(board.structured_content['panels'][0]['direction'], 'Walk')
                boards = await client.call_tool('inspect_studio', {'kind': 'storyboards'})
                self.assertEqual(boards.structured_content['data'][0]['run_id'], 'agent-board')
                quick = await client.call_tool('inspect_studio', {'kind': 'quick-start'})
                self.assertEqual(quick.structured_content['data']['dance_mode'] in ('off', 'group'), True)
                self.assertIn("preview_resume", names)
                self.assertIn("preview_retry_prompts", names)
                self.assertTrue({"caption_video", "list_caption_fonts"} <= names)
                self.assertNotIn('import_instrument', names)
                self.assertTrue({'inspect_opp', 'import_opp', 'select_opp_sheet'} <= names)
                self.assertTrue({'get_world', 'world_versions', 'create_world', 'export_world', 'rollback_world', 'delete_world',
                                 'inspect_world_proposal', 'accept_world_proposal', 'reject_world_proposal',
                                 'preview_world_edit', 'edit_world'} <= names)
                refused = await client.call_tool('edit_world', {'world_id': 'none', 'world': {'name': 'x'}, 'base_version': 1})
                self.assertTrue(refused.is_error)
                refused = await client.call_tool('accept_world_proposal', {'proposal_id': 'none', 'confirm': False})
                self.assertTrue(refused.is_error)
                refused = await client.call_tool('delete_world', {'world_id': 'none'})
                self.assertTrue(refused.is_error)
                instruments = await client.call_tool('inspect_studio', {'kind': 'instruments'})
                self.assertTrue(next(i for i in instruments.structured_content['data'] if i['id'] == 'guitar')['available'])
                self.assertIn("preview_production", names)
                self.assertTrue({'delete_actor', 'delete_style', 'create_style', 'export_style', 'import_style',
                    'save_vocabulary_preset', 'delete_vocabulary_preset',
                    'add_api_profile', 'remove_api_profile', 'select_api_profile', 'update_studio_settings',
                    'install_starter_assets', 'inspect_api_models'} <= names)
                self.assertNotIn("run_shell", names)
                self.assertNotIn("set_key", names)
                result = await client.call_tool("inspect_studio", {"kind": "version"})
                self.assertFalse(result.is_error)
                self.assertEqual(result.structured_content["data"]["version"], "1.12.3")
                result = await client.call_tool("start_production", {"quote_id": "fabricated", "consent": False})
                self.assertTrue(result.is_error)
                self.assertIn("authorization", result.content[0].text)
                result = await client.call_tool("inspect_studio", {"kind": "settings"})
                self.assertNotIn("secrets.json", json.dumps(result.model_dump()))
        asyncio.run(check())

    def test_mcp_api_profiles_settings_library_and_starters(self):
        async def check():
            import io
            from mcp import Client
            from mmv.mcp_server import create_server
            async with Client(create_server(self.url)) as client:
                with patch.dict(os.environ, {'MCP_TEST_KEY': 'mock-provider-secret'}):
                    result = await client.call_tool('add_api_profile', {'name': 'mcp-provider', 'role': 'writer',
                        'settings': {'writer_url': 'https://provider.example/v1', 'writer_model': 'mock-chat',
                                     'writer_mode': 'api', 'writer_call_estimate': .1}, 'key_env': 'MCP_TEST_KEY'})
                self.assertFalse(result.is_error, result)
                self.assertNotIn('mock-provider-secret', json.dumps(result.model_dump()))
                self.assertTrue(result.structured_content['key_configured'])
                result = await client.call_tool('select_api_profile', {'name': 'mcp-provider'})
                self.assertFalse(result.is_error, result)
                self.assertEqual(self.fixture.store.settings()['writer_model'], 'mock-chat')
                result = await client.call_tool('remove_api_profile', {'name': 'mcp-provider'})
                self.assertTrue(result.is_error)
                self.assertEqual(self.fixture.store.key('MMV_WRITER_API_KEY'), 'mock-provider-secret')
                result = await client.call_tool('remove_api_profile', {'name': 'mcp-provider', 'confirm': True})
                self.assertFalse(result.is_error, result)
                self.assertTrue(result.structured_content['manual_restored'])
                self.assertEqual(self.fixture.store.settings()['writer_model'], 'fixture-writer')
                result = await client.call_tool('update_studio_settings', {'changes': {'auto_updates': True, 'laya_device': 'cpu'}})
                self.assertFalse(result.is_error, result)
                self.assertTrue(self.fixture.store.settings()['auto_updates'])
                result = await client.call_tool('update_studio_settings', {'changes': {'writer_launch': '["forbidden"]'}})
                self.assertTrue(result.is_error)
                result = await client.call_tool('inspect_studio', {'kind': 'update'})
                self.assertFalse(result.is_error, result)
                with patch('mmv.provider_setup.urllib.request.build_opener') as opener:
                    opener.return_value.open.return_value = io.BytesIO(b'{"data":[{"id":"mock-chat"}]}')
                    result = await client.call_tool('inspect_api_models', {'url': 'https://provider.example/v1'})
                self.assertFalse(result.is_error, result)
                self.assertFalse(result.structured_content['generation_submitted'])
                result = await client.call_tool('create_style', {'style_id': 'remove-me', 'name': 'Temporary', 'direction': 'Daylight'})
                self.assertFalse(result.is_error, result)
                result = await client.call_tool('delete_style', {'style_id': 'remove-me'})
                self.assertTrue(result.is_error)
                result = await client.call_tool('delete_style', {'style_id': 'remove-me', 'confirm': True})
                self.assertFalse(result.is_error, result)
                result = await client.call_tool('save_vocabulary_preset', {
                    'vocab_id': 'test_mcp_preset', 'name': 'MCP Preset',
                    'tables': {'lighting': {'mode': 'replace', 'add': ['mcp_neon']}}
                })
                self.assertFalse(result.is_error, result)
                result = await client.call_tool('inspect_studio', {'kind': 'vocabularies'})
                self.assertFalse(result.is_error, result)
                self.assertTrue(any(p['id'] == 'test_mcp_preset' for p in result.structured_content['data']))
                result = await client.call_tool('delete_vocabulary_preset', {'vocab_id': 'test_mcp_preset'})
                self.assertTrue(result.is_error)
                result = await client.call_tool('delete_vocabulary_preset', {'vocab_id': 'test_mcp_preset', 'confirm': True})
                self.assertFalse(result.is_error, result)
                result = await client.call_tool('install_starter_assets', {})
                self.assertFalse(result.is_error, result)
                self.assertEqual(len(result.structured_content['pending_signer']), 4)
                result = await client.call_tool('install_starter_assets', {'accept_starter_signer': True})
                self.assertFalse(result.is_error, result)
                self.assertEqual(len(result.structured_content['installed']), 4)
                result = await client.call_tool('delete_actor', {'actor_id': 'animal_pig'})
                self.assertTrue(result.is_error)
                result = await client.call_tool('delete_actor', {'actor_id': 'animal_pig', 'confirm': True})
                self.assertFalse(result.is_error, result)
                self.assertFalse(self.fixture.store.actor('animal_pig'))
                result = await client.call_tool('install_starter_assets', {'accept_starter_signer': True})
                self.assertIn('actors/animal_pig', result.structured_content['removed'])
                result = await client.call_tool('install_starter_assets', {'accept_starter_signer': True, 'restore_removed': True})
                self.assertFalse(result.is_error, result)
                self.assertTrue(self.fixture.store.actor('animal_pig'))
        asyncio.run(check())

    def test_mcp_preview_start_flow(self):
        async def check():
            from mcp import Client
            from mmv.mcp_server import create_server
            async with Client(create_server(self.url)) as client:
                upload = await client.call_tool("upload_media", {"kind": "song", "path": str(self.song)})
                self.assertFalse(upload.is_error)
                song = upload.structured_content["file"]
                independent = await client.call_tool("preview_production", {"request": {"song": song, "dance_mode": "independent", "dance_parts": {}}})
                self.assertFalse(independent.is_error)
                self.assertEqual(independent.structured_content["dance"]["mode"], "independent")
                preview = await client.call_tool("preview_production", {"request": {"song": song, "direction": "Waves"}})
                self.assertFalse(preview.is_error)
                started = await client.call_tool("start_production", {"quote_id": preview.structured_content["id"], "consent": True})
                self.assertFalse(started.is_error)
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    status = await client.call_tool("inspect_studio", {"kind": "status"})
                    state = status.structured_content["data"]["state"]
                    if state not in ("running", "cancelling"):
                        break
                    await asyncio.sleep(.05)
                self.assertEqual(state, "complete", status)
        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
