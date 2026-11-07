"""OAP 0.5 actor packages: plain, sealed, attested and revoked. Temporary data only."""
import io
import json
import os
from pathlib import Path

import oap
import pytest
from PIL import Image

from mmv import actors
from mmv.storage import Storage


def picture():
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), "red").save(buffer, "PNG")
    return buffer.getvalue()


def package(tmp_path, *, clearance="public", tier="portfolio", recipients=None, identity=None, name="red.oap", **extra):
    identity = identity or oap.generate_identity()
    manifest = oap.new_manifest("red", "Red")
    manifest["identity"]["did"] = identity["did"] + "#red"
    manifest["agent"].update(name="Outside Agency", public_key=identity["public_key"])
    manifest["visual"]["sheets"] = [{"file": "identity/red.png", "clearance": clearance,
                                     "sha256": None, "role": "reference_sheet"}]
    stage = tmp_path / ("stage-" + name)
    (stage / "identity").mkdir(parents=True)
    (stage / "identity/red.png").write_bytes(picture())
    (stage / "manifest.json").write_text(json.dumps(manifest))
    output = tmp_path / name
    oap.package_actor(str(stage), str(output), tier=tier, sign_key=identity["_private"],
                      recipient_public_keys=recipients, **extra)
    return output, identity


def imported_image(store):
    return (store.home / "actors/red/reference.png").is_file()


def test_plain_package_imports_after_signer_acceptance(tmp_path):
    store = Storage(tmp_path / "studio")
    path, identity = package(tmp_path)
    manifest, verification = actors.package_info(path)
    assert manifest["oap_version"] == "0.5.0" and verification["signature_valid"] and verification["ok"]
    with pytest.raises(ValueError, match="explicitly accept"):
        actors.import_actor(store, path, "red")
    record = actors.import_actor(store, path, "red", accept_unknown=True)
    assert record["oap"]["signer"] == identity["public_key"] and imported_image(store)


def test_package_sealed_to_this_studio_imports(tmp_path):
    store = Storage(tmp_path / "studio")
    key = actors.recipient_identity(store)
    assert actors.recipient_identity(store) == key
    path, _ = package(tmp_path, clearance="cast", tier="full", recipients=[key["public_key"]])
    actors.import_actor(store, path, "red", accept_unknown=True)
    assert imported_image(store)
    assert (store.home / "actors/red/original.oap").read_bytes() == path.read_bytes()


def test_package_sealed_to_someone_else_names_this_studios_key(tmp_path):
    store = Storage(tmp_path / "studio")
    other = oap.generate_recipient_identity()
    path, _ = package(tmp_path, clearance="cast", tier="full", recipients=[other["public_key"]])
    assert actors.package_info(path)[1]["ok"]
    with pytest.raises(ValueError, match=actors.recipient_identity(store)["public_key"]):
        actors.import_actor(store, path, "red", accept_unknown=True)
    assert not imported_image(store)


def test_tampered_package_is_refused(tmp_path):
    import zipfile
    path, _ = package(tmp_path)
    forged = tmp_path / "forged.oap"
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(forged, "w") as sink:
        for name in source.namelist():
            sink.writestr(name, source.read(name) + (b"x" if name.endswith(".png") else b""))
    with pytest.raises(ValueError, match="verification failed"):
        actors.package_info(forged)


def test_unknown_attestation_issuer_does_not_block_an_actor(tmp_path):
    store = Storage(tmp_path / "studio")
    issuer = oap.generate_identity()
    document = tmp_path / "attestation.json"
    document.write_text(json.dumps(oap.create_attestation("red", {"representation": "demo"}, issuer["_private"])))
    path, _ = package(tmp_path, attestations=[str(document)])
    assert actors.package_info(path)[1]["ok"]
    actors.import_actor(store, path, "red", accept_unknown=True)
    assert imported_image(store)


def test_package_whose_signer_revoked_their_key_is_refused(tmp_path):
    identity = oap.generate_identity()
    entry = oap.create_revocation_entry(oap.calculate_key_id(identity["public_key"]), "agent_signing",
                                        "compromised", identity["_private"])
    document = tmp_path / "list.json"
    document.write_text(json.dumps(oap.create_revocation_list("urn:oap:revocation:list:test", [entry], identity["_private"])))
    path, _ = package(tmp_path, identity=identity, revocation_metadata={"lists": [str(document)]})
    with pytest.raises(ValueError, match="verification failed"):
        actors.package_info(path)


def test_older_packages_still_import(tmp_path):
    store = Storage(tmp_path / "studio")
    source = Path(__file__).resolve().parents[1] / "examples/starter-cast/animal_pig.oap"
    manifest, verification = actors.package_info(source)
    assert manifest["oap_version"] == "0.2.0" and verification["signature_valid"]
    actors.import_actor(store, source, "animal_pig", accept_unknown=True)
    assert (store.home / "actors/animal_pig/reference.png").is_file()


def test_private_recipient_key_is_not_world_readable(tmp_path):
    store = Storage(tmp_path / "studio")
    actors.recipient_identity(store)
    if os.name != "nt":
        assert (store.home / "recipient-identity.json").stat().st_mode & 0o077 == 0


def test_concurrent_first_callers_get_one_recipient_key(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    store = Storage(tmp_path / "studio")
    with ThreadPoolExecutor(8) as pool:
        keys = list(pool.map(lambda _: actors.recipient_identity(store)["public_key"], range(32)))
    assert len(set(keys)) == 1
    assert [p.name for p in store.home.glob("recipient-identity.json*")] == ["recipient-identity.json"]
