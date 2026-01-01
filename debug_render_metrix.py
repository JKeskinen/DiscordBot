from playwright.sync_api import sync_playwright
from pathlib import Path
url='https://discgolfmetrix.com/3512047'
out=Path('debug_tjing')
out.mkdir(exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto(url, timeout=20000)
    page.wait_for_timeout(500)
    content=page.content()
    (out/'metrix_rendered.html').write_text(content, encoding='utf-8')
    try:
        b_texts = page.eval_on_selector_all('b', 'els => els.map(e => e.innerText)')
        print('Found <b> tags:', len(b_texts))
        for t in b_texts[:200]:
            print('-', repr(t))
    except Exception as e:
        print('b tags error', e)
    try:
        state = page.evaluate('() => (window.__INITIAL_STATE__ || window.__INITIAL_DATA__ || window.__INITIAL || null)')
        print('state type', type(state))
        (out/'metrix_state.json').write_text(str(state), encoding='utf-8')
    except Exception as e:
        print('state eval failed', e)
    b.close()
print('saved to', out/'metrix_rendered.html')
