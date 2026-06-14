# macnotify_with_log.py
# Full working program:
# - SetWinEventHook (ctypes) to detect toast windows
# - Extract real text via UIA (pywinauto) when possible
# - Display macOS-style popups (PyQt6)
# - Save every notification as one JSON line to notifications_log.ndjson
#
# Requirements:
# pip install pyqt6 psutil pywinauto

import sys
import ctypes
import ctypes.wintypes as wintypes
import threading
import time
import queue
import psutil
import json
import os
import traceback
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QVBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QHBoxLayout,
)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QRect, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import QGraphicsDropShadowEffect

# UIA library
from pywinauto import Desktop
from pywinauto.findwindows import ElementNotFoundError

# -------------------------
# Config & Logger
# -------------------------
LOG_FILE = "notifications_log.ndjson"  # newline-delimited JSON (one entry per line)
_log_lock = threading.Lock()


def write_log_entry(entry: dict):
    """
    Append an entry as a single JSON line to LOG_FILE atomically.
    """
    try:
        line = json.dumps(entry, ensure_ascii=False)
        with _log_lock:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception:
        # be humble — don't break the main app for logging errors
        print("Log write error:", traceback.format_exc())


def make_entry(hw, pid, app, cls, window_title, extracted_text, title, message, source):
    return {
        "ts_iso": datetime.utcnow().isoformat() + "Z",
        "hwnd": int(hw) if hw is not None else None,
        "pid": int(pid) if pid is not None else None,
        "app": app,
        "class": cls,
        "window_title": window_title,
        "extracted_text": extracted_text,
        "title": title,
        "message": message,
        "source": source,
    }


def dump_pretty_json(outfile="notifications_log.pretty.json"):
    """
    Convert NDJSON to a pretty JSON array for easier inspection.
    """
    data = []
    if not os.path.exists(LOG_FILE):
        print("Log file not found:", LOG_FILE)
        return
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data.append(json.loads(line))
                except Exception:
                    continue
        with open(outfile, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print("Wrote pretty JSON to", outfile)
    except Exception:
        print("Dump error:", traceback.format_exc())


# -------------------------
# WinEvent Hook (ctypes)
# -------------------------
user32 = ctypes.windll.user32
ole32 = ctypes.windll.ole32

EVENT_OBJECT_SHOW = 0x8002
EVENT_OBJECT_NAMECHANGE = 0x800C
WINEVENT_OUTOFCONTEXT = 0x0000

WinEventProcType = ctypes.WINFUNCTYPE(
    None,
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.HWND,
    wintypes.LONG,
    wintypes.LONG,
    wintypes.DWORD,
    wintypes.DWORD,
)


def get_window_text(hwnd):
    try:
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value
    except Exception:
        return ""


def get_class_name(hwnd):
    try:
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        return buf.value
    except Exception:
        return ""


def get_pid_for_hwnd(hwnd):
    try:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value
    except Exception:
        return None


def get_process_name(pid):
    try:
        p = psutil.Process(pid)
        return p.name()
    except Exception:
        return ""


# -------------------------
# UIA text extraction
# -------------------------
def extract_toast_text_uia(hwnd, max_nodes=60):
    """
    Attempt to extract textual content from a window using UI Automation (pywinauto).
    Returns a string (joined text) or None on failure.
    """
    try:
        desktop = Desktop(backend="uia")
        wrapper = desktop.window(handle=hwnd)
        texts = []
        desc = wrapper.descendants(control_type="Text")
        count = 0
        for child in desc:
            if count >= max_nodes:
                break
            try:
                t = child.window_text()
                if not t:
                    t = getattr(child.element_info, "name", "") or ""
                if t and t.strip():
                    texts.append(t.strip())
                    count += 1
            except Exception:
                pass
        if not texts:
            try:
                txts = wrapper.texts()
                for t in txts:
                    if t and isinstance(t, str) and t.strip():
                        texts.append(t.strip())
            except Exception:
                pass
        if texts:
            seen = set()
            out = []
            for t in texts:
                if t not in seen:
                    seen.add(t)
                    out.append(t)
            if len(out) == 1:
                return out[0]
            elif len(out) >= 2:
                title = out[0]
                body = " — ".join(out[1:6])
                return f"{title}\n{body}"
            else:
                return " ".join(out)
        return None
    except ElementNotFoundError:
        return None
    except Exception:
        return None


# -------------------------
# PyQt6 Notification UI
# -------------------------
class MacStyleNotification(QWidget):
    def __init__(self, title: str, message: str, duration=4500, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.duration = duration

        self.container = QLabel()
        safe_title = (title or "Notification")[:220]
        safe_msg = (message or "")[:1200]
        safe_title = safe_title.replace("<", "&lt;").replace(">", "&gt;")
        safe_msg = safe_msg.replace("<", "&lt;").replace(">", "&gt;")
        self.container.setText(
            f"<b>{safe_title}</b><br><span style='font-size:10pt'>{safe_msg}</span>"
        )
        self.container.setWordWrap(True)
        self.container.setFont(QFont("Segoe UI", 10))
        self.container.setStyleSheet(
            """
            QLabel {
                color: black;
                background-color: rgba(255, 255, 255, 0.893);
                padding: 12px;
                border-radius: 25px;
                
            }
        """
        )
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 160))
        self.container.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.addWidget(self.container)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        self.resize(420, 100)
        self._animate_in()
        QTimer.singleShot(self.duration, self._animate_out)

    def _animate_in(self):
        screen = QApplication.primaryScreen().availableGeometry()
        target_w, target_h = self.width(), self.height()
        margin = 20
        end_x = screen.x() + screen.width() - target_w - margin
        end_y = screen.y() + margin
        start_rect = QRect(end_x + 60, end_y, target_w, target_h)
        end_rect = QRect(end_x, end_y, target_w, target_h)
        self.setGeometry(start_rect)
        self.show()
        anim = QPropertyAnimation(self, b"geometry")
        anim.setDuration(280)
        anim.setStartValue(start_rect)
        anim.setEndValue(end_rect)
        anim.start()
        self._anim = anim

    def _animate_out(self):
        geom = self.geometry()
        end_rect = QRect(geom.x() + 60, geom.y(), geom.width(), geom.height())
        anim = QPropertyAnimation(self, b"geometry")
        anim.setDuration(220)
        anim.setStartValue(geom)
        anim.setEndValue(end_rect)
        anim.finished.connect(self.close)
        anim.start()
        self._anim = anim


# -------------------------
# Sidebar/History
# -------------------------
class Sidebar(QWidget):
    def __init__(self, q: queue.Queue):
        super().__init__()
        self.q = q
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        self.init_ui()
        self.resize(360, 520)
        self._position()
        self.timer = QTimer()
        self.timer.timeout.connect(self._drain)
        self.timer.start(300)

    def init_ui(self):
        main = QWidget()
        main.setObjectName("card")
        main.setStyleSheet(
            """
            QWidget#card { background-color: rgba(28,28,28,220); border-radius: 12px; }
            QLabel { color: white; }
        """
        )
        layout = QVBoxLayout(main)
        header = QLabel("<b>MacNotify — History (real text)</b>")
        header.setStyleSheet("color: white;")
        layout.addWidget(header)
        self.listw = QListWidget()
        self.listw.setStyleSheet(
            "QListWidget { color: white; background: transparent; border: none; }"
        )
        layout.addWidget(self.listw)
        row = QHBoxLayout()
        clear = QPushButton("Clear")
        clear.clicked.connect(self.listw.clear)
        row.addWidget(clear)
        layout.addLayout(row)
        outer = QVBoxLayout(self)
        outer.addWidget(main)
        outer.setContentsMargins(8, 8, 8, 8)
        self.setLayout(outer)

    def _position(self):
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.x() + screen.width() - self.width() - 18
        y = screen.y() + 90
        self.move(x, y)

    def _drain(self):
        changed = False
        while True:
            try:
                t, m = self.q.get_nowait()
            except queue.Empty:
                break
            item = QListWidgetItem(f"{t}\n{m}")
            self.listw.insertItem(0, item)
            changed = True
        if changed:
            while self.listw.count() > 300:
                self.listw.takeItem(self.listw.count() - 1)


# -------------------------
# NotificationCenter: glue
# -------------------------
class NotificationCenter(QObject):
    _show = pyqtSignal(str, str)

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.queue = queue.Queue()
        self._show.connect(self._show_popup)
        self.sidebar = Sidebar(self.queue)
        # self.sidebar.show()
        self._start_hook_thread()

    def notify(
        self,
        title,
        message,
        hw=None,
        pid=None,
        appname=None,
        cls=None,
        window_title=None,
        extracted_text=None,
        source="fallback",
    ):
        if (
            "Qt691QWindowToolSaveBits" in cls
            or "Chrome_WidgetWin_1" in cls
            or "TrayClockWClass" in cls
        ):
            return
        if "Action Center," in window_title:
            return
        if window_title != "New notification":
            return
        tt = (title or "")[:300]
        # mm = mm.replace("(src:ShellExperienceHost.exe)", "")
        mm = (message.replace("(src:ShellExperienceHost.exe)", "") or "")[:2000]
        self.queue.put((tt, mm))
        self._show.emit(tt, mm)

        # save to log
        entry = make_entry(
            hw,
            pid,
            appname or (get_process_name(pid) if pid else ""),
            cls,
            window_title,
            extracted_text,
            title,
            message,
            source,
        )
        write_log_entry(entry)

    def _show_popup(self, t, m):
        if "Chrome Legacy Window" in t or "python" in t:
            return
        if "Chrome Legacy Window" in m or "python" in m:
            return
        popup = MacStyleNotification(t, m)
        popup.show()

    # ------------ native hook thread ------------
    def _start_hook_thread(self):
        t = threading.Thread(target=self._hook_loop, daemon=True)
        t.start()

    def _hook_loop(self):
        """
        Initialize COM, install SetWinEventHook for OBJECT_SHOW and NAMECHANGE,
        and pump messages. Uses UIA to extract text from candidate windows.
        """
        ole32.CoInitialize(None)

        @WinEventProcType
        def callback(
            hWinEventHook, event, hwnd, idObject, idChild, dwEventThread, dwmsEventTime
        ):
            try:
                OBJID_WINDOW = 0
                if idObject != OBJID_WINDOW:
                    return
                if not hwnd:
                    return

                window_title = get_window_text(hwnd)
                cls = get_class_name(hwnd)
                pid = get_pid_for_hwnd(hwnd)
                pname = get_process_name(pid)

                title_len = len(window_title.strip())
                cls_low = (cls or "").lower()
                pname_low = (pname or "").lower()

                likely = False
                if "toast" in cls_low or "notification" in cls_low:
                    likely = True
                if title_len and title_len < 240:
                    likely = likely or (
                        pname_low
                        in (
                            "chrome.exe",
                            "msedge.exe",
                            "slack.exe",
                            "discord.exe",
                            "telegram.exe",
                            "teams.exe",
                        )
                    )
                if (
                    "windows.ui.core.corewindow" in cls_low
                    or "applicationframewindow" in cls_low
                ):
                    if title_len and title_len < 120:
                        likely = True

                if not window_title.strip() and not likely:
                    return

                now = time.time()
                key = (hwnd, window_title.strip(), cls, pid)
                if not hasattr(self, "_seen_map"):
                    self._seen_map = {}
                last = self._seen_map.get(key, 0)
                if now - last < 0.6:
                    return
                self._seen_map[key] = now

                # Try extracting UIA text
                extracted = None
                source = "fallback"
                try:
                    extracted = extract_toast_text_uia(hwnd)
                    if extracted:
                        source = "uia"
                except Exception:
                    extracted = None

                if extracted:
                    # split title/body heuristically
                    if "\n" in extracted:
                        parts = extracted.splitlines()
                        head = parts[0]
                        body = " ".join(parts[1:4])
                        # Should ignore toasts that are in this list: ["Chrome Legacy Window", "python.exe"]

                        self.notify(
                            head,
                            body + f"  (src:{pname})",
                            hw=hwnd,
                            pid=pid,
                            appname=pname,
                            cls=cls,
                            window_title=window_title,
                            extracted_text=extracted,
                            source=source,
                        )
                    else:
                        txt = extracted
                        if " — " in txt:
                            head, rest = txt.split(" — ", 1)
                            self.notify(
                                head,
                                rest + f"  (src:{pname})",
                                hw=hwnd,
                                pid=pid,
                                appname=pname,
                                cls=cls,
                                window_title=window_title,
                                extracted_text=extracted,
                                source=source,
                            )
                        elif ":" in txt and len(txt.split(":")[0]) < 40:
                            head, rest = txt.split(":", 1)
                            self.notify(
                                head,
                                rest.strip() + f"  (src:{pname})",
                                hw=hwnd,
                                pid=pid,
                                appname=pname,
                                cls=cls,
                                window_title=window_title,
                                extracted_text=extracted,
                                source=source,
                            )
                        else:
                            self.notify(
                                window_title or pname,
                                txt + f"  (src:{pname})",
                                hw=hwnd,
                                pid=pid,
                                appname=pname,
                                cls=cls,
                                window_title=window_title,
                                extracted_text=extracted,
                                source=source,
                            )
                else:
                    # fallback: save generic info too
                    self.notify(
                        window_title or f"{pname} notification",
                        f"(app: {pname} | class: {cls})",
                        hw=hwnd,
                        pid=pid,
                        appname=pname,
                        cls=cls,
                        window_title=window_title,
                        extracted_text=None,
                        source="fallback",
                    )
            except Exception:
                # swallow errors
                # print("hook cb error:", traceback.format_exc())
                pass

        hook_show = user32.SetWinEventHook(
            EVENT_OBJECT_SHOW,
            EVENT_OBJECT_SHOW,
            0,
            callback,
            0,
            0,
            WINEVENT_OUTOFCONTEXT,
        )
        hook_name = user32.SetWinEventHook(
            EVENT_OBJECT_NAMECHANGE,
            EVENT_OBJECT_NAMECHANGE,
            0,
            callback,
            0,
            0,
            WINEVENT_OUTOFCONTEXT,
        )

        if not hook_show or not hook_name:
            print("Failed to install event hooks; try running as Administrator.")
            return

        msg = wintypes.MSG()
        while True:
            b = user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
            if b == 0:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))


# -------------------------
# Main
# -------------------------
def main():
    app = QApplication(sys.argv)
    center = NotificationCenter(app)

    print("MacNotify running — logging to", LOG_FILE)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
