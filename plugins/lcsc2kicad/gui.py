#!/usr/bin/env python3
"""lcsc2kicad GUI - choose your existing libraries, paste LCSC numbers, Import."""
from __future__ import annotations

import logging
import os
import queue
import sys
import threading


def _point_tk_at_base_python() -> None:
    """KiCad runs plugins in a venv made from its bundled (relocated) Python; there Tcl
    looks for init.tcl under /Library/Frameworks/... and Tk fails to start. Point
    TCL_LIBRARY/TK_LIBRARY at the base interpreter's own lib/tcl8.x, lib/tk8.x."""
    lib = os.path.join(sys.base_prefix, "lib")
    try:
        names = os.listdir(lib)
    except OSError:
        return
    for env, prefix, marker in (("TCL_LIBRARY", "tcl8.", "init.tcl"),
                                ("TK_LIBRARY", "tk8.", "tk.tcl")):
        if env in os.environ:
            continue
        for n in sorted(names, reverse=True):
            d = os.path.join(lib, n)
            if n.startswith(prefix) and os.path.isfile(os.path.join(d, marker)):
                os.environ[env] = d
                break


if sys.prefix != sys.base_prefix:  # only inside a venv
    _point_tk_at_base_python()

import tkinter as tk  # noqa: E402
from pathlib import Path  # noqa: E402
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk

from . import __version__, core


class QueueLogHandler(logging.Handler):
    def __init__(self, q: queue.Queue):
        super().__init__(logging.ERROR)
        self.q = q

    def emit(self, record):
        self.q.put(f"  [{record.levelname.lower()}] {record.getMessage()}")


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.q: queue.Queue = queue.Queue()
        self.busy = False
        logging.getLogger().addHandler(QueueLogHandler(self.q))
        logging.getLogger().setLevel(logging.ERROR)

        self.v = {k: tk.StringVar() for k in core.KEYS}
        self.prof = tk.StringVar()

        root.title(f"LCSC → KiCad {core.kicad_version().split('.')[0]}  (v{__version__})")
        root.minsize(620, 560)
        f = ttk.Frame(root, padding=10)
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)

        # ---- profile (one profile = symbol lib + footprint lib + 3D folder)
        ttk.Label(f, text="Profile:", font=("TkDefaultFont", 13, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 8))
        self.prof_box = ttk.Combobox(f, textvariable=self.prof, state="readonly")
        self.prof_box.grid(row=0, column=1, sticky="ew", padx=6, pady=(0, 8))
        self.prof_box.bind("<<ComboboxSelected>>", lambda e: self.switch_profile())
        pb = ttk.Frame(f)
        pb.grid(row=0, column=2, sticky="e", pady=(0, 8))
        ttk.Button(pb, text="New…", width=6, command=self.new_profile).pack(side="left")
        ttk.Button(pb, text="Rename…", width=8, command=self.rename_profile).pack(side="left")
        ttk.Button(pb, text="Delete", width=6, command=self.delete_profile).pack(side="left")
        ttk.Separator(f).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 6))

        # ---- library choices (rows 2..6 belong to the selected profile)
        def path_row(r, label, key, cmd, clear=False):
            ttk.Label(f, text=label).grid(row=r, column=0, sticky="w", pady=2)
            ttk.Entry(f, textvariable=self.v[key], state="readonly").grid(
                row=r, column=1, sticky="ew", padx=6)
            b = ttk.Frame(f)
            b.grid(row=r, column=2, sticky="e")
            ttk.Button(b, text="Choose…", command=cmd).pack(side="left")
            if clear:
                ttk.Button(b, text="None", width=5,
                           command=lambda: self.set_choice(key, "")).pack(side="left")

        path_row(2, "Symbol library:", "sym_lib", self.choose_sym)
        path_row(3, "Footprint library:", "fp_dir", self.choose_fp)

        ttk.Label(f, text="Footprint nickname:").grid(row=4, column=0, sticky="w", pady=2)
        self.nick_box = ttk.Combobox(f, textvariable=self.v["fp_nick"],
                                     values=sorted(core.fp_libraries()))
        self.nick_box.grid(row=4, column=1, sticky="ew", padx=6)
        ttk.Label(f, text="(used in symbol Footprint field)", foreground="#777").grid(
            row=4, column=2, sticky="w")

        path_row(5, "3D folder:", "model_dir", self.choose_3d, clear=True)

        ttk.Label(f, text="3D path in footprint:").grid(row=6, column=0, sticky="w", pady=2)
        ttk.Entry(f, textvariable=self.v["model_ref"]).grid(row=6, column=1, sticky="ew", padx=6)
        ttk.Label(f, text="(blank = 3D folder path)", foreground="#777").grid(
            row=6, column=2, sticky="w")

        # ---- parts input
        ttk.Label(f, text="LCSC part numbers (space / comma / new line):").grid(
            row=7, column=0, columnspan=3, sticky="w", pady=(12, 2))
        self.parts = tk.Text(f, height=3, wrap="word")
        self.parts.grid(row=8, column=0, columnspan=3, sticky="ew")
        self.parts.bind("<Command-Return>", lambda e: (self.do_import(), "break")[1])
        self.parts.bind("<Control-Return>", lambda e: (self.do_import(), "break")[1])

        row = ttk.Frame(f)
        row.grid(row=9, column=0, columnspan=3, sticky="ew", pady=6)
        self.overwrite = tk.BooleanVar(value=False)
        ttk.Checkbutton(row, text="Overwrite existing", variable=self.overwrite).pack(
            side="left")
        self.imp_btn = ttk.Button(row, text="Import  (⌘↵)", command=self.do_import)
        self.imp_btn.pack(side="right")

        # ---- log
        self.log_box = scrolledtext.ScrolledText(f, height=14, state="disabled",
                                                 font=("Menlo", 11))
        self.log_box.grid(row=10, column=0, columnspan=3, sticky="nsew")
        f.rowconfigure(10, weight=1)

        self.load_profile(core.active_name())
        root.after(100, self.pump)

    # ------------------------------------------------------------------ helpers
    def log(self, msg: str):
        self.q.put(msg)

    def pump(self):
        try:
            while True:
                msg = self.q.get_nowait()
                if msg == "__DONE__":
                    self.busy = False
                    self.imp_btn.state(["!disabled"])
                    continue
                self.log_box.configure(state="normal")
                self.log_box.insert("end", msg + "\n")
                self.log_box.see("end")
                self.log_box.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self.pump)

    def set_choice(self, key: str, value: str):
        self.v[key].set(value)
        core.save_profile(self.prof.get(), **{key: value})

    # ------------------------------------------------------------------ profiles
    def load_profile(self, name: str):
        """Show profile `name` in the form and make it the active one."""
        core.set_active(name)
        self.prof_box.configure(values=core.profile_names())
        self.prof.set(name)
        for k, val in core.get_profile(name).items():
            self.v[k].set(val)

    def _save_typed(self):
        # the nickname / 3D path boxes are typed into; store them before leaving a profile
        core.save_profile(self.prof.get(), fp_nick=self.v["fp_nick"].get().strip(),
                          model_ref=self.v["model_ref"].get().strip())

    def switch_profile(self):
        new = self.prof.get()
        old = core.active_name()
        if new == old:
            return
        self.prof.set(old)
        self._save_typed()
        self.load_profile(new)
        self.log(f"Profile: {new}")

    def _ask_name(self, title: str, initial: str = "") -> str | None:
        name = simpledialog.askstring(title, "Profile name:", initialvalue=initial,
                                      parent=self.root)
        name = (name or "").strip()
        if name and name in core.profile_names() and name != initial:
            messagebox.showwarning("lcsc2kicad", f"Profile '{name}' already exists.")
            return None
        return name or None

    def new_profile(self):
        name = self._ask_name("New profile")
        if not name:
            return
        self._save_typed()
        core.save_profile(name)  # empty: choose its libraries next
        self.load_profile(name)
        self.log(f"Profile: {name} (new - choose its symbol, footprint and 3D libraries)")

    def rename_profile(self):
        old = self.prof.get()
        name = self._ask_name("Rename profile", old)
        if not name or name == old:
            return
        self._save_typed()
        core.rename_profile(old, name)
        self.load_profile(name)

    def delete_profile(self):
        name = self.prof.get()
        if len(core.profile_names()) == 1:
            messagebox.showinfo("lcsc2kicad", "Can't delete the only profile.")
            return
        if not messagebox.askyesno(
                "lcsc2kicad", f"Delete profile '{name}'?\n\n"
                "Only the saved choices are removed; your libraries are not touched."):
            return
        core.delete_profile(name)
        self.load_profile(core.active_name())

    def _start_dir(self, key: str) -> str:
        p = self.v[key].get()
        return str(Path(p).parent if p else Path.home())

    # ------------------------------------------------------------------ choices
    def choose_sym(self):
        p = filedialog.askopenfilename(
            title="Existing symbol library", initialdir=self._start_dir("sym_lib"),
            filetypes=[("KiCad symbol library", "*.kicad_sym")])
        if p:
            self.set_choice("sym_lib", p)

    def choose_fp(self):
        p = filedialog.askdirectory(title="Existing footprint library folder",
                                    initialdir=self._start_dir("fp_dir"))
        if p:
            self.set_choice("fp_dir", p)
            self.set_choice("fp_nick", core.guess_fp_nick(p))

    def choose_3d(self):
        p = filedialog.askdirectory(title="Existing 3D model folder",
                                    initialdir=self._start_dir("model_dir"))
        if p:
            self.set_choice("model_dir", p)

    # ------------------------------------------------------------------ import
    def do_import(self):
        if self.busy:
            return
        c = {k: self.v[k].get().strip() for k in core.KEYS}
        prof = self.prof.get()
        self._save_typed()
        try:
            ids = core.parse_ids(self.parts.get("1.0", "end"))
        except ValueError as e:
            messagebox.showwarning("lcsc2kicad", str(e))
            return
        if not ids:
            return
        self.busy = True
        self.imp_btn.state(["disabled"])
        ow = self.overwrite.get()

        def work():
            try:
                self.log(f"\n=== Profile: {prof}")
                res = core.import_parts(ids, c["sym_lib"], c["fp_dir"], c["fp_nick"],
                                        c["model_dir"] or None, c["model_ref"] or None,
                                        overwrite=ow, log=self.log)
                ok = sum(r == "added" for r in res.values())
                sk = sum(r == "skipped" for r in res.values())
                self.log(f"\nDone: {ok} added, {sk} skipped, {len(res) - ok - sk} failed.")
                if ok:
                    self.log("In KiCad, reopen the symbol/footprint chooser to see new parts.")
            except Exception as e:
                self.log(f"ERROR: {e}")
            self.q.put("__DONE__")

        threading.Thread(target=work, daemon=True).start()


def main():
    root = tk.Tk()
    App(root)
    # launched from KiCad's toolbar the window would otherwise open behind KiCad
    root.lift()
    root.attributes("-topmost", True)
    root.after(300, lambda: root.attributes("-topmost", False))
    root.focus_force()
    root.mainloop()


if __name__ == "__main__":
    main()
