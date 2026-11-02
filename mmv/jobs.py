"""One active operation, cancellable child processes, and durable status."""
from __future__ import annotations

import logging
import os
import re
import unicodedata
import signal
import subprocess
import threading
import time
import uuid
from pathlib import Path

from .storage import identifier, read_json, write_json


def output_run_id(store, request, now=None):
    """Readable production folder with a bounded safe name and collision suffix."""
    song = request.get('song') or ''
    upload = read_json(store.home / 'uploads' / (Path(song).name + '.metadata.json'), {}) if song else {}
    title = upload.get('name') or request.get('title') or request.get('kind') or 'video'
    title = Path(str(title).replace('\\', '/')).stem
    ascii_title = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode().lower()
    slug = re.sub(r'[^a-z0-9]+', '_', ascii_title).strip('_')[:36] or 'video'
    stamp = time.strftime('%Y-%m-%d_%H%M%S', time.localtime(time.time() if now is None else now))
    base = f'{slug}_{stamp}'
    candidate, count = base, 2
    while (store.home / 'runs' / candidate).exists():
        suffix = f'-{count}'
        candidate = base[:64 - len(suffix)] + suffix
        count += 1
    return identifier(candidate)


def job_run_id(store, kind, label='', now=None):
    """Readable folder for a job's own record (log, result): what it is, then what it was for, then the date and time."""
    return output_run_id(store, {'title': f'{kind} {Path(str(label).replace(chr(92), "/")).stem}'.strip()}, now=now)


def upload_name(store, song):
    """The original file name of an uploaded song, for readable job folders (empty when unknown)."""
    return read_json(store.home / 'uploads' / (Path(song).name + '.metadata.json'), {}).get('name') or '' if song else ''


class BusyError(ValueError):
    pass


class Cancelled(Exception):
    pass


class JobContext:
    def __init__(self, manager, record):
        self.manager, self.record = manager, record
        self.cancelled = threading.Event()
        self.log_path = manager.store.home / "runs" / record["id"] / "operation.log"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def check(self):
        if self.cancelled.is_set():
            raise Cancelled("Operation cancelled. Remote work already submitted may still be billed.")

    def update(self, message, progress=None, **fields):
        with self.manager.lock:
            self.record.update(message=message, **fields)
            if progress is not None:
                self.record["progress"] = progress
            write_json(self.manager.status_path, self.record)
            with self.log_path.open("a", encoding="utf-8") as stream:
                stream.write(message + "\n")
        self.manager.notify(dict(self.record), log_line=message)

    def wait(self, seconds):
        if self.cancelled.wait(seconds):
            self.check()

    def command(self, argv, *, env=None, progress_path=None, cwd=None):
        self.check()
        kwargs = {"start_new_session": True} if os.name != "nt" else {
            "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        proc_env = {**os.environ, **(env or {}), "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        with self.log_path.open("ab") as log:
            process = subprocess.Popen([str(x) for x in argv], stdout=log,
                                       stderr=log, env=proc_env, cwd=cwd, **kwargs)
            try:
                last_progress = None
                while process.poll() is None:
                    if progress_path and progress_path.exists():
                        current_progress = read_json(progress_path)
                        if current_progress != last_progress:
                            self.update(**current_progress)
                            last_progress = current_progress
                    if self.cancelled.wait(0.2):
                        if os.name == "nt":
                            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                           capture_output=True, timeout=10)
                        else:
                            os.killpg(process.pid, signal.SIGTERM)
                        try:
                            process.wait(timeout=30)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                        self.check()
                if process.returncode:
                    detail = None
                    try:
                        if self.log_path and self.log_path.exists():
                            with self.log_path.open("rb") as stream:
                                stream.seek(max(0, self.log_path.stat().st_size - 16000))
                                lines = [ln.strip() for ln in stream.read().decode("utf-8", errors="replace").splitlines() if ln.strip()]
                            for ln in reversed(lines):
                                if any(token in ln for token in ("Error:", "Exception:", "failed:", "MISSING:", "FAILED:")):
                                    detail = ln
                                    break
                            if not detail and lines:
                                detail = lines[-1]
                    except Exception:
                        pass
                    if detail:
                        raise ValueError(f"Media command failed: {detail}")
                    raise ValueError("Media command failed; see the operation log")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
        self.check()


# Operations that only work on this computer: an interruption submitted nothing anywhere, and their results are published
# only when complete (re-encodes and caption assembly keep the finished video until a verified new one replaces it).
LOCAL_KINDS = ("reassemble", "captions", "export", "prompt_check", "stems")


def interrupted_message(kind):
    if kind in LOCAL_KINDS:
        return "The application stopped during this operation. Nothing finished was replaced; start it again when ready."
    return "Application stopped during this operation. Check remote request IDs before generating again."


class Jobs:
    def __init__(self, store):
        self.store = store
        self.lock = threading.RLock()
        self.active = None
        self.worker = None
        self.subscribers = []
        self.on_settled = self.on_idle = lambda record: None   # the queue records its ticket, then starts the next
        self.status_path = store.home / "operation.json"
        self.last = read_json(self.status_path, {"state": "idle"})
        if self.last.get("state") in ("running", "cancelling", "interrupted"):   # interrupted: re-word records saved earlier
            self.last.update(state="interrupted", message=interrupted_message(self.last.get("kind")))
            write_json(self.status_path, self.last)

    def subscribe(self, callback):
        with self.lock:
            self.subscribers.append(callback)
        def unsubscribe():
            with self.lock:
                if callback in self.subscribers:
                    self.subscribers.remove(callback)
        return unsubscribe

    def notify(self, status, log_line=None):
        with self.lock:
            subs = list(self.subscribers)
        for sub in subs:
            try:
                sub(dict(status), log_line)
            except Exception:
                pass

    def _hook(self, hook, record):
        try:
            hook(dict(record))
        except Exception as error:
            logging.getLogger("uvicorn.error").warning("Operation hook failed: %s", type(error).__name__)

    def require_idle(self):
        if self.active is not None:
            raise BusyError("An operation is active. Wait, cancel it, or add this production to the queue.")

    def reset(self):
        """Return a stopped operation's banner to ready; an active operation is left alone."""
        with self.lock:
            if self.active is not None:
                return dict(self.last)
            record = {"state": "idle", "message": "One idea. One production at a time.", "progress": 0}
            self.last = record
            write_json(self.status_path, record)
        self.notify(record)
        return dict(record)

    def status(self):
        with self.lock:
            return dict(self.last)

    def start(self, kind, function, *, run_id=None):
        with self.lock:
            self.require_idle()
            record = {"id": identifier(run_id) if run_id else uuid.uuid4().hex, "kind": kind, "state": "running",
                      "message": "Starting", "progress": 0, "started": time.time()}
            context = JobContext(self, record)
            self.active, self.last = context, record
            write_json(self.status_path, record)
            self.notify(record, log_line="Starting")

            def worker():
                try:
                    result = function(context)
                    context.check()
                    context.update("Complete", 100, state="complete", result=result)
                except Cancelled as exc:
                    context.update(str(exc), state="cancelled")
                except Exception as exc:
                    # Avoid exposing response bodies or credentials from external services.
                    message = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
                    for secret in self.store.secret_values():
                        message = message.replace(secret, "[redacted]")
                    context.update(message, state="failed")
                finally:
                    with self.lock:
                        record["finished"] = time.time()
                        write_json(self.store.home / "runs" / record["id"] / "operation.json", record)
                        write_json(self.status_path, record)
                        self.active = None
                        self._hook(self.on_settled, record)
                    self.notify(record)   # everyone hears this operation ended before another can begin
                    self._hook(self.on_idle, record)

            self.worker = threading.Thread(target=worker, daemon=True)
            self.worker.start()
            return dict(record)

    def cancel(self):
        with self.lock:
            if self.active:
                self.active.cancelled.set()
                self.active.update("Cancellation requested", state="cancelling")
            status = dict(self.last)
        self.notify(status, log_line="Cancellation requested")
        return status

    def shutdown(self):
        self.cancel()
        if self.worker:
            self.worker.join(timeout=10)
