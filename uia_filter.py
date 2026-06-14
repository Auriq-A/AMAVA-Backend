# uia_filter.py
# Requires: pip install pywin32 psutil

import time
import threading
import hashlib
import re
from collections import OrderedDict

import psutil
import win32gui
import win32process

# ---------- Config ----------
DEDUPE_WINDOW_SECONDS = (
    3.0  # consider identical events within this many seconds duplicates
)
IGNORE_IF_FOREGROUND = True  # ignore events coming from the current foreground window
IGNORE_CHILD_OF_FOREGROUND = True
BLACKLIST_PATTERNS = [
    r"Chrome Legacy Window",  # your log shows this repeated
    r"Qt\d+QWindowToolSaveBits",  # generic Qt tool classes
    r"python",  # windows titled "python" (if you don't want those)
]
BLACKLIST_APPS = [  # exe names to ignore
    "python.exe",  # if you generate UIA events yourself
]
# -----------------------------

_blacklist_regexes = [re.compile(pat, re.IGNORECASE) for pat in BLACKLIST_PATTERNS]


def get_foreground_info():
    """Return (hwnd, pid) of foreground window, or (None,None)."""
    try:
        hwnd = win32gui.GetForegroundWindow()
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return hwnd, pid
    except Exception:
        return None, None


def is_child_of(parent_hwnd, child_hwnd):
    """Walk up the chain to see if child_hwnd is inside parent_hwnd."""
    try:
        cur = child_hwnd
        while cur:
            if cur == parent_hwnd:
                return True
            cur = win32gui.GetParent(cur)
        return False
    except Exception:
        return False


def signature_for_event(ev: dict):
    """Create canonical signature string for dedupe & filter.
    ev expected keys: app, pid, hwnd, title, message, class
    """
    parts = (
        str(ev.get("app", "")).lower(),
        str(ev.get("title", "")).strip().lower(),
        str(ev.get("message", "")).strip().lower(),
        str(ev.get("class", "")).strip().lower(),
    )
    sig_raw = "\n".join(parts)
    return hashlib.sha1(sig_raw.encode("utf-8")).hexdigest()


class RecentSignatureStore:
    """Simple time-windowed LRU store for deduplication."""

    def __init__(self, expiry_seconds=DEDUPE_WINDOW_SECONDS, max_items=1024):
        self.expiry = expiry_seconds
        self.max_items = max_items
        self.lock = threading.Lock()
        self.store = OrderedDict()  # sig -> timestamp

    def seen_recent(self, sig):
        now = time.time()
        with self.lock:
            # purge expired
            to_delete = []
            for k, ts in list(self.store.items()):
                if now - ts > self.expiry:
                    to_delete.append(k)
            for k in to_delete:
                del self.store[k]

            # check
            if sig in self.store:
                # update LRU position
                self.store.move_to_end(sig)
                self.store[sig] = now
                return True
            # insert
            self.store[sig] = now
            # cap
            if len(self.store) > self.max_items:
                self.store.popitem(last=False)
            return False


# create a singleton store
_recent_signatures = RecentSignatureStore()

# get our PID so we can ignore our own windows
_OUR_PID = psutil.Process().pid


def matches_blacklist(ev: dict):
    title = str(ev.get("title", "") or "")
    classname = str(ev.get("class", "") or "")
    app = str(ev.get("app", "") or "")
    for regex in _blacklist_regexes:
        if regex.search(title) or regex.search(classname):
            return True
    if app.lower() in (name.lower() for name in BLACKLIST_APPS):
        return True
    return False


def should_ignore_event(ev: dict):
    """
    Return True if event should be ignored, otherwise False.
    Accepts ev like:
    {
      "ts_iso": "...",
      "hwnd": 12345,
      "pid": 5678,
      "app": "Discord.exe",
      "class": "Chrome_RenderWidgetHostHWND",
      "window_title": "Chrome Legacy Window",
      "extracted_text": "...",
      "title": "...",
      "message": "...",
      "source": "uia"
    }
    """
    try:
        hwnd = int(ev.get("hwnd") or 0)
    except Exception:
        hwnd = 0
    try:
        pid = int(ev.get("pid") or 0)
    except Exception:
        pid = 0

    # 1) ignore self
    if pid == _OUR_PID:
        return True

    # 2) blacklist by class/title/app heuristics
    if matches_blacklist(ev):
        return True

    # 3) foreground filtering
    if IGNORE_IF_FOREGROUND:
        fg_hwnd, fg_pid = get_foreground_info()
        if fg_hwnd:
            # exact same hwnd -> ignore
            if hwnd and fg_hwnd and hwnd == fg_hwnd:
                return True
            # same process -> ignore
            if pid and fg_pid and pid == fg_pid:
                return True
            # optionally ignore if the event window is a child of foreground
            if (
                IGNORE_CHILD_OF_FOREGROUND
                and hwnd
                and fg_hwnd
                and is_child_of(fg_hwnd, hwnd)
            ):
                return True

    # 4) dedupe
    sig = signature_for_event(ev)
    if _recent_signatures.seen_recent(sig):
        return True

    # passed all filters -> don't ignore
    return False


# Example pipeline hook
def process_event(ev: dict, on_accept):
    """Process a raw UIA event dict. If accepted, call on_accept(ev)."""
    if should_ignore_event(ev):
        # debug print (toggle as needed)
        # print("ignored:", ev.get("title"), ev.get("app"), ev.get("pid"))
        return False
    # accepted: pass to downstream (popup / log / widget)
    on_accept(ev)
    return True


# small demo of usage:
if __name__ == "__main__":
    # quick test harness: simulate events from your log
    sample_events = [
        {
            "ts_iso": "...",
            "hwnd": 198976,
            "pid": 29616,
            "app": "Discord.exe",
            "class": "Chrome_RenderWidgetHostHWND",
            "title": "Chrome Legacy Window",
            "message": "Chrome Legacy Window  (src:Discord.exe)",
            "source": "uia",
        },
        {
            "ts_iso": "...",
            "hwnd": 7276386,
            "pid": 5820,
            "app": "python.exe",
            "class": "Qt691QWindowToolSaveBits",
            "title": "python",
            "message": "Chrome Legacy Window (src:Discord.exe) (src:python.exe)",
            "source": "uia",
        },
    ]

    def accept(ev):
        print("ACCEPTED -> show popup:", ev.get("app"), ":", ev.get("title"))

    for e in sample_events:
        process_event(e, accept)
