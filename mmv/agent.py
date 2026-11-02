"""Local agent client shared by the optional MCP server and the shell helper."""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

AGENT_SETTINGS = {
    "auto_updates", "auto_collapse_panels", "h3_tag_normalizer", "backend", "writer_url", "writer_model", "writer_mode", "writer_call_estimate",
    "vision_url", "vision_model", "vision_call_estimate", "laya_model_dir", "laya_device", "h3_models", "workflow_preset",
    "writer_api_profile", "vision_api_profile", "video_api_profile", "comfy_url", "comfy_sdk_url",
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("The local application redirected the request; verify MMV_URL")


WORLD_EDIT_KEYS = ("name", "seed_sentence", "subjects", "pools", "core_laws", "locations", "practices", "objects", "factions",
                   "ecology_rules", "moral_ambiguities", "open_threads", "do_not_contradict")


def world_edit_body(world, base_version):
    """The editable fields of a ledger plus the version it was read at (a ledger read with get_world carries its own)."""
    version = base_version if base_version is not None else world.get("version")
    if not isinstance(version, int):
        raise ValueError("Give base_version, the version of the world the edit starts from")
    return {**{key: world[key] for key in WORLD_EDIT_KEYS if key in world}, "base_version": version}


class AgentClient:
    def __init__(self, base_url=None):
        parsed = urllib.parse.urlparse(base_url or os.environ.get("MMV_URL", "http://127.0.0.1:8091"))
        if (parsed.scheme not in ("http", "https") or parsed.hostname not in ("127.0.0.1", "localhost", "::1")
                or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
            raise ValueError("MMV_URL must be a localhost HTTP(S) URL without credentials, path or query")
        try:
            if parsed.port is not None and not 1 <= parsed.port <= 65535:
                raise ValueError("Invalid port")
        except ValueError:
            raise ValueError("MMV_URL has an invalid port") from None
        self.base = urllib.parse.urlunparse(parsed._replace(path="")).rstrip("/")
        # Never send local media or tool calls through an environment-configured proxy.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def _open(self, method, path, *, data=None, content_type=None, content_length=None):
        if not path.startswith("/api/") or ".." in path or "://" in path:
            raise ValueError("Unsupported application route")
        headers = {"Accept": "application/json"}
        if content_type:
            headers["Content-Type"] = content_type
        if content_length is not None:
            headers["Content-Length"] = str(content_length)
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            return self.opener.open(request, timeout=120)
        except urllib.error.HTTPError as exc:
            try:
                message = json.loads(exc.read()).get("detail", f"HTTP {exc.code}")
            except (ValueError, AttributeError):
                message = f"HTTP {exc.code}"
            raise ValueError(str(message)) from None
        except (urllib.error.URLError, TimeoutError):
            raise ValueError("Cannot reach Mondo Music Video. Start the local app and verify MMV_URL. "
                             "After a submission timeout, check status and saved request IDs before retrying.") from None

    def _json(self, method, path, payload=None):
        data = json.dumps(payload, allow_nan=False).encode() if payload is not None else None
        with self._open(method, path, data=data, content_type="application/json" if data is not None else None) as response:
            return json.load(response)

    def inspect(self, kind="status"):
        if kind not in ("status", "version", "catalog", "actors", "instruments", "props", "opp-guide", "vision-guide", "oap-collection", "styles", "vocabularies", "vocabulary", "stems", "lyrics", "outputs", "settings", "update", "agreements", "worlds", "storyboards", "quick-start"):
            raise ValueError("Unknown inspection kind")
        guides = {"opp-guide": "/api/props/guide", "vision-guide": "/api/vision/guide"}
        result = self._json("GET", guides.get(kind, "/api/" + kind))
        if kind == "outputs":
            for output in result:
                output["play_url"] = self.base + "/api/media/" + urllib.parse.quote(output["file"], safe="/")
        return result

    def preview(self, request):
        if not isinstance(request, dict) or request.get("kind", "video") not in ("video", "ident", "harvest", "world_harvest", "storyboard"):
            raise ValueError("Preview requires a music video, ident, style harvest, world harvest or storyboard request object")
        return self._json("POST", "/api/quote", request)

    def storyboard_result(self, run_id, raw_response=False):
        return self._json("GET", "/api/storyboards/" + urllib.parse.quote(run_id, safe="") + ("/response" if raw_response else ""))

    def detect_lyrics(self, song, model="large-v3", use_vocals=True):
        """Start free local lyrics detection for an uploaded song; poll status, the lines arrive in its result."""
        return self._json("POST", "/api/lyrics/detect", {"song": song, "model": model, "use_vocals": bool(use_vocals)})

    def align_lyrics(self, song, text, model="large-v3"):
        """Time pasted lyric lines against a song that detect_lyrics has already listened to."""
        return self._json("POST", "/api/lyrics/align", {"song": song, "text": text, "model": model})

    def start(self, quote_id, consent=False):
        if consent is not True:
            raise ValueError("Review the preview and obtain user authorization before starting")
        return self._json("POST", "/api/start", {"quote_id": quote_id, "consent": True})

    def queue(self):
        return self._json("GET", "/api/queue")

    def queue_add(self, quote_id, consent=False, replaces=None):
        """Add a reviewed preview to the queue. Consent is needed only when the preview has a price."""
        return self._json("POST", "/api/queue", {"quote_id": quote_id, "consent": consent is True, "replaces": replaces})

    def queue_start(self):
        return self._json("POST", "/api/queue/start")

    def queue_pause(self):
        return self._json("POST", "/api/queue/pause")

    def queue_move(self, ticket_id, delta):
        return self._json("POST", "/api/queue/" + urllib.parse.quote(ticket_id, safe="") + "/move", {"delta": delta})

    def queue_preview(self, ticket_id):
        return self._json("POST", "/api/queue/" + urllib.parse.quote(ticket_id, safe="") + "/preview")

    def queue_resume(self, ticket_id):
        return self._json("POST", "/api/queue/" + urllib.parse.quote(ticket_id, safe="") + "/resume")

    def queue_remove(self, ticket_id):
        return self._json("DELETE", "/api/queue/" + urllib.parse.quote(ticket_id, safe=""))

    def queue_clear_finished(self):
        return self._json("POST", "/api/queue/clear-finished")

    def preview_resume(self, run_id):
        return self._json("POST", "/api/resume/quote", {"run_id": run_id})

    def preview_retry_prompts(self, run_id):
        """Get a new quote from an unrendered run that exhausted prompt validation."""
        return self._json("POST", "/api/retry-prompts/quote", {"run_id": run_id})

    def cancel(self):
        return self._json("POST", "/api/cancel")

    def reset_operation(self, purge_run=False, clear_log=False):
        return self._json("POST", "/api/operation/reset", {"purge_run": purge_run, "clear_log": clear_log})

    def log(self, run_id):
        return self._json("GET", "/api/log/" + urllib.parse.quote(run_id, safe=""))

    def _multipart(self, route, fields, file_field=None, path=None):
        boundary = "mmvagent" + uuid.uuid4().hex
        head = b""
        for name, value in fields.items():
            head += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n").encode()
        if path is not None:
            path = Path(path).expanduser().resolve()
            if not path.is_file() or path.stat().st_size > 256 * 1024 * 1024:
                raise ValueError("Select an existing media file under 256 MB")
            filename = path.name if route == '/api/upload/song' else 'media' + path.suffix
            filename = filename.replace('"', '_').replace('\r', '_').replace('\n', '_').replace('\\', '_')
            head += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; "
                     f"filename=\"{filename}\"\r\nContent-Type: "
                     f"{mimetypes.guess_type(filename)[0] or 'application/octet-stream'}\r\n\r\n").encode()
        tail = ("\r\n" if path is not None else "") + f"--{boundary}--\r\n"
        tail = tail.encode()

        def chunks():
            yield head
            if path is not None:
                with path.open("rb") as stream:
                    while chunk := stream.read(1024 * 1024):
                        yield chunk
            yield tail

        length = len(head) + len(tail) + (path.stat().st_size if path is not None else 0)
        with self._open("POST", route, data=chunks(), content_type="multipart/form-data; boundary=" + boundary,
                        content_length=length) as response:
            return json.load(response)

    def upload(self, kind, path):
        if kind not in ("song", "reference", "oap", "opp", "agreement", "video", "lore"):
            raise ValueError("Choose song, reference, oap, opp, agreement, video or lore")
        return self._multipart("/api/upload/" + kind, {}, "file", path)

    def inspect_opp(self, filename, allow_unsigned=False):
        return self._json("GET", "/api/opp/inspect/" + urllib.parse.quote(filename, safe="") +
                          "?allow_unsigned=" + str(bool(allow_unsigned)).lower())

    def import_opp(self, filename, allow_unsigned=False, accept_signer=""):
        return self._multipart("/api/opp/import", {"filename": filename,
                               "allow_unsigned": str(bool(allow_unsigned)).lower(),
                               "accept_signer": accept_signer})

    def select_opp_sheet(self, prop_id, use=""):
        return self._json("GET", "/api/props/" + urllib.parse.quote(prop_id, safe="") +
                          "/selection?use=" + urllib.parse.quote(use, safe=""))

    def create_actor(self, actor_id, name, description, reference_path):
        return self._multipart("/api/actors", {"actor_id": actor_id, "name": name, "description": description},
                               "reference", reference_path)

    def check_oap_collection(self):
        return self.inspect("oap-collection")

    def oap_recipient_key(self):
        return self._json("GET", "/api/oap/recipient-key")

    def stage_oap_collection(self, actor_id, index_sha256):
        return self._json("POST", "/api/oap-collection/stage",
                          {"actor_id": actor_id, "index_sha256": index_sha256})

    def update_actor(self, actor_id, description):
        return self._json("PATCH", "/api/actors/" + urllib.parse.quote(actor_id, safe=""),
                          {"description": description})

    def create_style(self, style_id, name, direction, style_card=None, vocabulary=None):
        payload = {"id": style_id, "name": name, "direction": direction}
        if style_card:
            payload["style_card"] = style_card
        if vocabulary:
            payload["vocabulary"] = vocabulary
        return self._json("POST", "/api/styles", payload)

    def export_style(self, style_id, destination=None):
        path = "/api/styles/" + urllib.parse.quote(style_id, safe="") + "/export"
        with self._open("GET", path) as response:
            content = response.read()
        if destination is not None:
            dest = Path(destination)
            if dest.is_dir():
                dest = dest / f"{style_id}.json"
            dest.write_bytes(content)
            return {"saved": str(dest), "bytes": len(content)}
        return json.loads(content.decode("utf-8"))

    def import_style(self, style_id, name, direction, style_card=None, overwrite=False, vocabulary=None):
        payload = {
            "id": style_id,
            "name": name,
            "direction": direction,
            "overwrite": bool(overwrite),
        }
        if style_card:
            payload["style_card"] = style_card
        if vocabulary:
            payload["vocabulary"] = vocabulary
        return self._json("POST", "/api/styles/import", payload)

    def get_world(self, world_id, version=None):
        query = "" if version is None else "?version=" + str(int(version))
        return self._json("GET", "/api/worlds/" + urllib.parse.quote(world_id, safe="") + query)

    def world_versions(self, world_id):
        return self._json("GET", "/api/worlds/" + urllib.parse.quote(world_id, safe="") + "/versions")

    def create_world(self, world):
        """Save a world written by hand or by an agent; a harvest instead proposes one through preview and start."""
        return self._json("POST", "/api/worlds", world)

    def preview_world_edit(self, world_id, world, base_version=None):
        """What saving an edited ledger would change; nothing is saved. `world` may be a ledger read with get_world."""
        return self._json("POST", "/api/worlds/" + urllib.parse.quote(world_id, safe="") + "/edit-preview",
                          world_edit_body(world, base_version))

    def edit_world(self, world_id, world, base_version=None, confirm=False):
        """Save an edited ledger as the world's next version (restorable with rollback_world)."""
        if not confirm:
            raise ValueError("Editing a world changes its canon; set confirm only after the user has reviewed the changes from preview_world_edit")
        return self._json("PUT", "/api/worlds/" + urllib.parse.quote(world_id, safe=""), world_edit_body(world, base_version))

    def export_world(self, world_id, destination=None):
        path = "/api/worlds/" + urllib.parse.quote(world_id, safe="") + "/export"
        with self._open("GET", path) as response:
            content = response.read()
        if destination is None:
            return json.loads(content.decode("utf-8"))
        dest = Path(destination)
        dest = dest / f"{world_id}.world.json" if dest.is_dir() else dest
        dest.write_bytes(content)
        return {"saved": str(dest), "bytes": len(content)}

    def rollback_world(self, world_id, version):
        return self._json("POST", "/api/worlds/" + urllib.parse.quote(world_id, safe="") + "/rollback", {"version": int(version)})

    def delete_world(self, world_id, confirm=False):
        if confirm is not True:
            raise ValueError("Deleting a world requires explicit user authorization; set confirm only after that authorization")
        return self._json("DELETE", "/api/worlds/" + urllib.parse.quote(world_id, safe=""))

    def world_proposals(self):
        return self._json("GET", "/api/worlds/proposals")

    def world_proposal(self, proposal_id):
        """A harvest's proposed world with its field-level changes, for review before anything is saved."""
        return self._json("GET", "/api/worlds/proposals/" + urllib.parse.quote(proposal_id, safe=""))

    def accept_world_proposal(self, proposal_id, confirm=False):
        if confirm is not True:
            raise ValueError("Accepting a proposal changes a world's canon; set confirm only after the user has reviewed its changes")
        return self._json("POST", "/api/worlds/proposals/" + urllib.parse.quote(proposal_id, safe="") + "/accept")

    def reject_world_proposal(self, proposal_id):
        return self._json("DELETE", "/api/worlds/proposals/" + urllib.parse.quote(proposal_id, safe=""))

    def save_vocabulary(self, vocab_id, name, tables, description="", base_profile="full"):
        return self._json("POST", "/api/vocabularies", {
            "id": vocab_id, "name": name, "description": description,
            "base_profile": base_profile, "tables": tables,
        })

    def delete_actor(self, actor_id, confirm=False):
        if confirm is not True:
            raise ValueError("Deleting an actor requires explicit user authorization; set confirm only after that authorization")
        return self._json("DELETE", "/api/actors/" + urllib.parse.quote(actor_id, safe=""))

    def delete_style(self, style_id, confirm=False):
        if confirm is not True:
            raise ValueError("Deleting a style requires explicit user authorization; set confirm only after that authorization")
        return self._json("DELETE", "/api/styles/" + urllib.parse.quote(style_id, safe=""))

    def delete_vocabulary(self, vocab_id, confirm=False):
        if confirm is not True:
            raise ValueError("Deleting a vocabulary preset requires explicit user authorization; set confirm only after that authorization")
        return self._json("DELETE", "/api/vocabularies/" + urllib.parse.quote(vocab_id, safe=""))

    def select_api_profile(self, name):
        return self._json("POST", "/api/api-profiles/" + urllib.parse.quote(name, safe="") + "/activate")

    def add_api_profile(self, name, role, settings, key_env=""):
        payload = {"name": name, "role": role, "settings": settings}
        if key_env:
            key = os.environ.get(key_env, "")
            if not key:
                raise ValueError("The named API key environment variable is empty or missing")
            if len(key) > 1000 or any(ord(c) < 33 or ord(c) > 126 for c in key):
                raise ValueError("Invalid API key format")
            payload["key"] = key
        return self._json("POST", "/api/api-profiles", payload)

    def remove_api_profile(self, name, confirm=False):
        if confirm is not True:
            raise ValueError("Removing an API profile and stored key requires explicit user authorization")
        return self._json("DELETE", "/api/api-profiles/" + urllib.parse.quote(name, safe=""))

    def update_settings(self, changes):
        if not isinstance(changes, dict) or set(changes) - AGENT_SETTINGS:
            raise ValueError("Use supported service/model/profile/update preferences; executable commands and credentials require setup or the GUI")
        return self._json("PATCH", "/api/settings", changes)

    def install_starter_assets(self, accept_starter_signer=False, restore_removed=False):
        return self._json("POST", "/api/starter-assets", {
            "accept_starter_signer": accept_starter_signer, "restore_removed": restore_removed})

    def inspect_oap(self, filename, allow_unsigned=False):
        return self._json("GET", "/api/oap/inspect/" + urllib.parse.quote(filename, safe="") +
                          "?allow_unsigned=" + str(bool(allow_unsigned)).lower())

    def import_oap(self, filename, actor_id="", allow_unsigned=False, accept_unknown=False):
        return self._multipart("/api/oap/import", {"filename": filename, "actor_id": actor_id,
                               "allow_unsigned": str(bool(allow_unsigned)).lower(),
                               "accept_unknown": str(bool(accept_unknown)).lower()})

    def _save(self, method, route, destination):
        destination = Path(destination).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive create preserves existing files and gives each interrupted export a visible artifact.
        with destination.open("xb") as stream:
            try:
                with self._open(method, route) as response:
                    while chunk := response.read(1024 * 1024):
                        stream.write(chunk)
            except Exception:
                stream.close()
                if destination.stat().st_size == 0:
                    destination.unlink()
                raise
        return {"file": str(destination), "bytes": destination.stat().st_size}

    def download(self, output_file, destination):
        return self._save("GET", "/api/media/" + urllib.parse.quote(output_file, safe="/"), destination)

    def export_oap(self, actor_id, destination, tier="full", reference_clearance="cast"):
        query = urllib.parse.urlencode({"tier": tier, "reference_clearance": reference_clearance})
        return self._save("POST", "/api/actors/" + urllib.parse.quote(actor_id, safe="") + "/export?" + query, destination)

    def create_agreement(self, actor_id, agreement_id, title, offer, currency, character="",
                         role_description="", content=None, notes=""):
        payload = {"actor_id": actor_id, "agreement_id": agreement_id, "title": title, "offer": offer,
                   "currency": currency, "character": character, "role_description": role_description,
                   "notes": notes}
        if content is not None:
            payload["content"] = content
        return self._json("POST", "/api/agreements", payload)

    def sign_agreement(self, agreement_id, role, confirm=False):
        if not confirm:
            raise ValueError("Signing a role agreement commits this studio to its terms; obtain explicit user "
                             "authorization for this agreement and role, then set confirm")
        return self._json("POST", "/api/agreements/" + urllib.parse.quote(agreement_id, safe="") + "/sign",
                          {"role": role})

    def verify_agreement(self, agreement_id):
        return self._json("GET", "/api/agreements/" + urllib.parse.quote(agreement_id, safe="") + "/verify")

    def export_agreement(self, agreement_id, destination):
        return self._save("POST", "/api/agreements/" + urllib.parse.quote(agreement_id, safe="") + "/bundle",
                          destination)

    def import_agreement(self, filename):
        return self._multipart("/api/agreements/import", {"filename": filename})

    def music_score(self, output_file):
        run_id = str(output_file).split("/")[0]
        return self._json("GET", "/api/outputs/" + urllib.parse.quote(run_id, safe="") + "/score")

    def output_prompts(self, output_file):
        """Each passage's written prompt, planned shots and, while it is still on disk, its original rendered clip URL."""
        run_id = str(output_file).split("/")[0]
        result = self._json("GET", "/api/outputs/" + urllib.parse.quote(run_id, safe="") + "/prompts")
        for passage in result["segments"]:
            if passage.get("clip_url"):
                passage["clip_url"] = self.base + passage["clip_url"]
            for take in passage.get("takes") or []:
                if take.get("clip_url") and take["clip_url"].startswith("/"):
                    take["clip_url"] = self.base + take["clip_url"]
        return result

    def reroll_segment(self, output_file, segment_id, seed=None, confirm=False):
        """Re-render one passage on the local H3 renderer (GPU work; needs confirm=True) with a new seed, its saved
        prompt and cast references. The new take becomes active; re-encode the final video to use it."""
        run_id = str(output_file).split("/")[0]
        payload = {"confirm": bool(confirm), **({"seed": int(seed)} if seed is not None else {})}
        return self._json("POST", f"/api/outputs/{urllib.parse.quote(run_id, safe='')}/reroll/{urllib.parse.quote(segment_id, safe='')}", payload)

    def select_segment_take(self, output_file, segment_id, take_id):
        """Select a recorded take for a passage clip."""
        run_id = str(output_file).split("/")[0]
        return self._json("POST", f"/api/outputs/{urllib.parse.quote(run_id, safe='')}/takes/{urllib.parse.quote(segment_id, safe='')}",
                          {"take_id": take_id})

    def _prompt_url(self, output_file, segment_id, action):
        run_id = str(output_file).split("/")[0]
        return f"/api/outputs/{urllib.parse.quote(run_id, safe='')}/prompts/{urllib.parse.quote(segment_id, safe='')}/{action}"

    def rewrite_prompt(self, output_file, segment_id, confirm=False, accept_writer_cost=False, seed=None,
                       world_id=None, direction=None):
        """Write a new prompt for one passage (a video passage also rolls a fresh setting and motif) through the normal writer, Mondo checks and Laya
        review (confirm=True; an API writer also needs accept_writer_cost=True). Optional world_id steers the passage's vocabulary
        toward a Thematic World or saved World; optional direction adds a passage-specific creative note. The new version becomes
        the passage's prompt; reroll the clip to render it."""
        payload = {"confirm": bool(confirm), "accept_writer_cost": bool(accept_writer_cost),
                   **({"seed": int(seed)} if seed is not None else {}),
                   **({"world_id": str(world_id).strip()} if world_id else {}),
                   **({"direction": str(direction).strip()} if direction else {})}
        return self._json("POST", self._prompt_url(output_file, segment_id, "rewrite"), payload)

    def edit_prompt(self, output_file, segment_id, prompt, confirm=False):
        """Check a hand-edited prompt with the Mondo checks and Laya review (confirm=True). It becomes the passage's prompt
        only if it passes; otherwise it is kept as a version marked not passed."""
        return self._json("POST", self._prompt_url(output_file, segment_id, "edit"), {"prompt": prompt, "confirm": bool(confirm)})

    def select_prompt_take(self, output_file, segment_id, prompt_take_id):
        """Make a passed prompt version (e.g. 'prompt1', the original) the passage's prompt."""
        return self._json("POST", self._prompt_url(output_file, segment_id, "select"), {"prompt_take_id": prompt_take_id})

    def reassemble_output(self, output_file, selected_takes=None):
        """Re-encode the final music video using the active or selected passage takes, preserving previous final video takes."""
        run_id = str(output_file).split("/")[0]
        return self._json("POST", f"/api/outputs/{urllib.parse.quote(run_id, safe='')}/reassemble",
                          {"selected_takes": selected_takes or {}})

    def export_package(self, run_id, zip_it=False, allow_private_actors=False):
        """Copy a finished production into an editing package under the app's data folder (never published)."""
        return self._json("POST", "/api/outputs/" + urllib.parse.quote(run_id, safe="") + "/package",
                          {"zip": bool(zip_it), "allow_private_actors": bool(allow_private_actors)})

    def caption_fonts(self):
        return self._json("GET", "/api/captions/fonts")

    def caption_video(self, source, lyric_lines=None, style="classic", position="bottom", size="medium",
                      color="", outline_color="", font=""):
        """Rebuild captions from original sources; missing sources fail without re-encoding a final."""
        return self._json("POST", "/api/captions", {"source": source, "lyric_lines": lyric_lines or [], "style": style,
                                                    "position": position, "size": size, "color": color,
                                                    "outline_color": outline_color, "font": font})

    def upscale_models(self):
        return self._json("GET", "/api/upscale/models")

    def upscale_estimate(self, source, model="ahq-12", scale=2, options=None):
        return self._json("POST", "/api/upscale/estimate",
                          {"source": source, "model": model, "scale": scale, **({"options": options} if options else {})})

    def upscale(self, source, model="ahq-12", scale=2, max_credits=None, options=None):
        body = {"source": source, "model": model, "scale": scale}
        if options:
            body["options"] = options
        if max_credits:
            body["max_credits"] = max_credits
        return self._json("POST", "/api/upscale", body)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Operate a running local Mondo Music Video app")
    parser.add_argument("--url", default=None, help="Local app URL (or MMV_URL)")
    sub = parser.add_subparsers(dest="command", required=True)
    storyboard_parser = sub.add_parser("storyboard-result")
    storyboard_parser.add_argument("run_id")
    storyboard_parser.add_argument("--raw-response", action="store_true")
    for name in ("worlds", "status", "version", "catalog", "actors", "instruments", "props", "opp-guide", "vision-guide", "oap-collection", "styles", "vocabularies", "vocabulary", "stems", "lyrics", "outputs", "settings", "update", "agreements", "storyboards", "quick-start", "cancel"):
        sub.add_parser(name)
    reset_op = sub.add_parser("reset-operation")
    reset_op.add_argument("--purge-run", action="store_true", help="Delete the incomplete run folder")
    reset_op.add_argument("--clear-log", action="store_true", help="Clear the operation and studio logs")
    upload = sub.add_parser("upload")
    upload.add_argument("kind", choices=("song", "reference", "oap", "opp", "agreement", "video", "lore"))
    upload.add_argument("path")
    preview = sub.add_parser("preview")
    preview.add_argument("request_file", help="JSON production request file")
    resume = sub.add_parser("preview-resume")
    resume.add_argument("run_id")
    retry_prompts = sub.add_parser("preview-retry-prompts")
    retry_prompts.add_argument("run_id")
    start = sub.add_parser("start")
    start.add_argument("quote_id")
    start.add_argument("--consent", action="store_true")
    for name in ("queue", "queue-start", "queue-pause", "queue-clear-finished"):
        sub.add_parser(name)
    queue_add = sub.add_parser("queue-add")
    queue_add.add_argument("quote_id")
    queue_add.add_argument("--consent", action="store_true")
    queue_add.add_argument("--replaces")
    queue_move = sub.add_parser("queue-move")
    queue_move.add_argument("ticket_id")
    queue_move.add_argument("delta", type=int, choices=(-1, 1))
    for name in ("queue-preview", "queue-resume", "queue-remove"):
        sub.add_parser(name).add_argument("ticket_id")
    log = sub.add_parser("log")
    log.add_argument("run_id")
    for name in ("delete-actor", "delete-style", "delete-vocabulary"):
        delete = sub.add_parser(name)
        delete.add_argument("id")
        delete.add_argument("--confirm", action="store_true")
    update_actor = sub.add_parser("update-actor")
    update_actor.add_argument("id")
    update_actor.add_argument("description")
    update_settings = sub.add_parser("update-settings")
    update_settings.add_argument("changes", help="JSON object of supported settings changes")
    sub.add_parser("oap-recipient-key")
    stage_collection = sub.add_parser("oap-collection-stage")
    stage_collection.add_argument("actor_id")
    stage_collection.add_argument("index_sha256")
    for name in ("world", "world-versions", "world-proposal", "reject-world-proposal"):
        world_cmd = sub.add_parser(name)
        world_cmd.add_argument("id")
        if name == "world":
            world_cmd.add_argument("--version", type=int, default=None)
    sub.add_parser("world-proposals")
    create_world = sub.add_parser("create-world")
    create_world.add_argument("file", help="Path to world JSON file")
    for name in ("world-edit-preview", "edit-world"):
        edit_cmd = sub.add_parser(name)
        edit_cmd.add_argument("id")
        edit_cmd.add_argument("file", help="Path to the edited world JSON (a ledger read with `world`)")
        edit_cmd.add_argument("--base-version", type=int, default=None, help="Version the edit starts from; default: the file's own version")
        if name == "edit-world":
            edit_cmd.add_argument("--confirm", action="store_true")
    export_world = sub.add_parser("export-world")
    export_world.add_argument("id")
    export_world.add_argument("--destination", default=None)
    rollback_world = sub.add_parser("rollback-world")
    rollback_world.add_argument("id")
    rollback_world.add_argument("version", type=int)
    for name in ("delete-world", "accept-world-proposal"):
        confirmed = sub.add_parser(name)
        confirmed.add_argument("id")
        confirmed.add_argument("--confirm", action="store_true")
    sub.add_parser("upscale-models")
    for name in ("upscale-estimate", "upscale"):
        topaz = sub.add_parser(name)
        topaz.add_argument("source", help="Finished output file, e.g. <run id>/music-video.mp4")
        topaz.add_argument("--model", default="ahq-12")
        topaz.add_argument("--scale", type=int, choices=(1, 2, 4), default=2)
        topaz.add_argument("--options", default=None, metavar="JSON",
                           help='Topaz cloud only, e.g. \'{"interpolation": {"model": "apo-8", "fps": 60}}\'; model "none" = frame rate only')
        if name == "upscale":
            topaz.add_argument("--max-credits", type=int, default=None,
                               help="Topaz cloud only: the highest credits the user approved from upscale-estimate")
    profile = sub.add_parser("select-api-profile")
    profile.add_argument("name")
    download = sub.add_parser("download")
    download.add_argument("output_file")
    download.add_argument("destination")
    export_style = sub.add_parser("export-style")
    export_style.add_argument("id")
    export_style.add_argument("--destination", default=None)
    import_style = sub.add_parser("import-style")
    import_style.add_argument("file", help="Path to style JSON file")
    import_style.add_argument("--overwrite", action="store_true")
    inspect_opp = sub.add_parser("inspect-opp")
    inspect_opp.add_argument("filename")
    inspect_opp.add_argument("--allow-unsigned", action="store_true")
    import_opp = sub.add_parser("import-opp")
    import_opp.add_argument("filename")
    import_opp.add_argument("--allow-unsigned", action="store_true")
    import_opp.add_argument("--accept-signer", default="", metavar="PUBLIC_KEY")
    output_prompts = sub.add_parser("output-prompts", help="Passage prompts and original clips of a finished output")
    output_prompts.add_argument("output_file", help="An output's file from the outputs command")
    reroll_cmd = sub.add_parser("reroll-segment", help="Re-render a single passage clip with a new seed")
    reroll_cmd.add_argument("output_file")
    reroll_cmd.add_argument("segment_id")
    reroll_cmd.add_argument("--seed", type=int, default=None)
    reroll_cmd.add_argument("--confirm", action="store_true", help="Confirm the local GPU render of this passage")
    select_take_cmd = sub.add_parser("select-segment-take", help="Select a recorded take for a passage")
    select_take_cmd.add_argument("output_file")
    select_take_cmd.add_argument("segment_id")
    select_take_cmd.add_argument("take_id")
    rewrite_cmd = sub.add_parser("rewrite-prompt", help="Write a new checked prompt for one passage")
    rewrite_cmd.add_argument("output_file")
    rewrite_cmd.add_argument("segment_id")
    rewrite_cmd.add_argument("--seed", type=int, default=None, help="Optional variation seed for the passage's new setting and motif")
    rewrite_cmd.add_argument("--world", default=None, help="Optional Thematic World name or saved World ID to steer vocabulary")
    rewrite_cmd.add_argument("--direction", default=None, help="Optional passage-specific creative direction note")
    rewrite_cmd.add_argument("--confirm", action="store_true")
    rewrite_cmd.add_argument("--accept-writer-cost", action="store_true", help="Accept an API writer's charge for this call")
    edit_cmd = sub.add_parser("edit-prompt", help="Check a hand-edited prompt (read from a file) for one passage")
    edit_cmd.add_argument("output_file")
    edit_cmd.add_argument("segment_id")
    edit_cmd.add_argument("prompt_file")
    edit_cmd.add_argument("--confirm", action="store_true")
    select_prompt_cmd = sub.add_parser("select-prompt-take", help="Make a passed prompt version the passage's prompt")
    select_prompt_cmd.add_argument("output_file")
    select_prompt_cmd.add_argument("segment_id")
    select_prompt_cmd.add_argument("prompt_take_id")
    reassemble_cmd = sub.add_parser("reassemble-output", help="Re-encode final video with selected passage takes")
    reassemble_cmd.add_argument("output_file")
    reassemble_cmd.add_argument("--takes", default=None, help="Optional JSON mapping of segment_id to take_id")
    select_opp = sub.add_parser("select-opp-sheet")
    select_opp.add_argument("prop_id")
    select_opp.add_argument("--use", default="")
    args = parser.parse_args(argv)
    try:
        client = AgentClient(args.url)
        if args.command == "storyboard-result":
            result = client.storyboard_result(args.run_id, args.raw_response)
        elif args.command == "upload":
            result = client.upload(args.kind, args.path)
        elif args.command == "preview":
            result = client.preview(json.loads(Path(args.request_file).read_text(encoding="utf-8")))
        elif args.command == "preview-resume":
            result = client.preview_resume(args.run_id)
        elif args.command == "preview-retry-prompts":
            result = client.preview_retry_prompts(args.run_id)
        elif args.command == "start":
            result = client.start(args.quote_id, args.consent)
        elif args.command == "queue":
            result = client.queue()
        elif args.command == "queue-start":
            result = client.queue_start()
        elif args.command == "queue-pause":
            result = client.queue_pause()
        elif args.command == "queue-clear-finished":
            result = client.queue_clear_finished()
        elif args.command == "queue-add":
            result = client.queue_add(args.quote_id, args.consent, args.replaces)
        elif args.command == "queue-move":
            result = client.queue_move(args.ticket_id, args.delta)
        elif args.command == "queue-preview":
            result = client.queue_preview(args.ticket_id)
        elif args.command == "queue-resume":
            result = client.queue_resume(args.ticket_id)
        elif args.command == "queue-remove":
            result = client.queue_remove(args.ticket_id)
        elif args.command == "log":
            result = client.log(args.run_id)
        elif args.command == "download":
            result = client.download(args.output_file, args.destination)
        elif args.command == "upscale-estimate":
            result = client.upscale_estimate(args.source, args.model, args.scale, json.loads(args.options or "null"))
        elif args.command == "upscale":
            result = client.upscale(args.source, args.model, args.scale, args.max_credits, json.loads(args.options or "null"))
        elif args.command == "upscale-models":
            result = client.upscale_models()
        elif args.command == "cancel":
            result = client.cancel()
        elif args.command == "reset-operation":
            result = client.reset_operation(purge_run=args.purge_run, clear_log=args.clear_log)
        elif args.command == "delete-actor":
            result = client.delete_actor(args.id, args.confirm)
        elif args.command == "update-actor":
            result = client.update_actor(args.id, args.description)
        elif args.command == "update-settings":
            result = client.update_settings(json.loads(args.changes))
        elif args.command == "oap-recipient-key":
            result = client.oap_recipient_key()
        elif args.command == "oap-collection-stage":
            result = client.stage_oap_collection(args.actor_id, args.index_sha256)
        elif args.command == "delete-style":
            result = client.delete_style(args.id, args.confirm)
        elif args.command == "delete-vocabulary":
            result = client.delete_vocabulary(args.id, args.confirm)
        elif args.command == "select-api-profile":
            result = client.select_api_profile(args.name)
        elif args.command == "export-style":
            result = client.export_style(args.id, args.destination)
        elif args.command == "import-style":
            data = json.loads(Path(args.file).read_text(encoding="utf-8"))
            result = client.import_style(
                data["id"],
                data["name"],
                data["direction"],
                style_card=data.get("style_card"),
                overwrite=args.overwrite,
                vocabulary=data.get("vocabulary"),
            )
        elif args.command == "world":
            result = client.get_world(args.id, args.version)
        elif args.command == "world-versions":
            result = client.world_versions(args.id)
        elif args.command == "world-proposals":
            result = client.world_proposals()
        elif args.command == "world-proposal":
            result = client.world_proposal(args.id)
        elif args.command == "reject-world-proposal":
            result = client.reject_world_proposal(args.id)
        elif args.command == "create-world":
            result = client.create_world(json.loads(Path(args.file).read_text(encoding="utf-8")))
        elif args.command in ("world-edit-preview", "edit-world"):
            edited = json.loads(Path(args.file).read_text(encoding="utf-8"))
            result = (client.preview_world_edit(args.id, edited, args.base_version) if args.command == "world-edit-preview"
                      else client.edit_world(args.id, edited, args.base_version, args.confirm))
        elif args.command == "export-world":
            result = client.export_world(args.id, args.destination)
        elif args.command == "rollback-world":
            result = client.rollback_world(args.id, args.version)
        elif args.command == "delete-world":
            result = client.delete_world(args.id, args.confirm)
        elif args.command == "accept-world-proposal":
            result = client.accept_world_proposal(args.id, args.confirm)
        elif args.command == "inspect-opp":
            result = client.inspect_opp(args.filename, args.allow_unsigned)
        elif args.command == "import-opp":
            result = client.import_opp(args.filename, args.allow_unsigned, args.accept_signer)
        elif args.command == "output-prompts":
            result = client.output_prompts(args.output_file)
        elif args.command == "reroll-segment":
            result = client.reroll_segment(args.output_file, args.segment_id, seed=args.seed, confirm=args.confirm)
        elif args.command == "select-segment-take":
            result = client.select_segment_take(args.output_file, args.segment_id, args.take_id)
        elif args.command == "rewrite-prompt":
            result = client.rewrite_prompt(args.output_file, args.segment_id, args.confirm, args.accept_writer_cost,
                                           seed=args.seed, world_id=args.world, direction=args.direction)
        elif args.command == "edit-prompt":
            result = client.edit_prompt(args.output_file, args.segment_id, Path(args.prompt_file).read_text(encoding="utf-8"), args.confirm)
        elif args.command == "select-prompt-take":
            result = client.select_prompt_take(args.output_file, args.segment_id, args.prompt_take_id)
        elif args.command == "reassemble-output":
            result = client.reassemble_output(args.output_file, json.loads(args.takes) if args.takes else None)
        elif args.command == "select-opp-sheet":
            result = client.select_opp_sheet(args.prop_id, args.use)
        else:
            result = client.inspect(args.command)
        print(json.dumps(result, indent=2, allow_nan=False))
    except (ValueError, OSError) as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
