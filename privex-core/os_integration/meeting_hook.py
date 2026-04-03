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
        return any(_capability_active(cap) for cap in _CAPABILITIES)
    except OSError:
        # Fail open so firewall protection stays active if registry probing is unavailable.
        return True
    except Exception:
        # Defensive fail-open for unexpected parsing/platform edge cases.
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