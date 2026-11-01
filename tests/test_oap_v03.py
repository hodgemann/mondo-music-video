"""OAP integration: schema validation, audition exports and role agreements."""
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import oap

from mmv import actors
import test_public_app as public_fixtures
from test_public_app import picture


class OAPv03Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        public_fixtures.PublicAppTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        public_fixtures.PublicAppTests.tearDownClass()

    def setUp(self):
        self.fixture = public_fixtures.PublicAppTests("test_version_matches_package_and_readme")
        self.fixture.setUp()
        self.client, self.store, self.home = self.fixture.client, self.fixture.store, self.fixture.home

    def tearDown(self):
        self.fixture.tearDown()

    def create_local_actor(self, actor_id="blue"):
        self.client.post("/api/actors", data={"actor_id": actor_id, "name": "Blue", "description": "Blue jacket"},
                         files={"reference": ("ref.png", picture())}).raise_for_status()

    def import_external_actor(self, rider=None):
        """Import an actor signed by an outside Agent key; return that key."""
        identity = oap.generate_identity()
        manifest = oap.new_manifest("red", "Red")
        manifest["identity"]["did"] = identity["did"] + "#red"
        manifest["agent"].update(name="Outside Agency", public_key=identity["public_key"])
        manifest["rider"].update(rider or {})
        manifest["visual"]["sheets"] = [{"file": "identity/red.png", "clearance": "public",
                                         "sha256": None, "role": "reference_sheet"}]
        with tempfile.TemporaryDirectory() as temp:
            stage = Path(temp)
            (stage / "identity").mkdir()
            (stage / "identity/red.png").write_bytes(picture())
            (stage / "manifest.json").write_text(json.dumps(manifest))
            output = stage / "red.oap"
            oap.package_actor(str(stage), str(output), tier="portfolio", sign_key=identity["_private"])
            uploaded = self.client.post("/api/upload/oap", files={"file": ("red.oap", output.read_bytes())}).json()["file"]
        self.client.post("/api/oap/import", data={"filename": uploaded, "accept_unknown": "true"}).raise_for_status()
        return identity

    def agreement(self, actor_id, agreement_id="role_001", **changes):
        body = {"actor_id": actor_id, "agreement_id": agreement_id, "title": "Neon Rain",
                "character": "Lead", "offer": "150.00", "currency": "USD", **changes}
        return self.client.post("/api/agreements", json=body)

    def test_audition_export_omits_cast_assets_and_keeps_hashes(self):
        self.create_local_actor()
        full = self.client.post("/api/actors/blue/export")
        audition = self.client.post("/api/actors/blue/export", params={"tier": "audition"})
        cleared = self.client.post("/api/actors/blue/export",
                                   params={"tier": "audition", "reference_clearance": "audition"})
        for response in (full, audition, cleared):
            response.raise_for_status()
        self.assertIn("blue-audition.oap", audition.headers["content-disposition"])
        with zipfile.ZipFile(io.BytesIO(audition.content)) as archive:
            self.assertNotIn("identity/reference.png", archive.namelist())
            manifest = json.loads(archive.read("manifest.json"))
        self.assertEqual(manifest["oap_version"], "0.5.0")
        sheet = manifest["visual"]["sheets"][0]
        self.assertEqual(sheet["clearance"], "cast")
        self.assertIsNone(sheet["sha256"])
        with zipfile.ZipFile(io.BytesIO(cleared.content)) as archive:
            self.assertIn("identity/reference.png", archive.namelist())
        path = self.home / "audition.oap"
        path.write_bytes(audition.content)
        self.assertTrue(oap.verify_package(str(path), allow_untrusted=True)["ok"])
        with self.assertRaisesRegex(ValueError, "No reference sheet"):
            actors.import_actor(self.store, path, "blue_audition", accept_unknown=True)
        self.assertEqual(self.client.post("/api/actors/blue/export", params={"tier": "portfolio"}).status_code, 422)

    def test_imported_actor_cannot_be_reexported_as_audition(self):
        self.import_external_actor()
        response = self.client.post("/api/actors/red/export", params={"tier": "audition"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Agent", response.json()["detail"])

    def test_schema_invalid_manifest_rejected_with_path(self):
        self.create_local_actor()
        source = actors.export_actor(self.store, "blue")
        broken = self.home / "broken.oap"
        with zipfile.ZipFile(source) as archive, zipfile.ZipFile(broken, "w") as target:
            for member in archive.infolist():
                data = archive.read(member)
                if member.filename == "manifest.json":
                    manifest = json.loads(data)
                    manifest["rider"]["content"]["violence"] = "unrestricted"
                    data = json.dumps(manifest).encode()
                target.writestr(member, data)
        with self.assertRaisesRegex(ValueError, r"schema validation: \$\.rider"):
            actors.package_info(broken, allow_unsigned=True)

    def test_local_actor_agreement_signed_by_both_roles(self):
        self.create_local_actor()
        created = self.agreement("blue")
        created.raise_for_status()
        summary = created.json()
        self.assertTrue(summary["local_agent"])
        self.assertFalse(summary["complete"])
        self.assertNotEqual(summary["agent_did"], summary["director_did"])
        self.assertFalse(self.client.get("/api/agreements/role_001/verify").json()["ok"])
        self.assertEqual(self.agreement("blue").status_code, 400)
        for role in ("director", "agent"):
            self.client.post("/api/agreements/role_001/sign", json={"role": role}).raise_for_status()
        self.assertEqual(self.client.post("/api/agreements/role_001/sign", json={"role": "agent"}).status_code, 400)
        verified = self.client.get("/api/agreements/role_001/verify").json()
        self.assertTrue(verified["ok"] and verified["complete"], verified)
        listed = self.client.get("/api/agreements").json()
        self.assertEqual([(x["id"], x["actor_id"], x["complete"]) for x in listed], [("role_001", "blue", True)])
        bundle = self.client.post("/api/agreements/role_001/bundle")
        with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
            documents = {name: json.loads(archive.read(name)) for name in archive.namelist()}
        self.assertEqual(set(documents), {"agreement.json", "manifest.json", "casting_call.json"})
        self.assertEqual(documents["casting_call.json"]["project"]["intent"], "music_video")
        self.assertTrue(oap.verify_agreement(documents["agreement.json"], manifest=documents["manifest.json"],
                                             casting_call=documents["casting_call.json"])["complete"])

    def test_missing_agreement_sources_fail_closed(self):
        self.create_local_actor()
        self.agreement("blue").raise_for_status()
        for role in ("director", "agent"):
            self.client.post("/api/agreements/role_001/sign", json={"role": role}).raise_for_status()
        directory = self.home / "agreements" / "role_001"
        for name in ("manifest.json", "casting_call.json"):
            saved = (directory / name).read_bytes()
            (directory / name).unlink()
            response = self.client.get("/api/agreements/role_001/verify")
            self.assertEqual(response.status_code, 400, name)
            self.assertIn("missing or damaged", response.json()["detail"])
            listed = self.client.get("/api/agreements").json()
            self.assertTrue(listed[0]["damaged"] and not listed[0]["complete"])
            (directory / name).write_text("[]")
            self.assertEqual(self.client.get("/api/agreements/role_001/verify").status_code, 400, name)
            (directory / name).write_bytes(saved)
        self.assertTrue(self.client.get("/api/agreements/role_001/verify").json()["complete"])
        for name, change in (("casting_call.json", ("project", "title")), ("manifest.json", ("visual", "core_identity"))):
            path = directory / name
            saved = path.read_bytes()
            document = json.loads(saved)
            document[change[0]][change[1]] = "Substituted"
            path.write_text(json.dumps(document))
            verified = self.client.get("/api/agreements/role_001/verify").json()
            self.assertFalse(verified["ok"] or verified["complete"], name)
            self.assertFalse(self.client.get("/api/agreements").json()[0]["complete"], name)
            path.write_bytes(saved)

    def test_external_agent_countersigns_returned_agreement(self):
        agent = self.import_external_actor()
        self.agreement("red").raise_for_status()
        refused = self.client.post("/api/agreements/role_001/sign", json={"role": "agent"})
        self.assertEqual(refused.status_code, 400)
        self.assertIn("does not hold the agent key", refused.json()["detail"])
        self.client.post("/api/agreements/role_001/sign", json={"role": "director"}).raise_for_status()
        with zipfile.ZipFile(io.BytesIO(self.client.post("/api/agreements/role_001/bundle").content)) as archive:
            documents = {name: json.loads(archive.read(name)) for name in archive.namelist()}
        countersigned = oap.sign_agreement(documents["agreement.json"], "agent", agent["_private"],
                                           manifest=documents["manifest.json"],
                                           casting_call=documents["casting_call.json"])

        def upload(value):
            data = json.dumps(value).encode()
            return self.client.post("/api/upload/agreement", files={"file": ("signed.json", data)}).json()["file"]

        altered = dict(countersigned, accepted_compensation={"amount": "1.00", "currency": "USD"})
        response = self.client.post("/api/agreements/import", data={"filename": upload(altered)})
        self.assertEqual(response.status_code, 400)
        self.assertIn("differs", response.json()["detail"])
        forged = json.loads(json.dumps(countersigned))
        forged["signatures"]["agent"]["value"] = forged["signatures"]["director"]["value"]
        self.assertEqual(self.client.post("/api/agreements/import", data={"filename": upload(forged)}).status_code, 400)
        imported = self.client.post("/api/agreements/import", data={"filename": upload(countersigned)})
        imported.raise_for_status()
        self.assertTrue(imported.json()["complete"])
        self.assertFalse(imported.json()["local_agent"])
        self.assertTrue(self.client.get("/api/agreements/role_001/verify").json()["complete"])

    def test_agreement_refuses_rider_conflicts_and_bad_terms(self):
        self.import_external_actor()
        content = {key: "none" for key in oap.CONTENT_ENUMS}
        content["violence"] = "graphic"
        response = self.agreement("red", content=content)
        self.assertEqual(response.status_code, 400)
        self.assertIn("rider", response.json()["detail"])
        self.assertEqual(self.agreement("red", offer="free").status_code, 422)
        self.assertEqual(self.agreement("missing").status_code, 400)
        self.assertEqual(self.client.get("/api/agreements").json(), [])


if __name__ == "__main__":
    unittest.main()
