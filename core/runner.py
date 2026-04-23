"""
core/runner.py
==============
Runs the permit splitting pipeline in a background thread so the UI
stays responsive during processing. Communicates progress and results
back to the UI via a callback function.
"""

import threading
import traceback


def run_pipeline(
    pdf_path: str,
    output_dir: str,
    on_progress: callable,
    on_complete: callable,
    on_error: callable,
) -> None:
    """
    Launches the permit splitting pipeline in a daemon thread.

    Args:
        pdf_path:    Path to the input PTS permit PDF.
        output_dir:  Path to the event folder where outputs will be saved.
        on_progress: Callback(message: str) — called with status updates.
        on_complete: Callback(count: int) — called with number of permits produced.
        on_error:    Callback(message: str) — called if pipeline raises an exception.
    """

    def _run():
        try:
            # Import here so PyInstaller can resolve the module at runtime
            import permit_splitter as ps

            # Monkey-patch the print function in permit_splitter to also
            # forward log messages to the UI progress callback
            import builtins
            original_print = builtins.print

            def ui_print(*args, **kwargs):
                original_print(*args, **kwargs)
                msg = " ".join(str(a) for a in args)
                on_progress(msg)

            builtins.print = ui_print

            try:
                # Snapshot existing files before running
                import os
                existing_files = set(
                    f for f in os.listdir(output_dir)
                    if f.lower().endswith(".pdf")
                ) if os.path.exists(output_dir) else set()
                
                ps.main(pdf_path, output_dir)
            finally:
                # Always restore original print
                builtins.print = original_print

            # Count how many PDFs were produced by comparing before and after
            import os
            produced = [
                f for f in os.listdir(output_dir)
                if f.lower().endswith(".pdf") and f not in existing_files
            ]
            if not produced:
                on_error(
                    "No permits were found in this PDF.\n\n"
                    "Please make sure you are uploading a valid PTS parking permit PDF. "
                    "Other PDF types are not supported."
                )
            else:
                on_complete(len(produced))

        except Exception:
            error_detail = traceback.format_exc()
            on_error(error_detail)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
