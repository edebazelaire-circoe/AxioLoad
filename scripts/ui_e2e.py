from __future__ import annotations

import base64
import re
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

from pallet_optimizer.api import create_app


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)
SCREENSHOT = REPORTS / "ui-results-v7.png"
VEHICLE_SCREENSHOT = REPORTS / "vehicle-screen-v7.png"
SETTINGS_SCREENSHOT = REPORTS / "settings-dark-v7.png"
MOBILE_SCREENSHOT = REPORTS / "mobile-dark-v7.png"


def data_uri(path: Path, media_type: str) -> str:
    return f"data:{media_type};base64," + base64.b64encode(path.read_bytes()).decode()


with tempfile.TemporaryDirectory() as data_dir:
    app = create_app(data_dir)
    client = TestClient(app)
    html = client.get("/").text
    css = (ROOT / "src" / "pallet_optimizer" / "static" / "app.css").read_text(encoding="utf-8")
    js = (ROOT / "src" / "pallet_optimizer" / "static" / "app.js").read_text(encoding="utf-8")
    brand = ROOT / "src" / "pallet_optimizer" / "static" / "brand"
    html = html.replace('/static/brand/axioload-horizontal-dark.svg', data_uri(brand / 'axioload-horizontal-dark.svg', 'image/svg+xml'))
    html = re.sub(r'<link rel="stylesheet" href="/static/app\.css\?v=[^"]+">', f"<style>{css}</style>", html)
    html = re.sub(r'<script src="/static/app\.js\?v=[^"]+"></script>', "", html)
    html = re.sub(r'<link rel="icon"[^>]+>', "", html)

    def optimize(payload: dict) -> dict:
        return client.post("/local/optimize", json=payload).json()

    def list_vehicles() -> list[dict]:
        return client.get("/api/vehicles").json()

    def save_vehicle(payload: dict) -> dict:
        response = client.post("/api/vehicles", json=payload)
        return {"status": response.status_code, "body": response.json()}

    def operational_export(url: str, payload: dict) -> dict:
        response = client.post(url, json=payload)
        return {
            "status": response.status_code,
            "content_type": response.headers.get("content-type", "application/octet-stream"),
            "body_base64": base64.b64encode(response.content).decode(),
            "error": response.json() if response.status_code >= 400 else None,
        }

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path="/usr/bin/chromium",
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        page = browser.new_page(viewport={"width": 1600, "height": 1100})
        console_errors: list[str] = []
        page_errors: list[str] = []
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.expose_function("pythonOptimize", optimize)
        page.expose_function("pythonListVehicles", list_vehicles)
        page.expose_function("pythonSaveVehicle", save_vehicle)
        page.expose_function("pythonOperationalExport", operational_export)
        page.set_content(html, wait_until="domcontentloaded")
        page.add_script_tag(content="""
          (() => {
            const values = {};
            Object.defineProperty(window, 'localStorage', {value: {
              getItem: key => Object.prototype.hasOwnProperty.call(values, key) ? values[key] : null,
              setItem: (key, value) => { values[key] = String(value); },
              removeItem: key => { delete values[key]; },
              clear: () => { Object.keys(values).forEach(key => delete values[key]); }
            }});
          })();
        """)
        page.add_script_tag(content="""
          window.unexpectedFetches = [];
          window.fetch = async (url, options={}) => {
            const target = String(url);
            if (target.includes('/local/optimize')) {
              const result = await window.pythonOptimize(JSON.parse(options.body));
              return new Response(JSON.stringify(result), {status: 200, headers: {'Content-Type':'application/json'}});
            }
            if (target === '/api/vehicles' && (options.method || 'GET') === 'POST') {
              const result = await window.pythonSaveVehicle(JSON.parse(options.body));
              return new Response(JSON.stringify(result.body), {status: result.status, headers: {'Content-Type':'application/json'}});
            }
            if (target === '/api/vehicles') {
              const result = await window.pythonListVehicles();
              return new Response(JSON.stringify(result), {status: 200, headers: {'Content-Type':'application/json'}});
            }
            if (target.includes('/export-operational.pdf')) {
              const result = await window.pythonOperationalExport(target, JSON.parse(options.body));
              if (result.status >= 400) return new Response(JSON.stringify(result.error), {status: result.status, headers: {'Content-Type':'application/json'}});
              const binary = atob(result.body_base64);
              const bytes = new Uint8Array(binary.length);
              for (let i=0;i<binary.length;i++) bytes[i]=binary.charCodeAt(i);
              return new Response(bytes, {status: result.status, headers: {'Content-Type':result.content_type}});
            }
            if (target.startsWith('/api/history')) {
              return new Response(JSON.stringify([]), {status: 200, headers: {'Content-Type':'application/json'}});
            }
            window.unexpectedFetches.push(target);
            return new Response(JSON.stringify({detail:'Route non simulée'}), {status: 404, headers: {'Content-Type':'application/json'}});
          };
        """)
        page.add_script_tag(content=js)

        assert page.title().startswith("AxioLoad")
        assert page.locator('.brand-logo').is_visible()
        assert page.locator('#open-settings').is_visible()
        assert page.locator('.status-pill').count() == 0
        assert page.locator('#tab-vehicles.active').is_visible()
        assert page.locator('#vehicle-table tbody tr').count() == 2
        page.locator('#tab-vehicles .help-tip').first.hover()
        assert page.locator('#global-tooltip').is_visible()
        assert page.locator('#global-tooltip').inner_text().strip()
        page.mouse.move(10, 10)
        page.screenshot(path=str(VEHICLE_SCREENSHOT), full_page=True)

        page.locator('#open-settings').click()
        assert page.locator('#tab-settings.active').is_visible()
        assert page.locator('#account-form').is_visible()
        assert page.locator('#api-key-list .api-key-row').count() == 2
        page.locator('input[name="theme"][value="dark"]').check()
        assert page.locator('html').get_attribute('data-theme') == 'dark'
        page.locator('#new-username').fill('Exploitant AxioLoad')
        page.locator('#new-password').fill('MotDePasseTest9!')
        page.locator('#confirm-password').fill('MotDePasseTest9!')
        page.locator('#account-form button[type="submit"]').click()
        page.locator('#account-message.success').wait_for()
        assert 'enregistrées' in page.locator('#account-message').inner_text()
        page.locator('#api-key-list .api-key-row').first.locator('[data-api="key"]').fill('cle-test-non-active')
        page.locator('#api-key-list .api-key-row').first.locator('.api-save').click()
        page.locator('#api-message.success').wait_for()
        saved_settings = page.evaluate("JSON.parse(localStorage.getItem('axioload.settings.v1'))")
        assert saved_settings['theme'] == 'dark'
        assert saved_settings['account']['username'] == 'Exploitant AxioLoad'
        assert saved_settings['account']['passwordHash']
        assert 'MotDePasseTest9!' not in str(saved_settings)
        assert page.evaluate('window.unexpectedFetches') == []
        page.screenshot(path=str(SETTINGS_SCREENSHOT), full_page=True)
        page.locator('#close-settings').click()
        assert page.locator('#tab-vehicles.active').is_visible()

        semi_row = page.locator('#vehicle-table tbody tr').filter(
            has=page.locator('input[data-v="model_id"][value="semi_trailer"]')
        )
        semi_row.locator('[data-v="interior_length_mm"]').fill('5000')
        semi_row.locator('[data-v="interior_width_mm"]').fill('1600')
        semi_row.locator('[data-v="linear_meter_width_mm"]').fill('1600')
        semi_row.locator('[data-v="door_width_mm"]').fill('1600')
        page.locator('#save-vehicles').click()
        page.locator('#vehicle-message').wait_for(state='visible')
        assert 'Catalogue enregistré' in page.locator('#vehicle-message').inner_text()

        page.locator('[data-tab="data"]').click()
        page.locator('#vehicle-id').select_option('semi_trailer')
        rows = page.locator('#cargo-table tbody tr')
        rows.nth(1).locator('.row-delete').click()
        first = page.locator('#cargo-table tbody tr').first
        first.locator('[data-k="quantity"]').fill('3')
        first.locator('[data-k="length"]').fill('1200')
        first.locator('[data-k="width"]').fill('800')
        first.locator('[data-k="height"]').fill('1200')
        first.locator('[data-k="weight"]').fill('500')
        page.locator('#max-vehicles').fill('1')
        page.locator('#optimize').click()

        page.locator('#results-content:not(.hidden)').wait_for(timeout=15000)
        assert page.locator('.solution-card').count() == 5
        methods = page.locator('.solution-method strong').all_inner_texts()
        assert len(set(methods)) == 5
        assert page.locator('.solution-method .help-tip').count() == 5
        page.locator('.solution-method .help-tip').first.click()
        assert 'rotation' in page.locator('#global-tooltip').inner_text().lower()
        best_card = page.locator('.solution-card').first.inner_text()
        assert '2,00 m' in best_card, best_card
        assert '2,00 m.l.' in best_card, best_card
        assert page.locator('#viewer').is_visible()
        assert page.locator('#viewer-subtitle').inner_text().startswith('Longueur occupée 2,00 m')
        canvas_payload = page.locator('#viewer').evaluate("canvas => canvas.toDataURL('image/png')")
        assert len(canvas_payload) > 10_000
        page.screenshot(path=str(SCREENSHOT), full_page=True)

        with page.expect_download(timeout=20000) as download_info:
            page.locator('#export-operational-pdf').click()
        download = download_info.value
        assert download.suggested_filename.endswith('.pdf')
        operational_pdf = REPORTS / 'operational-plan-v4.pdf'
        download.save_as(operational_pdf)
        assert operational_pdf.read_bytes().startswith(b'%PDF')

        mobile = browser.new_page(viewport={"width": 390, "height": 844})
        mobile_errors: list[str] = []
        mobile.on("pageerror", lambda error: mobile_errors.append(str(error)))
        mobile.set_content(html, wait_until="domcontentloaded")
        mobile.add_script_tag(content="""
          (() => {
            const values = {'axioload.settings.v1': JSON.stringify({theme:'dark',account:{username:'Mobile',passwordHash:'',passwordSalt:''},apiKeys:[]})};
            Object.defineProperty(window, 'localStorage', {value: {
              getItem: key => Object.prototype.hasOwnProperty.call(values, key) ? values[key] : null,
              setItem: (key, value) => { values[key] = String(value); },
              removeItem: key => { delete values[key]; },
              clear: () => { Object.keys(values).forEach(key => delete values[key]); }
            }});
          })();
        """)
        mobile.add_script_tag(content=js)
        assert mobile.locator('.brand-logo').is_visible()
        assert mobile.locator('html').get_attribute('data-theme') == 'dark'
        mobile.locator('[data-tab="data"]').click()
        assert mobile.locator('#tab-data.active').is_visible()
        mobile.locator('#tab-data .help-tip').first.click()
        assert mobile.locator('#global-tooltip').is_visible()
        assert mobile.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
        mobile.screenshot(path=str(MOBILE_SCREENSHOT), full_page=True)
        assert not mobile_errors, mobile_errors

        assert not page_errors, page_errors
        assert not console_errors, console_errors
        browser.close()

print(f"UI E2E OK: {VEHICLE_SCREENSHOT}, {SETTINGS_SCREENSHOT}, {SCREENSHOT}, {MOBILE_SCREENSHOT}")
