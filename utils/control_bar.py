import argparse
import os
import sys
import time
import json
import threading
from typing import Optional, Dict, Any, List

import tkinter as tk

import psutil
import pyautogui
import win32gui
import win32con
import win32api
from urllib.parse import urlparse
import difflib
import subprocess
import shutil
# Optional low-level hotkey library (strong combo handling)
try:
    import keyboard as _kbd  # pip install keyboard
except Exception:
    _kbd = None
# Optional Windows TTS (SAPI via pywin32)
try:
    import win32com.client as _win32com_client
except Exception:
    _win32com_client = None

# ------------------------------ Config ------------------------------
# Because this file lives in utils/, the data directory is one level up.
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
EPISODE_SHEET = os.path.join(DATA_DIR, "EPISODE_SELECTION.xlsx")
LAST_WATCHED_FILE = os.path.join(DATA_DIR, "last_watched.json")
APP_TITLE_MAIN = "Accessible Menu"  # comm-v10.py window title

BUTTON_FONT = ("Arial Black", 20)   # was 16; ~25% larger
BAR_HEIGHT = 88                     # was 70; ~25% taller
BAR_OPACITY = 0.96
POLL_INTERVAL = 0.75
SCAN_DEBOUNCE = 0.35  # seconds after a scan/select before we accept another
SPACE_HOLD_DELAY = 3.0   # seconds to hold before auto-scan starts
SPACE_HOLD_REPEAT = 1.0  # repeat interval while holding Space

# ------------------------------ Platform profiles ------------------------------
PlatformProfile = Dict[str, Any]

PROFILES: List[PlatformProfile] = [
    {"name": "YouTube", "match": ["youtube.com", "youtu.be"],
     "playpause": ["k", "space"], "fullscreen": ["f"], "post_nav": ["f"]},
    {"name": "Disney+", "match": ["disneyplus.com"],
     "playpause": ["space"], "fullscreen": ["f"], "post_nav": ["f"]},
    {"name": "Netflix", "match": ["netflix.com"],
     "playpause": ["space"], "fullscreen": ["f"], "post_nav": ["f"]},
    {"name": "Prime Video", "match": ["primevideo.com", "amazon.com"],
     "playpause": ["space"], "fullscreen": ["f"], "post_nav": ["f"]},
    {"name": "Hulu", "match": ["hulu.com"],
     "playpause": ["space"], "fullscreen": ["f"], "post_nav": ["f"]},
    {"name": "Paramount+", "match": ["paramountplus.com"],
     "playpause": ["space"], "fullscreen": ["f"], "post_nav": ["f"]},
    {"name": "Max", "match": ["max.com", "hbomax.com"],
     "playpause": ["space"], "fullscreen": ["f"], "post_nav": ["f"]},
    {"name": "PlutoTV", "match": ["pluto.tv"],
     "playpause": ["space"], "fullscreen": ["f"], "post_nav": ["m", "f"]},
    {"name": "Plex", "match": ["plex.tv", "app.plex.tv"],
     "playpause": ["p", "space"], "fullscreen": ["f"], "post_nav": ["x", "enter", "p"]},
    {"name": "Generic", "match": ["."],  # fallback
     "playpause": ["space"], "fullscreen": ["f"], "post_nav": ["f"]},
]

# ------------------------------ Episode cache ------------------------------
EPISODE_CACHE: Dict[str, Dict[int, List[Dict[str, Any]]]] = {}
# Linear (row) order per show for strict next/prev by spreadsheet order
EPISODE_LINEAR: Dict[str, List[Dict[str, Any]]] = {}


def load_last_watched() -> dict:
    if os.path.exists(LAST_WATCHED_FILE):
        try:
            with open(LAST_WATCHED_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def set_last_position(show_title: str, season: int, episode: int, url: str, linear_index: Optional[int] = None):
    data = load_last_watched()
    rec = {"season": int(season), "episode": int(episode), "url": url}
    if linear_index is not None:
        rec["linear_index"] = int(linear_index)
    data[show_title] = rec
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(LAST_WATCHED_FILE, "w") as f:
        json.dump(data, f, indent=2)


def load_episode_catalog():
    """Populate caches from EPISODE_SELECTION.xlsx.
    Expected columns: Show Title | Season Number | Episode Number | Episode Title | Episode URL | Platform(optional)
    """
    global EPISODE_CACHE, EPISODE_LINEAR
    EPISODE_CACHE.clear()
    EPISODE_LINEAR.clear()
    try:
        import pandas as pd
    except Exception as e:
        print("[control_bar] pandas is required for episode mode:", e)
        return

    if not os.path.exists(EPISODE_SHEET):
        print(f"[control_bar] Episode sheet not found: {EPISODE_SHEET}")
        return

    df = pd.read_excel(EPISODE_SHEET)
    cols = {c.lower().strip(): c for c in df.columns}

    show_col = cols.get("show title") or cols.get("show") or cols.get("title")
    season_col = cols.get("season number") or cols.get("season")
    ep_col = cols.get("episode number") or cols.get("episode")
    title_col = cols.get("episode title") or cols.get("title")
    url_col = cols.get("episode url") or cols.get("url") or cols.get("disneyplusurl")
    plat_col = cols.get("platform")  # optional

    if not (show_col and season_col and ep_col and title_col and url_col):
        print("[control_bar] Missing expected columns in EPISODE_SELECTION.xlsx")
        return

    for _, row in df.iterrows():
        try:
            show = str(row[show_col]).strip()
            if not show:
                continue
            s = int(pd.to_numeric(row[season_col], errors="coerce"))
            e = int(pd.to_numeric(row[ep_col], errors="coerce"))
            t = str(row[title_col]).strip()
            u = str(row[url_col]).strip() if pd.notna(row[url_col]) else ""
            p = (str(row[plat_col]).strip() if plat_col and pd.notna(row[plat_col]) else None)
        except Exception:
            continue

        key = show.lower()
        rec = {
            "Season Number": s,
            "Episode Number": e,
            "Episode Title": t,
            "Episode URL": u,
            "Show Title": show,
            "Platform": p,
        }
        EPISODE_CACHE.setdefault(key, {}).setdefault(s, []).append(rec)
        EPISODE_LINEAR.setdefault(key, []).append(rec)  # preserve spreadsheet row order

    # sort per season (linear list remains in spreadsheet row order)
    for show_key, seasons in EPISODE_CACHE.items():
        for s in seasons:
            seasons[s].sort(key=lambda r: r["Episode Number"]) 

# ------------------------------ Chrome helpers ------------------------------

def is_chrome_running() -> bool:
    for p in psutil.process_iter(["name"]):
        n = p.info.get("name")
        if n and "chrome" in n.lower():
            return True
    return False


def _enum_chrome_windows() -> List[int]:
    handles: List[int] = []
    def _enum(hwnd, _res):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd) or ""
            cls = win32gui.GetClassName(hwnd) or ""
            if "chrome" in title.lower() or cls.lower().startswith("chrome"):
                handles.append(hwnd)
        except Exception:
            pass
    win32gui.EnumWindows(_enum, None)
    return handles

# NEW: enumerate all visible top-level windows (not limited to Chrome)
def _enum_visible_windows() -> List[int]:
    handles: List[int] = []
    def _enum(hwnd, _res):
        try:
            if win32gui.IsWindowVisible(hwnd):
                handles.append(hwnd)
        except Exception:
            pass
    win32gui.EnumWindows(_enum, None)
    return handles


def focus_chrome_window() -> bool:
    """Bring a Chrome window to the foreground. Returns True on success."""
    for hwnd in _enum_chrome_windows():
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.05)
            return True
        except Exception:
            continue
    return False


def close_chrome():
    hwnd = win32gui.GetForegroundWindow()
    title = win32gui.GetWindowText(hwnd)
    if "chrome".lower() in title.lower():
        pyautogui.hotkey("alt", "f4")
        return
    def _enum(hwnd, _res):
        t = win32gui.GetWindowText(hwnd)
        if t and "chrome".lower() in t.lower():
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
    win32gui.EnumWindows(_enum, None)

# NEW: find Chrome executable path (best-effort on Windows)
def _find_chrome_exe() -> Optional[str]:
    # Try PATH first
    exe = shutil.which("chrome") or shutil.which("chrome.exe")
    if exe and os.path.exists(exe):
        return exe
    # Common install paths
    candidates = [
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def focus_comm_app():
    hwnd = win32gui.FindWindow(None, APP_TITLE_MAIN)
    if hwnd:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)


def navigate_current_tab(url: str) -> bool:
    """Navigate the active Chrome tab to a URL via CDP (no OS focus change)."""
    ws = cdp_find_ws()
    if ws:
        return cdp_navigate(ws, url)
    # No CDP available → don't steal focus; caller can warn/log.
    print("[control_bar] CDP unavailable; cannot navigate without stealing focus.")
    return False

# Try to read Chrome's active tab URL via the DevTools HTTP endpoint.
# Requires launching Chrome with --remote-debugging-port=9222.
try:
    import requests  # local loopback only
except Exception:
    requests = None

# Optional: WebSocket CDP for focus-free control
try:
    import websocket  # pip install websocket-client
except Exception:
    websocket = None


def get_active_chrome_url_via_cdp() -> Optional[str]:
    if not requests:
        return None
    try:
        r = requests.get("http://127.0.0.1:9222/json", timeout=0.3)
        tabs = r.json() if r.ok else []
        # Pick the first page tab; CDP doesn't always expose "active" without extra calls
        for t in tabs:
            if t.get("type") == "page" and t.get("url"):
                return t.get("url")
    except Exception:
        return None
    return None

# ---------------- CDP helpers (no focus change) ----------------

def _cdp_tabs():
    if not requests:
        return []
    try:
        r = requests.get("http://127.0.0.1:9222/json", timeout=0.4)
        return r.json() if r.ok else []
    except Exception:
        return []


def cdp_find_ws(url_hint: Optional[str] = None) -> Optional[str]:
    tabs = _cdp_tabs()
    if not tabs:
        return None
    if url_hint:
        base = _normalize_url(url_hint)
        # try exact/startswith match first
        for t in tabs:
            u = t.get("url", "")
            if t.get("type") == "page" and t.get("webSocketDebuggerUrl") and (base == _normalize_url(u) or _normalize_url(u).startswith(base)):
                return t.get("webSocketDebuggerUrl")
    # fallback: first page tab with ws
    for t in tabs:
        if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
            return t.get("webSocketDebuggerUrl")
    return None


def _cdp_send(ws, method: str, params: Optional[dict] = None, msg_id: int = 1, timeout: float = 1.2):
    payload = {"id": msg_id, "method": method}
    if params:
        payload["params"] = params
    ws.send(json.dumps(payload))
    ws.settimeout(timeout)
    try:
        reply = ws.recv()
        return json.loads(reply)
    except Exception:
        return None


def cdp_runtime_eval(ws_url: str, expression: str) -> bool:
    if not websocket or not ws_url:
        return False
    try:
        ws = websocket.create_connection(ws_url, timeout=0.8)
    except Exception:
        return False
    try:
        _cdp_send(ws, "Runtime.enable")
        res = _cdp_send(ws, "Runtime.evaluate", {"expression": expression, "awaitPromise": True, "returnByValue": True})
        return bool(res)
    finally:
        try:
            ws.close()
        except Exception:
            pass


def cdp_navigate(ws_url: str, url: str) -> bool:
    if not websocket or not ws_url:
        return False
    try:
        ws = websocket.create_connection(ws_url, timeout=0.8)
    except Exception:
        return False
    try:
        _cdp_send(ws, "Page.enable")
        res = _cdp_send(ws, "Page.navigate", {"url": url})
        return bool(res)
    finally:
        try:
            ws.close()
        except Exception:
            pass


def cdp_toggle_play(ws_url: str) -> bool:
    js = """
(() => { const v = document.querySelector('video'); if (!v) return 'no video';
  if (v.paused) { try{v.play();}catch(e){} return 'play'; } else { v.pause(); return 'pause'; } })();
"""
    return cdp_runtime_eval(ws_url, js)

# NEW: ensure video is playing and page is fullscreen (best-effort, focus-safe)
def cdp_ensure_play_and_fullscreen(ws_url: Optional[str]) -> bool:
    if not websocket or not ws_url:
        return False
    try:
        ws = websocket.create_connection(ws_url, timeout=1.2)
    except Exception:
        return False
    ok = False
    try:
        _cdp_send(ws, "Runtime.enable")
        # Try to play video
        _cdp_send(ws, "Runtime.evaluate", {
            "expression": "(async() => {try{const v=document.querySelector('video'); if(v){await v.play().catch(()=>{});} }catch(e){} })();",
            "awaitPromise": True
        })
        # If not fullscreen, try to request it
        _cdp_send(ws, "Runtime.evaluate", {
            "expression": "(async()=>{try{if(!document.fullscreenElement){const v=document.querySelector('video'); if(v&&v.requestFullscreen){await v.requestFullscreen().catch(()=>{});} else if(document.documentElement.requestFullscreen){await document.documentElement.requestFullscreen().catch(()=>{});} }}catch(e){} })();",
            "awaitPromise": True
        })
        # Fallback: send 'f' to toggle fullscreen if still not fullscreen shortly after
        time.sleep(0.15)
        _cdp_send(ws, "Runtime.evaluate", {"expression": "!!document.fullscreenElement", "returnByValue": True})
        _cdp_send(ws, "Input.dispatchKeyEvent", {"type": "keyDown", "key": "f", "code": "KeyF", "windowsVirtualKeyCode": 0x46, "keyCode": 0x46})
        _cdp_send(ws, "Input.dispatchKeyEvent", {"type": "keyUp", "key": "f", "code": "KeyF", "windowsVirtualKeyCode": 0x46, "keyCode": 0x46})
        ok = True
    finally:
        try:
            ws.close()
        except Exception:
            pass
    return ok

# NEW: send Shift+Arrow (Left/Right) via CDP with explicit Shift keyDown/Up + Arrow sequence
def cdp_press_shift_arrow(ws_url: Optional[str], direction: str) -> bool:
    """Send Shift+Arrow via Chrome DevTools Protocol (focus-free)."""
    if not websocket or not ws_url:
        return False
    direction = (direction or "").lower()
    if direction not in ("left", "right"):
        return False
    key_name = "ArrowLeft" if direction == "left" else "ArrowRight"
    vk = 37 if direction == "left" else 39
    try:
        ws = websocket.create_connection(ws_url, timeout=0.8)
    except Exception:
        return False
    try:
        # Shift down as rawKeyDown, establish modifiers=8
        _cdp_send(ws, "Input.dispatchKeyEvent", {
            "type": "rawKeyDown",
            "key": "Shift",
            "code": "ShiftLeft",
            "windowsVirtualKeyCode": 16,
            "keyCode": 16,
            "modifiers": 8
        })
        # Arrow with Shift held (raw down + up)
        _cdp_send(ws, "Input.dispatchKeyEvent", {
            "type": "rawKeyDown",
            "key": key_name,
            "code": key_name,
            "windowsVirtualKeyCode": vk,
            "keyCode": vk,
            "modifiers": 8
        })
        _cdp_send(ws, "Input.dispatchKeyEvent", {
            "type": "keyUp",
            "key": key_name,
            "code": key_name,
            "windowsVirtualKeyCode": vk,
            "keyCode": vk,
            "modifiers": 8
        })
        # Shift up (no modifiers needed on release)
        _cdp_send(ws, "Input.dispatchKeyEvent", {
            "type": "keyUp",
            "key": "Shift",
            "code": "ShiftLeft",
            "windowsVirtualKeyCode": 16,
            "keyCode": 16
        })
        return True
    finally:
        try:
            ws.close()
        except Exception:
            pass

def cdp_press_shift_arrow_any(direction: str) -> bool:
    if not websocket:
        return False
    tabs = _cdp_tabs()
    if not tabs:
        return False
    sent = False
    for t in tabs:
        ws_url = t.get("webSocketDebuggerUrl")
        if t.get("type") != "page" or not ws_url:
            continue
        try:
            if cdp_press_shift_arrow(ws_url, direction):
                sent = True
        except Exception:
            continue
    return sent

# NEW: find Chrome content child HWNDs likely to receive key events
def _chrome_content_hwnds() -> List[int]:
    targets: List[int] = []
    for top in _enum_chrome_windows():
        try:
            # Try to find a render host child
            def _enum_child(ch, acc):
                try:
                    cls = (win32gui.GetClassName(ch) or "").lower()
                    if "render" in cls or "chromium" in cls or "d3d" in cls:
                        acc.append(ch)
                except Exception:
                    pass
            acc: List[int] = []
            win32gui.EnumChildWindows(top, _enum_child, acc)
            if acc:
                targets.extend(acc)
            else:
                # Fallback to top-level if no child found
                targets.append(top)
        except Exception:
            pass
    return targets

# NEW: send Shift+Arrow to Chrome via Win32 messages (fallback when CDP is unavailable)
def _send_shift_arrow_winmsg(direction: str) -> bool:
    direction = (direction or "").lower()
    vk = 0x25 if direction == "left" else 0x27  # VK_LEFT / VK_RIGHT
    if vk == 0:
        return False
    sent_any = False
    for hwnd in _chrome_content_hwnds():
        try:
            # Press Shift
            win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, 0x10, 0x00000001)  # VK_SHIFT
            # Press Arrow
            win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, vk, 0x00000001)
            # Release Arrow
            win32gui.PostMessage(hwnd, win32con.WM_KEYUP, vk, 0xC0000001)
            # Release Shift
            win32gui.PostMessage(hwnd, win32con.WM_KEYUP, 0x10, 0xC0000001)
            sent_any = True
        except Exception:
            continue
    return sent_any

# NEW: pyautogui-based OS fallback that truly holds Shift while pressing Arrow
def _send_shift_arrow_pyautogui(direction: str) -> bool:
    d = (direction or "").lower()
    key = "left" if d == "left" else "right"
    if not focus_chrome_window():
        return False
    try:
        time.sleep(0.05)  # give Chrome a tick to take focus
        pyautogui.keyDown("shift")
        time.sleep(0.01)
        pyautogui.press(key)
        time.sleep(0.01)
        pyautogui.keyUp("shift")
        time.sleep(0.02)
        return True
    except Exception:
        return False

# NEW: in-focus, low-level Shift+Arrow using SendInput (more reliable than keybd_event/pyautogui)
def _send_shift_arrow_sendinput(direction: str) -> bool:
    """Reliable low-level combo using SendInput with SCANCODEs.
    Temporarily focuses Chrome; overlay focus is restored by caller."""
    d = (direction or "").lower()
    if d not in ("left", "right"):
        return False
    if not focus_chrome_window():
        return False
    try:
        import ctypes
        from ctypes import wintypes
        time.sleep(0.02)
        # Extended scancodes for arrows (E0-prefixed)
        SC_LEFT, SC_RIGHT = 0x4B, 0x4D
        sc_arrow = SC_LEFT if d == "left" else SC_RIGHT
        SC_LSHIFT = 0x2A

        INPUT_KEYBOARD = 1
        KEYEVENTF_EXTENDEDKEY = 0x0001
        KEYEVENTF_KEYUP = 0x0002
        KEYEVENTF_SCANCODE = 0x0008

        ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR),
            ]
        class INPUT_UNION(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]
        class INPUT(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]

        def make_scan(sc: int, flags: int) -> INPUT:
            ki = KEYBDINPUT(wVk=0, wScan=sc, dwFlags=flags, time=0, dwExtraInfo=ULONG_PTR(0))
            iu = INPUT_UNION(ki=ki)
            return INPUT(type=INPUT_KEYBOARD, union=iu)

        ext = KEYEVENTF_SCANCODE | KEYEVENTF_EXTENDEDKEY
        seq = (INPUT * 4)(
            make_scan(SC_LSHIFT, KEYEVENTF_SCANCODE),                         # Shift down
            make_scan(sc_arrow, ext),                                         # Arrow down (extended)
            make_scan(sc_arrow, ext | KEYEVENTF_KEYUP),                       # Arrow up (extended)
            make_scan(SC_LSHIFT, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP),       # Shift up
        )
        sent = ctypes.windll.user32.SendInput(len(seq), ctypes.byref(seq), ctypes.sizeof(INPUT))
        time.sleep(0.02)
        return sent == len(seq)
    except Exception:
        return False

# Optional: keyboard module fallback for strong combo synth
def _send_shift_arrow_keyboard(direction: str) -> bool:
    if _kbd is None:
        return False
    d = (direction or "").lower()
    combo = "shift+right" if d == "right" else "shift+left"
    if not focus_chrome_window():
        return False
    try:
        _kbd.send(combo)
        time.sleep(0.01)
        return True
    except Exception:
        return False

# NEW: final fallback – briefly focus Chrome and send OS-level Shift+Arrow keystrokes
def _send_shift_arrow_os(direction: str) -> bool:
    vk = 0x25 if (direction or "").lower() == "left" else 0x27  # VK_LEFT / VK_RIGHT
    if not focus_chrome_window():
        return False
    try:
        # Shift down
        win32api.keybd_event(0x10, 0, 0, 0)
        time.sleep(0.01)
        # Arrow tap
        win32api.keybd_event(vk, 0, 0, 0)
        time.sleep(0.01)
        win32api.keybd_event(vk, 0, 2, 0)
        time.sleep(0.005)
    finally:
        # Shift up
        win32api.keybd_event(0x10, 0, 2, 0)
    return True

def cdp_click_center(ws_url: Optional[str]) -> bool:
    if not websocket or not ws_url:
        return False
    try:
        ws = websocket.create_connection(ws_url, timeout=0.8)
    except Exception:
        return False
    try:
        _cdp_send(ws, "Runtime.enable")
        # get viewport size
        res = _cdp_send(ws, "Runtime.evaluate", {
            "expression": "({w: window.innerWidth, h: window.innerHeight})",
            "returnByValue": True
        })
        wh = (res or {}).get("result", {}).get("value", {}) if isinstance(res, dict) else {}
        w = int(wh.get("w", 800))
        h = int(wh.get("h", 600))
        x = max(0, w // 2); y = max(0, h // 2)
        _cdp_send(ws, "Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
        _cdp_send(ws, "Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
        _cdp_send(ws, "Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
        return True
    finally:
        try:
            ws.close()
        except Exception:
            pass

def cdp_toggle_mute(ws_url: Optional[str]) -> bool:
    js = "(() => { const v = document.querySelector('video'); if (!v) return 'no video'; v.muted = !v.muted; return v.muted; })();"
    return cdp_runtime_eval(ws_url, js)

# NEW: adjust HTML5 video volume by delta (±0.1 = 10%) without stealing focus
def cdp_adjust_volume(ws_url: Optional[str], delta: float) -> bool:
    if ws_url is None:
        return False
    try:
        # Clamp volume to [0,1]
        expr = f"(() => {{ const v=document.querySelector('video'); if(!v) return false; v.volume=Math.max(0,Math.min(1,(v.volume||0)+({delta}))); return true; }})()"
        return cdp_runtime_eval(ws_url, expr)
    except Exception:
        return False

# ------------------------------ Platform detection & actions ------------------------------

def get_profile_for_url(url: Optional[str], explicit_platform: Optional[str] = None) -> PlatformProfile:
    if explicit_platform:
        for prof in PROFILES:
            if prof["name"].lower() == explicit_platform.lower():
                return prof
    if not url:
        return PROFILES[-1]  # Generic
    u = url.lower()
    for prof in PROFILES:
        for needle in prof["match"]:
            if needle in u:
                return prof
    return PROFILES[-1]

# NEW: quick URL check for Plex domains/paths/ports
def _is_plex_url(u: Optional[str]) -> bool:
    if not u:
        return False
    s = u.lower()
    # app.plex.tv or direct server (port 32400) or standard web app path
    return ("plex" in s) or (":32400" in s) or ("/web/index.html" in s)

def send_to_chrome(seq: List[str], delay: float = 0.05, fallback_media_key: bool = True):
    """Keep overlay focused; DO NOT send normal keys (they'd type into the bar).
    We only use the system media key as a best-effort fallback.
    """
    if fallback_media_key:
        try:
            # VK_MEDIA_PLAY_PAUSE = 0xB3
            win32api.keybd_event(0xB3, 0, 0, 0)
            win32api.keybd_event(0xB3, 0, 2, 0)
        except Exception:
            pass

# ------------------------------ Resolver ------------------------------

def _normalize_url(u: str) -> str:
    base = u.split('#', 1)[0]
    base = base.split('?', 1)[0]
    return base.rstrip('/')


def resolve_current_index(show_title: str, url_hint: Optional[str]):
    key = show_title.lower()
    seasons = EPISODE_CACHE.get(key, {})
    if not seasons:
        return None, None

    last = load_last_watched().get(show_title)
    if isinstance(last, str):
        url_hint = url_hint or last
        last = None

    if isinstance(last, dict):
        s = int(last.get("season") or 0)
        e = int(last.get("episode") or 0)
        if s in seasons:
            eps = seasons[s]
            for i, rec in enumerate(eps):
                if rec["Episode Number"] == e:
                    return s, i

    if url_hint:
        hint = _normalize_url(url_hint)
        for s, eps in seasons.items():
            for i, rec in enumerate(eps):
                u = _normalize_url(rec.get("Episode URL", ""))
                if u and (hint == u or hint.startswith(u)):
                    return s, i

    s = sorted(seasons.keys())[0]
    return s, 0


def step_episode_linear(show_title: str, current_url: Optional[str], delta: int):
    key = show_title.lower()
    arr = EPISODE_LINEAR.get(key, [])
    if not arr:
        return None, None, None, None

    idx = None
    if current_url:
        hint = _normalize_url(current_url)
        for i, rec in enumerate(arr):
            u = _normalize_url(rec.get("Episode URL", ""))
            if u and (hint == u or hint.startswith(u)):
                idx = i
                break
    if idx is None:
        s, i2 = resolve_current_index(show_title, current_url)
        if s is None:
            return None, None, None, None
        target = None
        rec = EPISODE_CACHE[key][s][i2]
        for j, r in enumerate(arr):
            if r is rec:
                target = j
                break
        idx = target if target is not None else 0

    new_idx = max(0, min(len(arr) - 1, idx + delta))
    rec2 = arr[new_idx]
    return rec2["Season Number"], rec2["Episode Number"], rec2.get("Episode URL", ""), rec2.get("Platform")


def step_episode(show_title: str, current_url: Optional[str], delta: int):
    # Prefer strict spreadsheet row order
    s, e, url, plat = step_episode_linear(show_title, current_url, delta)
    if url:
        return s, e, url, plat
    # Fallback to season grouping logic
    key = show_title.lower()
    seasons = EPISODE_CACHE.get(key, {})
    if not seasons:
        return None, None, None, None

    s, idx = resolve_current_index(show_title, current_url)
    if s is None:
        return None, None, None, None

    eps = seasons[s]
    new_idx = idx + delta
    if new_idx < 0:
        prev_seasons = sorted([x for x in seasons.keys() if x < s])
        if not prev_seasons:
            new_idx = 0
        else:
            s = prev_seasons[-1]
            eps = seasons[s]
            new_idx = len(eps) - 1
    elif new_idx >= len(eps):
        next_seasons = sorted([x for x in seasons.keys() if x > s])
        if not next_seasons:
            new_idx = len(eps) - 1
        else:
            s = next_seasons[0]
            eps = seasons[s]
            new_idx = 0

    rec = eps[new_idx]
    return s, rec["Episode Number"], rec.get("Episode URL", ""), rec.get("Platform")

# ------------------------------ Helper matching (row-based) ------------------------------

def _host(u: str) -> str:
    try:
        return urlparse(u).netloc.lower().split(":")[0]
    except Exception:
        return ""


def find_linear_index_by_url(show_title: str, current_url: Optional[str]) -> Optional[int]:
    if not current_url:
        return None
    key = show_title.lower()
    arr = EPISODE_LINEAR.get(key, [])
    if not arr:
        return None
    h = _host(current_url)
    p = _normalize_url(current_url)
    best = (-1, -1.0)
    for i, rec in enumerate(arr):
        u = rec.get("Episode URL", "")
        if not u:
            continue
        if _host(u) != h:
            continue
        up = _normalize_url(u)
        # Fast paths
        if p == up or p.startswith(up) or up.startswith(p):
            return i
        # Fuzzy path similarity to tolerate token/query differences
        r = difflib.SequenceMatcher(None, p, up).ratio()
        if r > best[1]:
            best = (i, r)
    # Accept a fuzzy match if fairly close
    if best[1] >= 0.55:
        return best[0]
    return None

# ------------------------------ UI (Scan/Select) ------------------------------
class ControlBar(tk.Tk):
    def __init__(self, mode: str, show_title: Optional[str]):
        super().__init__()
        self.mode = mode
        self.show_title = show_title
        self.title("Playback Bar")
        self.overrideredirect(True)
        self.configure(bg="#111111")
        self.attributes("-topmost", True)
        try:
            self.attributes("-alpha", BAR_OPACITY)
        except Exception:
            pass

        self._place_bottom()

        # Build button model, then draw widgets from it
        self.items: List[Dict[str, Any]] = self._make_items()
        self.tk_buttons: List[tk.Button] = []
        self.current_index = 0
        self._return_hold_thread: Optional[threading.Thread] = None
        # NEW: one-time activation click flag
        self._activated_once = False
        # NEW: guard bar while we intentionally restart Chrome
        self._restarting_chrome = False
        self._restart_deadline = 0.0
        # NEW: map logical ids to button indices (e.g., prev/next)
        self._btn_idx: Dict[str, int] = {}
        # NEW: SAPI TTS voice (async; purges previous utterance)
        self._tts = None
        if _win32com_client:
            try:
                self._tts = _win32com_client.Dispatch("SAPI.SpVoice")
            except Exception:
                self._tts = None

        self._build_ui()
        self._highlight(0)

        # After UI build, seed index and update button labels
        if self.mode == "episodes" and self.show_title:
            self._ensure_linear_index()
        self._update_prev_next_labels()
        # Periodically refresh labels to reflect context
        self.after(800, self._pulse_labels)

        # Key input state
        self._last_action_ts = 0.0
        # NEW: Space-hold state
        self._space_pressed = False
        self._space_press_time = 0.0
        self._space_hold_job = None
        self._space_hold_active = False

        # Chrome watcher + always-on-top keeper
        self._watcher = threading.Thread(target=self._watch_chrome, daemon=True)
        self._watcher.start()
        self.after(500, self._raise_forever)

        # Scan/Select bindings (match comm-v10)
        self.bind("<KeyPress-space>", self._on_space_press)      # NEW
        self.bind("<KeyRelease-space>", self._on_space_release)
        self.bind("<KeyPress-Return>", self._on_return_press)
        self.bind("<KeyRelease-Return>", self._on_return_release)

        # Grab focus & capture keyboard globally so Space/Return always come here
        try:
            self.grab_set_global()
        except Exception:
            self.grab_set()
        self.focus_force()
        self.lift()

    # ---------- Layout ----------
    def _place_bottom(self):
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{sw}x{BAR_HEIGHT}+0+{sh - BAR_HEIGHT}")

    def _make_items(self) -> List[Dict[str, Any]]:
        items = [
            {"label": "⏯ Play / Pause", "action": self.on_play_pause},
            # NEW: volume down/up buttons using low/high volume emojis
            {"id": "vol_down", "label": "🔉", "action": self.on_volume_down},
            {"id": "vol_up", "label": "🔊", "action": self.on_volume_up},
        ]
        # Always include Previous/Next. Enable/label dynamically for Plex or Episodes mode.
        items.append({"id": "prev", "label": "⏮ Previous", "action": self.on_prev})
        items.append({"id": "next", "label": "⏭ Next", "action": self.on_next})
        items.append({"label": "⏹ Exit", "action": self.on_exit})
        return items

    def _build_ui(self):
        row = tk.Frame(self, bg="#111111")
        row.pack(expand=True, fill=tk.BOTH)
        self.tk_buttons.clear()
        for it in self.items:
            b = tk.Button(
                row,
                text=it["label"],
                font=BUTTON_FONT,
                bg="#e6f0ff",
                fg="#000",
                activebackground="#ffeb99",
                activeforeground="#000",
                command=it["action"],
                wraplength=800,
                justify="center",
                takefocus=0
            )
            b.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=8, pady=10)  # was padx=6, pady=8
            self.tk_buttons.append(b)
            # NEW: record button indices by id
            if "id" in it:
                self._btn_idx[it["id"]] = len(self.tk_buttons) - 1

    # ---------- Highlight helpers ----------
    def _highlight(self, idx: int):
        for i, b in enumerate(self.tk_buttons):
            if i == idx:
                b.configure(bg="#ffd84d")  # yellow
            else:
                b.configure(bg="#e6f0ff")
        self.update_idletasks()
        # NEW: announce the currently highlighted button
        self._announce_highlight(idx)

    # NEW: small helper to speak text (async + purge)
    def _speak(self, text: str):
        if not text:
            return
        if self._tts:
            try:
                self._tts.Speak(str(text), 3)  # 1=Async,2=Purge → 3
            except Exception:
                pass

    # UPDATED: verbalize current highlight; in episodes mode speak titles for prev/next
    def _announce_highlight(self, idx: int):
        try:
            item = self.items[idx]
            bid = item.get("id")
            label = self.tk_buttons[idx].cget("text")
            say = None

            # NEW: speak when scanning to volume buttons
            if bid == "vol_down":
                say = "volume down"
            elif bid == "vol_up":
                say = "volume up"
            elif bid in ("prev", "next"):
                if self._has_episode_selector() and self.show_title:
                    # Speak the episode title for the neighbor
                    self._ensure_linear_index()
                    key = self.show_title.lower()
                    arr = EPISODE_LINEAR.get(key, [])
                    if not arr:
                        return
                    cur = int(self._linear_idx or 0)
                    if bid == "prev":
                        if cur > 0:
                            title = (arr[cur - 1].get("Episode Title") or "").strip()
                            say = title or "Previous"
                        else:
                            say = "Previous"
                    else:  # next
                        if cur < len(arr) - 1:
                            title = (arr[cur + 1].get("Episode Title") or "").strip()
                            say = title or "Next"
                        else:
                            say = "Next"
                else:
                    # Not episodes mode: say generic label
                    say = "Previous" if bid == "prev" else "Next"
            else:
                low = (label or "").lower()
                if "play" in low:
                    say = "Play Pause"
                elif "mute" in low:
                    say = "Mute Unmute"
                elif "exit" in low:
                    say = "Exit"

            if say:
                self._speak(say)
        except Exception:
            pass

    def _scan_forward(self):
        self.current_index = (self.current_index + 1) % len(self.tk_buttons)
        self._highlight(self.current_index)

    def _scan_backward(self):
        self.current_index = (self.current_index - 1) % len(self.tk_buttons)
        self._highlight(self.current_index)

    def _select_current(self):
        # Debounce select
        now = time.time()
        if now - self._last_action_ts < SCAN_DEBOUNCE:
            return
        self._last_action_ts = now
        try:
            self.items[self.current_index]["action"]()
        except Exception:
            pass

    def _refocus_bar(self):
        """Aggressively reclaim focus for the control bar."""
        try:
            self.grab_set_global()
        except Exception:
            self.grab_set()
        try:
            hwnd = self.winfo_id()
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
        self.focus_force()
        self.lift()
        self.update_idletasks()

    # NEW: aggressively reclaim focus for a short window after actions that may steal focus
    def _refocus_for(self, seconds: float = 2.0):
        end = time.time() + max(0.2, seconds)
        def _tick():
            if not self.winfo_exists():
                return
            self._refocus_bar()
            if time.time() < end:
                self.after(120, _tick)
        _tick()

    # ---------- Key handling ----------
    # NEW: Space pressed → maybe start auto-scan after delay
    def _on_space_press(self, _evt=None):
        if self._space_pressed:
            return
        self._space_pressed = True
        self._space_press_time = time.time()
        self._space_hold_active = False
        # schedule a check loop to start auto-scan after SPACE_HOLD_DELAY
        def _check():
            if not self.winfo_exists() or not self._space_pressed:
                self._space_hold_job = None
                return
            if time.time() - self._space_press_time >= SPACE_HOLD_DELAY:
                self._space_hold_job = None
                self._space_hold_active = True
                self._space_hold_tick()
                return
            self._space_hold_job = self.after(100, _check)
        if not self._space_hold_job:
            self._space_hold_job = self.after(100, _check)

    # UPDATED: Space released → single scan step; stop any auto-scan
    def _on_space_release(self, _evt=None):
        # stop any scheduled auto-scan
        self._space_pressed = False
        if self._space_hold_job:
            try:
                self.after_cancel(self._space_hold_job)
            except Exception:
                pass
            self._space_hold_job = None
        # if auto-scan had started, skip the extra release step
        if self._space_hold_active:
            self._space_hold_active = False
            return
        # Debounced single step on release
        now = time.time()
        if now - self._last_action_ts < SCAN_DEBOUNCE:
            return
        self._last_action_ts = now
        self._scan_forward()

    # NEW: auto-scan tick while Space is held
    def _space_hold_tick(self):
        if not self.winfo_exists() or not self._space_pressed:
            self._space_hold_active = False
            return
        self._scan_forward()
        self._space_hold_job = self.after(int(SPACE_HOLD_REPEAT * 1000), self._space_hold_tick)

    # UPDATED: Return press should do nothing (no hold behavior)
    def _on_return_press(self, _evt=None):
        pass

    # UPDATED: Return release always selects (no hold/scan)
    def _on_return_release(self, _evt=None):
        self._select_current()

    # removed: _return_hold_loop (no longer needed)

    # ---------- Housekeeping ----------
    def _watch_chrome(self):
        while True:
            time.sleep(POLL_INTERVAL)
            running = is_chrome_running()
            if not running:
                # If we are intentionally restarting Chrome, wait until it comes back or deadline passes
                if getattr(self, "_restarting_chrome", False):
                    if time.time() <= getattr(self, "_restart_deadline", 0.0):
                        continue
                    # Timed out while waiting for restart; fall through and close the bar
                try:
                    self.destroy()
                except Exception:
                    pass
                break

    def _raise_forever(self):
        if not self.winfo_exists():
            return
        try:
            self.attributes("-topmost", True)
            self.lift()
        except Exception:
            pass
        self.after(1500, self._raise_forever)

    # ---------------- actions ----------------
    def _init_linear_index(self) -> Optional[int]:
        if not self.show_title:
            return None
        key = self.show_title.lower()
        arr = EPISODE_LINEAR.get(key, [])
        if not arr:
            return None
        # 1) If last_watched has a saved linear_index, trust it
        last = load_last_watched().get(self.show_title)
        if isinstance(last, dict):
            li = last.get("linear_index")
            if isinstance(li, int) and 0 <= li < len(arr):
                return li
            # Map season/episode to linear index
            s = last.get("season"); e = last.get("episode")
            if isinstance(s, int) and isinstance(e, int):
                for i, r in enumerate(arr):
                    if r.get("Season Number") == s and r.get("Episode Number") == e:
                        return i
        # 2) Try to infer by current URL (CDP or UI)
        url_hint = self._last_url_hint()
        idx = find_linear_index_by_url(self.show_title, url_hint)
        if idx is not None:
            return idx
        # 3) Default to first row
        return 0

    def _ensure_linear_index(self):
        if getattr(self, "_linear_idx", None) is None:
            self._linear_idx = self._init_linear_index()
        if self._linear_idx is None:
            self._linear_idx = 0

    def _last_url_hint(self) -> Optional[str]:
        # Prefer DevTools URL if available; otherwise fall back to last_watched.json
        url = get_active_chrome_url_via_cdp()
        if url:
            return url
        if not self.show_title:
            return None
        lw = load_last_watched().get(self.show_title)
        if isinstance(lw, str):
            return lw
        if isinstance(lw, dict):
            return lw.get("url")
        return None

    # NEW: pretty label for an episode row
    def _format_ep_label(self, rec: Dict[str, Any]) -> str:
        try:
            s = int(rec.get("Season Number", 0))
            e = int(rec.get("Episode Number", 0))
            t = str(rec.get("Episode Title", "") or "").strip()
            return f"S{s}E{e} - {t}" if t else f"S{s}E{e}"
        except Exception:
            return str(rec.get("Episode Title", "") or "Episode")

    # NEW: S#E# formatter only (no title)
    def _format_se_only(self, rec: Dict[str, Any]) -> str:
        try:
            s = int(rec.get("Season Number", 0))
            e = int(rec.get("Episode Number", 0))
            return f"S{s}E{e}"
        except Exception:
            return "S?E?"

    # UPDATED: update the Previous/Next button texts and enabled state (S#E# only)
    def _update_episode_button_labels(self):
        if not (self.mode == "episodes" and self.show_title):
            return
        key = self.show_title.lower()
        arr = EPISODE_LINEAR.get(key, [])
        if not arr:
            return
        self._ensure_linear_index()
        cur = int(self._linear_idx or 0)
        # prev
        prev_idx = self._btn_idx.get("prev")
        if prev_idx is not None:
            if cur > 0:
                prev_rec = arr[cur - 1]
                self.tk_buttons[prev_idx].configure(
                    text=self._format_se_only(prev_rec),
                    state=tk.NORMAL
                )
            else:
                self.tk_buttons[prev_idx].configure(
                    text="(None)",
                    state=tk.DISABLED
                )
        # next
        next_idx = self._btn_idx.get("next")
        if next_idx is not None:
            if cur < len(arr) - 1:
                next_rec = arr[cur + 1]
                self.tk_buttons[next_idx].configure(
                    text=self._format_se_only(next_rec),
                    state=tk.NORMAL
                )
            else:
                self.tk_buttons[next_idx].configure(
                    text="(None)",
                    state=tk.DISABLED
                )

    # NEW: determine if we should use the spreadsheet Episode Selector
    def _has_episode_selector(self) -> bool:
        if not (self.mode == "episodes" and self.show_title):
            return False
        arr = EPISODE_LINEAR.get(self.show_title.lower(), [])
        return len(arr) > 0

    # UPDATED: update Previous/Next button labels and enabled state based on context
    def _update_prev_next_labels(self):
        prev_idx = self._btn_idx.get("prev")
        next_idx = self._btn_idx.get("next")
        if prev_idx is None or next_idx is None:
            return

        if self._has_episode_selector():
            # Episodes mode with spreadsheet rows → show neighbor episode titles
            self._update_episode_button_labels()
            return

        # Default: generic labels without hints
        self.tk_buttons[prev_idx].configure(text="⏮ Previous", state=tk.NORMAL)
        self.tk_buttons[next_idx].configure(text="⏭ Next", state=tk.NORMAL)

    # NEW: periodic label refresher to follow platform changes
    def _pulse_labels(self):
        if not self.winfo_exists():
            return
        try:
            self._update_prev_next_labels()
        except Exception:
            pass
        self.after(1500, self._pulse_labels)

    # NEW: send system media Previous/Next keys
    def _send_media_prev_next(self, direction: str) -> bool:
        try:
            vk = 0xB0 if (direction or "").lower() == "next" else 0xB1  # NEXT_TRACK / PREV_TRACK
            win32api.keybd_event(vk, 0, 0, 0)
            win32api.keybd_event(vk, 0, 2, 0)
            return True
        except Exception:
            return False

    # NEW: is the current URL a Plex web app?
    def _is_plex_active(self) -> bool:
        return _is_plex_url(self._last_url_hint())

    # UPDATED: prev uses Episodes mode or media key only (no Shift+Arrow fallback)
    def on_prev(self):
        if self._has_episode_selector():
            key = self.show_title.lower()
            arr = EPISODE_LINEAR.get(key, [])
            if not arr:
                return
            self._ensure_linear_index()
            cur = int(self._linear_idx or 0)
            if cur <= 0:
                return
            self._switch_to_index(cur - 1)
            return
        # Always use system media key for Previous
        self._send_media_prev_next("previous")
        self._refocus_for(1.0)

    # UPDATED: next uses Episodes mode or media key only (no Shift+Arrow fallback)
    def on_next(self):
        if self._has_episode_selector():
            key = self.show_title.lower()
            arr = EPISODE_LINEAR.get(key, [])
            if not arr:
                return
            self._ensure_linear_index()
            cur = int(self._linear_idx or 0)
            if cur >= len(arr) - 1:
                return
            self._switch_to_index(cur + 1)
            return
        # Always use system media key for Next
        self._send_media_prev_next("next")
        self._refocus_for(1.0)

    def on_play_pause(self):
        # On first press, try to "activate" the player by clicking page center, then return.
        if not self._activated_once:
            self._activated_once = True
            did = False
            ws = cdp_find_ws(self._last_url_hint())
            if ws:
                # CDP center-click without focus change
                did = cdp_click_center(ws)
                # Ensure playback/fullscreen if possible (non-toggling)
                cdp_ensure_play_and_fullscreen(ws)
            else:
                # Fallback: real OS click at screen center (may focus Chrome)
                try:
                    sw, sh = pyautogui.size()
                    pyautogui.click(sw // 2, sh // 2)
                    did = True
                except Exception:
                    pass
            # Refocus the bar and exit early to avoid toggling immediately after activation
            self._refocus_bar()
            if did:
                return
            # If activation did nothing, fall through to normal toggle below

        # Prefer CDP so we never move focus
        ws = cdp_find_ws(self._last_url_hint())
        ok = cdp_toggle_play(ws)
        if not ok:
            # Fallback: system Play/Pause media key only (doesn't steal focus)
            send_to_chrome([" "])
        self._refocus_bar()

    # NEW: 10% volume up with TTS and focus-safe CDP; fallback to system volume key
    def on_volume_up(self):
        self._speak("Volume up")
        ws = cdp_find_ws(self._last_url_hint())
        if not cdp_adjust_volume(ws, 0.1):
            try:
                # VK_VOLUME_UP = 0xAF
                win32api.keybd_event(0xAF, 0, 0, 0)
                win32api.keybd_event(0xAF, 0, 2, 0)
            except Exception:
                pass
        self._refocus_bar()

    # NEW: 10% volume down with TTS and focus-safe CDP; fallback to system volume key
    def on_volume_down(self):
        self._speak("Volume down")
        ws = cdp_find_ws(self._last_url_hint())
        if not cdp_adjust_volume(ws, -0.1):
            try:
                # VK_VOLUME_DOWN = 0xAE
                win32api.keybd_event(0xAE, 0, 0, 0)
                win32api.keybd_event(0xAE, 0, 2, 0)
            except Exception:
                pass
        self._refocus_bar()

    def on_mute_toggle(self):
        # ...existing code (unused now; safe to keep or remove)...
        pass

    def _apply_post_nav(self, prof: PlatformProfile):
        # Ensure playback & fullscreen via CDP without stealing focus
        ws = cdp_find_ws(self._last_url_hint())
        if ws:
            cdp_ensure_play_and_fullscreen(ws)

    def on_exit(self):
        close_chrome()
        deadline = time.time() + 5
        while time.time() < deadline and is_chrome_running():
            time.sleep(0.2)
        focus_comm_app()
        try:
            self.destroy()
        except Exception:
            pass

# ------------------------------ Main ------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["basic", "episodes"], default="basic")
    ap.add_argument("--show", type=str, default=None, help="Show title when using episodes mode")
    ap.add_argument("--cdp", action="store_true", help="Ensure Chrome was launched with --remote-debugging-port=9222 for URL detection")
    args = ap.parse_args()

    if args.mode == "episodes":
        load_episode_catalog()
        if not args.show:
            print("[control_bar] --show is required for episodes mode")
            args.mode = "basic"

    if requests is None and args.mode == "episodes":
        print("[control_bar] Tip: install 'requests' and run Chrome with --remote-debugging-port=9222 for accurate Prev/Next.")

    app = ControlBar(args.mode, args.show)
    app.mainloop()


if __name__ == "__main__":
    main()