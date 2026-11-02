"""Browser smoke against temporary services when Chromium is already installed."""
import importlib.util
import os
import unittest
from pathlib import Path

from test_agent import LiveAppFixture


def _cached_chromium():
    roots = [Path.home() / '.cache/ms-playwright']
    if os.environ.get('PLAYWRIGHT_BROWSERS_PATH'):
        roots.insert(0, Path(os.environ['PLAYWRIGHT_BROWSERS_PATH']))
    if os.environ.get('LOCALAPPDATA'):
        roots.append(Path(os.environ['LOCALAPPDATA']) / 'ms-playwright')
    roots.append(Path.home() / 'Library/Caches/ms-playwright')
    patterns = (
        'chromium-*/chrome-linux*/chrome',
        'chromium-*/chrome-win*/chrome.exe',
        'chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium',
    )
    found = []
    for root in roots:
        if root.exists():
            for pattern in patterns:
                found.extend(root.glob(pattern))
    return found



def autosaved(page, action):
    """Run a settings change and wait for its own automatic save (the status line is cleared first)."""
    page.evaluate('() => { document.querySelector("#settings-autosave-status").textContent = ""; }')
    action()
    page.wait_for_function('() => document.querySelector("#settings-autosave-status").textContent.includes("Saved automatically")')


@unittest.skipUnless(importlib.util.find_spec('playwright') and importlib.util.find_spec('comfy_sdk')
                     and _cached_chromium(),
                     'optional Playwright, cached Chromium and SDK required')

def pick_cast(page, ids):
    """Choose the cast through the visible checkbox list (the native select is hidden)."""
    for box in page.locator('#cast-checkbox-list input[type=checkbox]').all():
        box.set_checked(box.get_attribute('value') in ids)


class BrowserTests(LiveAppFixture, unittest.TestCase):
    def test_public_oap_collection_is_on_demand_and_stages_for_review(self):
        from playwright.sync_api import sync_playwright, expect
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=str(_cached_chromium()[-1]))
            page = browser.new_page()
            requests = []
            listing = {"source": "https://github.com/hodgemann/oap-actors", "license": "CC-BY-4.0",
                       "attribution": "Maximum Goose Laboratory", "index_sha256": "a" * 64,
                       "actors": [{"id": "human_female_baker_01", "name": "Baker", "bytes": 4064775,
                                   "oap_version": "0.5.0", "signer": {"public_key": "test-signer"}, "installed": False}]}
            staged = {"filename": "checked.oap", "manifest": {
                "identity": {"actor_id": "human_female_baker_01", "display_name": "Baker"},
                "agent": {"public_key": "test-signer"}, "rider": {"content": {"violence": "action"}}},
                "verification": {"ok": True, "signature_valid": True, "agent_known": False}}
            page.route('**/api/oap-collection/stage', lambda route: (requests.append('stage'), route.fulfill(json=staged)))
            page.route('**/api/oap-collection', lambda route: (requests.append('check'), route.fulfill(json=listing)))
            try:
                page.goto(self.url)
                expect(page.locator('#oap-collection-fold')).to_have_count(1)
                self.assertEqual(requests, [])
                page.locator('.nav[data-panel="actors"]').click()
                page.locator('#oap-collection-fold summary').click()
                page.locator('#check-oap-collection').click()
                expect(page.locator('#oap-collection-list')).to_contain_text('OAP 0.5.0')
                self.assertEqual(requests, ['check'])
                page.locator('#oap-collection-list button').click()
                expect(page.locator('#oap-report-card')).to_contain_text('test-signer')
                expect(page.locator('#oap-import-form')).to_be_visible()
                expect(page.locator('#oap-import-form [name=accept_unknown]')).not_to_be_checked()
                self.assertEqual(requests, ['check', 'stage'])
            finally:
                browser.close()

    def test_music_video_panel_progress_blur_partial_review_and_restore(self):
        from playwright.sync_api import sync_playwright, expect
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=str(_cached_chromium()[-1]))
            page = browser.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            try:
                page.goto(self.url)
                first = page.locator('[data-component-id="card-track-direction"]')
                second = page.locator('[data-component-id="card-cast-staging"]')
                expect(first.locator('.progress-cue')).to_have_text('Needs 2')
                expect(second.locator('.progress-cue')).to_have_text('Optional')
                page.wait_for_function('() => document.querySelector("#video-form .song-input").onchange !== null')
                page.locator('#video-form textarea[name=direction]').fill('A sunlit coastline in motion.')
                expect(first.locator('.progress-cue')).to_have_text('Needs 1')
                page.locator('#video-form .song-input').set_input_files(str(self.song))
                expect(first.locator('.song-receipt')).to_contain_text('Uploaded:')
                page.locator('#panel-video h1').click()
                expect(first.locator('.progress-toggle')).to_have_attribute('aria-expanded', 'false')
                expect(first.locator('.progress-cue')).to_have_text('✓ Done')
                first.locator('.progress-options').click()
                expect(first.locator('.progress-toggle')).to_have_attribute('aria-expanded', 'true')
                expect(first.locator('textarea[name=direction]')).to_be_hidden()
                expect(first.locator('input[name=title]')).to_be_visible()
                first.locator('.progress-toggle').click()
                first.locator('.progress-toggle').click()
                first.locator('input[name=title]').fill('Optional title')
                page.locator('#panel-video h1').click()
                expect(first.locator('.progress-toggle')).to_have_attribute('aria-expanded', 'true')
                first.locator('textarea[name=direction]').fill('')
                expect(first.locator('.progress-cue')).to_have_text('Needs 1')
                first.locator('.progress-toggle').click()
                expect(first.locator('.progress-cue')).to_have_text('Needs 1')
                page.evaluate('''async () => (await import('/js/panel_progress.js')).showPanelForQuoteError('This renderer needs a reference in every passage. Choose an actor/image and Reference policy: All')''')
                self.assertTrue(page.evaluate('document.querySelector("#director-camera").open'))
                second.locator('.progress-toggle').click()
                expect(second.locator('.progress-cue')).to_have_text('✓ Reviewed')
                page.locator('#director-format summary').click()
                expect(page.locator('#director-format .progress-cue')).to_have_text('✓ Reviewed')
                expect(page.locator('[data-component-id="director-control-room"] .progress-cue').first).to_have_text('1 of 4 reviewed')
                page.wait_for_timeout(500)
                page.reload()
                expect(first.locator('.progress-toggle')).to_have_attribute('aria-expanded', 'false')
                expect(second.locator('.progress-cue')).to_have_text('✓ Reviewed')
                expect(page.locator('#director-format .progress-cue')).to_have_text('✓ Reviewed')
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_panel_progress_setting_and_renderer_requirement(self):
        from playwright.sync_api import sync_playwright, expect
        self.fixture.client.patch('/api/settings', json={'auto_collapse_panels': False}).raise_for_status()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=str(_cached_chromium()[-1]))
            page = browser.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#video-form .song-input").onchange !== null')
                first = page.locator('[data-component-id="card-track-direction"]')
                page.locator('#video-form .song-input').set_input_files(str(self.song))
                expect(first.locator('.song-receipt')).to_contain_text('Uploaded:')
                first.locator('textarea[name=direction]').fill('A moving coast at sunrise.')
                page.locator('#panel-video h1').click()
                expect(first.locator('.progress-cue')).to_have_text('✓ Done')
                expect(first.locator('.progress-toggle')).to_have_attribute('aria-expanded', 'true')
                page.locator('#director-camera summary').click()
                page.locator('#director-camera [name=ref_policy]').select_option('single_subject')
                page.locator('#video-form [name=backend]').select_option('wavespeed')
                expect(page.locator('[data-component-id="card-cast-staging"] .progress-cue')).to_have_text('Needs 1')
                cue = page.locator('[data-component-id="card-cast-staging"] .progress-cue')
                expect(cue).to_have_attribute('tabindex', '0')
                expect(cue).to_have_attribute('aria-label', 'Needs: Cast actor or reference image')
                expect(page.locator('#video-form .cast-picker').locator('..')).to_have_class('field-needed')
                expect(page.locator('#director-camera .progress-cue')).to_have_text('Needs 1')
                page.locator('#director-camera [name=ref_policy]').select_option('all')
                expect(page.locator('#director-camera .progress-cue')).to_have_text('✓ Done')
                page.locator('#panel-video h1').click()
                self.assertTrue(page.evaluate('document.querySelector("#director-camera").open'))
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_storyboard_drafts_reorder_reload_and_keep_forms_independent(self):
        from playwright.sync_api import sync_playwright, expect
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=str(_cached_chromium()[-1]))
            page = browser.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            try:
                page.goto(self.url)
                page.wait_for_selector('#video-form .storyboard-editor')
                editor = page.locator('#video-form .storyboard-editor')
                editor.locator('summary').click()
                editor.get_by_role('button', name='Add text panel').click()
                editor.locator('textarea').fill('Walk toward the trees')
                editor.get_by_role('button', name='Add text panel').click()
                editor.locator('textarea').nth(1).fill('Turn toward the moon')
                editor.get_by_role('button', name='Move up').nth(1).click()
                expect(editor.locator('textarea').first).to_have_value('Turn toward the moon')
                editor.locator('[name=storyboard_enabled]').check()
                page.wait_for_timeout(1200)
                page.reload()
                page.wait_for_function("() => document.querySelector('#video-form [name=storyboard_draft]')?.value.includes('Turn toward the moon')")
                page.locator('#video-form .storyboard-editor summary').click()
                expect(editor.locator('textarea').first).to_have_value('Turn toward the moon')
                expect(editor.locator('[name=storyboard_enabled]')).to_be_checked()
                expect(page.locator('#ident-form .storyboard-panel')).to_have_count(0)
                self.assertFalse(errors, errors)
            finally:
                browser.close()


    def test_preview_adds_a_free_production_to_the_queue_tab(self):
        from playwright.sync_api import sync_playwright, expect
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=str(_cached_chromium()[-1]))
            page = browser.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelectorAll(".file-drop-target").length === 16')
                page.locator('#quick-start').click()
                page.locator('#quick-start-song').set_input_files({'name': 'queued song.wav', 'mimeType': 'audio/wav', 'buffer': self.song.read_bytes()})
                expect(page.locator('#preview-dialog')).to_be_visible(timeout=60000)
                expect(page.locator('#add-to-queue')).to_be_visible()
                expect(page.locator('#consent')).not_to_be_checked()
                page.locator('#add-to-queue').click()
                expect(page.locator('#preview-dialog')).to_be_hidden()
                page.locator('.nav[data-panel=queue]').click()
                expect(page.locator('#queue-list .queue-ticket')).to_contain_text('queued song.wav')
                expect(page.locator('#queue-list .queue-ticket')).to_contain_text('local, free')
                expect(page.locator('#queue-state')).to_have_text('Paused · 1 waiting')
                expect(page.locator('#queue-start')).to_be_enabled()
                page.locator('#queue-list .queue-ticket button', has_text='Remove').click()
                expect(page.locator('#queue-state')).to_have_text('Nothing waiting')
                self.assertFalse(errors, errors)
            finally:
                browser.close()

    def test_quick_start_asks_for_a_song_then_opens_the_preview_without_instruments(self):
        from playwright.sync_api import sync_playwright, expect
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=str(_cached_chromium()[-1]))
            page = browser.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelectorAll(".file-drop-target").length === 16')
                page.locator('#quick-start').click()
                expect(page.locator('#quick-start-dialog')).to_be_visible()
                expect(page.locator('#quick-start-dialog')).to_contain_text('Select a song to begin')
                page.locator('#quick-start-song').set_input_files({'name': 'my song.wav', 'mimeType': 'audio/wav', 'buffer': self.song.read_bytes()})
                expect(page.locator('#preview-dialog')).to_be_visible(timeout=60000)
                self.assertEqual(page.locator('#video-form [name=title]').input_value(), 'my song')
                self.assertTrue(page.locator('#video-form [name=direction]').input_value())
                self.assertEqual(page.locator('#video-form [name=instrument_mode]').input_value(), 'off')
                self.assertEqual(page.locator('#video-form [name=subliminal_mode]').input_value(), 'off')
                expect(page.locator('#consent')).not_to_be_checked()
                page.locator('#preview-dialog .dialog-close').click()
                direction = page.locator('#video-form [name=direction]').input_value()
                page.locator('#quick-start').click()          # song already chosen: no dialog, same plan, kept direction
                expect(page.locator('#preview-dialog')).to_be_visible(timeout=60000)
                expect(page.locator('#quick-start-dialog')).not_to_be_visible()
                self.assertEqual(page.locator('#video-form [name=direction]').input_value(), direction)
                self.assertFalse(errors, errors)
            finally:
                browser.close()

    def test_start_fresh_confirms_then_clears_the_video_panel_but_keeps_the_renderer(self):
        from playwright.sync_api import sync_playwright, expect
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=str(_cached_chromium()[-1]))
            page = browser.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelectorAll(".file-drop-target").length === 16')
                page.locator('#video-form .song-input').set_input_files({'name': 'keep.wav', 'mimeType': 'audio/wav', 'buffer': self.song.read_bytes()})
                expect(page.locator('#video-form .song-receipt')).to_contain_text('Uploaded: keep.wav')
                page.locator('#video-form [name=title]').fill('Old title')
                page.locator('#video-form [name=direction]').fill('Old direction')
                backend = page.locator('#video-form [name=backend]').input_value()
                page.locator('#start-fresh').click()
                expect(page.locator('#start-fresh-dialog')).to_be_visible()
                page.locator('#start-fresh-cancel').click()
                self.assertEqual(page.locator('#video-form [name=title]').input_value(), 'Old title')
                page.locator('#start-fresh').click()
                page.locator('#start-fresh-confirm').click()
                expect(page.locator('#video-form [name=title]')).to_have_value('')
                expect(page.locator('#video-form [name=direction]')).to_have_value('')
                expect(page.locator('#cast-checkbox-list input:checked')).to_have_count(0)
                expect(page.locator('#video-form .song-receipt')).not_to_contain_text('keep.wav')
                expect(page.locator('#video-form .song-preview-wrap')).to_be_hidden()
                self.assertEqual(page.locator('#video-form [name=backend]').input_value(), backend)
                page.locator('#quick-start').click()          # no song any more: asks for one again
                expect(page.locator('#quick-start-dialog')).to_be_visible()
                self.assertFalse(errors, errors)
            finally:
                browser.close()

    def test_settings_save_automatically_without_a_save_button(self):
        from playwright.sync_api import sync_playwright, expect
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=str(_cached_chromium()[-1]))
            page = browser.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#video-form .song-input").onchange !== null')
                page.locator('.nav[data-panel=settings]').click()
                expect(page.get_by_role('button', name='Save settings', exact=True)).to_have_count(0)
                page.locator('input[name=render_timeout_minutes]').fill('45')
                page.locator('input[name=render_timeout_minutes]').press('Tab')
                expect(page.locator('#settings-autosave-status')).to_contain_text('Saved automatically')
                self.assertEqual(self.fixture.store.settings()['render_timeout_minutes'], 45)
                page.locator('input[name=render_timeout_minutes]').fill('50')
                page.locator('input[name=render_timeout_minutes]').press('Enter')
                page.wait_for_function('() => document.querySelector("#settings-autosave-status").textContent.includes("Saved automatically")')
                page.wait_for_timeout(300)
                self.assertEqual(self.fixture.store.settings()['render_timeout_minutes'], 50)
                self.assertFalse(errors, errors)
            finally:
                browser.close()

    def test_file_drop_uses_existing_upload_handlers_and_rejects_bad_files(self):
        from test_public_app import picture
        from playwright.sync_api import sync_playwright, expect

        def drop(page, selector, files):
            return page.evaluate('''({selector, files}) => {
              const input = document.querySelector(selector);
              const target = input.closest('label');
              const transfer = new DataTransfer();
              for (const item of files) transfer.items.add(new File([new Uint8Array(item.bytes)], item.name, {type: item.type}));
              target.dispatchEvent(new DragEvent('dragenter', {bubbles: true, dataTransfer: transfer}));
              const hovered = target.classList.contains('file-drop-hover');
              target.dispatchEvent(new DragEvent('drop', {bubbles: true, cancelable: true, dataTransfer: transfer}));
              return {hovered, cleared: !target.classList.contains('file-drop-hover'), names: [...input.files].map(file => file.name)};
            }''', {'selector': selector, 'files': files})

        image = {'name': 'one.png', 'type': 'image/png', 'bytes': list(picture())}
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=str(_cached_chromium()[-1]))
            page = browser.new_page()
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelectorAll(".file-drop-target").length === 16')
                song = {'name': 'dropped.wav', 'type': 'audio/wav', 'bytes': list(self.song.read_bytes())}
                result = drop(page, '#video-form .song-input', [song])
                self.assertTrue(result['hovered'] and result['cleared'])
                expect(page.locator('#video-form .song-receipt')).to_contain_text('Uploaded: dropped.wav')
                self.assertEqual(result['names'], ['dropped.wav'])
                for form in ('video-form', 'harvest-form', 'ident-form'):
                    selector = f'#{form} .refs-input'
                    second = {**image, 'name': 'two.png'}
                    drop(page, selector, [image, second])
                    expect(page.locator(f'#{form} .refs-receipt')).to_contain_text('two.png')
                    if form == 'video-form':
                        page.locator('#video-form .remove-ref').nth(1).click()
                        expect(page.locator('#video-form .refs-receipt code')).to_have_count(1)
                        expect(page.locator('#video-form .refs-receipt')).not_to_contain_text('two.png')
                        drop(page, selector, [image, second])
                        page.locator('#video-form .remove-ref').first.click()
                        expect(page.locator('#video-form .refs-receipt code')).to_have_count(1)
                        expect(page.locator('#video-form .refs-receipt')).not_to_contain_text('one.png')
                        page.locator('#video-form [name=backend]').select_option('wavespeed')
                        expect(page.locator('[data-component-id="card-cast-staging"] .progress-cue')).to_have_text('✓ Done')
                        page.locator('#video-form .clear-refs').click()
                        expect(page.locator('[data-component-id="card-cast-staging"] .progress-cue')).to_have_text('Needs 1')
                    self.assertEqual(drop(page, selector, [image])['names'], ['one.png'])
                    expect(page.locator(f'#{form} .refs-receipt')).to_contain_text('one.png')
                    bad = {'name': 'bad.txt', 'type': 'text/plain', 'bytes': [65]}
                    self.assertEqual(drop(page, selector, [bad])['names'], ['one.png'])
                    expect(page.locator(selector).locator('..').locator('.file-drop-error')).to_contain_text('Unsupported')
                    self.assertEqual(drop(page, selector, [image] * 10)['names'], ['one.png'])
                    expect(page.locator(selector).locator('..').locator('.file-drop-error')).to_contain_text('at most nine')
                for selector, filename, mime in (
                    ('#opp-file', 'prop.opp', 'application/octet-stream'),
                    ('#oap-file', 'actor.oap', 'application/octet-stream'),
                    ('#agreement-file', 'agreement.json', 'application/json'),
                    ('#style-import-file', 'style.json', 'application/json')):
                    result = drop(page, selector, [{'name': filename, 'type': mime, 'bytes': [65]}])
                    self.assertEqual(result['names'], [filename])
                    self.assertEqual(drop(page, selector, [image])['names'], [filename])
                page.locator('.nav[data-panel=actors]').click()
                page.locator('#actor-form [name=actor_id]').fill('drop_actor')
                page.locator('#actor-form [name=name]').fill('Drop Actor')
                page.locator('#actor-form [name=description]').fill('Test portrait')
                drop(page, '#actor-form [name=reference]', [image])
                page.locator('#actor-form').get_by_role('button', name='Create actor').click()
                expect(page.locator('#actor-list')).to_contain_text('Drop Actor')
                expect(page.locator('#actor-list article').filter(has_text='Drop Actor').locator('.actor-desc-count')).to_have_text('13 chars')
                expect(page.locator('#instrument-library-fold')).to_have_count(0)
                page.locator('#opp-library-fold summary').click()
                expect(page.locator('#opp-library')).to_contain_text('Electric guitar')
                page.evaluate('''() => {
                  document.querySelector('#oap-import-form').hidden = false;
                  document.querySelector('#oap-report-card').hidden = false;
                  document.querySelector('#opp-import-form').hidden = false;
                  document.querySelector('#opp-report').hidden = false;
                }''')
                drop(page, '#oap-file', [{'name': 'next.oap', 'type': 'application/octet-stream', 'bytes': [66]}])
                drop(page, '#opp-file', [{'name': 'next.opp', 'type': 'application/octet-stream', 'bytes': [66]}])
                expect(page.locator('#oap-import-form')).to_be_hidden()
                expect(page.locator('#oap-report-card')).to_be_hidden()
                expect(page.locator('#opp-import-form')).to_be_hidden()
                expect(page.locator('#opp-report')).to_be_hidden()
                page.evaluate('''() => {
                  const label = document.querySelector('#actor-form [name=reference]').closest('label');
                  const transfer = new DataTransfer();
                  transfer.items.add(new File(['x'], 'one.png', {type: 'image/png'}));
                  label.dispatchEvent(new DragEvent('dragenter', {bubbles: true, dataTransfer: transfer}));
                  label.dispatchEvent(new DragEvent('dragleave', {bubbles: true, relatedTarget: document.body, dataTransfer: transfer}));
                }''')
                expect(page.locator('#actor-form [name=reference]').locator('..')).not_to_have_class('file-drop-hover')
                page.route('**/api/upload/reference', lambda route: route.abort())
                drop(page, '#harvest-form .refs-input', [image])
                expect(page.locator('#harvest-form .refs-receipt')).to_contain_text('Upload failed')
                page.unroute('**/api/upload/reference')
                page.locator('#style-import-file').set_input_files({'name': 'chosen.json', 'mimeType': 'application/json', 'buffer': b'{}'})
                self.assertEqual(page.locator('#style-import-file').evaluate('(node) => node.files[0].name'), 'chosen.json')
            finally:
                browser.close()

    def test_actor_cards_collapse_and_preview_filename_is_text(self):
        from test_public_app import picture
        from playwright.sync_api import sync_playwright, expect
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=str(_cached_chromium()[-1]))
            page = browser.new_page()
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#actor-form .progress-toggle") !== null')
                page.locator('.nav[data-panel=actors]').click()
                expect(page.get_by_role('heading', name='Create an actor')).to_have_count(1)
                for card in ('#actor-form', '[data-component-id="oap-import-card"]', '#agreements-card'):
                    toggle = page.locator(f'{card} > .card-title .progress-toggle')
                    expect(toggle).to_have_attribute('aria-expanded', 'true')
                    toggle.click()
                    expect(toggle).to_have_attribute('aria-expanded', 'false')
                    expect(page.locator(f'{card} > .progress-body')).to_be_hidden()
                    toggle.click()
                    expect(page.locator(f'{card} > .progress-body')).to_be_visible()
                filename = '<img src=x onerror=alert(1)>.png'
                page.locator('#actor-form [name=reference]').set_input_files({
                    'name': filename, 'mimeType': 'image/png', 'buffer': picture()
                })
                preview = page.locator('#actor-ref-preview')
                expect(preview).to_be_visible()
                expect(preview.locator('img')).to_have_count(1)
                expect(preview.locator('.actor-ref-name')).to_have_text(filename)
                page.evaluate('document.querySelector("#actor-form").reset()')
                expect(preview).to_be_hidden()
                page.route('**/api/styles', lambda route: route.fulfill(json=[{
                    'id': 'forensic_test', 'name': 'Forensic Test', 'direction': 'Muted light',
                    'style_card': 'STYLE CARD: Forensic Test\nAxis 1: muted light'
                }]))
                page.evaluate('async () => (await import("/js/library.js")).loadStyles()')
                page.locator('.nav[data-panel=styles]').click()
                expect(page.locator('#style-list .style-card-shown')).to_be_visible()
                expect(page.locator('#style-list .style-card-shown')).to_have_text('Axis 1: muted light')
                fold = page.locator('#style-list .style-card-fold')
                expect(fold.locator('.style-full-text')).to_be_hidden()
                fold.locator('summary').click()
                expect(fold.locator('.style-full-text')).to_be_visible()
                expect(fold.locator('.style-full-text')).to_have_text('Muted light')
                fold.locator('summary').click()
                expect(fold.locator('.style-full-text')).to_be_hidden()
            finally:
                browser.close()

    def test_opp_inspection_import_and_instrument_choice(self):
        from mmv import actors
        from tests.test_opp_props import package as make_opp_package
        from test_public_app import picture
        from playwright.sync_api import sync_playwright, expect
        source = make_opp_package(self.home, signed=True)
        actors.create_actor(self.fixture.store, 'guitarist', 'Guitarist', 'Test actor', picture())
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=str(_cached_chromium()[-1]))
            page = browser.new_page()
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#video-form .song-input").onchange !== null')
                page.locator('[data-panel="actors"]').click()
                page.locator('#opp-library-fold summary').click()
                page.locator('#opp-file').set_input_files(str(source))
                page.locator('#inspect-opp').click()
                expect(page.locator('#opp-report')).to_contain_text('blue-guitar')
                expect(page.locator('#opp-report')).to_contain_text('signature_valid')
                page.locator('#opp-import-form [name=accept_signer]').check()
                page.locator('#opp-import-form button').click()
                expect(page.locator('#opp-library')).to_contain_text('Blue Guitar')
                page.locator('[data-panel="video"]').click()
                form = page.locator('#video-form')
                pick_cast(page, ['guitarist'])
                form.locator('[name=instrument_mode]').select_option('perform')
                form.get_by_label('Guitarist instrument', exact=True).select_option('guitar')
                expect(form.locator('.instrument-props')).to_be_visible()
                form.locator('[name=instrument_prop_guitar]').select_option('blue-guitar')
                form.locator('[name=instrument_use_guitar]').fill('strumming strings')
                result = page.evaluate('''async () => {
                    const {instrumentsFromForm} = await import('/js/instruments.js');
                    const request = {actors: ['guitarist'], instrument_mode: 'perform'};
                    instrumentsFromForm(document.querySelector('#video-form'), request);
                    return request;
                }''')
                self.assertEqual(result['instrument_props'], {'guitar': 'blue-guitar'})
                self.assertEqual(result['instrument_prop_uses'], {'guitar': 'strumming strings'})
                self.assertNotIn('instrument_prop_guitar', result)
            finally:
                browser.close()

    def test_instrument_assignments_restore_by_actor_and_flat_fields_are_removed(self):
        from mmv import actors
        from test_public_app import picture
        from playwright.sync_api import sync_playwright, expect
        actors.create_actor(self.fixture.store, 'player_a', 'Player A', 'Overview', picture())
        actors.create_actor(self.fixture.store, 'player_b', 'Player B', 'Overview', picture())
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=str(_cached_chromium()[-1]))
            page = browser.new_page()
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#video-form .song-input").onchange !== null')
                form = page.locator('#video-form')
                expect(form.locator('.instrument-assignments')).to_be_hidden()
                expect(form.locator('.instrument-notice')).to_have_count(0)
                pick_cast(page, ['player_a', 'player_b'])
                form.locator('[name=instrument_mode]').select_option('perform')
                expect(form.locator('.instrument-notice')).to_have_count(0)
                form.get_by_label('Player B instrument', exact=True).select_option('keyboards')
                pick_cast(page, ['player_b'])
                expect(form.get_by_label('Player B instrument', exact=True)).to_have_value('keyboards')
                page.wait_for_timeout(800)
                page.reload()
                page.wait_for_function('() => document.querySelector("#video-form .song-input").onchange !== null')
                expect(form.get_by_label('Player B instrument', exact=True)).to_have_value('keyboards')
                result = page.evaluate('''async () => {
                    const {instrumentsFromForm} = await import('/js/instruments.js');
                    const request = {actors: ['player_b'], instrument_mode: 'perform', instrument_actor_0: 'keyboards', instrument_assignments_json: '{}'};
                    instrumentsFromForm(document.querySelector('#video-form'), request);
                    return request;
                }''')
                self.assertEqual(result['instrument_assignments'], {'player_b': 'keyboards'})
                self.assertTrue(result['instrument_references'])
                self.assertNotIn('instrument_assignments_json', result)
                self.assertNotIn('instrument_actor_0', result)
            finally:
                browser.close()

    def test_independent_dance_parts_follow_actor_and_restore(self):
        from mmv import actors
        from test_public_app import picture
        from playwright.sync_api import sync_playwright, expect
        actors.create_actor(self.fixture.store, 'dance_a', 'Dancer A', 'Overview', picture())
        actors.create_actor(self.fixture.store, 'dance_b', 'Dancer B', 'Overview', picture())
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=str(_cached_chromium()[-1]))
            page = browser.new_page()
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#video-form .song-input").onchange !== null')
                form = page.locator('#video-form')
                expect(form.locator('.dance-parts')).to_be_hidden()
                pick_cast(page, ['dance_a', 'dance_b'])
                form.locator('[name=dance_mode]').select_option('independent')
                form.get_by_label('Dancer B part', exact=True).select_option('bass')
                pick_cast(page, ['dance_b'])
                expect(form.get_by_label('Dancer B part', exact=True)).to_have_value('bass')
                page.wait_for_timeout(1200)
                page.reload()
                page.wait_for_function('() => document.querySelector("#video-form .song-input").onchange !== null')
                expect(form.locator('[name=dance_mode]')).to_have_value('independent')
                expect(form.get_by_label('Dancer B part', exact=True)).to_have_value('bass')
                result = page.evaluate("""async () => {
                    const { dancePartsFromForm } = await import('/js/dance.js');
                    const request = {actors: ['dance_b'], dance_mode: 'independent', dance_part_0: 'bass', dance_parts_json: '{}'};
                    dancePartsFromForm(document.querySelector('#video-form'), request);
                    return request;
                }""")
                self.assertEqual(result['dance_parts'], {'dance_b': 'bass'})
                self.assertNotIn('dance_parts_json', result)
                self.assertNotIn('dance_part_0', result)
            finally:
                browser.close()

    def test_delete_local_actor_and_style_with_confirmation(self):
        from mmv import actors
        from test_public_app import picture
        from playwright.sync_api import sync_playwright, expect
        actors.create_actor(self.fixture.store, 'disposable', 'Disposable Actor', 'Overview', picture())
        self.fixture.client.post('/api/styles', json={'id': 'disposable', 'name': 'Disposable Style', 'direction': 'Daylight'}).raise_for_status()
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#video-form .song-input").onchange !== null')
                page.locator('.nav[data-panel=actors]').click()
                card = page.locator('#actor-list article').filter(has_text='Disposable Actor')
                page.once('dialog', lambda dialog: dialog.dismiss())
                card.get_by_role('button', name='Delete actor', exact=True).click()
                expect(card).to_have_count(1)
                page.once('dialog', lambda dialog: dialog.accept())
                card.get_by_role('button', name='Delete actor', exact=True).click()
                expect(card).to_have_count(0)
                expect(page.locator('.actor-select option[value=disposable]')).to_have_count(0)
                page.locator('.nav[data-panel=styles]').click()
                card = page.locator('#style-list article').filter(has_text='Disposable Style')
                page.once('dialog', lambda dialog: dialog.accept())
                card.get_by_role('button', name='Delete style', exact=True).click()
                expect(card).to_have_count(0)
                expect(page.locator('.style-select option[value=disposable]')).to_have_count(0)
                page.reload()
                page.wait_for_function('() => document.querySelector("#video-form .song-input").onchange !== null')
                self.assertFalse(self.fixture.store.actor('disposable'))
                self.assertFalse((self.home / 'styles/disposable.json').exists())
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_topaz_cloud_choice_saves_and_opens_cloud_dialog(self):
        from playwright.sync_api import sync_playwright, expect
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=str(_cached_chromium()[-1]))
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#video-form .song-input").onchange !== null')
                page.locator('.nav[data-panel=settings]').click()
                page.locator('select[name=topaz_backend]').select_option('cloud')
                expect(page.locator('#settings-autosave-status')).to_contain_text('Saved automatically')
                self.assertEqual(self.fixture.store.settings()['topaz_backend'], 'cloud')
                expect(page.locator('select[name=topaz_backend]')).to_have_value('cloud')
                page.evaluate("""() => { const s = document.querySelector('#upscale-service'); s.value = 'local'; s.dispatchEvent(new Event('change')); }""")
                for _ in range(50):
                    if self.fixture.store.settings()['topaz_backend'] == 'local':
                        break
                    page.wait_for_timeout(100)
                page.wait_for_function("() => document.querySelector('#upscale-cloud').hidden === true")
                self.assertEqual(self.fixture.store.settings()['topaz_backend'], 'local')
                page.evaluate("""() => { const s = document.querySelector('#upscale-service'); s.value = 'cloud'; s.dispatchEvent(new Event('change')); }""")
                for _ in range(50):
                    if self.fixture.store.settings()['topaz_backend'] == 'cloud':
                        break
                    page.wait_for_timeout(100)
                page.wait_for_function("() => document.querySelector('#upscale-cloud').hidden === false")
                self.assertEqual(self.fixture.store.settings()['topaz_backend'], 'cloud')
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_saved_api_profiles_switch_independently_without_network_generation(self):
        from mmv.api_profiles import save_profile
        from playwright.sync_api import sync_playwright, expect
        store = self.fixture.store
        original = store.settings()
        for name in ('account-a', 'account-b'):
            save_profile(store, name, 'writer', {'writer_url': f'https://{name}.example/v1',
                'writer_model': name, 'writer_mode': 'api', 'writer_call_estimate': .1}, f'private-{name}')
        save_profile(store, 'vision-account', 'vision', {'vision_url': 'https://vision.example/v1',
            'vision_model': 'vision-model'}, 'private-vision')
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#video-form .song-input").onchange !== null')
                page.locator('.nav[data-panel=settings]').click()
                writer = page.locator('select[name=writer_api_profile]')
                expect(writer).to_have_value('')
                writer.select_option('account-a')
                page.locator('select[name=vision_api_profile]').select_option('vision-account')
                expect(page.locator('input[name=writer_model]')).to_have_value('account-a')
                expect(page.locator('input[name=vision_model]')).to_have_value('vision-model')
                page.locator('select[name=writer_api_profile]').select_option('account-b')
                expect(page.locator('input[name=writer_model]')).to_have_value('account-b')
                self.assertEqual(store.key('MMV_WRITER_API_KEY'), 'private-account-b')
                self.assertEqual(store.key('MMV_VISION_API_KEY'), 'private-vision')
                page.once('dialog', lambda dialog: dialog.accept('saved-copy'))
                page.get_by_role('button', name='Save configured writer API as a profile').click()
                expect(page.locator('select[name=writer_api_profile] option[value=saved-copy]')).to_have_count(1)
                page.locator('select[name=writer_api_profile]').select_option('')
                page.locator('select[name=vision_api_profile]').select_option('')
                expect(page.locator('input[name=writer_model]')).to_have_value(original['writer_model'])
                self.assertEqual(store.settings()['writer_url'], original['writer_url'])
                self.assertNotIn('private-account', page.locator('body').inner_text())
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_model_picker_and_oap_summary_preserve_operator_choices(self):
        import json
        from mmv import actors
        from test_public_app import picture
        from playwright.sync_api import sync_playwright, expect
        self.fixture.install_test_h3_models()
        graph, mapping, map_path = self.fixture.custom_h3_workflow()
        settings = self.fixture.store.settings()
        settings['workflow_map_path'] = str(map_path)
        self.fixture.client.put('/api/settings', json=settings).raise_for_status()
        actors.create_actor(self.fixture.store, 'blue', 'Blue <b>Performer</b>', 'Blue jacket', picture())
        package = actors.export_actor(self.fixture.store, 'blue')
        manifest, _ = actors.package_info(package)
        source_bytes = Path(mapping['workflow']).read_bytes()
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#video-form .song-input").onchange !== null')
                page.locator('.nav[data-panel=settings]').click()
                model = page.locator('select[name=h3_diffusion_model]')
                expect(model).to_have_value('my-current-model.safetensors')
                self.assertIn('test_diffusion.safetensors', model.locator('option').evaluate_all('(items) => items.map(o => o.value)'))
                autosaved(page, lambda: model.select_option('test_diffusion.safetensors'))
                expect(page.locator('select[name=h3_diffusion_model]')).to_have_value('test_diffusion.safetensors')
                self.assertEqual(Path(mapping['workflow']).read_bytes(), source_bytes)
                # Choose another binding map through the file picker. Unchanged model
                # selectors must not override the newly chosen workflow.
                map_input = page.locator('input[name=workflow_map_path]')
                map_input.locator('..').locator('button').click()
                expect(page.locator('#folder-picker-dialog')).to_be_visible()
                expect(page.locator('#picker-confirm')).to_be_disabled()
                page.locator('#picker-breadcrumbs').get_by_role('button', name='Up').click()
                page.locator('#picker-filter').fill('operator-map.json')
                with page.expect_response(lambda r: r.url.endswith('/api/settings') and r.request.method == 'PUT') as saved:
                    page.locator('#picker-entries .picker-entry').filter(has_text='operator-map.json').dblclick()
                expect(map_input).to_have_value(str(map_path))
                self.assertEqual(saved.value.status, 200)
                expect(page.locator('select[name=h3_diffusion_model]')).to_have_value('my-current-model.safetensors')
                self.assertEqual(self.fixture.store.settings()['workflow_map_path'], str(map_path))
                # Folder selection and keyboard traversal use temporary directories only.
                folder_input = page.locator('input[name=comfy_input]')
                folder_input.locator('..').locator('button').click()
                expect(page.locator('#picker-selected-path')).to_have_value(str(self.home / 'comfy-input'))
                page.locator('#picker-confirm').click()
                expect(folder_input).to_have_value(str(self.home / 'comfy-input'))
                # OAP guide and signed package summary use the upstream schema.
                page.locator('.nav[data-panel=actors]').click()
                page.locator('#panel-actors .oap-help-btn').click()
                expect(page.locator('#oap-helper-dialog')).to_be_visible()
                page.locator('.oap-tab-btn[data-tab=riders]').click()
                expect(page.locator('#tab-riders')).to_be_visible()
                page.locator('.close-oap-dialog').click()
                page.locator('#oap-file').set_input_files(str(package))
                page.locator('#inspect-oap').click()
                card = page.locator('#oap-report-card')
                expect(card).to_contain_text('Blue <b>Performer</b>')
                expect(card).to_contain_text('nudity: none')
                expect(card).to_contain_text('signer not locally trusted')
                expect(card).to_contain_text(manifest['agent']['public_key'])
                expect(card).to_contain_text('political_ads')
                self.assertEqual(card.locator('b').count(), 0)
                self.assertNotIn('Non-commercial only', card.inner_text())
                page.locator('#toggle-raw-oap').click()
                expect(page.locator('#oap-report')).to_be_visible()
                page.set_viewport_size({'width': 390, 'height': 844})
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), 390)
                expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
                toggle = page.locator('#theme-toggle')
                expect(toggle).to_have_attribute('aria-pressed', 'true')
                toggle.click()
                expect(page.locator('html')).to_have_attribute('data-theme', 'light')
                page.reload()
                expect(page.locator('html')).to_have_attribute('data-theme', 'light')
                page.locator('#theme-toggle').click()
                page.reload()
                expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
                page.set_viewport_size({'width': 360, 'height': 800})
                expect(page.locator('#theme-toggle')).to_be_in_viewport()
                self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
                page.set_viewport_size({'width': 1440, 'height': 1000})
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_song_preview_setup_guide_and_status_fallback(self):
        import json
        import threading
        from playwright.sync_api import sync_playwright, expect
        from mmv.storage import write_json
        settings = self.fixture.store.settings()
        command = json.dumps(['my-writer', '-m', "my-model's.gguf", '-c', '8192'])
        settings['writer_launch'] = command
        write_json(self.home / 'settings.json', settings)
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            done = threading.Event()
            try:
                page.goto(self.url)
                expect(page.locator('#version')).to_have_text('1.12.3')
                page.evaluate("""async () => {
                  const m = await import('/js/production.js');
                  m.renderServices({vision_quality: {activity: 'offline', available: false, has_launch: true,
                    detail: 'Mondo starts it when the vision check runs'}});
                }""")
                expect(page.locator('#service-badge-vision_quality')).to_have_text('STARTS AUTOMATICALLY')
                expect(page.locator('#service-detail-vision_quality')).to_contain_text('Mondo starts it')
                expect(page.locator('#service-card-vision .service-role')).to_have_text('Style Harvester')
                page.wait_for_function('() => document.querySelector("#video-form .song-input").onchange !== null')
                page.locator('#video-form .song-input').set_input_files(str(self.song))
                expect(page.locator('#vocab-profile-select')).not_to_contain_text('hellonearthis')
                expect(page.locator('.song-preview-wrap')).to_be_visible()
                expect(page.locator('.song-preview')).to_have_attribute('src', __import__('re').compile(r'^blob:'))
                expect(page.locator('#video-form .song-receipt')).to_contain_text('Uploaded:')
                page.wait_for_function('() => document.querySelector(".song-preview").readyState >= 1')
                page.evaluate("() => import('/js/project.js').then(m => m.saveProject())")
                saved = self.fixture.client.get('/api/project').json()
                assert saved.get('files', {}).get('video-form', {}).get('song'), saved
                page.reload()
                page.wait_for_function('() => document.querySelector("#video-form .song-input").onchange !== null')
                expect(page.locator('.song-preview')).to_have_attribute('src', __import__('re').compile(r'^/api/uploads/song/'))
                page.locator('.nav[data-panel=settings]').click()
                expect(page.locator('select[name=laya_device]')).to_have_value('cuda')
                page.locator('#panel-settings > .panel-header-row .llama-help-btn').click()
                expect(page.locator('#llama-helper-dialog')).to_be_visible()
                expect(page.locator('#writer-tuning-preset')).not_to_contain_text('hellonearthis')
                expect(page.locator('#llama-current-json')).to_have_text(command)
                page.locator('#writer-tuning-preset').select_option('context_16k')
                preview = json.loads(page.locator('#llama-current-json').inner_text())
                self.assertEqual(preview[preview.index('-m') + 1], "my-model's.gguf")
                self.assertEqual(preview[preview.index('-c') + 1], '16384')
                self.assertNotIn('--image-min-tokens', preview)
                expect(page.locator('input[name=writer_launch]')).to_have_value(command)
                page.locator('#apply-writer-tuning').click()
                self.assertEqual(json.loads(page.locator('input[name=writer_launch]').input_value()), preview)
                self.assertEqual(self.fixture.store.settings()['writer_launch'], command)
                page.wait_for_function("() => import('/js/production.js').then(m => m.isSseConnected())")
                jobs = self.fixture.app.state.jobs
                def operation(context):
                    context.update('Live stream progress', 30)
                    done.wait(10)
                    return {'mock': True}
                jobs.start('test', operation)
                expect(page.locator('#status-message')).to_have_text('Live stream progress')
                # Simulate a failed stream after it was connected; watchdog polling must survive.
                page.evaluate("() => import('/js/production.js').then(m => { const s = m.getSseSource(); s.close(); s.dispatchEvent(new Event('error')); })")
                jobs.active.update('Polling fallback progress', 60)
                expect(page.locator('#status-message')).to_have_text('Polling fallback progress', timeout=12000)
                done.set()
                expect(page.locator('#status-title')).to_have_text('COMPLETE', timeout=12000)
                page.set_viewport_size({'width': 360, 'height': 800})
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), 360)
            finally:
                done.set()
                browser.close()

    def test_vocabulary_editor_does_not_restore_stale_text_after_reset_or_reopen(self):
        from playwright.sync_api import sync_playwright, expect
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            page.on('dialog', lambda dialog: dialog.accept())
            errors = []
            page.on('pageerror', lambda err: errors.append(str(err)))
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#open-vocab-panel-btn").onclick !== null')
                page.evaluate('() => document.querySelector("#open-vocab-panel-btn").click()')
                expect(page.locator('#panel-vocab')).to_be_visible()
                textarea = page.locator('#vocab-custom-textarea')
                textarea.fill('stale entry that was never applied')
                page.locator('#vocab-reset-all-btn').click()
                expect(textarea).to_have_value('')
                textarea.fill('dismissed edit')
                page.locator('.nav[data-panel=video]').click()
                page.locator('.nav[data-panel=vocab]').click()
                expect(textarea).to_have_value('')
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_vocabulary_workspace_restores_selection_and_independent_folds(self):
        from playwright.sync_api import sync_playwright, expect
        project = {
            'panel': 'vocab',
            'forms': {'video-form': {'vocabulary_profile': 'full'}},
            'custom_vocabulary': {'settings': {'mode': 'replace', 'add': ['Workspace fixture', 'Remaining fixture'], 'exclude': []}},
            'details_sections': {'director-pacing': False, 'director-camera': True, 'director-render': False},
        }
        self.fixture.client.put('/api/project', json=project).raise_for_status()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=str(_cached_chromium()[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            errors = []
            page.on('pageerror', lambda err: errors.append(str(err)))
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#open-vocab-panel-btn").onclick !== null')
                expect(page.locator('#panel-vocab')).to_be_visible()
                # A draft saved before the format fold existed leaves it at its default (open).
                self.assertTrue(page.evaluate('document.querySelector("#video-form details[id*=format]").open'))
                # Summary cards render lazily, when the collapsed summary is first opened.
                page.locator('#vocab-random-summary-details').evaluate('(el) => el.open = true')
                card = page.locator('.vocab-summary-cat-card[data-category=settings]')
                expect(card).to_contain_text('Workspace fixture')
                # Edits to one card preserve the other cards and remain stable after opening.
                page.evaluate('window.otherCard = document.querySelector(".vocab-summary-cat-card[data-category=lighting]")')
                page.locator('#vocab-random-summary-details').evaluate('(el) => el.open = true')
                card.locator('.vocab-chip-remove').first.click()
                expect(card).not_to_contain_text('Workspace fixture')
                expect(card).to_contain_text('Remaining fixture')
                self.assertTrue(page.evaluate('window.otherCard === document.querySelector(".vocab-summary-cat-card[data-category=lighting]")'))
                page.locator('#vocab-apply-btn').click()
                expect(page.locator('#panel-video')).to_be_visible()
                self.assertEqual(page.locator('#video-form details').evaluate_all('(els) => els.map(el => el.open)'), [False, False, True, True, False, False])
                page.wait_for_function('() => JSON.parse(localStorage.getItem("mmv_project_draft") || "{}").panel === "video"')
                page.reload()
                page.wait_for_function('() => document.querySelector("#open-vocab-panel-btn").onclick !== null')
                self.assertEqual(page.locator('#video-form details').evaluate_all('(els) => els.map(el => el.open)'), [False, False, True, True, False, False])
                page.locator('.nav[data-panel=vocab]').click()
                page.locator('#vocab-random-summary-details').evaluate('(el) => el.open = true')
                expect(page.locator('.vocab-summary-cat-card[data-category=settings]')).to_contain_text('Remaining fixture')
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_worlds_panel_lists_reviews_and_feeds_the_video_form(self):
        from mmv import worlds
        from playwright.sync_api import sync_playwright, expect
        ledger = {"name": "Salt Archive", "seed_sentence": "A filing system.", "core_laws": ["The record outlives the person"],
                  "pools": {"settings": {"include": ["a basement archive"]}}}
        self.agent.create_world({"id": "salt", **ledger})
        proposed = {**worlds.normalize(ledger), "id": "salt", "core_laws": ["The record outlives the person", "<b>Nothing leaves unfiled</b>"]}
        worlds.write_proposal(self.fixture.store, "grow-one", "salt", "grow", 1, proposed, [("image", "x.png")], {"vision": "m"})
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=str(_cached_chromium()[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#world-select").options.length === 2')
                expect(page.locator('#world-select option').nth(1)).to_have_text('Salt Archive')
                page.wait_for_function('() => document.querySelector(".nav[data-panel=worlds]").onclick !== null')
                page.locator('.nav[data-panel="worlds"]').click()
                expect(page.locator('#panel-worlds')).to_be_visible()
                expect(page.locator('#worlds-list')).to_contain_text('Salt Archive')
                expect(page.locator('#world-proposals-card')).to_be_visible()
                expect(page.locator('#world-proposals .world-diff-add')).to_contain_text('<b>Nothing leaves unfiled</b>')
                self.assertEqual(page.locator('#world-proposals b').count(), 0)
                page.locator('#worlds-list button:text-is("Open")').click()
                expect(page.locator('#world-detail')).to_contain_text('version 1')
                expect(page.locator('#world-detail button:text-is("Edit")')).to_have_count(2)
                page.locator('#world-proposals button', has_text='Accept').click()
                expect(page.locator('#world-proposals-card')).to_be_hidden()
                self.assertEqual(self.agent.get_world('salt')['version'], 2)
                page.locator('#world-form textarea[name="direction"]').fill('keep it damp')
                page.locator('#world-form select[name="world_mode"]').select_option('grow')
                page.wait_for_timeout(1500)
                page.reload()
                page.wait_for_function('() => document.querySelector("#world-select").options.length === 2')
                page.wait_for_timeout(500)
                self.assertEqual(page.locator('#world-form textarea[name="direction"]').input_value(), 'keep it damp')
                self.assertEqual(page.locator('#world-form select[name="world_mode"]').input_value(), 'grow')
                page.locator('.nav[data-panel="worlds"]').click()
                expect(page.locator('#world-form select[name="world_existing"]')).to_be_visible()
                expect(page.locator('#world-form input[name="world_new_id"]')).to_be_hidden()
            finally:
                browser.close()

    def test_thematic_world_pools_keep_choices_count_down_and_restore_the_applied_worlds(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=str(_cached_chromium()[-1]))
            page = browser.new_page()
            errors = []
            page.on('pageerror', lambda err: errors.append(str(err)))
            try:
                page.goto(self.url)
                result = page.evaluate("""async () => {
                  const m = await import('/js/vocab-worlds.js');
                  const pool = {dimension: 'Settings', pool: 4, need: 3, terms: ['a', 'b', 'c', 'd'], chipStates: {}};
                  const pinned = m.setPoolChipState([pool], 0, 'a', 1);
                  const added = m.addTermToPool(pinned, 0, 'custom hall');
                  const excluded = m.setPoolChipState(added, 0, 'b', 2);
                  const cleared = m.setPoolChipState(excluded, 0, 'a', 0);
                  return {
                    pinnedText: m.formatPoolStatusText(pinned[0]),
                    addedText: m.formatPoolStatusText(added[0]),
                    addedIsPinned: added[0].chipStates['custom hall'],
                    excludedCount: m.computePoolCounts(excluded[0]).currentPoolCount,
                    clearedHasA: 'a' in cleared[0].chipStates,
                    guided: m.compileWorldsToCustomVocab(excluded, 'guided'),
                    oldDraft: m.restoreWorlds({activeWorlds: ['Industrial Decay', 'Deep Sea Salvage']}).filter(w => w.active).map(w => w.name),
                    savedList: m.restoreWorlds({worlds: [{name: 'X', active: true, locked: true, score: .9}]}),
                    noDraft: m.restoreWorlds(null).map(w => w.active),
                    tooltip: m.renderPoolsHtml([excluded[0]], false).includes('data-tooltip="Click to cycle'),
                  };
                }""")
                self.assertEqual(result['pinnedText'], '4 in pool, 2 needed (1/3 selected)')
                self.assertEqual(result['addedText'], '5 in pool, 1 needed (2/3 selected)')
                self.assertEqual(result['addedIsPinned'], 1)
                self.assertEqual(result['excludedCount'], 4)
                self.assertFalse(result['clearedHasA'])
                self.assertEqual(result['guided'], {'settings': {'mode': 'append', 'add': ['a', 'custom hall'], 'exclude': ['b']}})
                self.assertEqual(result['oldDraft'], ['Industrial Decay', 'Deep Sea Salvage'])
                self.assertEqual(result['savedList'], [{'name': 'X', 'active': True, 'locked': True, 'score': .9}])
                self.assertEqual(result['noDraft'][:3], [True, True, False])
                self.assertTrue(result['tooltip'])
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_world_editor_previews_before_saving_a_new_version(self):
        from playwright.sync_api import sync_playwright, expect
        self.agent.create_world({"id": "salt", "name": "Salt Archive", "core_laws": ["The record outlives the person"],
                                 "subjects": [{"designation": "the Graft Clerk", "canon": "Stamps wounds as forms"}]})
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=str(_cached_chromium()[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            errors = []
            page.on('pageerror', lambda err: errors.append(str(err)))
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector(".nav[data-panel=worlds]").onclick !== null')
                page.locator('.nav[data-panel="worlds"]').click()
                page.locator('#worlds-list button:text-is("Edit")').click()
                expect(page.locator('#world-detail h3')).to_contain_text('Edit Salt Archive')
                save = page.locator('#world-detail button:text-is("Save as new version")')
                expect(save).to_be_disabled()
                page.locator('#world-detail textarea[name="core_laws"]').fill('<b>Ink is never dry</b>')
                page.locator('#world-detail .world-subject-canon').fill('Stamps wounds as forms and files the scars')
                page.locator('#world-detail summary', has_text='Vocabulary pools').click()
                page.locator('#world-detail .vocab-tab-btn', has_text='Lighting').click()
                standard = page.locator('#world-detail .vocab-item-label').first
                kept_out = standard.inner_text()
                standard.locator('input').uncheck()
                page.locator('#world-detail textarea[name="own"]').fill('lamp oil glow')
                expect(save).to_be_disabled()
                page.locator('#world-detail button:text-is("Preview changes")').click()
                expect(page.locator('#world-detail .world-diff-remove')).to_contain_text('The record outlives the person')
                expect(page.locator('#world-detail .world-diff-add', has_text='<b>Ink is never dry</b>')).to_have_count(1)
                expect(page.locator('#world-detail .world-diff-change')).to_contain_text('the Graft Clerk')
                expect(page.locator('#world-detail .world-diff-add', has_text='lamp oil glow')).to_have_count(1)
                expect(page.locator('#world-detail .world-diff-add', has_text=kept_out)).to_have_count(1)
                self.assertEqual(page.locator('#world-detail b').count(), 0)
                self.assertEqual(self.agent.get_world('salt')['version'], 1)
                expect(save).to_be_enabled()
                page.locator('#world-detail textarea[name="seed_sentence"]').fill('A filing system.')
                expect(save).to_be_disabled()
                page.locator('#world-detail button:text-is("Preview changes")').click()
                expect(save).to_be_enabled()
                save.click()
                expect(page.locator('#world-detail')).to_contain_text('version 2')
                edit_top = page.locator('#world-detail button:text-is("Edit")').first
                expect(edit_top).to_be_visible()
                self.assertLess(edit_top.bounding_box()['y'] - page.locator('#world-detail').bounding_box()['y'], 120)
                world = self.agent.get_world('salt')
                self.assertEqual((world['version'], world['core_laws'], world['seed_sentence']), (2, ['<b>Ink is never dry</b>'], 'A filing system.'))
                self.assertEqual(world['pools']['lighting'], {'include': ['lamp oil glow'], 'exclude': [kept_out]})
                self.assertEqual(self.agent.get_world('salt', 1)['core_laws'], ['The record outlives the person'])
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_vocabulary_guide_navigation_and_dark_overflow_contrast(self):
        from playwright.sync_api import sync_playwright, expect
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=str(_cached_chromium()[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#open-vocab-panel-btn").onclick !== null')
                page.locator('#video-form .vocab-help-btn').click()
                expect(page.locator('#vocab-helper-dialog')).to_be_visible()
                expect(page.locator('#vocab-guide-raw')).to_contain_text('Visual vocabulary')
                page.locator('.nav-to-vocab-btn').click()
                expect(page.locator('#vocab-helper-dialog')).not_to_be_visible()
                expect(page.locator('#panel-vocab')).to_be_visible()
                page.locator('#vocab-random-summary-details').evaluate('(el) => el.open = true')
                page.evaluate('document.documentElement.dataset.theme = "dark"')
                more = page.locator('.vocab-chip-more').first
                expect(more).to_have_attribute('aria-label', __import__('re').compile('Show all entries in .+'))
                more.hover()
                colors = more.evaluate('(el) => { const s = getComputedStyle(el); return [s.color, s.backgroundColor]; }')
                def luminance(rgb):
                    channels = [int(n) / 255 for n in __import__('re').findall(r'\d+', rgb)[:3]]
                    linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
                    return sum(c * w for c, w in zip(linear, [.2126, .7152, .0722]))
                light, dark = sorted(map(luminance, colors), reverse=True)
                self.assertGreaterEqual((light + .05) / (dark + .05), 4.5)
                more.click()
                expect(page.locator('#vocab-editor-pane')).to_be_visible()
                page.locator('#panel-vocab .vocab-help-btn >> nth=0').click()
                expect(page.locator('#vocab-helper-dialog')).to_be_visible()
            finally:
                browser.close()

    def test_score_editor_edits_beats_and_sections_and_gates_start(self):
        import json
        from playwright.sync_api import sync_playwright, expect
        name = self.fixture.client.post('/api/upload/song', files={'file': ('test.wav', self.song.read_bytes(), 'audio/wav')}).json()['file']
        beats = [{'time': round(0.5 * i, 3), 'downbeat': i % 4 == 1} for i in range(1, 17)]
        detected = {'duration': 8.5, 'tempo_bpm': 120, 'beats_per_bar': 4, 'beats': beats,
                    'sections': [{'start': 0, 'end': 4, 'label': 'low', 'energy': .2}, {'start': 4, 'end': 8.5, 'label': 'high', 'energy': .8}]}
        score = {'beats': [{'time': b['time'], 'energy': .5} for b in beats],
                 'passages': [{'start': 0, 'end': 4, 'shots': [{'start': 0}, {'start': 2}]}, {'start': 4, 'end': 8.5, 'shots': [{'start': 4}]}]}
        quote = {'detected': detected, 'score': score}
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            errors = []
            page.on('pageerror', lambda err: errors.append(str(err)))
            try:
                page.route('**/api/stems', lambda route: route.fulfill(json={'installed': False, 'install_command': 'pip install demucs', 'models': {}}))
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#open-vocab-panel-btn").onclick !== null')
                page.evaluate("""([name, quote]) => import('/js/score_editor.js').then(m => {
                    window.__dirty = []; window.__replans = []; window.__drivers = [];
                    const host = document.createElement('div'); host.id = 'test-editor'; document.body.append(host);
                    return m.mountScoreEditor(host, {kind: 'video', song: name}, quote, {
                        onDirty: d => window.__dirty.push(d), onReplan: async (e, d) => { window.__replans.push(e); window.__drivers.push(d); }});
                })""", [name, quote])
                strip = page.locator('#test-editor .se-strip')
                expect(strip).to_be_visible()
                expect(page.locator('#test-editor .se-status')).to_contain_text('matches what you see')
                expect(page.locator('#test-editor .se-section-row')).to_have_count(2)
                strip.focus()
                page.keyboard.press('ArrowRight')
                page.keyboard.press('ArrowRight')
                page.keyboard.press('m')
                page.keyboard.press('b')
                page.locator('#test-editor input[type=range]').fill('50')
                expect(page.locator('#test-editor .se-status')).to_contain_text('not planned yet')
                self.assertTrue(page.evaluate('window.__dirty.at(-1)'))
                page.locator('#test-editor .se-section-row select').first.select_option('peak')
                expect(page.locator('#test-editor .se-driver-note')).to_contain_text('pip install demucs')
                self.assertTrue(page.evaluate('document.querySelector("#test-editor .se-driver option[value=drums]").disabled'))
                self.assertFalse(page.evaluate('document.querySelector("#test-editor .se-driver option[value=mix]").disabled'))
                page.locator('#test-editor button.primary').click()
                page.wait_for_function('window.__replans.length === 1')
                edits = page.evaluate('window.__replans[0]')
                self.assertEqual(page.evaluate('window.__drivers[0]'), 'mix')
                self.assertEqual(edits['muted_beats'], [1])
                self.assertEqual(edits['bar_one_beat'], 1)
                self.assertEqual(edits['beat_nudge_ms'], 50)
                self.assertEqual(edits['sections'], [{'start': 0, 'label': 'peak'}, {'start': 4, 'label': 'high'}])
                page.locator('#test-editor button:has-text("Reset edits")').click()
                expect(page.locator('#test-editor .se-status')).to_contain_text('matches what you see')
                self.assertFalse(page.evaluate('window.__dirty.at(-1)'))
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_stem_quality_choice_needs_its_own_model_and_passes_through_replan(self):
        from playwright.sync_api import sync_playwright, expect
        name = self.fixture.client.post('/api/upload/song', files={'file': ('test.wav', self.song.read_bytes(), 'audio/wav')}).json()['file']
        beats = [{'time': round(0.5 * i, 3), 'downbeat': i % 4 == 1} for i in range(1, 17)]
        quote = {'detected': {'duration': 8.5, 'tempo_bpm': 120, 'beats_per_bar': 4, 'beats': beats,
                              'sections': [{'start': 0, 'end': 8.5, 'label': 'mid', 'energy': .5}]},
                 'score': {'beats': [{'time': b['time'], 'energy': .5} for b in beats],
                           'passages': [{'start': 0, 'end': 8.5, 'shots': [{'start': 0}]}]}}
        models = {'htdemucs': {'ready': True}, 'htdemucs_ft': {'ready': False}, 'htdemucs_6s': {'ready': False}}
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            try:
                page.route('**/api/stems', lambda route: route.fulfill(json={'installed': True, 'install_command': 'pip install demucs', 'models': models}))
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#open-vocab-panel-btn").onclick !== null')
                page.evaluate("""([name, quote]) => import('/js/score_editor.js').then(m => {
                    window.__calls = [];
                    const host = document.createElement('div'); host.id = 'test-editor'; document.body.append(host);
                    return m.mountScoreEditor(host, {kind: 'video', song: name}, quote, {
                        onDirty: () => {}, onReplan: async (e, d, q) => { window.__calls.push([d, q]); }});
                })""", [name, quote])
                disabled = lambda sel: page.evaluate('s => document.querySelector(s).disabled', sel)
                expect(page.locator('#test-editor .se-driver select').first).to_be_visible()
                self.assertFalse(disabled('#test-editor .se-driver option[value=drums]'))
                self.assertTrue(disabled('#test-editor .se-driver option[value=guitar]'))
                self.assertEqual(page.locator('#test-editor .se-setup-row').count(), 2)      # high-quality and 6-stem still missing
                expect(page.locator('#test-editor .se-driver-setup')).to_contain_text('about 324 MB')
                self.assertTrue(page.locator('#test-editor .se-driver-label:has-text("Stem quality")').is_hidden())
                page.locator('#test-editor .se-driver select').first.select_option('drums')
                self.assertTrue(page.locator('#test-editor .se-driver-label:has-text("Stem quality")').is_visible())
                self.assertTrue(disabled('#test-editor select option[value=high]'))
                models['htdemucs_ft']['ready'] = True
                page.locator('#test-editor button:has-text("Reset edits")').click()
                page.locator('#test-editor .se-driver select').first.select_option('drums')
                page.locator('#test-editor button.primary:has-text("Re-plan")').click()
                page.wait_for_function('window.__calls.length === 1')
                self.assertEqual(page.evaluate('window.__calls[0]'), ['drums', 'standard'])
            finally:
                browser.close()

    def test_lip_sync_editor_edits_lyric_lines_and_singer_and_gates_replan(self):
        from playwright.sync_api import sync_playwright, expect
        name = self.fixture.client.post('/api/upload/song', files={'file': ('test.wav', self.song.read_bytes(), 'audio/wav')}).json()['file']
        beats = [{'time': round(0.5 * i, 3), 'downbeat': i % 4 == 1} for i in range(1, 17)]
        quote = {'detected': {'duration': 8.5, 'tempo_bpm': 120, 'beats_per_bar': 4, 'beats': beats,
                              'sections': [{'start': 0, 'end': 8.5, 'label': 'mid', 'energy': .5}]},
                 'score': {'beats': [{'time': b['time'], 'energy': .5} for b in beats],
                           'passages': [{'index': 0, 'start': 0, 'end': 4, 'shots': [{'start': 0}]}, {'index': 1, 'start': 4, 'end': 8.5, 'shots': [{'start': 4}]}]},
                 'lipsync': {'singer': 'pig', 'actors': {'pig': 'Hambo', 'goon': 'Henchman'},
                             'passages': {'seg000': {'singing': True, 'reason': 'main singer', 'actor_id': 'pig'},
                                          'seg001': {'singing': False, 'reason': 'no sung lines in this passage', 'actor_id': None}}}}
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            errors = []
            page.on('pageerror', lambda err: errors.append(str(err)))
            try:
                page.route('**/api/stems', lambda route: route.fulfill(json={'installed': False, 'install_command': 'pip install demucs', 'models': {}}))
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#open-vocab-panel-btn").onclick !== null')
                page.evaluate("""([name, quote]) => import('/js/score_editor.js').then(m => {
                    window.__calls = [];
                    const host = document.createElement('div'); host.id = 'test-editor'; document.body.append(host);
                    return m.mountScoreEditor(host, {kind: 'video', song: name, mouth_mode: 'lip_sync', actors: ['pig', 'goon'],
                        lyric_lines: [{start: 0.5, end: 3.5, text: 'Interdimensional lover'}], singers: []}, quote, {
                        onDirty: () => {}, onReplan: async (e, d, q, lip) => { window.__calls.push(lip); }});
                })""", [name, quote])
                expect(page.locator('#test-editor .se-lip')).to_be_visible()
                expect(page.locator('#test-editor .se-lip-summary')).to_contain_text('Hambo sings (main singer)')
                expect(page.locator('#test-editor .se-lip-summary')).to_contain_text('sealed (no sung lines in this passage)')
                expect(page.locator('#test-editor .se-line-row')).to_have_count(1)
                self.assertEqual(page.get_by_label('Main singer').locator('option').all_inner_texts(), ['Choose for me (seeded)', 'Hambo', 'Henchman'])
                expect(page.locator('#test-editor .se-status')).to_contain_text('matches what you see')
                page.get_by_label('Main singer').select_option('goon')
                expect(page.locator('#test-editor .se-status')).to_contain_text('not planned yet')
                page.locator('#test-editor button:has-text("Add line at cursor")').click()
                expect(page.locator('#test-editor .se-line-row')).to_have_count(2)
                expect(page.locator('#test-editor .se-status')).to_contain_text('Each lyric line needs words')
                self.assertTrue(page.evaluate('document.querySelector("#test-editor button.primary").disabled'))
                page.locator('#test-editor .se-line-row input[type=text]').nth(0).fill('I dated you')
                page.locator('#test-editor button.primary:has-text("Re-plan")').click()
                page.wait_for_function('window.__calls.length === 1')
                lip = page.evaluate('window.__calls[0]')
                self.assertEqual(lip['singers'], ['goon'])
                self.assertEqual([line['text'] for line in lip['lyric_lines']], ['I dated you', 'Interdimensional lover'])   # kept in time order
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_lyrics_detection_and_pasted_lyrics_fill_the_lines_in_the_editor(self):
        from playwright.sync_api import sync_playwright, expect
        name = self.fixture.client.post('/api/upload/song', files={'file': ('test.wav', self.song.read_bytes(), 'audio/wav')}).json()['file']
        beats = [{'time': round(0.5 * i, 3), 'downbeat': i % 4 == 1} for i in range(1, 17)]
        quote = {'detected': {'duration': 8.5, 'tempo_bpm': 120, 'beats_per_bar': 4, 'beats': beats,
                              'sections': [{'start': 0, 'end': 8.5, 'label': 'mid', 'energy': .5}]},
                 'score': {'beats': [{'time': b['time'], 'energy': .5} for b in beats],
                           'passages': [{'index': 0, 'start': 0, 'end': 8.5, 'shots': [{'start': 0}]}]},
                 'lipsync': {'singer': 'pig', 'actors': {'pig': 'Hambo'}, 'passages': {'seg000': {'singing': False, 'reason': 'no sung lines in this passage'}}}}
        models = {name_: {'cached': name_ == 'large-v3', 'download': 'about 1 GB'} for name_ in ('tiny', 'base', 'small', 'medium', 'large-v3')}
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            errors, posts = [], []
            page.on('pageerror', lambda err: errors.append(str(err)))
            try:
                page.route('**/api/stems', lambda route: route.fulfill(json={'installed': False, 'install_command': 'pip install demucs', 'models': {}}))
                page.route('**/api/lyrics', lambda route: route.fulfill(json={'available': True, 'install_command': 'pip install openai-whisper', 'models': models}))
                def post(route):
                    posts.append((route.request.url.rsplit('/', 1)[1], route.request.post_data_json))
                    if route.request.url.endswith('/detect'):
                        route.fulfill(json={'id': 'j1', 'state': 'running'})
                    else:
                        route.fulfill(json={'lines': [{'start': 1.0, 'end': 3.0, 'text': 'Interdimensional lover', 'timing': 'matched'},
                                                      {'start': 3.0, 'end': 5.0, 'text': 'I dated you', 'timing': 'interpolated'}], 'source': 'vocals stem'})
                page.route('**/api/lyrics/detect', post)
                page.route('**/api/lyrics/align', post)
                page.route('**/api/status', lambda route: route.fulfill(json={'state': 'complete', 'message': 'Complete', 'result': {
                    'lines': [{'start': 9.9, 'end': 12.1, 'text': 'Interdimensional lover'}], 'source': 'vocals stem', 'language': 'en', 'model': 'large-v3'}}))
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#open-vocab-panel-btn").onclick !== null')
                page.evaluate("""([name, quote]) => import('/js/score_editor.js').then(m => {
                    const host = document.createElement('div'); host.id = 'test-editor'; document.body.append(host);
                    return m.mountScoreEditor(host, {kind: 'video', song: name, mouth_mode: 'lip_sync', actors: ['pig'], lyric_lines: [], singers: []}, quote,
                        {onDirty: () => {}, onReplan: async () => {}});
                })""", [name, quote])
                expect(page.locator('#test-editor .se-lip-summary')).to_contain_text('No lyric lines yet')
                expect(page.get_by_label('Speech model for lyrics detection')).to_have_value('large-v3')
                self.assertFalse(page.evaluate('document.querySelector("#test-editor .se-lip button[title^=\'Listen\']").disabled'))
                page.locator('#test-editor button:has-text("Detect lyrics")').click()
                expect(page.locator('#test-editor .se-line-row')).to_have_count(1, timeout=15000)
                expect(page.locator('#test-editor .se-status')).to_contain_text('Detected 1 lines from the vocals stem')
                self.assertEqual(posts[0][1]['model'], 'large-v3')
                page.locator('#test-editor textarea').fill('Interdimensional lover\nI dated you')
                page.locator('#test-editor button:has-text("Time pasted lyrics")').click()
                expect(page.locator('#test-editor .se-line-row')).to_have_count(2)
                expect(page.locator('#test-editor .se-status')).to_contain_text('1 line(s) could not be matched well')
                expect(page.locator('#test-editor .se-lip-summary')).to_contain_text('not used for singing until you confirm')
                page.locator('#test-editor button:has-text("Confirm timing")').click()
                expect(page.locator('#test-editor .se-lip-summary')).not_to_contain_text('guessed timing')
                self.assertEqual(posts[1][1]['text'], 'Interdimensional lover\nI dated you')
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_a_modified_prompting_scheme_shows_a_warning_banner_and_an_intact_one_shows_nothing(self):
        from playwright.sync_api import sync_playwright, expect
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#open-vocab-panel-btn").onclick !== null')
                expect(page.locator('#scheme-notice')).to_be_hidden()
                page.route('**/api/integrity', lambda route: route.fulfill(json={
                    'intact': False, 'changed': ['the writer prompt'], 'notice': 'This installation has changed Mondo\'s protected prompting scheme (the writer prompt). Videos made with it may not meet the Mondo standard.'}))
                page.reload()
                expect(page.locator('#scheme-notice')).to_be_visible()
                expect(page.locator('#scheme-notice')).to_contain_text('may not meet the Mondo standard')
            finally:
                browser.close()

    def test_subliminal_controls_show_the_right_fields_and_build_one_nested_request_object(self):
        from playwright.sync_api import sync_playwright, expect
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            errors = []
            page.on('pageerror', lambda err: errors.append(str(err)))
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#open-vocab-panel-btn").onclick !== null')
                page.evaluate('() => { document.querySelectorAll("#video-form details").forEach(el => el.open = true); }')
                fields = page.locator('#video-form .subliminal-fields')
                expect(fields).to_be_hidden()
                page.locator('#video-form select[name=subliminal_mode]').select_option('text')
                expect(fields).to_be_visible()
                expect(page.locator('#video-form input[name=subliminal_text]')).to_be_visible()
                expect(page.locator('#video-form input[name=subliminal_file]')).to_be_hidden()
                expect(page.locator('#video-form input[name=subliminal_times]')).to_be_visible()
                page.locator('#video-form select[name=subliminal_mode]').select_option('image')
                expect(page.locator('#video-form input[name=subliminal_file]')).to_be_visible()
                expect(page.locator('#video-form input[name=subliminal_text]')).to_be_hidden()
                page.locator('#video-form select[name=subliminal_placement]').select_option('downbeats')
                expect(page.locator('#video-form input[name=subliminal_count]')).to_be_visible()
                expect(page.locator('#video-form input[name=subliminal_times]')).to_be_hidden()
                nested = page.evaluate("""() => import('/js/production.js').then(m => {
                    const request = {title: 'x', subliminal_mode: 'text', subliminal_text: 'HONK', subliminal_frames: '3', subliminal_placement: 'manual',
                                     subliminal_times: '12.5, 40 55.2', subliminal_count: '4', subliminal_file: {}, subliminal_image: ''};
                    m.subliminalFromForm(request);
                    let message = '';
                    try { m.subliminalFromForm({subliminal_mode: 'text', subliminal_times: 'soon'}); } catch (error) { message = error.message; }
                    return {request, message};
                })""")
                self.assertEqual(nested['request'], {'title': 'x', 'subliminal': {'mode': 'text', 'image': '', 'text': 'HONK', 'frames': 3,
                                 'placement': 'manual', 'times': [12.5, 40, 55.2], 'count': 4}})
                self.assertIn('seconds', nested['message'])
                page.locator('#video-form select[name=captions_mode]').select_option('burned')
                colours = page.locator('#video-form [data-caption-colours]')
                expect(colours).to_be_hidden()
                def caption_request():
                    return page.evaluate("""() => import('/js/production.js').then(m => {
                        const request = Object.fromEntries(new FormData(document.querySelector('#video-form')));
                        m.captionsFromForm(request);
                        return {captions: request.captions, flat: Object.keys(request).filter(k => k.startsWith('captions_'))};
                    })""")
                defaults = {'mode': 'burned', 'style': 'classic', 'position': 'bottom', 'size': 'medium',
                            'color': '', 'outline_color': '', 'font': ''}
                self.assertEqual(caption_request(), {'captions': defaults, 'flat': []})
                page.locator('#video-form input[name=captions_custom]').check()
                expect(colours).to_be_visible()
                page.locator('#video-form input[name=captions_color]').fill('#123456')
                page.locator('#video-form input[name=captions_outline]').fill('#654321')
                page.locator('#video-form input[name=captions_font]').fill('DejaVu Sans')
                self.assertEqual(caption_request(), {'captions': {**defaults, 'color': '#123456',
                                 'outline_color': '#654321', 'font': 'DejaVu Sans'}, 'flat': []})
                page.locator('#video-form input[name=captions_custom]').uncheck()
                expect(colours).to_be_hidden()
                self.assertEqual(caption_request(), {'captions': {**defaults, 'font': 'DejaVu Sans'}, 'flat': []})
                page.evaluate("() => import('/js/project.js').then(m => m.saveProject())")
                page.reload()
                page.wait_for_function("() => document.querySelector('#video-form input[name=captions_font]').value === 'DejaVu Sans'")
                page.evaluate('() => { document.querySelectorAll("#video-form details").forEach(el => el.open = true); }')
                expect(page.locator('#video-form [data-caption-colours]')).to_be_hidden()
                page.locator('#video-form input[name=captions_custom]').check()
                self.assertEqual(page.locator('#video-form input[name=captions_color]').input_value(), '#123456')
                page.evaluate("() => import('/js/project.js').then(m => m.saveProject())")
                page.reload()
                page.wait_for_function("() => document.querySelector('#video-form input[name=captions_custom]').checked")
                page.evaluate('() => { document.querySelectorAll("#video-form details").forEach(el => el.open = true); }')
                expect(page.locator('#video-form [data-caption-colours]')).to_be_visible()
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_an_open_edit_view_shows_a_take_finished_after_it_was_opened(self):
        from playwright.sync_api import sync_playwright, expect
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=str(_cached_chromium()[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            errors = []
            page.on('pageerror', lambda err: errors.append(str(err)))
            video = {'file': 'run1/music-video.mp4', 'kind': 'video', 'title': 'Test video', 'duration': 5}
            take = lambda n: {'id': f'take{n}', 'label': f'Take {n}', 'seed': n, 'clip_url': f'/api/outputs/run1/clips/seg000?take=take{n}'}
            breakdown = {'run_id': 'run1', 'source_run_id': 'run1', 'title': 'Test video', 'kind': 'video', 'final_takes': [],
                         'reroll_blocked': None, 'prompt_blocked': None, 'writer_charge': {}, 'prompt_limit': None,
                         'segments': [{'index': 0, 'segment_id': 'seg000', 'prompt': 'Coastline.', 'duration': 2, 'trim_frames': 48,
                                       'shots': [], 'has_clip': True, 'clip_url': '/api/outputs/run1/clips/seg000',
                                       'active_take': 'take1', 'takes': [take(1)], 'active_prompt_take': None, 'prompt_takes': []}]}
            page.route('**/api/outputs', lambda route: route.fulfill(json=[video]))
            page.route('**/api/outputs/run1/prompts', lambda route: route.fulfill(json=breakdown))
            page.route('**/api/outputs/run1/clips/**', lambda route: route.fulfill(status=404))
            page.route('**/api/media/**', lambda route: route.fulfill(status=404))
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#open-vocab-panel-btn").onclick !== null')
                page.locator('button.nav[data-panel=outputs]').click()
                page.locator('#output-list button', has_text='Edit').click()
                expect(page.locator('select.passage-take-select option')).to_have_count(1)
                # A take finishes elsewhere (e.g. started before the view was reopened); the operation's completion refreshes it.
                breakdown['segments'][0].update(takes=[take(1), take(2)], active_take='take2')
                page.evaluate("""async () => { const m = await import('/js/production.js');
                    await m.applyStatus({state: 'running', kind: 'reroll'}); await m.applyStatus({state: 'complete', kind: 'reroll'}); }""")
                expect(page.locator('select.passage-take-select option')).to_have_count(2)
                self.assertEqual(page.locator('select.passage-take-select').input_value(), 'take2')
                # ↻ Refresh reads it again on demand.
                breakdown['segments'][0].update(takes=[take(1), take(2), take(3)], active_take='take3')
                page.locator('#prompts-view-refresh-btn').click()
                expect(page.locator('select.passage-take-select option')).to_have_count(3)
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_the_caption_dialog_defaults_to_the_bottom_and_sends_the_chosen_look(self):
        from playwright.sync_api import sync_playwright, expect
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            errors, sent = [], []
            page.on('pageerror', lambda err: errors.append(str(err)))
            video = {'file': 'run1/music-video.mp4', 'kind': 'video', 'title': 'Test video', 'duration': 5}
            page.route('**/api/outputs', lambda route: route.fulfill(json=[video]))
            page.route('**/api/captions/fonts', lambda route: route.fulfill(json={'fonts': ['DejaVu Sans', 'Liberation Serif']}))
            page.route('**/api/captions', lambda route: (sent.append(route.request.post_data_json), route.fulfill(json={'id': 'x'}))[1])
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#open-vocab-panel-btn").onclick !== null')
                page.locator('button.nav[data-panel=outputs]').click()
                page.get_by_role('button', name='Add lyric captions').click()
                expect(page.locator('#caption-fonts option')).to_have_count(2)
                self.assertEqual(page.locator('#caption-fonts option').evaluate_all('(nodes) => nodes.map(n => n.value)'), ['DejaVu Sans', 'Liberation Serif'])
                dialog = page.locator('#caption-dialog')
                expect(dialog).to_be_visible()
                expect(page.locator('#caption-form [data-caption-colours]')).to_be_hidden()
                self.assertEqual(page.locator('#caption-form select[name=position]').input_value(), 'bottom')   # the default
                self.assertEqual([o.get_attribute('value') for o in page.locator('#caption-form select[name=position] option').all()], ['bottom', 'middle', 'top'])
                dialog.get_by_role('button', name='Add captions').click()
                expect(dialog).to_be_hidden()
                page.get_by_role('button', name='Add lyric captions').click()
                page.locator('#caption-form select[name=position]').select_option('top')
                page.locator('#caption-form select[name=style]').select_option('neon')
                page.locator('#caption-form input[name=custom]').check()
                expect(page.locator('#caption-form [data-caption-colours]')).to_be_visible()
                page.locator('#caption-form input[name=color]').fill('#abcdef')
                page.locator('#caption-form input[name=outline]').fill('#112233')
                page.locator('#caption-form input[name=font]').fill('Liberation Serif')
                dialog.get_by_role('button', name='Add captions').click()
                expect(dialog).to_be_hidden()
                page.get_by_role('button', name='Add lyric captions').click()
                page.locator('#caption-form input[name=custom]').uncheck()
                expect(page.locator('#caption-form [data-caption-colours]')).to_be_hidden()
                dialog.get_by_role('button', name='Add captions').click()
                expect(dialog).to_be_hidden()
                self.assertEqual(sent, [{'position': 'bottom', 'style': 'classic', 'size': 'medium', 'color': '', 'outline_color': '', 'font': '', 'source': 'run1/music-video.mp4'},
                                        {'position': 'top', 'style': 'neon', 'size': 'medium', 'color': '#abcdef', 'outline_color': '#112233', 'font': 'Liberation Serif', 'source': 'run1/music-video.mp4'},
                                        {'position': 'top', 'style': 'neon', 'size': 'medium', 'color': '', 'outline_color': '', 'font': 'Liberation Serif', 'source': 'run1/music-video.mp4'}])
                page.unroute('**/api/captions/fonts')
                page.route('**/api/captions/fonts', lambda route: route.abort())
                page.reload()
                page.wait_for_function('() => document.querySelector("#open-vocab-panel-btn").onclick !== null')
                expect(page.locator('#caption-fonts option')).to_have_count(0)
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_colour_wheel_maths_round_trips_and_wraps_hue(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page()
            try:
                page.goto(self.url)
                got = page.evaluate("""() => import('/js/colorwheel.js').then(m => ({
                    trip: ['#ff8800', '#000000', '#ffffff', '#123456', '#34b354'].map(h => m.toHex(m.hsvToRgb(...Object.values(m.rgbToHsv(m.parseHex(h)))))),
                    parsed: [m.parseHex('#f80'), m.parseHex('abc'), m.parseHex(' #AABBCC '), m.parseHex('nonsense'), m.parseHex('#12345')],
                    wrapped: [m.toHex(m.hsvToRgb(-120, 1, 1)), m.toHex(m.hsvToRgb(240, 1, 1)), m.toHex(m.hsvToRgb(750, 1, 1))],
                    grey: m.rgbToHsv([128, 128, 128]), black: m.rgbToHsv([0, 0, 0])
                }))""")
                self.assertEqual(got['trip'], ['#ff8800', '#000000', '#ffffff', '#123456', '#34b354'])
                self.assertEqual(got['parsed'], [[255, 136, 0], [170, 187, 204], [170, 187, 204], None, None])
                self.assertEqual(got['wrapped'], ['#0000ff', '#0000ff', '#ff8000'])
                self.assertEqual((got['grey']['s'], got['black']['v']), (0, 0))
            finally:
                browser.close()

    def test_colour_wheels_replace_the_native_pickers_and_drive_the_hex_values(self):
        from playwright.sync_api import sync_playwright, expect
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            errors, sent = [], []
            page.on('pageerror', lambda err: errors.append(str(err)))
            video = {'file': 'run1/music-video.mp4', 'kind': 'video', 'title': 'Test video', 'duration': 5}
            page.route('**/api/outputs', lambda route: route.fulfill(json=[video]))
            page.route('**/api/captions', lambda route: (sent.append(route.request.post_data_json), route.fulfill(json={'id': 'x'}))[1])
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#open-vocab-panel-btn").onclick !== null')
                page.evaluate('() => { document.querySelectorAll("#video-form details").forEach(el => el.open = true); }')
                self.assertEqual(page.locator('input[type=color]').count(), 0)                     # no native picker anywhere
                page.locator('#video-form select[name=captions_mode]').select_option('burned')
                page.locator('#video-form input[name=captions_custom]').check()
                wheels = page.locator('#video-form .colour-wheel canvas')
                self.assertEqual((wheels.count(), page.locator('#video-form .colour-wheel input[type=range]').count()), (2, 2))
                text = page.locator('#video-form input[name=captions_color]')
                wheels.nth(0).scroll_into_view_if_needed()
                box = wheels.nth(0).bounding_box()
                cx, cy, r = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2, box['width'] / 2
                self.assertEqual(text.input_value(), '#ffffff')
                page.mouse.click(cx + r * 0.9, cy)                                                  # the right edge is red
                red = text.input_value()
                self.assertRegex(red, r'^#ff[0-4][0-9a-f]{3}$|^#f[0-9a-f]{1}[0-4][0-9a-f]{3}$')
                self.assertEqual(wheels.nth(0).get_attribute('role'), 'slider')
                self.assertIn(red, wheels.nth(0).get_attribute('aria-valuetext'))
                page.locator('#video-form .colour-wheel input[type=range]').first.fill('50')       # half brightness darkens it
                dark = text.input_value()
                self.assertLess(int(dark[1:3], 16), int(red[1:3], 16))
                self.assertGreater(int(dark[1:3], 16), 100)
                page.mouse.click(cx - r * 0.9, cy)                                                  # the left edge is cyan-ish: red drops out
                self.assertLess(int(text.input_value()[1:3], 16), 0x80)
                page.mouse.click(cx, cy)                                                            # the centre has no saturation: grey
                grey = text.input_value()
                self.assertEqual(grey[1:3], grey[3:5])
                self.assertEqual(grey[3:5], grey[5:7])
                text.fill('abc'); text.blur()                                                       # typing: 3 digits expand
                self.assertEqual(text.input_value(), '#aabbcc')
                text.fill('nonsense'); text.blur()                                                  # junk goes back to the last good colour
                self.assertEqual(text.input_value(), '#aabbcc')
                page.mouse.click(cx + r * 0.9, cy, button='right')                                  # a right click does not pick
                self.assertEqual(text.input_value(), '#aabbcc')
                wheels.nth(0).focus()                                                               # keyboard: arrows move hue and saturation
                before = text.input_value()
                page.keyboard.press('ArrowRight')
                self.assertNotEqual(text.input_value(), before)
                page.mouse.click(cx + r * 0.5, cy + r * 0.5)                                       # a click takes focus, so arrows act on the wheel
                self.assertTrue(page.evaluate('() => document.activeElement.tagName === "CANVAS"'))
                outline = page.locator('#video-form input[name=captions_outline]')
                expect(outline).to_have_value('#000000')                                           # black: a wheel pick lifts it to full brightness
                other = wheels.nth(1).bounding_box()
                page.mouse.click(other['x'] + other['width'] * 0.9, other['y'] + other['height'] / 2)
                self.assertRegex(outline.input_value(), r'^#ff')
                request = page.evaluate("""() => import('/js/production.js').then(m => {
                    const request = Object.fromEntries(new FormData(document.querySelector('#video-form'))); m.captionsFromForm(request); return request.captions; })""")
                self.assertEqual((request['color'], request['outline_color']), (text.input_value(), outline.input_value()))
                # the dialog uses the same wheels and posts their values
                page.locator('button.nav[data-panel=outputs]').click()
                page.get_by_role('button', name='Add lyric captions').click()
                page.locator('#caption-form input[name=custom]').check()
                dialog_wheel = page.locator('#caption-form .colour-wheel canvas').first
                d = dialog_wheel.bounding_box()
                page.mouse.click(d['x'] + d['width'] * 0.5, d['y'] + d['height'] * 0.05)           # the top edge is a green-yellow hue
                chosen = page.locator('#caption-form input[name=color]').input_value()
                page.get_by_role('button', name='Add captions').click()
                expect(page.locator('#caption-dialog')).to_be_hidden()
                self.assertEqual(sent[-1]['color'], chosen)
                self.assertNotEqual(chosen, '#ffffff')
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_the_flash_picture_upload_cannot_race_fail_silently_or_go_stale(self):
        from playwright.sync_api import sync_playwright, expect
        png = self.home / 'flash.png'
        png.write_bytes(b'\x89PNG\r\n\x1a\n')
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            errors = []
            page.on('pageerror', lambda err: errors.append(str(err)))
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#open-vocab-panel-btn").onclick !== null')
                page.evaluate('() => { document.querySelectorAll("#video-form details").forEach(el => el.open = true); }')
                page.locator('#video-form select[name=subliminal_mode]').select_option('image')
                counter = {'n': 0}

                def upload(route):
                    counter['n'] += 1
                    route.fulfill(json={'file': f'picture-{counter["n"]}.png'})
                page.route('**/api/upload/reference', upload)
                picture = page.locator('#video-form input[name=subliminal_file]')
                image = lambda: page.evaluate('document.querySelector("#video-form input[name=subliminal_image]").value')
                picture.set_input_files(str(png))
                page.wait_for_function('() => document.querySelector("#video-form input[name=subliminal_image]").value === "picture-1.png"')
                picture.set_input_files([])                                    # clearing the choice clears the stored picture
                page.wait_for_function('() => document.querySelector("#video-form input[name=subliminal_image]").value === ""')
                self.assertIsNone(page.evaluate('document.querySelector("#video-form").dataset.subliminalPending || null'))
                # a failed upload leaves nothing selected and nothing pending
                page.unroute('**/api/upload/reference')
                page.route('**/api/upload/reference', lambda route: route.abort())
                picture.set_input_files(str(png))
                page.wait_for_function('() => !document.querySelector("#video-form").dataset.subliminalPending')
                self.assertEqual(image(), '')
                # the helper makes older selections lose to the newest, whatever order they finish in
                result = page.evaluate("""() => import('/js/production.js').then(m => {
                    const selection = m.latestSelection();
                    const first = selection.begin(), second = selection.begin();
                    return [selection.isCurrent(first), selection.isCurrent(second)];
                })""")
                self.assertEqual(result, [False, True])
                # previewing while a picture is still uploading, or in picture mode with none chosen, is refused
                message = page.evaluate("""() => import('/js/production.js').then(m => {
                    const form = document.querySelector('#video-form');
                    form.dataset.subliminalPending = '1';
                    return m.preview(form).then(() => 'no error', error => error.message);
                })""")
                self.assertIn('Wait for the flash picture', message)
                page.evaluate('() => { delete document.querySelector("#video-form").dataset.subliminalPending; }')
                message = page.evaluate("""() => import('/js/production.js').then(m => {
                    try { m.subliminalFromForm({subliminal_mode: 'image', subliminal_image: '', subliminal_times: '5'}); return 'no error'; } catch (error) { return error.message; }
                })""")
                self.assertIn('Choose the picture', message)
                self.assertEqual([e for e in errors if 'Failed to' not in e], [])
            finally:
                browser.close()

    def test_saved_custom_vocabulary_preset_survives_reload(self):
        from playwright.sync_api import sync_playwright, expect
        self.fixture.client.post('/api/vocabularies', json={
            'id': 'mine', 'name': 'Mine', 'base_profile': 'full', 'tables': {}}).raise_for_status()
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            try:
                page.goto(self.url)
                page.wait_for_function('() => document.querySelector("#vocab-profile-select option[value=mine]") !== null')
                page.evaluate('() => { document.querySelectorAll("#video-form details").forEach(el => el.open = true); }')
                page.locator('#vocab-profile-select').select_option('mine')
                page.evaluate("() => import('/js/project.js').then(m => m.saveProject())")
                page.reload()
                page.wait_for_function('() => document.querySelector("#video-form .song-input").onchange !== null')
                expect(page.locator('#vocab-profile-select')).to_have_value('mine')
            finally:
                browser.close()

    def test_update_notice_link_and_opt_in_setting(self):
        from mmv.storage import write_json
        from playwright.sync_api import sync_playwright, expect
        write_json(self.home / 'update-status.json', {
            'state': 'available', 'available': True, 'automatic': False,
            'message': 'An update is available. Automatic installation is turned off.',
            'available_version': '9.0.0', 'repository_url': 'https://github.com/example/mmv'})
        with sync_playwright() as p:
            cached = _cached_chromium()
            browser = p.chromium.launch(headless=True, executable_path=str(cached[-1]))
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            try:
                page.goto(self.url)
                expect(page.locator('#update-banner')).to_be_visible()
                expect(page.locator('#update-message')).to_contain_text('9.0.0')
                expect(page.locator('#update-repository')).to_have_attribute('href', 'https://github.com/example/mmv')
                page.wait_for_function('() => document.querySelector("#video-form .song-input").onchange !== null')
                page.locator('.nav[data-panel=settings]').click()
                choice = page.locator('input[name=auto_updates]')
                expect(choice).not_to_be_checked()
                autosaved(page, choice.check)
                expect(choice).to_be_checked()
                self.assertTrue(self.fixture.store.settings()['auto_updates'])
                autosaved(page, choice.uncheck)
                expect(choice).not_to_be_checked()
                self.assertFalse(self.fixture.store.settings()['auto_updates'])
            finally:
                browser.close()

    def test_sdk_selection_preview_recovery_and_playback(self):
        from playwright.sync_api import sync_playwright, expect
        self.fixture.configure_sdk()
        self.fixture.server.v2_download_fail = True
        with sync_playwright() as p:
            cached = _cached_chromium()
            kwargs = {'executable_path': str(cached[-1])} if cached else {}
            browser = p.chromium.launch(headless=True, **kwargs)
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            page.on('pageerror', lambda err: errors.append(str(err)))
            try:
                page.goto(self.url)
                expect(page.locator('#version')).to_have_text('1.12.3')
                page.wait_for_function('() => document.querySelector("#video-form .song-input").onchange !== null')
                page.locator('#video-form select[name=backend]').select_option('comfy_sdk_h3')
                page.locator('#video-form .song-input').set_input_files(str(self.song))
                expect(page.locator('#video-form .song-receipt')).to_contain_text('Uploaded:')
                expect(page.locator('#video-form .song-preview')).to_be_visible()
                page.locator('#video-form textarea[name=direction]').fill('A sunlit coast with rhythmic waves.')
                page.locator('#video-form button[type=submit]').click()
                expect(page.locator('#preview-dialog')).to_be_visible()
                expect(page.locator('#quote-summary')).to_contain_text('$0.00')
                page.locator('#consent').check()
                page.locator('#start-production').click()
                expect(page.locator('#status-title')).to_have_text('FAILED', timeout=30000)
                self.fixture.server.v2_download_fail = False
                page.locator('#resume-production').click()
                expect(page.locator('#preview-dialog')).to_be_visible()
                expect(page.locator('#quote-summary')).to_contain_text('No writer calls')
                expect(page.locator('#consent')).not_to_be_checked()
                page.locator('#consent').check()
                page.locator('#start-production').click()
                expect(page.locator('#status-title')).to_have_text('COMPLETE', timeout=30000)
                page.locator('button[data-panel=outputs]').click()
                player = page.locator('#output-list video')
                expect(player).to_be_visible()
                page.wait_for_function('() => document.querySelector("#output-list video").readyState >= 2')
                self.assertAlmostEqual(player.evaluate('(v) => v.duration'), 1.1, delta=.08)
                self.assertEqual(len(self.fixture.server.v2_submits), 1)
                page.set_viewport_size({'width': 390, 'height': 844})
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), 390)
                self.assertEqual(errors, [])
            finally:
                browser.close()
