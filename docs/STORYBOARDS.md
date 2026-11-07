# Storyboards

Music Video and Ident / Credits each have their own optional **Storyboard** editor.
Add up to 24 storyboard images (64 MB combined after upload), or add text panels.
Adding images preserves existing panel directions. Actor and renderer reference images remain separate. Storyboards are off by default.

Choose **Narrative** to extract actions, story beats and mood, or **Visual direction**
to extract composition, framing and lighting. Preview interpretation, review the
configured vision provider's estimated charge, then start it. This makes one vision
call using the existing per-call estimate. Images go to that configured provider.
There are no automatic interpretation retries. No new models are installed.

When it finishes, refresh Saved interpretations and load the result for review.
Each panel shows its source image and editable direction. Move panels up/down,
remove them, or add text panels. A sheet containing several panels may produce
several directions referencing the same source image. Loading a result leaves
**Use this storyboard** unchecked so you can review it before use.

**Humanize directions** previews local cleanup of common AI clichés in the current
panels. The **Humanize directions** checkbox applies the same cleanup to a new
vision interpretation; it is off by default. Review the resulting text before
using it, since a phrase can carry a meaning the cleanup misses or removes.

Check **Use this storyboard**, then preview your video or ident. Music video panels
are spread in order across the existing planned shots, with approximately equal
numbers of shots per panel. Preview shows their start times. More panels than shots
is rejected: combine panels or reduce their number. Musical timing, casting and
mouth/motion checks remain authoritative. Ident panels instead divide its existing
4–12 second duration into ordered time ranges, allowing several beats within a short
clip. Ident style and storyboard drafts are independent of the music video form.

Visual direction is descriptive guidance, not exact image replication. Storyboard
images are analyzed by vision; they are not added to the renderer's actor slots.
Existing actor sheets supply identity. Direction adherence and lettering accuracy
still depend on the selected writer and renderer; this release was verified with
mock services, not a real visual-quality comparison.

Ident already accepted multiple uploads. **Use all reference images together** now
passes them all through the existing ensemble casting controls. Off preserves the
one-reference default. On rejects selections above the renderer's supported limit;
the total actor/reference limit is nine.

## Agents

1. Upload images with `upload_media(kind="reference", path=...)` or CLI
   `upload reference PATH`. Keep upload IDs in the desired reading order.
2. Call `preview_production` (CLI `preview request.json`) with:

   ```json
   {"kind":"storyboard","direction":"A journey from dusk to dawn",
    "storyboard":{"mode":"narrative","images":["UPLOAD_ID.png"]}}
   ```

3. Review cost and service availability. Start the accepted quote using the normal
   consent flow. Poll status; cancellation uses the existing cancel tool.
4. List results with `inspect_studio(kind="storyboards")` or CLI `storyboards`.
   Read one with `inspect_storyboard(run_id)` or CLI `storyboard-result RUN_ID`.
   For opt-in cleanup during interpretation, set `storyboard.humanize: true` in
   the storyboard preview request. To preview cleanup of existing panels, call
   `humanize_storyboard(panels)` or CLI `humanize-storyboard PANELS_JSON_FILE`.
   This is local and free; review/edit the returned panels before use.
5. Edit the returned panels, then include the following in a video/ident request:

   ```json
   {"storyboard":{"enabled":true,"mode":"narrative","images":["UPLOAD_ID.png"],
     "panels":[{"image":"UPLOAD_ID.png","direction":"The cast walks toward the sunrise."}]}}
   ```

   Text-only panels may use `image: ""` and an empty images list. Set
   `ident_all_references: true` for all attached ident references.
6. Inspect the returned `storyboard.passages` alignment before starting production.
   Review the final video through the existing output inspection/download tools.

REST equivalents: `POST /api/storyboards/humanize` (JSON panel array), `POST /api/quote`, `POST /api/start`, `GET /api/status`,
`GET /api/storyboards`, `GET /api/storyboards/{run_id}`. These cover the same
preview/action/review/recovery flow as the GUI. Editing is local draft editing;
there is no extra server mutation or approval endpoint.

## Recovery and privacy

Interpretation results persist under their operation's private run directory.
Recover a completed interpretation from the result list after a reload. Failed
interpretations retain the raw response when available; inspect operation logs and
`storyboard-response.txt` before explicitly requesting another call. Use **Inspect saved response**,
`inspect_storyboard(run_id, raw_response=true)`, or CLI `storyboard-result RUN_ID --raw-response`
to retrieve it without another model call.
Video/ident requests snapshot the reviewed panels; saved alignment and prompts are
bound together for the existing supported resume workflow; changed alignment is rejected on resume. Failed interpretation
calls are not resumable renderer jobs.

Drafts persist with the existing saved project. Source images remain in private
uploads. Production packages do not copy storyboard images or storyboard metadata
into demo receipts. Generated prompts and rendered video can still describe/show
the storyboard content; review any package before sharing it.
