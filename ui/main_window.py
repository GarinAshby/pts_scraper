"""
ui/main_window.py
=================
Main tkinter application window for the UT Austin Permit Splitter.
Hosts three sequential screens:
    1. Event name input
    2. PDF drag-and-drop
    3. Progress + success/error result

Design language: Clean, institutional, UT Austin branded.
Colors: Burnt Orange (#BF5700) + White + Charcoal (#1a1a1a)
Font: Uses system fonts for .exe compatibility (no bundling needed)
"""

import os
import tkinter as tk
from tkinter import filedialog, font
import threading

from core.folder_manager import validate_event_name, get_or_create_event_folder, get_permits_folder
from core.file_guard import any_pdfs_exist
from core.runner import run_pipeline

# ── Brand colors ──
UT_ORANGE    = "#BF5700"
UT_ORANGE_DK = "#A04800"
WHITE        = "#FFFFFF"
OFF_WHITE    = "#F9F6F2"
CHARCOAL     = "#1A1A1A"
MID_GRAY     = "#666666"
LIGHT_GRAY   = "#E8E4E0"
SUCCESS_GRN  = "#2D6A4F"
ERROR_RED    = "#C1121F"

# ── Dimensions ──
WIN_W = 580
WIN_H = 520


class PermitApp(tk.Tk):
    """Root application window — manages screen transitions."""

    def __init__(self):
        super().__init__()
        self.title("PTS Mobile Permits")
        self.geometry(f"{WIN_W}x{WIN_H}")
        self.resizable(False, False)
        self.configure(bg=OFF_WHITE)

        # Try to set the window icon
        try:
            self.iconbitmap(self._resource("assets/icon.ico"))
        except Exception:
            pass

        # Shared state across screens
        self.event_name   = tk.StringVar()
        self.event_folder = ""
        self.pdf_path     = ""

        # Start on screen 1
        self._current_frame = None
        self.show_event_screen()

    def _resource(self, relative_path: str) -> str:
        """Resolve asset paths that work both in dev and in a PyInstaller .exe."""
        import sys
        if getattr(sys, "_MEIPASS", None):
            base = sys._MEIPASS
        else:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, relative_path)

    def _switch_to(self, frame_class, **kwargs):
        """Destroy current frame and show a new one."""
        if self._current_frame:
            self._current_frame.destroy()
        self._current_frame = frame_class(self, **kwargs)
        self._current_frame.pack(fill="both", expand=True)

    def show_event_screen(self):
        self._switch_to(EventNameScreen)

    def show_pdf_screen(self):
        self._switch_to(PDFDropScreen)

    def show_progress_screen(self):
        self._switch_to(ProgressScreen)


# ══════════════════════════════════════════════════════════════════════════════
# SCREEN 1 — Event Name Input
# ══════════════════════════════════════════════════════════════════════════════

class EventNameScreen(tk.Frame):
    """Screen 1: Ask the user for the event name and validate it."""

    def __init__(self, master: PermitApp):
        super().__init__(master, bg=OFF_WHITE)
        self.master: PermitApp = master
        self._build()

    def _build(self):
        # ── Header bar ──
        header = tk.Frame(self, bg=UT_ORANGE, height=6)
        header.pack(fill="x")

        # ── Logo area ──
        logo_frame = tk.Frame(self, bg=OFF_WHITE, pady=28)
        logo_frame.pack(fill="x")

        tk.Label(
            logo_frame,
            text="THE UNIVERSITY OF TEXAS AT AUSTIN",
            bg=OFF_WHITE, fg=UT_ORANGE,
            font=("Georgia", 9, "bold"),
        ).pack()
        tk.Label(
            logo_frame,
            text="Events & Experience ",
            bg=OFF_WHITE, fg=MID_GRAY,
            font=("Georgia", 9),
        ).pack()

        # ── Divider ──
        tk.Frame(self, bg=LIGHT_GRAY, height=1).pack(fill="x", padx=40)

        # ── Main content ──
        content = tk.Frame(self, bg=OFF_WHITE, pady=36)
        content.pack(fill="both", expand=True, padx=60)

        tk.Label(
            content,
            text="PTS Mobile Permits",
            bg=OFF_WHITE, fg=CHARCOAL,
            font=("Georgia", 22, "bold"),
            anchor="w",
        ).pack(fill="x")

        tk.Label(
            content,
            text="Convert PTS permit PDFs into mobile-ready individual permits.",
            bg=OFF_WHITE, fg=MID_GRAY,
            font=("Helvetica", 10),
            anchor="w",
            wraplength=460,
            justify="left",
        ).pack(fill="x", pady=(4, 28))

        tk.Label(
            content,
            text="What event is this permit for?",
            bg=OFF_WHITE, fg=CHARCOAL,
            font=("Helvetica", 11, "bold"),
            anchor="w",
        ).pack(fill="x")

        tk.Label(
            content,
            text=f"Permits folder: {get_permits_folder()}",
            bg=OFF_WHITE, fg=MID_GRAY,
            font=("Helvetica", 8),
            anchor="w",
        ).pack(fill="x", pady=(2, 10))

        # Entry field
        entry_frame = tk.Frame(content, bg=CHARCOAL, padx=1, pady=1)
        entry_frame.pack(fill="x")
        self.entry = tk.Entry(
            entry_frame,
            textvariable=self.master.event_name,
            font=("Helvetica", 12),
            bg=WHITE, fg=CHARCOAL,
            insertbackground=UT_ORANGE,
            relief="flat",
            bd=8,
        )
        self.entry.pack(fill="x")
        self.entry.focus()
        self.entry.bind("<Return>", lambda e: self._submit())

        # Error label (hidden until needed)
        self.error_label = tk.Label(
            content,
            text="",
            bg=OFF_WHITE, fg=ERROR_RED,
            font=("Helvetica", 9),
            anchor="w",
            wraplength=460,
            justify="left",
        )
        self.error_label.pack(fill="x", pady=(6, 0))

        # ── Continue button ──
        btn_frame = tk.Frame(content, bg=OFF_WHITE, pady=20)
        btn_frame.pack(fill="x")
        self.btn = _OrangeButton(btn_frame, text="Continue →", command=self._submit)
        self.btn.pack(side="right")

    def _submit(self):
        name = self.master.event_name.get().strip()
        valid, error_msg = validate_event_name(name)

        if not valid:
            self.error_label.config(text=f"⚠  {error_msg}")
            self.entry.focus()
            return

        # Create or find the event folder
        folder, was_created = get_or_create_event_folder(name)
        self.master.event_folder = folder

        # Warn if folder already has PDFs
        existing = any_pdfs_exist(folder)
        if existing:
            self.error_label.config(
                text=f"⚠  This event folder already contains {len(existing)} permit PDF(s). "
                     f"Processing will be blocked if filenames conflict."
            )

        self.master.show_pdf_screen()


# ══════════════════════════════════════════════════════════════════════════════
# SCREEN 2 — PDF Drop / Select
# ══════════════════════════════════════════════════════════════════════════════

class PDFDropScreen(tk.Frame):
    """Screen 2: Let the user drag-and-drop or browse for the PTS permit PDF."""

    def __init__(self, master: PermitApp):
        super().__init__(master, bg=OFF_WHITE)
        self.master: PermitApp = master
        self._pdf_path = ""
        self._build()
        self._try_enable_dnd()

    def _build(self):
        # ── Header bar ──
        tk.Frame(self, bg=UT_ORANGE, height=6).pack(fill="x")

        # ── Back + title ──
        nav = tk.Frame(self, bg=OFF_WHITE, pady=20)
        nav.pack(fill="x", padx=40)
        tk.Button(
            nav, text="← Back",
            bg=OFF_WHITE, fg=MID_GRAY,
            font=("Helvetica", 9),
            relief="flat", cursor="hand2",
            command=self.master.show_event_screen,
        ).pack(side="left")

        tk.Label(
            nav,
            text=f"Event: {self.master.event_name.get()}",
            bg=OFF_WHITE, fg=CHARCOAL,
            font=("Georgia", 13, "bold"),
        ).pack(side="left", padx=16)

        tk.Frame(self, bg=LIGHT_GRAY, height=1).pack(fill="x", padx=40)

        content = tk.Frame(self, bg=OFF_WHITE, pady=30)
        content.pack(fill="both", expand=True, padx=60)

        tk.Label(
            content,
            text="Add the PTS permit PDF",
            bg=OFF_WHITE, fg=CHARCOAL,
            font=("Georgia", 18, "bold"),
            anchor="w",
        ).pack(fill="x")

        tk.Label(
            content,
            text="Drag and drop the PDF below, or click to browse.",
            bg=OFF_WHITE, fg=MID_GRAY,
            font=("Helvetica", 10),
            anchor="w",
        ).pack(fill="x", pady=(4, 20))

        # ── Drop zone ──
        self.drop_frame = tk.Frame(
            content,
            bg=WHITE,
            highlightbackground=LIGHT_GRAY,
            highlightthickness=2,
            cursor="hand2",
        )
        self.drop_frame.pack(fill="x", ipady=30)

        self.drop_icon = tk.Label(
            self.drop_frame, text="📄",
            bg=WHITE, font=("Helvetica", 28),
        )
        self.drop_icon.pack(pady=(16, 4))

        self.drop_label = tk.Label(
            self.drop_frame,
            text="Drop PDF here",
            bg=WHITE, fg=MID_GRAY,
            font=("Helvetica", 11),
        )
        self.drop_label.pack()

        self.drop_sub = tk.Label(
            self.drop_frame,
            text="or click to browse",
            bg=WHITE, fg=UT_ORANGE,
            font=("Helvetica", 9, "underline"),
            cursor="hand2",
        )
        self.drop_sub.pack(pady=(2, 16))

        # Bind click anywhere in drop zone to browse
        for widget in [self.drop_frame, self.drop_icon, self.drop_label, self.drop_sub]:
            widget.bind("<Button-1>", lambda e: self._browse())

        # ── Error label ──
        self.error_label = tk.Label(
            content, text="",
            bg=OFF_WHITE, fg=ERROR_RED,
            font=("Helvetica", 9),
            anchor="w", wraplength=460, justify="left",
        )
        self.error_label.pack(fill="x", pady=(10, 0))

        # ── Process button ──
        btn_frame = tk.Frame(content, bg=OFF_WHITE, pady=16)
        btn_frame.pack(fill="x")
        self.process_btn = _OrangeButton(
            btn_frame, text="Process Permits →",
            command=self._submit, state="disabled",
        )
        self.process_btn.pack(side="right")

    def _try_enable_dnd(self):
        """Enable drag-and-drop if tkinterdnd2 is available."""
        try:
            from tkinterdnd2 import DND_FILES
            self.drop_frame.drop_target_register(DND_FILES)
            self.drop_frame.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            # tkinterdnd2 not available — browse-only mode
            self.drop_sub.config(text="click to browse (drag-and-drop unavailable)")

    def _on_drop(self, event):
        path = event.data.strip().strip("{}")
        self._set_pdf(path)

    def _browse(self):
        path = filedialog.askopenfilename(
            title="Select PTS Permit PDF",
            filetypes=[("PDF files", "*.pdf")],
        )
        if path:
            self._set_pdf(path)

    def _set_pdf(self, path: str):
        if not path.lower().endswith(".pdf"):
            self.error_label.config(text="⚠  Please select a PDF file.")
            return
        if not os.path.isfile(path):
            self.error_label.config(text="⚠  File not found. Please try again.")
            return

        self._pdf_path = path
        filename = os.path.basename(path)
        self.drop_label.config(text=filename, fg=CHARCOAL, font=("Helvetica", 10, "bold"))
        self.drop_icon.config(text="✅")
        self.drop_sub.config(text="Click to change file")
        self.error_label.config(text="")
        self.process_btn.config(state="normal")

    def _submit(self):
        if not self._pdf_path:
            self.error_label.config(text="⚠  Please select a PDF first.")
            return
        self.master.pdf_path = self._pdf_path
        self.master.show_progress_screen()


# ══════════════════════════════════════════════════════════════════════════════
# SCREEN 3 — Progress + Result
# ══════════════════════════════════════════════════════════════════════════════

class ProgressScreen(tk.Frame):
    """Screen 3: Shows a running log while the pipeline executes,
    then displays success or error and closes the app."""

    def __init__(self, master: PermitApp):
        super().__init__(master, bg=OFF_WHITE)
        self.master: PermitApp = master
        self._build()
        self._start_pipeline()

    def _build(self):
        tk.Frame(self, bg=UT_ORANGE, height=6).pack(fill="x")

        content = tk.Frame(self, bg=OFF_WHITE, pady=30)
        content.pack(fill="both", expand=True, padx=60)

        tk.Label(
            content,
            text="Processing Permits",
            bg=OFF_WHITE, fg=CHARCOAL,
            font=("Georgia", 18, "bold"),
            anchor="w",
        ).pack(fill="x")

        self.status_label = tk.Label(
            content,
            text="Starting...",
            bg=OFF_WHITE, fg=MID_GRAY,
            font=("Helvetica", 10),
            anchor="w",
        )
        self.status_label.pack(fill="x", pady=(4, 14))

        # Scrollable log box
        log_frame = tk.Frame(content, bg=CHARCOAL, padx=1, pady=1)
        log_frame.pack(fill="both", expand=True)
        self.log_box = tk.Text(
            log_frame,
            bg="#0F0F0F", fg="#CCCCCC",
            font=("Courier", 8),
            relief="flat",
            state="disabled",
            wrap="word",
            height=12,
        )
        scrollbar = tk.Scrollbar(log_frame, command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.log_box.pack(fill="both", expand=True, padx=8, pady=8)

        # Result area (shown after completion)
        self.result_frame = tk.Frame(content, bg=OFF_WHITE, pady=14)
        self.result_frame.pack(fill="x")

    def _log(self, message: str):
        """Append a line to the log box (thread-safe via after())."""
        def _append():
            self.log_box.config(state="normal")
            self.log_box.insert("end", message + "\n")
            self.log_box.see("end")
            self.log_box.config(state="disabled")
        self.after(0, _append)

    def _start_pipeline(self):
        # Conflict detection happens per-file inside permit_splitter.py,
        # checking the exact [GARAGE_CODE]_[PERMIT_ID] filename before writing.
        # This allows new permits for the same garage with different permit IDs
        # to be added to the same event folder without being incorrectly blocked.
        run_pipeline(
            pdf_path=self.master.pdf_path,
            output_dir=self.master.event_folder,
            on_progress=self._on_progress,
            on_complete=self._on_complete,
            on_error=self._on_error,
        )

    def _on_progress(self, message: str):
        self._log(message)
        self.after(0, lambda: self.status_label.config(text=message[:80]))

    def _on_complete(self, count: int):
        def _show():
            self.status_label.config(text="Done!", fg=SUCCESS_GRN)
            self._log(f"\n✅ {count} permit(s) saved to:\n   {self.master.event_folder}")

            # Success message
            tk.Label(
                self.result_frame,
                text=f"✅  {count} permit PDF(s) created successfully.",
                bg=OFF_WHITE, fg=SUCCESS_GRN,
                font=("Helvetica", 11, "bold"),
                anchor="w",
            ).pack(fill="x")

            tk.Label(
                self.result_frame,
                text=self.master.event_folder,
                bg=OFF_WHITE, fg=MID_GRAY,
                font=("Helvetica", 8),
                anchor="w",
            ).pack(fill="x", pady=(2, 12))

            # Start Over and Close buttons
            btn_row = tk.Frame(self.result_frame, bg=OFF_WHITE)
            btn_row.pack(fill="x")

            tk.Button(
                btn_row, text="← Process Another",
                bg=OFF_WHITE, fg=MID_GRAY,
                font=("Helvetica", 10),
                relief="flat", cursor="hand2",
                command=self.master.show_event_screen,
            ).pack(side="left")

            _OrangeButton(
                btn_row,
                text="Close",
                command=self.master.destroy,
            ).pack(side="right")

        self.after(0, _show)

    def _on_error(self, detail: str):
        def _show():
            self.status_label.config(text="An error occurred.", fg=ERROR_RED)
            self._log(f"\n❌ ERROR:\n{detail}")

            # Check if it's a conflict error
            if "exists" in detail.lower() or "conflict" in detail.lower():
                conflict_msg = "⚠  Same permit files already exist in this folder.\nDelete or rename the existing files and try again."
            elif "not a garage" in detail.lower() or "surface lot" in detail.lower():
                conflict_msg = "⚠  This tool only processes garage permits.\nSurface lot permits (e.g. Lot 80) must be handled separately."
            elif "no permits were found" in detail.lower():
                conflict_msg = "⚠  No permits were found in this PDF.\nPlease make sure you are uploading a valid PTS parking permit PDF."
            else:
                conflict_msg = "❌  Something went wrong. See the log above for details."

            tk.Label(
                self.result_frame,
                text=conflict_msg,
                bg=OFF_WHITE, fg=ERROR_RED,
                font=("Helvetica", 10, "bold"),
                anchor="w",
                wraplength=460,
                justify="left",
            ).pack(fill="x")

            btn_row = tk.Frame(self.result_frame, bg=OFF_WHITE, pady=10)
            btn_row.pack(fill="x")

            tk.Button(
                btn_row, text="← Start Over",
                bg=OFF_WHITE, fg=MID_GRAY,
                font=("Helvetica", 10),
                relief="flat", cursor="hand2",
                command=self.master.show_event_screen,
            ).pack(side="left")

            _OrangeButton(btn_row, text="Close", command=self.master.destroy).pack(side="right")

        self.after(0, _show)


# ══════════════════════════════════════════════════════════════════════════════
# SHARED WIDGET — Orange Button
# ══════════════════════════════════════════════════════════════════════════════

class _OrangeButton(tk.Button):
    """Reusable UT burnt orange button with hover effect."""

    def __init__(self, master, text, command, state="normal", **kwargs):
        super().__init__(
            master,
            text=text,
            command=command,
            state=state,
            bg=UT_ORANGE,
            fg=WHITE,
            activebackground=UT_ORANGE_DK,
            activeforeground=WHITE,
            disabledforeground="#DDDDDD",
            font=("Helvetica", 11, "bold"),
            relief="flat",
            cursor="hand2",
            padx=20,
            pady=8,
            **kwargs,
        )
        self.bind("<Enter>", lambda e: self.config(bg=UT_ORANGE_DK) if str(self["state"]) != "disabled" else None)
        self.bind("<Leave>", lambda e: self.config(bg=UT_ORANGE) if str(self["state"]) != "disabled" else None)
