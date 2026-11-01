"""Explicit discovery and staging of the public OAP actor collection."""
from __future__ import annotations

import hashlib
import io
import json
import re
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from . import actors
from .storage import identifier

SOURCE = "https://github.com/hodgemann/oap-actors"
RAW = "https://raw.githubusercontent.com/hodgemann/oap-actors/main"
INDEX_LIMIT = 512 * 1024
PACKAGE_LIMIT = actors.MAX_PACKAGE_BYTES


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def _fetch(url, sink, limit, *, opener=None):
    opener = opener or urllib.request.build_opener(NoRedirect())
    request = urllib.request.Request(url, headers={"Accept": "application/octet-stream"}, method="GET")
    size = 0
    try:
        with opener.open(request, timeout=20) as response:
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise ValueError("OAP collection response exceeds its size limit")
                sink.write(chunk)
    except urllib.error.HTTPError as error:
        raise ValueError(f"OAP collection returned HTTP {error.code}; no actor was imported") from None
    except (OSError, urllib.error.URLError):
        raise ValueError("OAP collection could not be reached; no actor was imported") from None
    return size


def _validated_index(raw):
    try:
        data = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("OAP collection index is not valid JSON") from error
    if not isinstance(data, dict) or data.get("kind") != "oap.actor_collection" or data.get("source") != SOURCE:
        raise ValueError("Unexpected OAP collection index")
    if data.get("license") != "CC-BY-4.0" or not isinstance(data.get("actors"), list) or len(data["actors"]) > 200:
        raise ValueError("OAP collection has an unsupported license or actor list")
    seen = set()
    for entry in data["actors"]:
        if not isinstance(entry, dict):
            raise ValueError("Invalid OAP collection actor")
        actor_id = identifier(entry.get("id", ""))
        if actor_id in seen or entry.get("file") != f"actors/{actor_id}.oap":
            raise ValueError("OAP collection has duplicate or unsafe actor paths")
        if (not isinstance(entry.get("name"), str) or not entry["name"] or len(entry["name"]) > 160 or
                not isinstance(entry.get("bytes"), int) or not 0 < entry["bytes"] <= PACKAGE_LIMIT or
                not re.fullmatch(r"[0-9a-f]{64}", entry.get("sha256", "")) or
                not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", str(entry.get("oap_version"))) or
                not isinstance(entry.get("signer"), dict) or
                not isinstance(entry["signer"].get("public_key"), str)):
            raise ValueError("OAP collection actor metadata is incomplete")
        seen.add(actor_id)
    return data


def read_index(*, opener=None):
    sink = io.BytesIO()
    _fetch(RAW + "/index.json", sink, INDEX_LIMIT, opener=opener)
    raw = sink.getvalue()
    return hashlib.sha256(raw).hexdigest(), _validated_index(raw)


def check(store, *, opener=None):
    digest, data = read_index(opener=opener)
    return {
        "source": SOURCE,
        "license": data["license"],
        "license_url": data.get("license_url", ""),
        "attribution": data.get("attribution", ""),
        "index_sha256": digest,
        "actors": [{key: entry[key] for key in ("id", "name", "bytes", "sha256", "oap_version", "signer")}
                   | {"installed": bool(store.actor(entry["id"]))} for entry in data["actors"]],
    }


def stage(store, actor_id, index_sha256, *, opener=None, publish=None):
    actor_id = identifier(actor_id)
    if not re.fullmatch(r"[0-9a-f]{64}", index_sha256):
        raise ValueError("Check the OAP collection again before selecting an actor")
    digest, data = read_index(opener=opener)
    if digest != index_sha256:
        raise ValueError("The OAP collection changed; check again before selecting an actor")
    entry = next((item for item in data["actors"] if item["id"] == actor_id), None)
    if entry is None:
        raise ValueError("Actor is not in the checked OAP collection")
    if store.actor(actor_id):
        raise ValueError("Actor already exists in this studio; existing work is preserved")
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=store.home / "uploads", prefix="oap-collection-", suffix=".part", delete=False) as stream:
            temp_path = Path(stream.name)
            size = _fetch(RAW + "/" + entry["file"], stream, min(PACKAGE_LIMIT, entry["bytes"]), opener=opener)
        with temp_path.open("rb") as stream:
            actual_sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
        if size != entry["bytes"] or actual_sha256 != entry["sha256"]:
            raise ValueError("OAP collection package checksum or size does not match the checked index")
        manifest, verification = actors.package_info(temp_path)
        if (not verification.get("signature_valid") or manifest["identity"].get("actor_id") != actor_id or
                manifest["agent"].get("public_key") != entry["signer"]["public_key"] or
                manifest.get("oap_version") != entry["oap_version"]):
            raise ValueError("OAP collection actor identity or signer does not match the checked index")
        destination = temp_path.with_suffix(".oap")
        (publish or Path.replace)(temp_path, destination)
        temp_path = None
        return {"filename": destination.name, "manifest": manifest, "verification": verification,
                "source": SOURCE, "license": data["license"], "attribution": data.get("attribution", "")}
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
