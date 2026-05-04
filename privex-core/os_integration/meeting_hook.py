import os
import threading
import time
import winreg


_CONSENT_STORE_BASE = r"SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore"
_CAPABILITIES = ("webcam", "microphone")
_CACHE_TTL_SECONDS = 0.25

_cache_lock = threading.Lock()
_cached_value = True
_last_check_ts = 0.0
_MEETING_KEYWORDS = (
    "zoom meeting",
    "meet - ",
    "google meet",
    "meet.google.com",
    "microsoft teams",
)


def _iter_subkey_names(key_handle: winreg.HKEYType) -> list[str]:
    names: list[str] = []
    index = 0
    while True:
        try:
            names.append(winreg.EnumKey(key_handle, index))
            index += 1
        except OSError:
            break
    return names


def _is_stop_value_active(app_key: winreg.HKEYType) -> bool:
    try:
        stop_value, _ = winreg.QueryValueEx(app_key, "LastUsedTimeStop")
    except OSError:
        return False

    if isinstance(stop_value, int):
        return stop_value == 0
    if isinstance(stop_value, str):
        return stop_value.strip() == "0"
    return False


def _any_active_child(parent_key: winreg.HKEYType) -> bool:
    for child_name in _iter_subkey_names(parent_key):
        try:
            with winreg.OpenKey(parent_key, child_name) as child_key:
                if _is_stop_value_active(child_key):
                    return True
        except OSError:
            continue
    return False


def _capability_active(capability: str) -> bool:
    path = f"{_CONSENT_STORE_BASE}\\{capability}"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as capability_key:
        # Check packaged apps directly under webcam/microphone.
        for subkey_name in _iter_subkey_names(capability_key):
            if subkey_name == "NonPackaged":
                continue
            try:
                with winreg.OpenKey(capability_key, subkey_name) as app_key:
                    if _is_stop_value_active(app_key):
                        return True
            except OSError:
                continue

        # Check desktop apps under NonPackaged.
        try:
            with winreg.OpenKey(capability_key, "NonPackaged") as non_packaged_key:
                if _any_active_child(non_packaged_key):
                    return True
        except OSError:
            pass

    return False


def _compute_meeting_active() -> bool:
    if os.name != "nt":
        return True

    try:
        try:
            import win32gui

            # 👇 NEW LOGIC: Scan ALL open windows, not just the active one
            def enum_windows_callback(hwnd, active_titles):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title:
                        active_titles.append(title.lower())

            active_titles = []
            win32gui.EnumWindows(enum_windows_callback, active_titles)

            matched_keywords = [k for k in _MEETING_KEYWORDS if any(k in t for t in active_titles)]
            # Only print if we find a match to avoid spam, or print a summary
            print(f"🔍 [Meeting Hook] Scanned {len(active_titles)} windows. Matches found: {matched_keywords}")

            if matched_keywords:
                return True
        except Exception:
            pass

        # Fallback to microphone/webcam registry checks
        return any(_capability_active(cap) for cap in _CAPABILITIES)
    except OSError:
        return True
    except Exception:
        return True


def is_meeting_active() -> bool:
    """Return True when webcam/microphone appears actively in use, with a short TTL cache."""
    global _cached_value, _last_check_ts

    now = time.monotonic()
    if now - _last_check_ts < _CACHE_TTL_SECONDS:
        return _cached_value

    with _cache_lock:
        now = time.monotonic()
        if now - _last_check_ts < _CACHE_TTL_SECONDS:
            return _cached_value

        _cached_value = _compute_meeting_active()
        _last_check_ts = now
        return _cached_value