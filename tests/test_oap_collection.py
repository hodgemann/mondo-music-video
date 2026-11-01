"""Public OAP collection checks use mock transport and temporary studio data."""
import hashlib
import io
import json
from pathlib import Path

import pytest

from mmv import actors, oap_collection
from mmv.storage import Storage


class FakeOpener:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def open(self, request, timeout):
        self.calls.append(request.full_url)
        return io.BytesIO(self.responses[request.full_url])


def fixture_collection(tmp_path):
    package = Path(__file__).resolve().parents[1] / "examples/starter-cast/animal_pig.oap"
    content = package.read_bytes()
    manifest, _ = actors.package_info(package)
    index = {"kind": "oap.actor_collection", "source": oap_collection.SOURCE,
             "license": "CC-BY-4.0", "attribution": "Maximum Goose Laboratory",
             "actors": [{"id": "animal_pig", "name": "Hambo", "file": "actors/animal_pig.oap",
                         "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(),
                         "oap_version": "0.2.0", "signer": {"public_key": manifest["agent"]["public_key"]}}]}
    raw = json.dumps(index).encode()
    opener = FakeOpener({oap_collection.RAW + "/index.json": raw,
                         oap_collection.RAW + "/actors/animal_pig.oap": content})
    return Storage(tmp_path / "studio"), opener


def test_check_stage_and_explicit_signer_acceptance(tmp_path):
    store, opener = fixture_collection(tmp_path)
    checked = oap_collection.check(store, opener=opener)
    assert checked["actors"][0]["installed"] is False
    assert checked["actors"][0]["oap_version"] == "0.2.0"
    assert opener.calls == [oap_collection.RAW + "/index.json"]
    staged = oap_collection.stage(store, "animal_pig", checked["index_sha256"], opener=opener)
    assert staged["verification"]["signature_valid"] is True
    assert staged["manifest"]["identity"]["actor_id"] == "animal_pig"
    path = store.home / "uploads" / staged["filename"]
    assert path.is_file()
    with pytest.raises(ValueError, match="explicitly accept"):
        actors.import_actor(store, path, "animal_pig")
    actors.import_actor(store, path, "animal_pig", accept_unknown=True)
    assert oap_collection.check(store, opener=opener)["actors"][0]["installed"] is True
    with pytest.raises(ValueError, match="already exists"):
        oap_collection.stage(store, "animal_pig", checked["index_sha256"], opener=opener)


def test_changed_index_and_bad_package_leave_no_staged_upload(tmp_path):
    store, opener = fixture_collection(tmp_path)
    with pytest.raises(ValueError, match="changed"):
        oap_collection.stage(store, "animal_pig", "0" * 64, opener=opener)
    checked = oap_collection.check(store, opener=opener)
    opener.responses[oap_collection.RAW + "/actors/animal_pig.oap"] = b"wrong package"
    with pytest.raises(ValueError, match="checksum or size"):
        oap_collection.stage(store, "animal_pig", checked["index_sha256"], opener=opener)
    assert not list((store.home / "uploads").iterdir())


def test_collection_index_rejects_unsafe_paths(tmp_path):
    store, opener = fixture_collection(tmp_path)
    data = json.loads(opener.responses[oap_collection.RAW + "/index.json"])
    data["actors"][0]["file"] = "../private/actor.oap"
    opener.responses[oap_collection.RAW + "/index.json"] = json.dumps(data).encode()
    with pytest.raises(ValueError, match="unsafe actor paths"):
        oap_collection.check(store, opener=opener)


def test_future_protocol_version_does_not_break_the_index(tmp_path):
    store, opener = fixture_collection(tmp_path)
    url = oap_collection.RAW + "/index.json"
    index = json.loads(opener.responses[url])
    index["actors"][0]["oap_version"] = "0.5.0"
    opener.responses[url] = json.dumps(index).encode()
    checked = oap_collection.check(store, opener=opener)
    assert checked["actors"][0]["oap_version"] == "0.5.0"
    with pytest.raises(ValueError, match="does not match the checked index"):
        oap_collection.stage(store, "animal_pig", checked["index_sha256"], opener=opener)
