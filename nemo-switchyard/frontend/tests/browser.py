"""Browser tests for routing methods; inference is mocked."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
BASE = os.getenv("UI_URL", "http://frontend:8080")
OUT = Path(os.getenv("QA_OUTPUT", "/qa")); OUT.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width":1440,"height":1100})
    errors=[]; page.on("pageerror",lambda error:errors.append(str(error)))
    methods={r['id']:r for r in page.request.get(BASE+'/api/config').json()['routes']}
    calls=[]; failure=[False]
    def respond(route):
        payload=route.request.post_data_json; calls.append(payload)
        if failure[0]: route.fulfill(status=429,json={"error":{"message":"Free quota reached"}}); return
        method=methods[payload['route']]; model=method['general']['model']
        decision={"classifier_label":method['label'],"judge":method['judge'],"selected_tier":"general","selected_label":"Configured target" if method['routing_type']=='direct' else "Pool target" if method['routing_type']=='random' else "General purpose","selected_model":model,"candidates":method['candidates'],"configured_policy":method['policy'],"source":"Mock selection","session_id":payload.get("session_id"),"preview_runs_completion":method.get("preview_runs_completion",False)}
        data={"selected":{"model":model},"fallbacks":[]} if payload['mode']=='preview' else {"model":model,"choices":[{"message":{"content":"Offline reply. <script> stays plain text."},"finish_reason":"stop"}],"usage":{"prompt_tokens":20,"completion_tokens":12}}
        route.fulfill(json={"data":data,"selected_model":model,"routing_decision":decision,"latency_ms":1450})
    page.route('**/api/run',respond)
    page.goto(BASE)
    expect(page.locator('#connection-label')).to_have_text('Gateway connected')
    expect(page.locator('#method-gallery button')).to_have_count(7)
    expect(page.locator('#routing-method')).to_have_value('direct')
    expect(page.locator('#run')).to_be_disabled()
    page.screenshot(path=str(OUT/'routing-methods-desktop.png'),full_page=True)
    page.locator('[data-example="simple"]').click()
    page.locator('#run').click()
    expect(page.locator('#result-state')).to_have_text('Complete')
    expect(page.locator('.decision-outcome')).to_contain_text('Configured target selected')
    expect(page.locator('#results .answer')).to_contain_text('<script> stays plain text')
    page.locator('#compare').click()
    expect(page.locator('#results .result-card')).to_have_count(7)
    expect(page.locator('#result-state')).to_have_text('Complete')
    assert {item['route'] for item in calls[-7:]} == set(methods)
    page.screenshot(path=str(OUT/'routing-methods-comparison.png'),full_page=True)
    page.locator('#routing-method').select_option('llm-classifier')
    expect(page.locator('#judge-label')).to_have_text('LLM classifier')
    page.locator('#run').click()
    expect(page.locator('#result-state')).to_have_text('Complete')
    expect(page.locator('#results .decision-card')).to_contain_text('liquid/lfm-2.5-2.6b:free')
    page.locator('[data-method="weighted-random"]').click()
    page.locator('[data-example="coding"]').click()
    expect(page.locator('#routing-method')).to_have_value('weighted-random')
    page.locator('#mode').select_option('preview'); page.locator('#run').click()
    expect(page.locator('#results .preview-note')).to_contain_text('no answer was generated')
    expect(page.locator('#results .decision-card')).to_contain_text('Pool target selected')
    page.locator('[data-method="advisor-review"]').click()
    expect(page.locator('#run-hint')).to_contain_text('not inference-free')
    page.locator('#run').click()
    expect(page.locator('#results .preview-note')).to_contain_text('executor/reviewer work')
    old_session=page.locator('#session-id').input_value()
    page.locator('#new-session').click()
    assert page.locator('#session-id').input_value()!=old_session
    failure[0]=True; page.locator('#run').click()
    expect(page.locator('#result-state')).to_have_text('Failed')
    expect(page.locator('#results .error-box')).to_contain_text('rate limited')
    page.locator('[data-view="routes"]').click()
    expect(page.locator('#route-cards .explorer-card')).to_have_count(7)
    expect(page.locator('#advanced-cards .advanced-card')).to_have_count(5)
    page.locator('[data-use-route="system-one"]').click()
    expect(page.locator('#routing-method')).to_have_value('system-one')
    page.locator('[data-view="history"]').click()
    expect(page.locator('.history-item')).to_have_count(12)
    page.locator('#clear-history').click(); expect(page.locator('#history-count')).to_have_text('0')
    page.locator('[data-view="playground"]').click()
    page.locator('#guide-button').click(); expect(page.locator('#guide')).to_be_visible(); page.locator('#close-guide').click()
    page.reload(); expect(page.locator('#method-gallery button')).to_have_count(7)
    page.set_viewport_size({"width":390,"height":844})
    page.screenshot(path=str(OUT/'routing-methods-mobile.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile overflow'
    assert not errors,errors
    print('PASS routing methods: selection, all-method comparison, previews, decisions, examples, advanced explorer, errors, history and mobile')
    browser.close()
