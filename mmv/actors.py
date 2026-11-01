"""Visual actors and a thin adapter to the upstream Open Actor Protocol."""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath

import oap
from PIL import Image, ImageOps

from .storage import identifier, inside, read_json, write_json

MAX_PACKAGE_BYTES = 128 * 1024 * 1024


def clean_image(data: bytes, destination: Path):
    if len(data) > 25 * 1024 * 1024:
        raise ValueError("Reference images must be under 25 MB")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > 40_000_000:
                raise ValueError("Reference image exceeds 40 megapixels")
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((4096, 4096))
            clean = Image.new("RGB", image.size)
            clean.paste(image)
            clean.save(destination, "PNG")
    except (OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Not a supported reference image") from exc


def create_actor(store, actor_id, name, description, image_data):
    actor_id = identifier(actor_id)
    target = store.home / "actors" / actor_id
    if target.exists():
        raise ValueError("Actor already exists; choose a different ID")
    with tempfile.TemporaryDirectory(dir=target.parent) as temp:
        stage = Path(temp)
        clean_image(image_data, stage / "reference.png")
        record = {"id": actor_id, "name": name or actor_id, "description": description,
                  "reference": "reference.png", "rider": oap.new_manifest(actor_id)["rider"]}
        write_json(stage / "actor.json", record)
        stage.rename(target)
    return record


def recipient_identity(store):
    """This studio's X25519 key: Agents seal cast-cleared packages to its public half."""
    key_path = store.home / "recipient-identity.json"
    identity = read_json(key_path)
    if identity is not None:
        return identity
    # Publish with a hard link so a concurrent first caller cannot replace a key already handed out.
    stage = key_path.with_name(key_path.name + "." + uuid.uuid4().hex)
    write_json(stage, oap.generate_recipient_identity(), private=True)
    try:
        os.link(stage, key_path)
    except FileExistsError:
        pass
    finally:
        stage.unlink()
    return read_json(key_path)


def _verify(path, manifest, allow_unsigned):
    """Check a package by its own protocol version; signer acceptance stays a separate step.

    Attestations are not used by the studio and no issuers are configured, so an
    attestation from an unknown issuer does not block an actor. Revocation lists a
    package carries are always checked.
    """
    if re.fullmatch(r"0\.[0-3]\.[0-9]+", str(manifest.get("oap_version"))):
        return oap.verify_package(str(path), require_signature=not allow_unsigned,
                                  strict=True, known_agents=[], legacy=True)
    return oap.verify_package(str(path), allow_untrusted=True, attestation_policy="ignore",
                              allow_legacy_manifest=str(manifest.get("oap_version")).startswith("0.4."))


def package_info(path, *, allow_unsigned=False):
    if path.stat().st_size > MAX_PACKAGE_BYTES:
        raise ValueError("OAP package exceeds 128 MB")
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if len(members) > 512 or sum(x.file_size for x in members) > MAX_PACKAGE_BYTES:
                raise ValueError("OAP package has too many assets or exceeds expanded size limit")
            seen = set()
            for member in members:
                name = member.filename
                if (name in seen or "\\" in name or ":" in name or
                    PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts or
                    ((member.external_attr >> 16) & 0o170000) == 0o120000):
                    raise ValueError("OAP package contains duplicate or unsafe paths")
                seen.add(name)
            if archive.getinfo("manifest.json").file_size > 2 * 1024 * 1024:
                raise ValueError("OAP manifest is too large")
            manifest = json.loads(archive.read("manifest.json"))
        if not isinstance(manifest, dict):
            raise ValueError("OAP manifest must be an object")
        # Bundled offline schemas accept every manifest version and unknown extension keys.
        validation = oap.validate_document(manifest)
        if not validation["ok"]:
            raise ValueError("OAP manifest failed schema validation: " + "; ".join(validation["issues"][:10]))
        if any(not isinstance(manifest.get(name, {}), dict) for name in ("identity", "visual", "agent", "rider")):
            raise ValueError("Invalid OAP identity, visual, agent or rider record")
        visual = manifest.get("visual", {})
        if not isinstance(visual.get("sheets", []), list) or any(
                not isinstance(sheet, dict) or not isinstance(sheet.get("file"), str)
                for sheet in visual.get("sheets", [])):
            raise ValueError("Invalid OAP reference sheet list")
        if not isinstance(visual.get("core_identity", ""), str):
            raise ValueError("OAP core identity must be text")
        verification = _verify(path, manifest, allow_unsigned)
        if not verification["ok"]:
            raise ValueError("OAP verification failed: " + "; ".join(verification["issues"]))
        if manifest.get("kind") != "oap.actor.manifest":
            raise ValueError("This is not an OAP actor package")
        return manifest, verification
    except (zipfile.BadZipFile, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid OAP package") from exc


def _reference_bytes(store, path, manifest, sheet):
    """A plain sheet is read directly; a sealed one is opened with this studio's key, in memory."""
    if not sheet.get("sealed"):
        with zipfile.ZipFile(path) as archive:
            return archive.read(sheet["file"])
    identity = recipient_identity(store)
    wraps = {wrap.get("public_key") for wrap in sheet["sealed"].get("wraps", [])}
    if identity["public_key"] not in wraps:
        raise ValueError("This package is sealed to another studio. Ask its Agent to reissue it "
                         "to this studio's recipient key: " + identity["public_key"])
    return oap.open_asset_buffer(str(path), sheet["file"], identity["_private"], allow_untrusted=True,
                                 attestation_policy="ignore", max_bytes=MAX_PACKAGE_BYTES)


def import_actor(store, path, actor_id, *, allow_unsigned=False, accept_unknown=False):
    manifest, verification = package_info(path, allow_unsigned=allow_unsigned)
    if verification.get("signature_valid") and not accept_unknown:
        raise ValueError("Signature is valid, but the signer is not locally trusted. "
                         "Review the package and explicitly accept this signer.")
    actor_id = identifier(actor_id or manifest["identity"]["actor_id"])
    target = store.home / "actors" / actor_id
    if target.exists():
        raise ValueError("Actor already exists; imports never overwrite actors")
    with zipfile.ZipFile(path) as archive:
        present = set(archive.namelist())
    # Portfolio and audition tiers may list a cast-cleared sheet without including it.
    sheets = [entry for entry in manifest.get("visual", {}).get("sheets", [])
              if entry.get("role") == "reference_sheet" and
              (entry["file"] in present or entry.get("sealed", {}).get("path") in present)]
    if not sheets:
        raise ValueError("No reference sheet. Import a full OAP package, not a portfolio or audition package")
    with tempfile.TemporaryDirectory(dir=target.parent) as temp:
        stage = Path(temp)
        default = (manifest.get("visual", {}).get("contract") or {}).get("default_sheet")
        sheet = next((entry for entry in sheets if entry["file"] == default), sheets[0])
        clean_image(_reference_bytes(store, path, manifest, sheet), stage / "reference.png")
        # Preserve all original protocol metadata/assets without executing or loading them.
        shutil.copyfile(path, stage / "original.oap")
        record = {"id": actor_id, "name": manifest["identity"].get("display_name") or actor_id,
                  "description": manifest.get("visual", {}).get("core_identity", ""),
                  "reference": "reference.png", "rider": manifest.get("rider", {}),
                  "oap": {"did": manifest["identity"].get("did"),
                          "signer": manifest.get("agent", {}).get("public_key"),
                          "signature_valid": verification.get("signature_valid"),
                          "agent_known": False, "original_preserved": True}}
        write_json(stage / "actor.json", record)
        stage.rename(target)
    return record


def export_actor(store, actor_id, *, tier="full", reference_clearance="cast"):
    """Export a signed package. Audition packages omit assets cleared only for cast.

    A full export carries the reference as a plain public asset, readable by whoever
    receives the file, as it always has; OAP 0.5 calls that a portfolio package.
    """
    if tier not in ("full", "audition"):
        raise ValueError("Export tier must be full or audition")
    if reference_clearance not in ("cast", "audition"):
        raise ValueError("Reference clearance must be cast or audition")
    record = store.actor(actor_id)
    if not record:
        raise ValueError("Actor not found")
    directory = store.home / "actors" / actor_id
    if (directory / "original.oap").exists():
        if tier != "full" or reference_clearance != "cast":
            raise ValueError("Imported actors export only their original package; "
                             "request audition packages from the actor's Agent")
        return directory / "original.oap"
    key_path = store.home / "signing-identity.json"
    identity = read_json(key_path)
    if identity is None:
        identity = oap.generate_identity()
        if not identity.get("_private"):
            raise ValueError("OAP signing requires cryptography")
        write_json(key_path, identity, private=True)
    manifest = oap.new_manifest(actor_id, record["name"])
    manifest["identity"]["did"] = identity["did"] + "#" + actor_id
    manifest["agent"].update(name="Mondo Music Video", public_key=identity["public_key"])
    manifest["rider"] = record["rider"]
    manifest["visual"].update(core_identity=record["description"],
                               visual_contract=record["description"],
                               sheets=[{"file": "identity/reference.png",
                                        "clearance": "public" if tier == "full" else reference_clearance,
                                        "sha256": None, "role": "reference_sheet"}])
    output = store.home / "exports" / (actor_id + "-" + uuid.uuid4().hex + ".oap")
    with tempfile.TemporaryDirectory() as temp:
        stage = Path(temp)
        (stage / "identity").mkdir()
        shutil.copyfile(inside(directory, record["reference"]), stage / "identity/reference.png")
        write_json(stage / "manifest.json", manifest)
        oap.package_actor(str(stage), str(output), tier="portfolio" if tier == "full" else tier,
                          sign_key=identity["_private"])
    if not oap.verify_package(str(output), known_agents=[identity["public_key"]])["ok"]:
        output.unlink()
        raise ValueError("Export did not pass OAP verification")
    return output


def check_cast(store, actor_ids, content):
    references, descriptions = [], []
    if len(set(actor_ids)) != len(actor_ids) or len(actor_ids) > 9:
        raise ValueError("Select up to nine different actors")
    for actor_id in actor_ids:
        record = store.actor(actor_id)
        if not record:
            raise ValueError("Actor not found: " + actor_id)
        conflicts = oap.check_rider(record.get("rider", {}), {"content": content, "intent": "music_video"})
        if conflicts:
            raise ValueError(record["name"] + ": " + "; ".join(conflicts))
        references.append(inside(store.home / "actors" / actor_id, record["reference"]))
        descriptions.append(record["name"] + ": " + record["description"])
    return references, descriptions
