"""The in-page question overlay used by Teach Mode.

A small panel is injected into whatever page the user is on. It renders the
agent's current question (text + buttons, or an input + submit) and reports the
answer back to Python through the ``amavaAnswer`` binding. It also quietly
tracks the last form field the user focused/typed in and the last button they
clicked, so the wizard can learn selectors without the user pasting anything.

Design notes:
  * Rendered inside a shadow root so the host site's CSS can't touch it.
  * Re-attaches itself on a timer, so SPA route changes (Next.js/React) that
    rewrite the DOM don't make the panel disappear.
  * Field/click captures are mirrored to sessionStorage so they survive a full
    page navigation (e.g. the redirect right after a successful login).
"""
from __future__ import annotations

from typing import Any

# Injected via context.add_init_script so it runs on every document. Pure JS —
# do NOT format this as an f-string (the braces are JavaScript).
OVERLAY_JS = r"""
(() => {
  if (window.__amavaInit) return;
  window.__amavaInit = true;

  const HOST_ID = '__amava_host__';
  let lastField = null;   // {selector, value, type}
  let lastClick = null;   // {selector, text}

  try {
    lastField = JSON.parse(sessionStorage.getItem('__amava_field') || 'null');
    lastClick = JSON.parse(sessionStorage.getItem('__amava_click') || 'null');
  } catch (e) {}

  function cssPath(el) {
    if (!(el instanceof Element)) return null;
    if (el.id) return '#' + CSS.escape(el.id);
    const nm = el.getAttribute && el.getAttribute('name');
    if (nm) return el.tagName.toLowerCase() + '[name="' + nm + '"]';
    const parts = [];
    let cur = el;
    while (cur && cur.nodeType === 1 && parts.length < 6) {
      let sel = cur.tagName.toLowerCase();
      const p = cur.parentElement;
      if (p) {
        const same = Array.from(p.children).filter(c => c.tagName === cur.tagName);
        if (same.length > 1) sel += ':nth-of-type(' + (same.indexOf(cur) + 1) + ')';
      }
      parts.unshift(sel);
      cur = cur.parentElement;
    }
    return parts.join(' > ');
  }

  function inHost(el) {
    return el && el.closest && el.closest('#' + HOST_ID);
  }

  // From a clicked element, walk up to the repeating "card" container: the
  // nearest ancestor whose class selector matches several siblings (a grid of
  // products). Returns a general selector like 'div.product-card', or null.
  function cardSelector(el) {
    let cur = el;
    for (let depth = 0; cur && cur.nodeType === 1 && depth < 9; depth++, cur = cur.parentElement) {
      if (!cur.classList || !cur.classList.length) continue;
      for (const cls of cur.classList) {
        if (!cls || cls.length < 2) continue;
        const sel = cur.tagName.toLowerCase() + '.' + CSS.escape(cls);
        try {
          const n = document.querySelectorAll(sel).length;
          if (n >= 3 && n <= 300) return sel;  // looks like a repeated grid item
        } catch (e) {}
      }
    }
    if (el && el.classList && el.classList.length) {
      return el.tagName.toLowerCase() + '.' + CSS.escape(el.classList[0]);
    }
    return null;
  }

  document.addEventListener('focusin', (e) => {
    const t = e.target;
    if (!t || inHost(t)) return;
    const tag = (t.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') {
      lastField = { selector: cssPath(t), value: t.value || '', type: t.getAttribute('type') || tag };
      try { sessionStorage.setItem('__amava_field', JSON.stringify(lastField)); } catch (e) {}
    }
  }, true);

  document.addEventListener('input', (e) => {
    const t = e.target;
    if (!t || inHost(t)) return;
    if (lastField && cssPath(t) === lastField.selector) {
      lastField.value = t.value || '';
      try { sessionStorage.setItem('__amava_field', JSON.stringify(lastField)); } catch (e) {}
    }
  }, true);

  document.addEventListener('click', (e) => {
    const t = e.target;
    if (!t || inHost(t)) return;
    const btn = t.closest('button, a, input[type=submit], [role=button]') || t;
    lastClick = {
      selector: cssPath(btn),
      text: (btn.innerText || btn.value || '').trim().slice(0, 60),
      cardSelector: cardSelector(t),  // for learning product-card selectors
    };
    try { sessionStorage.setItem('__amava_click', JSON.stringify(lastClick)); } catch (e) {}
  }, true);

  window.__amavaLastField = () => lastField;
  window.__amavaLastClick = () => lastClick;
  window.__amavaResetField = () => { lastField = null; try { sessionStorage.removeItem('__amava_field'); } catch (e) {} };
  window.__amavaResetClick = () => { lastClick = null; try { sessionStorage.removeItem('__amava_click'); } catch (e) {} };

  const STYLE = `
    .card{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
      background:#111827;color:#f9fafb;width:min(440px,92vw);border-radius:14px;
      box-shadow:0 12px 40px rgba(0,0,0,.45);padding:18px 20px;border:1px solid #374151;}
    .brand{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#9ca3af;margin-bottom:6px;}
    .title{font-size:16px;font-weight:600;margin:0 0 6px;line-height:1.35;}
    .body{font-size:13px;color:#d1d5db;margin:0 0 14px;line-height:1.5;white-space:pre-wrap;word-break:break-word;}
    .row{display:flex;flex-wrap:wrap;gap:8px;}
    button{font:inherit;font-size:13px;font-weight:600;border:none;border-radius:9px;padding:9px 14px;cursor:pointer;}
    .primary{background:#6366f1;color:#fff;}
    .ghost{background:#1f2937;color:#e5e7eb;border:1px solid #374151;}
    .danger{background:#7f1d1d;color:#fee2e2;}
    input,textarea{font:inherit;font-size:14px;width:100%;box-sizing:border-box;padding:10px 12px;
      border-radius:9px;border:1px solid #374151;background:#0b1220;color:#f9fafb;margin-bottom:12px;}
    textarea{min-height:80px;resize:vertical;font-size:13px;}
  `;

  function ensureHost() {
    let host = document.getElementById(HOST_ID);
    if (host && host.isConnected) return host;
    host = document.createElement('div');
    host.id = HOST_ID;
    host.style.cssText = 'position:fixed;z-index:2147483647;bottom:20px;left:50%;transform:translateX(-50%);';
    host.__root = host.attachShadow ? host.attachShadow({ mode: 'open' }) : host;
    (document.documentElement || document.body).appendChild(host);
    return host;
  }

  let pending = null;  // current spec or null

  function renderPending() {
    if (!pending) return;
    const host = ensureHost();
    const root = host.__root;
    if (root.__renderedId === pending.__id) return;  // don't clobber user's typing
    root.__renderedId = pending.__id;
    const spec = pending;
    root.innerHTML = '<style>' + STYLE + '</style>';
    const card = document.createElement('div');
    card.className = 'card';
    let html = '<div class="brand">AMAVA · teaching</div>';
    if (spec.title) html += '<div class="title"></div>';
    if (spec.body) html += '<div class="body"></div>';
    if (spec.input) html += (spec.input.multiline ? '<textarea></textarea>' : '<input/>');
    html += '<div class="row"></div>';
    card.innerHTML = html;
    if (spec.title) card.querySelector('.title').textContent = spec.title;
    if (spec.body) card.querySelector('.body').textContent = spec.body;
    let fieldEl = null;
    if (spec.input) {
      fieldEl = card.querySelector(spec.input.multiline ? 'textarea' : 'input');
      if (!spec.input.multiline && spec.input.type) fieldEl.type = spec.input.type;
      if (spec.input.placeholder) fieldEl.placeholder = spec.input.placeholder;
      if (spec.input.value != null) fieldEl.value = spec.input.value;
    }
    const row = card.querySelector('.row');
    (spec.options || []).forEach(opt => {
      const b = document.createElement('button');
      b.className = opt.style || 'primary';
      b.textContent = opt.label;
      b.onclick = () => {
        const ans = { id: opt.id };
        if (fieldEl) ans.value = fieldEl.value;
        pending = null;
        root.innerHTML = '';
        root.__renderedId = null;
        if (window.amavaAnswer) window.amavaAnswer(JSON.stringify(ans));
      };
      row.appendChild(b);
    });
    root.appendChild(card);
    if (fieldEl) setTimeout(() => { try { fieldEl.focus(); } catch (e) {} }, 60);
  }

  // Survive SPA DOM rewrites: re-attach + re-render on a gentle timer.
  setInterval(() => { try { renderPending(); } catch (e) {} }, 1200);

  window.__amavaRender = (spec) => {
    spec.__id = String(Date.now()) + ':' + Math.random();
    pending = spec;
    const host = ensureHost();
    if (host.__root) host.__root.__renderedId = null;
    renderPending();
  };

  window.__amavaClear = () => {
    pending = null;
    const host = document.getElementById(HOST_ID);
    if (host && host.__root) { host.__root.innerHTML = ''; host.__root.__renderedId = null; }
  };
})();
"""


# --- spec builders ---------------------------------------------------------
def buttons(title: str, body: str, options: list[tuple[str, str, str]]) -> dict[str, Any]:
    """A question with one or more buttons.

    ``options`` is a list of (id, label, style) where style is
    'primary' | 'ghost' | 'danger'.
    """
    return {
        "title": title,
        "body": body,
        "options": [{"id": i, "label": lbl, "style": st} for (i, lbl, st) in options],
    }


def text_input(
    title: str,
    body: str,
    *,
    placeholder: str = "",
    value: str = "",
    input_type: str = "text",
    multiline: bool = False,
    submit_label: str = "Continue",
    submit_id: str = "submit",
) -> dict[str, Any]:
    """A question with a single input field and a submit button."""
    return {
        "title": title,
        "body": body,
        "input": {
            "placeholder": placeholder,
            "value": value,
            "type": input_type,
            "multiline": multiline,
        },
        "options": [{"id": submit_id, "label": submit_label, "style": "primary"}],
    }


def info(title: str, body: str) -> dict[str, Any]:
    """A message with no buttons (an instruction the wizard waits on itself)."""
    return {"title": title, "body": body, "options": []}
