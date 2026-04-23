"""
core/file_guard.py
==================
Checks whether output permit PDFs already exist in the target event folder.
Prevents any overwriting — if conflicts are found, the run is aborted
and the user is shown which files already exist.
"""

import os


def check_for_conflicts(event_folder: str, expected_filenames: list[str]) -> list[str]:
    """
    Checks which of the expected output filenames already exist
    in the event folder.

    Args:
        event_folder:       Absolute path to the event output folder.
        expected_filenames: List of output PDF filenames the pipeline would produce.

    Returns:
        List of filenames that already exist (conflicts).
        Empty list means no conflicts — safe to proceed.
    """
    conflicts = []
    for filename in expected_filenames:
        full_path = os.path.join(event_folder, filename)
        if os.path.exists(full_path):
            conflicts.append(filename)
    return conflicts


def any_pdfs_exist(event_folder: str) -> list[str]:
    """
    Returns a list of all .pdf files already in the event folder.
    Used as a quick pre-check before running the pipeline.

    Args:
        event_folder: Absolute path to the event output folder.

    Returns:
        List of existing PDF filenames in the folder.
    """
    if not os.path.exists(event_folder):
        return []
    return [f for f in os.listdir(event_folder) if f.lower().endswith(".pdf")]
