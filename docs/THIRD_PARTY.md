# Dependencies and external services

The public application is licensed under Apache-2.0. Its dependencies remain
under their respective licenses; this project does not relicense them.

| Component | Role | License / provenance |
| --- | --- | --- |
| Open Actor Protocol 0.5.0 | Required actor protocol, signing, package verification and riders | MIT; pinned source commit in pyproject.toml; https://github.com/hodgemann/oap |
| cryptography (OAP dependency) | Ed25519 identities and signatures | See upstream distribution notices; https://github.com/pyca/cryptography |
| FastAPI / Starlette / Pydantic | Local web application | See installed dependency licenses |
| Uvicorn | Local HTTP server | See installed dependency license |
| python-multipart | Media upload parsing | See installed dependency license |
| Pillow | Reference-image decoding and metadata removal | See installed dependency license |
| MCP Python SDK (optional) | stdio agent tools | https://github.com/modelcontextprotocol/python-sdk; see upstream distribution notices |
| wavesurfer.js 7.10.1 (vendored: `webapp/vendor/wavesurfer/`) | Waveform display and draggable regions in the pre-generation score editor | BSD-3-Clause; copyright katspaugh and contributors; licence copy included; https://github.com/katspaugh/wavesurfer.js |
| Demucs (optional add-on, not bundled) | Instrument stem separation for the score editor | MIT; installed by the user with `pip install demucs`; model weights download once after approval; https://github.com/adefossez/demucs |
| openai-whisper (optional add-on, not bundled) | Optional lyrics detection | MIT; installed by the user with `pip install openai-whisper` or an existing Whisper Python is reused; model files download once after approval; https://github.com/openai/whisper |
| FFmpeg / ffprobe | External, user-installed media tools | Licenses depend on the user's build; no binary is bundled |
| ComfyUI, custom nodes and model files | Optional, user-installed local generation | Separate upstream terms; no copies bundled |
| Topaz | Optional, user-owned export tool or cloud API (api.topazlabs.com) | Separate vendor license/terms and credits; no copy bundled; the user's own API key |

Provider API documentation used to implement the hosted adapters and estimate
card, checked 2026-10-15:

- https://wavespeed.ai/docs/docs-api/minimax/minimax-h3-reference-to-video
- https://wavespeed.ai/docs/docs-api/bytedance/bytedance-seedance-2.0-text-to-video
- https://wavespeed.ai/docs/docs-api/bytedance/bytedance-seedance-2.5-text-to-video

Prices are estimates based on those dated pages and can change. The app does not
retry paid submissions automatically. Remote request IDs are saved with each
production. Always check the provider dashboard after an interrupted submission.

Laya inference modules are vendored from the Apache-2.0 upstream revision recorded
in `mmv/engine/validators/laya/VENDOR.md`. Model weights are not distributed.
NumPy, SciPy and Librosa provide audio analysis; Torch, Transformers and
Safetensors support Laya inference. Their distributions retain upstream notices.
The source extraction manifest records the authorized music-video source files
and the portability changes made to them.
