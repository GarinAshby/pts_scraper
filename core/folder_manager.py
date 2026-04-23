"""
core/folder_manager.py
======================
Validates event name input and manages the event output folder.
The output folder always lives inside the 'permits' folder,
which is defined as the directory containing the .exe (or app.py in dev).
"""

import os
import re
import sys


# Characters forbidden in folder names across Windows, macOS, and Linux
_WINDOWS_FORBIDDEN = r'[<>:"/\\|?*\x00-\x1f]'
_FORBIDDEN_NAMES_WINDOWS = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


def get_permits_folder() -> str:
    """
    Returns the absolute path to the 'permits' folder.
    In production (.exe), this is the folder containing the executable.
    In development, this is the folder containing app.py.
    """
    if getattr(sys, "frozen", False):
        # Running as a PyInstaller .exe
        base = os.path.dirname(sys.executable)
    else:
        # Running as a Python script
        base = os.path.dirname(os.path.abspath(__file__))
        base = os.path.dirname(base)  # go up from core/ to permit_app/
    return base


def validate_event_name(name: str) -> tuple[bool, str]:
    """
    Validates that an event name is safe to use as a folder name
    across Windows, macOS, and Linux.

    Args:
        name: The raw event name string entered by the user.

    Returns:
        (True, "") if valid.
        (False, error_message) if invalid.
    """
    name = name.strip()

    # Must not be empty
    if not name:
        return False, "Event name cannot be empty."

    # Must not be too long (Windows max path component is 255 chars)
    if len(name) > 255:
        return False, "Event name must be 255 characters or fewer."

    # Must not contain forbidden characters (cross-platform superset)
    if re.search(_WINDOWS_FORBIDDEN, name):
        bad_chars = r'< > : " / \ | ? * and control characters'
        return False, f"Event name contains invalid characters.\nPlease remove: {bad_chars}"

    # Must not be a reserved Windows device name
    stem = name.split(".")[0].upper()
    if stem in _FORBIDDEN_NAMES_WINDOWS:
        return False, f'"{name}" is a reserved system name. Please choose a different event name.'

    # Must not start or end with a space or period (Windows restriction)
    if name != name.strip() or name.endswith("."):
        return False, "Event name must not start/end with a space or period."

    return True, ""


def get_or_create_event_folder(event_name: str) -> tuple[str, bool]:
    """
    Finds or creates a folder named after the event inside the permits folder.

    Args:
        event_name: Validated event name string.

    Returns:
        (folder_path, was_created) — was_created is True if folder is new.
    """
    permits_folder = get_permits_folder()
    event_folder = os.path.join(permits_folder, event_name.strip())
    was_created = not os.path.exists(event_folder)
    os.makedirs(event_folder, exist_ok=True)
    return event_folder, was_created
