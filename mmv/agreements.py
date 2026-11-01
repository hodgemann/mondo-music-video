"""OAP role agreements: this studio casts as Director; Agents countersign.

Each agreement stores the exact actor manifest and casting call it is bound to.
Signature validity is reported separately from signer trust, which the operator
must still confirm. Agreements never approve rider exceptions or move money.
"""
from __future__ import annotations

import copy
import json
import tempfile
import uuid
import zipfile
from pathlib import Path

import oap

from . import actors
from .storage import identifier, read_json, write_json

MAX_AGREEMENT_BYTES = 2 * 1024 * 1024
ROLES = ("agent", "director")


def _identity(store, name):
    path = store.home / name
    identity = read_json(path)
    if identity is None:
        identity = oap.generate_identity()
        if not identity.get("_private"):
            raise ValueError("OAP signing requires cryptography")
        write_json(path, identity, private=True)
    return identity


def director_identity(store):
    # Kept apart from the export signing identity: OAP requires distinct party keys.
    return _identity(store, "director-identity.json")


def _did(identity):
    return "oap:ed25519:" + identity["public_key"]


def _directory(store, agreement_id):
    return store.home / "agreements" / identifier(agreement_id)


def _load(store, agreement_id):
    directory = _directory(store, agreement_id)
    agreement = read_json(directory / "agreement.json")
    if agreement is None:
        raise ValueError("Agreement not found")
    sources = [read_json(directory / name) for name in ("manifest.json", "casting_call.json")]
    # OAP treats an absent source as "not supplied" and skips its binding, so fail closed here.
    if not all(isinstance(source, dict) for source in sources):
        raise ValueError("Agreement source documents are missing or damaged; it cannot be verified or signed")
    return (directory, agreement, *sources)


def _actor_manifest(store, actor_id):
    """Return the signed manifest the Agent published, or a fresh signed local export."""
    record = store.actor(actor_id)
    if not record:
        raise ValueError("Actor not found")
    original = store.home / "actors" / identifier(actor_id) / "original.oap"
    if original.exists():
        manifest, verification = actors.package_info(original)
    else:
        package = actors.export_actor(store, actor_id)
        try:
            manifest, verification = actors.package_info(package)
        finally:
            package.unlink(missing_ok=True)
    if not verification.get("signature_valid"):
        raise ValueError("Role agreements require an actor package with a valid Agent signature")
    return record, manifest


def summary(store, agreement_id):
    _, agreement, manifest, call = _load(store, agreement_id)
    result = oap.verify_agreement(agreement, require_both=False, manifest=manifest, casting_call=call)
    local_agent = read_json(store.home / "signing-identity.json")
    return {"id": agreement["agreement_id"], "actor_id": agreement.get("mmv_actor_id"),
            "title": call["project"].get("title"), "character": call["role"].get("character_name"),
            "compensation": agreement["accepted_compensation"], "call_id": agreement["call_id"],
            "actor_did": agreement["actor_did"], "agent_did": agreement["agent_did"],
            "director_did": agreement["director_did"], "created_at": agreement["created_at"],
            "signed": sorted(agreement["signatures"]), "signatures_valid": result["signatures_valid"],
            "complete": result["complete"] and result["ok"], "issues": result["issues"],
            "local_agent": bool(local_agent) and agreement["agent_did"] == _did(local_agent)}


def list_agreements(store):
    result = []
    for path in sorted((store.home / "agreements").glob("*/agreement.json")):
        try:
            result.append(summary(store, path.parent.name))
        except ValueError as exc:
            # Keep damaged records visible without letting one hide the others.
            result.append({"id": path.parent.name, "damaged": True, "complete": False, "signed": [],
                           "issues": [str(exc)], "compensation": {}, "local_agent": False})
    return result


def create_agreement(store, actor_id, agreement_id, *, title, character="", role_description="",
                     content=None, offer, currency, notes="", director_name="Mondo Music Video"):
    agreement_id = identifier(agreement_id)
    target = _directory(store, agreement_id)
    if target.exists():
        raise ValueError("Agreement already exists; choose a different ID")
    record, manifest = _actor_manifest(store, actor_id)
    director = director_identity(store)
    call = {"oap_version": oap.OAP_VERSION, "kind": "oap.casting_call", "call_id": "call_" + agreement_id,
            "director": {"name": director_name, "did": _did(director)},
            "project": {"title": title, "synopsis": None, "intent": "music_video",
                        "content": dict(content or {key: "none" for key in oap.CONTENT_ENUMS}),
                        "commercial_category": None, "brand": None},
            "role": {"character_name": character or record["name"], "description": role_description or None,
                     "wardrobe_requirement": None, "requires_wardrobe_change": False,
                     "voice_required": False, "audition_side": None},
            "compensation": {"offer": offer, "currency": currency, "notes": notes},
            "deadline": None, "submission_endpoint": None}
    validation = oap.validate_document(call)
    if not validation["ok"]:
        raise ValueError("Casting call is invalid: " + "; ".join(validation["issues"]))
    compatibility = oap.check_call(manifest, call)
    if not compatibility["compatible"]:
        raise ValueError("Actor rider conflicts with this role: " + "; ".join(compatibility["conflicts"]))
    agreement = oap.new_role_agreement(manifest, call, {"amount": offer, "currency": currency}, agreement_id)
    # Unknown extension keys are signed with the body, so record the local actor link now.
    agreement["mmv_actor_id"] = record["id"]
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as temp:
        stage = Path(temp)
        write_json(stage / "manifest.json", manifest)
        write_json(stage / "casting_call.json", call)
        write_json(stage / "agreement.json", agreement)
        stage.rename(target)
    return summary(store, agreement_id)


def sign(store, agreement_id, role):
    if role not in ROLES:
        raise ValueError("Role must be agent or director")
    directory, agreement, manifest, call = _load(store, agreement_id)
    if role in agreement["signatures"]:
        raise ValueError("This party has already signed")
    identity = director_identity(store) if role == "director" else read_json(store.home / "signing-identity.json")
    if not identity or agreement[role + "_did"] != _did(identity):
        raise ValueError("This studio does not hold the " + role + " key. Send the agreement bundle "
                         "to that party to countersign, then import their signed agreement.")
    signed = oap.sign_agreement(agreement, role, identity["_private"], manifest=manifest, casting_call=call)
    write_json(directory / "agreement.json", signed)
    return summary(store, agreement_id)


def verify(store, agreement_id):
    _, agreement, manifest, call = _load(store, agreement_id)
    result = oap.verify_agreement(agreement, manifest=manifest, casting_call=call)
    # OAP's "complete" covers signatures only; source-binding failures must also count.
    return dict(result, complete=result["complete"] and result["ok"], id=agreement["agreement_id"],
                note="Signatures prove these keys signed this exact record. Confirm the keys belong "
                     "to the intended parties; this does not approve rider exceptions or payment.")


def bundle(store, agreement_id):
    """Zip the agreement with its exact sources so the other party can verify and countersign."""
    directory, agreement, _, _ = _load(store, agreement_id)
    output = store.home / "exports" / (agreement["agreement_id"] + "-" + uuid.uuid4().hex + ".zip")
    with zipfile.ZipFile(output, "x", zipfile.ZIP_DEFLATED) as archive:
        for name in ("agreement.json", "manifest.json", "casting_call.json"):
            archive.write(directory / name, name)
    return output


def import_signed(store, path):
    """Merge valid signatures from a returned copy of an agreement this studio created."""
    if path.stat().st_size > MAX_AGREEMENT_BYTES:
        raise ValueError("Agreement file is too large")
    try:
        incoming = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Agreement file is not valid JSON") from exc
    if not isinstance(incoming, dict) or not isinstance(incoming.get("agreement_id"), str):
        raise ValueError("Not an OAP role agreement")
    directory, agreement, manifest, call = _load(store, incoming["agreement_id"])
    body = lambda value: {key: item for key, item in value.items() if key != "signatures"}
    if body(incoming) != body(agreement):
        raise ValueError("Returned agreement differs from the stored draft; terms must not change after creation")
    checked = oap.verify_agreement(incoming, require_both=False, manifest=manifest, casting_call=call)
    if not checked["ok"]:
        raise ValueError("Returned agreement failed verification: " + "; ".join(checked["issues"]))
    merged = copy.deepcopy(agreement)
    merged["signatures"].update({role: incoming["signatures"][role] for role in ROLES
                                 if checked["signatures_valid"][role]})
    write_json(directory / "agreement.json", merged)
    return summary(store, agreement["agreement_id"])
