"""Official Comfy SDK transport for the existing H3 graph, via a local v2 proxy."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import time
import uuid

import httpx
from pathlib import Path
from urllib.parse import urlsplit

from .engine.backends.local_h3 import LocalH3Backend
from .engine.backends.base import BackendError
from .engine import assemble
from .engine.comfy import WorkflowBuilder, slice_audio
from .storage import identifier, read_json, write_json

SDK_REVISION = "6d2dd7233dfa0a1abdf199beada55b2282e26b44"


def validate_proxy_url(value):
    url = urlsplit(value)
    if (url.scheme not in ('http', 'https') or url.hostname not in ('127.0.0.1', 'localhost', '::1')
            or url.username or url.password or url.query or url.fragment or url.path not in ('', '/')):
        raise ValueError('Comfy SDK H3 requires a loopback proxy URL, such as http://127.0.0.1:8189')
    try:
        url.port
    except ValueError:
        raise ValueError('Invalid Comfy proxy port') from None
    if url.port == 0:
        raise ValueError('Invalid Comfy proxy port')
    return value.rstrip('/')


def require_sdk():
    if importlib.util.find_spec('comfy_sdk') is None:
        raise ValueError('Install the Comfy SDK extra: pip install ".[comfy]"')


class SdkSession:
    """SDK assets/jobs with its documented non-retrying low-level submit.

    Comfy.submit retries 429s independently of RetryPolicy. ComfyLow.post_jobs
    sends exactly once. Both are shipped by the same pinned official SDK.
    """
    def __init__(self, url, key=''):
        require_sdk()
        import httpx
        from comfy_low.transport import ComfyLow
        from comfy_sdk.assets import AssetFactory
        from comfy_sdk.jobs import JobFactory
        url = validate_proxy_url(url)
        expected = httpx.URL(url)
        def local_request(request):
            target = request.url
            if (target.scheme, target.host, target.port) != (expected.scheme, expected.host, expected.port):
                raise ValueError('Comfy proxy returned a link outside the configured local endpoint')
        self.http = httpx.Client(timeout=30, trust_env=False, follow_redirects=False,
                                 event_hooks={'request': [local_request]})
        self.low = ComfyLow(url, key or None, client=self.http,
                            client_info='mondo-music-video')
        self.assets = AssetFactory(self.low)
        self.jobs = JobFactory(self.low)

    def submit(self, graph, key):
        from comfy_sdk.jobs import Job
        return Job(self.low, self.low.post_jobs(graph, idempotency_key=key))

    def close(self):
        self.low.close()
        self.http.close()


def wait_for_job(remote, record, receipt_path, timeout=None, pause=.5, retry_pause=5):
    """Poll a submitted job until it ends. No time limit unless one is passed. A status check that fails in transit (a busy proxy
    timing out) is only retried: the job is already submitted and the saved receipt keeps it from being submitted again."""
    deadline = time.monotonic() + timeout if timeout else None
    while remote.status not in ('succeeded', 'failed', 'canceled', 'expired'):
        if deadline is not None and time.monotonic() >= deadline:
            raise BackendError('Comfy job timed out; its saved request can be resumed without resubmitting.')
        time.sleep(pause)
        try:
            remote.refresh()
        except httpx.TransportError:
            time.sleep(retry_pause)
            continue
        record['state'] = remote.status
        write_json(receipt_path, record)


def check_proxy(url, key=''):
    session = SdkSession(url, key)
    try:
        response = session.low.raw_request('GET', '/health', timeout=3)
        response.raise_for_status()
        if response.json().get('status') != 'healthy':
            raise ValueError('Unexpected proxy health response')
    except Exception:
        raise ValueError('Cannot reach the Comfy API v2 proxy. Start comfy-api-proxy and check its URL in Settings.') from None
    finally:
        session.close()


def cancel_requests(directory, url, key=''):
    """Cancel only jobs whose IDs were durably recorded by this run."""
    session = SdkSession(url, key)
    try:
        for path in (Path(directory) / 'renders').glob('*/comfy-request.json'):
            record = read_json(path, {})
            if record.get('job_id') and record.get('state') not in ('succeeded', 'failed', 'canceled', 'expired'):
                try:
                    job = session.jobs.get(record['job_id']).cancel()
                    record['state'] = job.status
                    record['cancellation_requested'] = True
                    write_json(path, record)
                except Exception:
                    # Retain the request ID for explicit operator reconciliation.
                    record['cancellation_unconfirmed'] = True
                    write_json(path, record)
    finally:
        session.close()


def completion_media(directory, result, minimum):
    files = {}
    for kind in ('video', 'audio'):
        value = result.get(kind)
        if not value:
            if kind == 'video':
                raise ValueError('Missing completed video')
            continue
        path = Path(value)
        resolved = path.resolve()
        if not resolved.is_relative_to(directory.resolve()) or not resolved.is_file() or path.suffix == '.partial' or resolved.suffix == '.partial':
            raise ValueError('Completed media is outside the segment directory or incomplete')
        size = resolved.stat().st_size
        if not size:
            raise ValueError('Empty completed media')
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-i', str(resolved),
                        '-f', 'null', '-'], check=True, capture_output=True, timeout=assemble.PROBE_TIMEOUT_S)
        digest = hashlib.sha256()
        with resolved.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        files[kind] = {'path': str(resolved.relative_to(directory.resolve())),
                       'sha256': digest.hexdigest(), 'size': size}
    frames = assemble.probe_frames(result['video'])
    if frames < max(1, minimum):
        raise ValueError('Completed video is shorter than the required frames')
    return files, frames


def local_completion(directory, record, minimum):
    if record.get('state') != 'succeeded':
        return None
    try:
        manifest = read_json(directory / 'completion.json', {})
        result = read_json(directory / 'result.json', {})
        if (manifest.get('job_id') != record['job_id'] or manifest.get('fingerprint') != record['fingerprint']
                or manifest.get('endpoint') != record['endpoint'] or result.get('request_id') != record['job_id']
                or result.get('backend') != 'comfy_sdk_h3'):
            return None
        files, frames = completion_media(directory, result, minimum)
        if manifest.get('files') == files and manifest.get('frame_count') == frames:
            return result
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RuntimeError, subprocess.SubprocessError):
        pass
    return None


# Raw clip quality: "standard" keeps the workflow as shipped. The studio options switch the VideoHelperSuite save node to a
# near-lossless (ProRes 4444) or mathematically lossless (FFV1) file with the audio inside; the final video is still encoded
# down from these by ffmpeg at assembly, so only the raw clips get larger.
CLIP_QUALITIES = {'standard': None, 'prores': ('video/ProRes', {'profile': '4444'}), 'lossless': ('video/ffv1-mkv', {})}
H264_ONLY_INPUTS = ('pix_fmt', 'crf')
EXTENSIONS = {'video/mp4': '.mp4', 'video/quicktime': '.mov', 'video/x-matroska': '.mkv', 'video/webm': '.webm',
              'audio/flac': '.flac', 'audio/x-flac': '.flac', 'audio/wav': '.wav', 'audio/x-wav': '.wav',
              'audio/mpeg': '.mp3', 'audio/mp4': '.m4a', 'audio/ogg': '.ogg'}


def studio_node_id(builder_map):
    return builder_map['targets'].get('video_prefix', {}).get('node')


def studio_graph(graph, builder_map, quality):
    """A copy of the built graph whose VideoHelperSuite save node writes the studio-quality clip."""
    if quality not in CLIP_QUALITIES or CLIP_QUALITIES[quality] is None:
        return graph
    node_id = studio_node_id(builder_map)
    node = graph.get(node_id) if node_id else None
    if not node or node.get('class_type') != 'VHS_VideoCombine':
        raise BackendError('Studio-quality clips need the workflow\'s VideoHelperSuite save node (VHS_VideoCombine); this workflow has none.')
    fmt, extra = CLIP_QUALITIES[quality]
    graph = json.loads(json.dumps(graph))
    inputs = {k: v for k, v in graph[node_id]['inputs'].items() if k not in H264_ONLY_INPUTS}
    graph[node_id]['inputs'] = {**inputs, 'format': fmt, **extra}
    return graph


def media_suffix(output, default):
    """The real file extension for a returned output, so a FLAC or ProRes file is never named .wav or .mp4."""
    return EXTENSIONS.get(str(getattr(output, 'content_type', '')).split(';')[0].strip().lower()) \
        or Path(str(getattr(output, 'name', ''))).suffix.lower() or default


class ComfySdkH3Backend(LocalH3Backend):
    name = 'comfy_sdk_h3'
    clip_quality = 'standard'          # set per production by open_render

    def capabilities(self):
        card = super().capabilities()
        return {**card, 'backend': self.name, 'display_name': 'H3 / official Comfy SDK (local proxy)'}

    def open_render(self, **run):
        self.directory = Path(run['out_dir'])
        self.directory.mkdir(parents=True, exist_ok=True)
        self.builder = WorkflowBuilder.load(run.get('map_path'), run.get('root'))
        self.url = validate_proxy_url(run['comfy_sdk_url'])
        self.timeout = run.get('timeout_s')        # None: a local render may take as long as it needs; the operator can cancel
        self.clip_quality = run.get('clip_quality') or 'standard'
        if self.clip_quality not in CLIP_QUALITIES:
            raise BackendError('Unknown clip quality')
        self.session = SdkSession(self.url, run.get('comfy_sdk_key', ''))

    def render_segment(self, **job):
        seg_id = identifier(job['segment_id'])
        directory = self.directory / seg_id
        directory.mkdir(parents=True, exist_ok=True)
        receipt_path = directory / 'comfy-request.json'
        # Binding the receipt to exact inputs prevents accidental reuse for a new job.
        digest = hashlib.sha256(json.dumps({k:v for k,v in job.items() if k not in ('images', 'song')},
                                         sort_keys=True).encode())
        for _, path in job.get('images') or []:
            digest.update(Path(path).read_bytes())
        digest.update(Path(job['song']).read_bytes())
        digest.update(json.dumps(self.builder.base, sort_keys=True).encode())
        digest.update(json.dumps(self.builder.map, sort_keys=True).encode())
        if self.clip_quality != 'standard':
            digest.update(('clip_quality=' + self.clip_quality).encode())       # standard keeps older fingerprints valid
        fingerprint = digest.hexdigest()
        record = read_json(receipt_path, {})
        if record:
            if record.get('fingerprint') != fingerprint or record.get('endpoint') != self.url:
                raise BackendError('Saved Comfy request has different inputs. Refusing a new submission.')
            if not record.get('job_id'):
                raise BackendError('Comfy submission outcome is unknown. Inspect comfy-request.json and the proxy; do not resubmit.')
            completed = local_completion(directory, record, job['gen_frames'])
            if completed is not None:
                return completed
            remote = self.session.jobs.get(record['job_id'])
        else:
            audio = directory / 'passage.wav'
            slice_audio(job['song'], audio, job['audio_start_s'], job['audio_end_s'] - job['audio_start_s'])
            files = {}
            images = []
            for index, (_, path) in enumerate(job.get('images') or []):
                name = f'image-{index}.png'
                files[name] = Path(path)
                images.append(name)
            files['passage.wav'] = audio
            prompt = job['prompt']
            if job.get('cast'):
                from .engine.backends.local_h3 import normalize_h3_prompt
                prompt = normalize_h3_prompt(prompt, job['cast'])
            graph, _ = self.builder.build(prompt=prompt, duration_input=job['duration_input'],
                seed=job['seed'], width=job['width'], height=job['height'], steps=int(self.builder.map.get('default_steps', 20)),
                image_files=images, audio_files=['passage.wav'],
                video_prefix=f"mondo/{job['slug']}/{seg_id}", audio_prefix=f"mondo/{job['slug']}/{seg_id}_diegetic")
            graph = studio_graph(graph, self.builder.map, self.clip_quality)
            # Only replace the explicit loader widgets generated by the injection map.
            for spec_name in ('image_refs', 'audio_refs'):
                spec = self.builder.map[spec_name]
                for node in graph.values():
                    if node.get('class_type') == spec['loader_class']:
                        value = node.get('inputs', {}).get(spec['loader_field'])
                        if isinstance(value, str) and value in files:
                            asset = self.session.assets.from_file(files[value])
                            node['inputs'][spec['loader_field']] = asset.as_reference()
            write_json(directory / 'workflow.json', graph)
            record = {'backend': self.name, 'endpoint': self.url, 'sdk_revision': SDK_REVISION,
                      'fingerprint': fingerprint, 'idempotency_key': str(uuid.uuid4()),
                      'state': 'submitting', 'submitted_at': time.time()}
            # Persist BEFORE dispatch: even a killed process cannot silently submit twice.
            write_json(receipt_path, record)
            try:
                remote = self.session.submit(graph, record['idempotency_key'])
            except Exception:
                record['state'] = 'unknown'
                write_json(receipt_path, record)
                raise BackendError('Comfy submission did not return a usable receipt. It may be running. '
                                   'Inspect comfy-request.json and the proxy before generating again.') from None
            record.update(job_id=remote.id, state=remote.status)
            write_json(receipt_path, record)
        wait_for_job(remote, record, receipt_path, self.timeout)
        record['state'] = remote.status
        write_json(receipt_path, record)
        if remote.status != 'succeeded':
            raise BackendError(f'Comfy job {remote.id} ended {remote.status}; no replacement generation submitted.')
        (directory / 'completion.json').unlink(missing_ok=True)
        result = {'video': '', 'audio': '', 'request_id': remote.id, 'backend': self.name}
        for kind, default in (('video', '.mp4'), ('audio', '.wav')):
            candidates = [o for o in remote.outputs if o.content_type.startswith(kind + '/')]
            if not candidates:
                if kind == 'video':
                    raise BackendError('Comfy job returned no video output')
                continue
            # Prefer the mapped primary video/audio saver; ignore provider filenames. In studio mode the primary
            # video is the VideoHelperSuite file; if the job did not return it, fall back and say so.
            target_name = 'savevideo_prefix' if kind == 'video' else 'audio_prefix'
            target = self.builder.map['targets'].get(target_name, {}).get('node')
            if kind == 'video' and self.clip_quality != 'standard':
                studio = next((o for o in candidates if o.node_id == studio_node_id(self.builder.map)), None)
                if studio is None:
                    result['clip_quality_note'] = 'Studio-quality clip was not returned; the standard clip was used.'
                target = studio.node_id if studio else target
            output = next((o for o in candidates if o.node_id == target), candidates[0])
            suffix = media_suffix(output, default)
            destination = directory / (kind + suffix)
            partial = directory / (kind + suffix + '.partial')
            # Re-download instead of trusting files left by an interrupted transfer.
            output.to_file(partial)
            if not partial.stat().st_size:
                raise BackendError('Comfy returned an empty media asset')
            partial.replace(destination)
            result[kind] = str(destination)
        result['clip_quality'] = self.clip_quality
        write_json(directory / 'result.json', result)
        try:
            files, frames = completion_media(directory, result, job['gen_frames'])
        except (OSError, ValueError, subprocess.SubprocessError):
            return result
        write_json(directory / 'completion.json', {'job_id': remote.id, 'fingerprint': fingerprint,
                   'endpoint': self.url, 'files': files, 'frame_count': frames})
        return result

    def close_render(self):
        if getattr(self, 'session', None):
            self.session.close()
