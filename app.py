"""
app.py
======
Entry point for the "EE Mobile Garage Permits" application.
Run directly with `python app.py` in development,
or packaged as a .exe with PyInstaller using build.spec.
"""

import sys
import os

# ── Allow imports to resolve correctly whether running as script or .exe ──
if getattr(sys, "frozen", False):
    # PyInstaller sets sys._MEIPASS to the temp extraction folder
    base_dir = sys._MEIPASS
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, base_dir)

# ── Try to initialise tkinterdnd2 root (enables drag-and-drop) ──
# Falls back to standard tk.Tk if not installed.
try:
    from tkinterdnd2 import TkinterDnD
    _use_dnd = True
except ImportError:
    _use_dnd = False

from ui.main_window import PermitApp


def main():
    if _use_dnd:
        # Patch PermitApp to inherit from TkinterDnD.Tk for DnD support
        import tkinter as tk
        from tkinterdnd2 import TkinterDnD

        class DnDPermitApp(PermitApp, TkinterDnD.Tk):
            def __init__(self):
                TkinterDnD.Tk.__init__(self)
                # Re-run PermitApp setup without calling tk.Tk.__init__ again
                self.title("UEE Mobile Garage Permits")
                self.geometry("580x520")
                self.resizable(False, False)
                self.configure(bg="#F9F6F2")
                try:
                    self.iconbitmap(self._resource("assets/icon.ico"))
                except Exception:
                    pass
                import tkinter as tk
                self.event_name   = tk.StringVar()
                self.event_folder = ""
                self.pdf_path     = ""
                self._current_frame = None
                self.show_event_screen()

        app = DnDPermitApp()
    else:
        app = PermitApp()

    app.mainloop()


if __name__ == "__main__":
    main()
