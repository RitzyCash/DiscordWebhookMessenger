#!/usr/bin/env python3
import json
import os
import re
import tempfile
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import ttk, filedialog, messagebox, simpledialog, colorchooser

try:
    import requests
except ImportError:
    raise SystemExit("pip install requests")

try:
    from PIL import ImageGrab, Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".discord_webhook_gui_config.json")
DISCORD_CONTENT_LIMIT = 2000
URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
SOFT_FILE_SIZE_WARNING = 8 * 1024 * 1024
SEND_DELAY = 0.35

EMOJIS = [
    "😀", "😂", "😅", "😉", "😊", "😍", "😘", "😜", "🤔", "😎",
    "😢", "😭", "😡", "🥳", "😴", "🤯", "🥺", "😱", "🙄", "😇",
    "👍", "👎", "👏", "🙌", "🙏", "💪", "🤝", "👀", "🔥", "✨",
    "🎉", "🎊", "❤️", "💔", "⭐", "✅", "❌", "⚠️", "💯", "🚀",
    "🤖", "👾", "💀", "🎮", "🎵", "📌", "📎", "🔔", "🔒", "🕐",
]

SHORTCUTS = [
    ("Ctrl+B", "Bold"),
    ("Ctrl+I", "Italic"),
    ("Ctrl+U", "Underline"),
    ("Ctrl+Shift+X", "Strikethrough"),
    ("Ctrl+E", "Inline code"),
    ("Ctrl+Shift+C", "Code block"),
    ("Ctrl+Shift+S", "Spoiler"),
    ("Ctrl+Shift+Q", "Quote selected lines"),
    ("Ctrl+K", "Insert link"),
    ("Ctrl+Shift+M", "Insert mention"),
    ("Ctrl+Shift+P", "Emoji picker"),
    ("Ctrl+Shift+N", "Clear message"),
    ("Ctrl+O", "Add files"),
    ("Ctrl+Enter", "Send"),
    ("Ctrl+/", "Show this list"),
]


class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, event=None):
        if self.tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 6
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text, bg="#111214", fg="#dbdee1", relief="solid",
                 borderwidth=1, padx=6, pady=2, font=("Segoe UI", 8)).pack()

    def hide(self, event=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"profiles": [], "username": "", "avatar_url": ""}


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except OSError as e:
        print(f"couldn't save config: {e}")


def split_message(content, limit=DISCORD_CONTENT_LIMIT):
    if not content:
        return [""]
    if len(content) <= limit:
        return [content]

    chunks = []
    remaining = content
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        window = remaining[:limit]
        cut = window.rfind("\n\n")
        if cut < limit * 0.4:
            cut = window.rfind("\n")
        if cut < limit * 0.4:
            cut = window.rfind(" ")
        if cut < limit * 0.4:
            cut = limit
        chunk = remaining[:cut].rstrip()
        if not chunk:
            chunk = remaining[:limit]
            cut = limit
        chunks.append(chunk)
        remaining = remaining[cut:].lstrip("\n")
    return chunks


class DiscordWebhookGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Discord Webhook Messenger")
        self.root.geometry("760x900")
        self.root.minsize(640, 680)

        self.cfg = load_config()
        self.attachments = []

        self._build_style()
        self._build_widgets()
        self._load_profiles_into_ui()
        self._bind_hotkeys()

    def _build_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        bg = "#2b2d31"
        panel = "#313338"
        fg = "#dbdee1"
        accent = "#5865F2"

        self.root.configure(bg=bg)
        style.configure(".", background=bg, foreground=fg, fieldbackground=panel)
        style.configure("TFrame", background=bg)
        style.configure("TLabelframe", background=bg, foreground=fg)
        style.configure("TLabelframe.Label", background=bg, foreground=fg)
        style.configure("TLabel", background=bg, foreground=fg)
        style.configure("TCheckbutton", background=bg, foreground=fg)
        style.configure("TButton", background=panel, foreground=fg, padding=6)
        style.map("TButton", background=[("active", accent)])
        style.configure("Accent.TButton", background=accent, foreground="white", padding=8)
        style.map("Accent.TButton", background=[("active", "#4752C4")])
        style.configure("TEntry", fieldbackground=panel, foreground=fg, insertcolor=fg)
        style.configure("TCombobox", fieldbackground=panel, foreground=fg)

        self.colors = {"bg": bg, "panel": panel, "fg": fg, "accent": accent,
                        "muted": "#949BA4", "danger": "#f04747", "ok": "#3ba55d"}

    def _build_widgets(self):
        pad = {"padx": 10, "pady": 6}

        top = ttk.Frame(self.root)
        top.pack(fill="x", **pad)

        ttk.Label(top, text="Webhook profile:").grid(row=0, column=0, sticky="w")
        self.profile_var = tk.StringVar()
        self.profile_combo = ttk.Combobox(top, textvariable=self.profile_var, state="readonly", width=22)
        self.profile_combo.grid(row=0, column=1, sticky="w", padx=(6, 6))
        self.profile_combo.bind("<<ComboboxSelected>>", self._on_profile_selected)

        ttk.Button(top, text="Save as...", command=self._save_profile).grid(row=0, column=2, padx=2)
        ttk.Button(top, text="Delete", command=self._delete_profile).grid(row=0, column=3, padx=2)

        ttk.Label(top, text="Webhook URL:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.webhook_var = tk.StringVar()
        self.webhook_entry = ttk.Entry(top, textvariable=self.webhook_var, show="*")
        self.webhook_entry.grid(row=1, column=1, columnspan=2, sticky="ew", pady=(6, 0))
        self.show_url_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="show", variable=self.show_url_var,
                         command=self._toggle_show_url).grid(row=1, column=3, sticky="w", pady=(6, 0))
        top.columnconfigure(1, weight=1)

        bcast = ttk.LabelFrame(self.root, text="Multi-webhook broadcast")
        bcast.pack(fill="x", padx=10, pady=(0, 6))

        self.broadcast_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            bcast, text="Broadcast to multiple saved profiles instead of the single URL above",
            variable=self.broadcast_var, command=self._toggle_broadcast_mode
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=6, pady=(4, 0))

        self.broadcast_listbox = tk.Listbox(
            bcast, height=4, selectmode="extended",
            bg=self.colors["panel"], fg=self.colors["fg"], relief="flat"
        )
        self.broadcast_listbox.grid(row=1, column=0, columnspan=3, sticky="ew", padx=6, pady=4)
        bcast.columnconfigure(0, weight=1)

        btn_row = ttk.Frame(bcast)
        btn_row.grid(row=2, column=0, columnspan=3, sticky="w", padx=6, pady=(0, 6))
        ttk.Button(btn_row, text="Select All", command=self._broadcast_select_all).pack(side="left")
        ttk.Button(btn_row, text="Select None", command=self._broadcast_select_none).pack(side="left", padx=6)
        ttk.Label(btn_row, text="(save profiles above first, via 'Save as...')",
                  foreground=self.colors["muted"]).pack(side="left", padx=6)

        self._toggle_broadcast_mode()

        row2 = ttk.Frame(self.root)
        row2.pack(fill="x", **pad)
        ttk.Label(row2, text="Username override:").grid(row=0, column=0, sticky="w")
        self.username_var = tk.StringVar(value=self.cfg.get("username", ""))
        ttk.Entry(row2, textvariable=self.username_var, width=20).grid(row=0, column=1, padx=(6, 16))

        ttk.Label(row2, text="Avatar URL override:").grid(row=0, column=2, sticky="w")
        self.avatar_var = tk.StringVar(value=self.cfg.get("avatar_url", ""))
        ttk.Entry(row2, textvariable=self.avatar_var, width=24).grid(row=0, column=3, padx=(6, 16))

        self.tts_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row2, text="TTS", variable=self.tts_var).grid(row=0, column=4)

        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill="x", padx=10, pady=(6, 0))

        def tb(text, cmd, width=4, tip=None):
            btn = ttk.Button(toolbar, text=text, width=width, command=cmd)
            btn.pack(side="left", padx=2)
            if tip:
                ToolTip(btn, tip)
            return btn

        tb("B", lambda: self.wrap_selection("**"), tip="Bold (Ctrl+B)")
        tb("I", lambda: self.wrap_selection("*"), tip="Italic (Ctrl+I)")
        tb("U", lambda: self.wrap_selection("__"), tip="Underline (Ctrl+U)")
        tb("S", lambda: self.wrap_selection("~~"), tip="Strikethrough (Ctrl+Shift+X)")
        tb("Code", lambda: self.wrap_selection("`"), width=5, tip="Inline code (Ctrl+E)")
        tb("Block", lambda: self.wrap_selection("```\n", "\n```"), width=5, tip="Code block (Ctrl+Shift+C)")
        tb("Spoiler", lambda: self.wrap_selection("||"), width=7, tip="Spoiler (Ctrl+Shift+S)")
        tb("Quote", self.insert_quote, width=6, tip="Quote (Ctrl+Shift+Q)")
        tb("Link", self.insert_link, width=5, tip="Insert link (Ctrl+K)")
        tb("\U0001F600", self.open_emoji_picker, width=3, tip="Emoji picker (Ctrl+Shift+P)")
        tb("@", self.open_mention_helper, width=3, tip="Insert mention (Ctrl+Shift+M)")
        tb("?", self.open_shortcuts_help, width=3, tip="Keyboard shortcuts (Ctrl+/)")

        msg_frame = ttk.LabelFrame(self.root, text="Message")
        msg_frame.pack(fill="both", expand=True, padx=10, pady=6)

        text_container = tk.Frame(msg_frame, bg=self.colors["panel"])
        text_container.pack(fill="both", expand=True, padx=4, pady=4)

        self.text = tk.Text(
            text_container, wrap="word", undo=True,
            bg=self.colors["panel"], fg=self.colors["fg"],
            insertbackground=self.colors["fg"], relief="flat",
            font=("Consolas", 11), height=10,
        )
        scrollbar = ttk.Scrollbar(text_container, command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.text.bind("<<Paste>>", self._on_paste)
        self.text.bind("<KeyRelease>", self._update_char_count)

        counter_row = ttk.Frame(msg_frame)
        counter_row.pack(fill="x", padx=6)
        self.auto_split_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(counter_row, text="Auto-split long messages",
                         variable=self.auto_split_var).pack(side="left")
        self.char_count_var = tk.StringVar(value=f"0 / {DISCORD_CONTENT_LIMIT}")
        ttk.Label(counter_row, textvariable=self.char_count_var,
                  foreground=self.colors["muted"]).pack(side="right")

        embed_frame = ttk.LabelFrame(self.root, text="Embed (optional, sent with first message only)")
        embed_frame.pack(fill="x", padx=10, pady=6)

        self.embed_enabled_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(embed_frame, text="Attach an embed", variable=self.embed_enabled_var,
                         command=self._toggle_embed_fields).grid(row=0, column=0, sticky="w", padx=6, pady=4)

        ttk.Label(embed_frame, text="Title:").grid(row=1, column=0, sticky="w", padx=6)
        self.embed_title_var = tk.StringVar()
        self.embed_title_entry = ttk.Entry(embed_frame, textvariable=self.embed_title_var)
        self.embed_title_entry.grid(row=1, column=1, columnspan=2, sticky="ew", padx=6)

        ttk.Label(embed_frame, text="Description:").grid(row=2, column=0, sticky="nw", padx=6, pady=4)
        self.embed_desc_text = tk.Text(embed_frame, height=3, bg=self.colors["panel"],
                                        fg=self.colors["fg"], insertbackground=self.colors["fg"], relief="flat")
        self.embed_desc_text.grid(row=2, column=1, columnspan=2, sticky="ew", padx=6, pady=4)

        ttk.Label(embed_frame, text="Color:").grid(row=3, column=0, sticky="w", padx=6)
        self.embed_color = "#5865F2"
        self.embed_color_btn = tk.Button(embed_frame, text="  Pick  ", bg=self.embed_color,
                                          command=self._pick_embed_color, relief="flat")
        self.embed_color_btn.grid(row=3, column=1, sticky="w", padx=6, pady=4)

        embed_frame.columnconfigure(1, weight=1)
        self._embed_widgets = [self.embed_title_entry, self.embed_desc_text, self.embed_color_btn]
        self._toggle_embed_fields()

        att_frame = ttk.LabelFrame(self.root, text="Attachments")
        att_frame.pack(fill="x", padx=10, pady=6)

        att_top = ttk.Frame(att_frame)
        att_top.pack(fill="x", padx=6, pady=4)
        add_files_btn = ttk.Button(att_top, text="Add Files...", command=self._add_files)
        add_files_btn.pack(side="left")
        ToolTip(add_files_btn, "Add files (Ctrl+O)")
        ttk.Button(att_top, text="Remove Selected", command=self._remove_selected_file).pack(side="left", padx=6)
        ttk.Button(att_top, text="Clear All", command=self._clear_files).pack(side="left")

        dnd_hint = "Drag files here to attach" if HAS_DND else \
            "Drag-and-drop disabled (pip install tkinterdnd2 to enable it)"
        ttk.Label(att_top, text=dnd_hint, foreground=self.colors["muted"]).pack(side="right")

        self.file_listbox = tk.Listbox(att_frame, height=4, bg=self.colors["panel"],
                                        fg=self.colors["fg"], relief="flat", selectmode="extended")
        self.file_listbox.pack(fill="x", padx=6, pady=(0, 6))

        if HAS_DND:
            self.file_listbox.drop_target_register(DND_FILES)
            self.file_listbox.dnd_bind("<<Drop>>", self._on_drop_files)
            att_frame.drop_target_register(DND_FILES)
            att_frame.dnd_bind("<<Drop>>", self._on_drop_files)

        if not HAS_PIL:
            ttk.Label(att_frame, text="Tip: pip install pillow to paste clipboard screenshots directly.",
                      foreground=self.colors["muted"]).pack(anchor="w", padx=6, pady=(0, 4))

        bottom = ttk.Frame(self.root)
        bottom.pack(fill="x", padx=10, pady=(0, 10))

        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(bottom, textvariable=self.status_var, foreground=self.colors["muted"]).pack(side="left")

        clear_btn = ttk.Button(bottom, text="Clear Message", command=self._clear_message)
        clear_btn.pack(side="right", padx=(6, 0))
        ToolTip(clear_btn, "Clear message (Ctrl+Shift+N)")
        self.send_btn = ttk.Button(bottom, text="Send", style="Accent.TButton", command=self._on_send_clicked)
        self.send_btn.pack(side="right")
        ToolTip(self.send_btn, "Send (Ctrl+Enter)")

    def _load_profiles_into_ui(self):
        names = [p["name"] for p in self.cfg.get("profiles", [])]
        self.profile_combo["values"] = names
        if names:
            self.profile_var.set(names[0])
            self._on_profile_selected()
        self._refresh_broadcast_list()

    def _on_profile_selected(self, event=None):
        name = self.profile_var.get()
        for p in self.cfg.get("profiles", []):
            if p["name"] == name:
                self.webhook_var.set(p["url"])
                break

    def _save_profile(self):
        url = self.webhook_var.get().strip()
        if not url:
            messagebox.showwarning("No URL", "Enter a webhook URL before saving a profile.")
            return
        name = simpledialog.askstring("Save profile", "Name this webhook (e.g. 'My Server #general'):")
        if not name:
            return
        profiles = self.cfg.setdefault("profiles", [])
        profiles = [p for p in profiles if p["name"] != name]
        profiles.append({"name": name, "url": url})
        self.cfg["profiles"] = profiles
        save_config(self.cfg)
        self._load_profiles_into_ui()
        self.profile_var.set(name)
        self.status_var.set(f"Saved profile '{name}'.")

    def _delete_profile(self):
        name = self.profile_var.get()
        if not name:
            return
        if not messagebox.askyesno("Delete profile", f"Delete saved profile '{name}'?"):
            return
        self.cfg["profiles"] = [p for p in self.cfg.get("profiles", []) if p["name"] != name]
        save_config(self.cfg)
        self.profile_var.set("")
        self._load_profiles_into_ui()

    def _toggle_show_url(self):
        self.webhook_entry.configure(show="" if self.show_url_var.get() else "*")

    def _refresh_broadcast_list(self):
        self.broadcast_listbox.delete(0, tk.END)
        for p in self.cfg.get("profiles", []):
            self.broadcast_listbox.insert(tk.END, p["name"])

    def _toggle_broadcast_mode(self):
        broadcasting = self.broadcast_var.get()
        self.broadcast_listbox.configure(state="normal" if broadcasting else "disabled")
        self.webhook_entry.configure(state="disabled" if broadcasting else "normal")
        self.profile_combo.configure(state="disabled" if broadcasting else "readonly")

    def _broadcast_select_all(self):
        self.broadcast_listbox.select_set(0, tk.END)

    def _broadcast_select_none(self):
        self.broadcast_listbox.select_clear(0, tk.END)

    def _get_broadcast_targets(self):
        profiles = self.cfg.get("profiles", [])
        targets = []
        for i in self.broadcast_listbox.curselection():
            if i < len(profiles):
                targets.append((profiles[i]["name"], profiles[i]["url"]))
        return targets

    def wrap_selection(self, prefix, suffix=None):
        suffix = prefix if suffix is None else suffix
        try:
            start = self.text.index(tk.SEL_FIRST)
            end = self.text.index(tk.SEL_LAST)
            selected = self.text.get(start, end)
            self.text.delete(start, end)
            self.text.insert(start, f"{prefix}{selected}{suffix}")
            new_cursor = f"{start}+{len(prefix) + len(selected) + len(suffix)}c"
            self.text.mark_set(tk.INSERT, new_cursor)
        except tk.TclError:
            pos = self.text.index(tk.INSERT)
            self.text.insert(pos, f"{prefix}{suffix}")
            self.text.mark_set(tk.INSERT, f"{pos}+{len(prefix)}c")
        self.text.focus_set()
        self._update_char_count()

    def insert_quote(self):
        try:
            start = self.text.index(tk.SEL_FIRST)
            end = self.text.index(tk.SEL_LAST)
            selected = self.text.get(start, end)
            quoted = "\n".join(f"> {line}" for line in selected.split("\n"))
            self.text.delete(start, end)
            self.text.insert(start, quoted)
        except tk.TclError:
            pos = self.text.index(tk.INSERT)
            self.text.insert(pos, "> ")
        self.text.focus_set()
        self._update_char_count()

    def insert_link(self):
        try:
            start = self.text.index(tk.SEL_FIRST)
            end = self.text.index(tk.SEL_LAST)
            label = self.text.get(start, end)
        except tk.TclError:
            start = end = None
            label = "link text"

        url = simpledialog.askstring("Insert link", "URL:")
        if not url:
            return
        markdown = f"[{label}]({url})"
        if start:
            self.text.delete(start, end)
            self.text.insert(start, markdown)
        else:
            self.text.insert(tk.INSERT, markdown)
        self._update_char_count()

    def _insert_at_cursor(self, s):
        self.text.insert(tk.INSERT, s)
        self.text.focus_set()
        self._update_char_count()

    def open_emoji_picker(self):
        win = tk.Toplevel(self.root)
        win.title("Emoji picker")
        win.configure(bg=self.colors["bg"])
        win.geometry("360x260")
        win.transient(self.root)

        grid = ttk.Frame(win)
        grid.pack(fill="both", expand=True, padx=8, pady=8)

        cols = 10
        for idx, emoji in enumerate(EMOJIS):
            r, c = divmod(idx, cols)
            btn = tk.Button(
                grid, text=emoji, font=("Segoe UI Emoji", 14), relief="flat",
                bg=self.colors["panel"], activebackground=self.colors["accent"],
                command=lambda e=emoji: self._insert_at_cursor(e),
            )
            btn.grid(row=r, column=c, padx=2, pady=2)

        ttk.Label(win, text="Or type a custom Discord emoji as :name: (e.g. :pepe:)",
                  foreground=self.colors["muted"]).pack(padx=8, pady=(0, 6))
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=(0, 8))

    def open_mention_helper(self):
        win = tk.Toplevel(self.root)
        win.title("Insert mention")
        win.configure(bg=self.colors["bg"])
        win.transient(self.root)
        win.resizable(False, False)

        frame = ttk.Frame(win)
        frame.pack(padx=12, pady=12)

        kind_var = tk.StringVar(value="user")
        options = [
            ("User (needs numeric user ID)", "user"),
            ("Role (needs numeric role ID)", "role"),
            ("Channel (needs numeric channel ID)", "channel"),
            ("@everyone", "everyone"),
            ("@here", "here"),
        ]
        for text, val in options:
            ttk.Radiobutton(frame, text=text, value=val, variable=kind_var).pack(anchor="w")

        id_row = ttk.Frame(frame)
        id_row.pack(fill="x", pady=(8, 0))
        ttk.Label(id_row, text="ID:").pack(side="left")
        id_var = tk.StringVar()
        id_entry = ttk.Entry(id_row, textvariable=id_var, width=24)
        id_entry.pack(side="left", padx=6)

        ttk.Label(
            frame, text="Tip: enable Developer Mode in Discord, then\n"
                        "right-click a user/role/channel -> Copy ID.",
            foreground=self.colors["muted"], justify="left",
        ).pack(anchor="w", pady=(8, 0))

        def do_insert():
            kind = kind_var.get()
            if kind == "everyone":
                self._insert_at_cursor("@everyone")
            elif kind == "here":
                self._insert_at_cursor("@here")
            else:
                raw_id = id_var.get().strip()
                if not raw_id.isdigit():
                    messagebox.showwarning("Invalid ID", "Please enter a numeric Discord ID.")
                    return
                if kind == "user":
                    self._insert_at_cursor(f"<@{raw_id}>")
                elif kind == "role":
                    self._insert_at_cursor(f"<@&{raw_id}>")
                elif kind == "channel":
                    self._insert_at_cursor(f"<#{raw_id}>")
            win.destroy()

        btn_row = ttk.Frame(frame)
        btn_row.pack(fill="x", pady=(10, 0))
        ttk.Button(btn_row, text="Insert", style="Accent.TButton", command=do_insert).pack(side="right")
        ttk.Button(btn_row, text="Cancel", command=win.destroy).pack(side="right", padx=6)

    def open_shortcuts_help(self):
        win = tk.Toplevel(self.root)
        win.title("Keyboard shortcuts")
        win.configure(bg=self.colors["bg"])
        win.resizable(False, False)
        win.transient(self.root)

        frame = ttk.Frame(win)
        frame.pack(padx=14, pady=14)

        for i, (keys, desc) in enumerate(SHORTCUTS):
            tk.Label(frame, text=keys, font=("Consolas", 10, "bold"), bg=self.colors["bg"],
                     fg=self.colors["accent"], anchor="w", width=16).grid(row=i, column=0, sticky="w", pady=2)
            tk.Label(frame, text=desc, bg=self.colors["bg"], fg=self.colors["fg"],
                     anchor="w").grid(row=i, column=1, sticky="w", padx=(10, 0), pady=2)

        ttk.Button(win, text="Close", command=win.destroy).pack(pady=(4, 10))

    def _bind_hotkeys(self):
        t = self.text

        def wrap(prefix, suffix=None):
            def handler(event):
                self.wrap_selection(prefix, suffix)
                return "break"
            return handler

        def call(fn):
            def handler(event):
                fn()
                return "break"
            return handler

        def bind_both_cases(seq_upper, seq_lower, handler):
            t.bind(seq_upper, handler)
            t.bind(seq_lower, handler)

        t.bind("<Control-b>", wrap("**"))
        t.bind("<Control-i>", wrap("*"))
        t.bind("<Control-u>", wrap("__"))
        t.bind("<Control-e>", wrap("`"))
        t.bind("<Control-k>", call(self.insert_link))

        bind_both_cases("<Control-Shift-X>", "<Control-Shift-x>", wrap("~~"))
        bind_both_cases("<Control-Shift-C>", "<Control-Shift-c>", wrap("```\n", "\n```"))
        bind_both_cases("<Control-Shift-S>", "<Control-Shift-s>", wrap("||"))
        bind_both_cases("<Control-Shift-Q>", "<Control-Shift-q>", call(self.insert_quote))
        bind_both_cases("<Control-Shift-M>", "<Control-Shift-m>", call(self.open_mention_helper))
        bind_both_cases("<Control-Shift-P>", "<Control-Shift-p>", call(self.open_emoji_picker))
        bind_both_cases("<Control-Shift-N>", "<Control-Shift-n>", call(self._clear_message))

        t.bind("<Control-Return>", call(self._on_send_clicked))

        self.root.bind_all("<Control-Return>", call(self._on_send_clicked))
        self.root.bind_all("<Control-o>", call(self._add_files))
        self.root.bind_all("<Control-slash>", call(self.open_shortcuts_help))

    def _on_paste(self, event):
        if HAS_PIL:
            try:
                clip_obj = ImageGrab.grabclipboard()
            except Exception:
                clip_obj = None
            if isinstance(clip_obj, Image.Image):
                path = self._save_clipboard_image(clip_obj)
                self._register_attachment(path)
                self.status_var.set(f"Pasted image from clipboard -> {os.path.basename(path)}")
                return "break"
            if isinstance(clip_obj, list) and clip_obj:
                added = 0
                for p in clip_obj:
                    if isinstance(p, str) and os.path.isfile(p):
                        self._register_attachment(p)
                        added += 1
                if added:
                    self.status_var.set(f"Attached {added} file(s) from clipboard.")
                    return "break"

        try:
            clip = self.root.clipboard_get()
        except tk.TclError:
            return None
        if not clip:
            return None
        clip = clip.strip()
        if not URL_RE.match(clip):
            return None

        try:
            start = self.text.index(tk.SEL_FIRST)
            end = self.text.index(tk.SEL_LAST)
        except tk.TclError:
            return None

        selected = self.text.get(start, end)
        self.text.delete(start, end)
        self.text.insert(start, f"[{selected}]({clip})")
        self._update_char_count()
        return "break"

    def _save_clipboard_image(self, img):
        folder = tempfile.gettempdir()
        name = f"clipboard_{datetime.now():%Y%m%d_%H%M%S}.png"
        path = os.path.join(folder, name)
        if img.mode in ("RGBA", "P"):
            img.save(path, "PNG")
        else:
            img.convert("RGB").save(path, "PNG")
        return path

    def _update_char_count(self, event=None):
        content = self.text.get("1.0", "end-1c")
        n = len(content)
        limit_note = "" if (self.auto_split_var.get() or n <= DISCORD_CONTENT_LIMIT) else "  (will be blocked)"
        self.char_count_var.set(f"{n} / {DISCORD_CONTENT_LIMIT}{limit_note}")

    def _clear_message(self):
        self.text.delete("1.0", tk.END)
        self._update_char_count()

    def _toggle_embed_fields(self):
        state = "normal" if self.embed_enabled_var.get() else "disabled"
        self.embed_title_entry.configure(state=state)
        self.embed_desc_text.configure(state=state)
        self.embed_color_btn.configure(state=state)

    def _pick_embed_color(self):
        _, hex_color = colorchooser.askcolor(color=self.embed_color, title="Embed color")
        if hex_color:
            self.embed_color = hex_color
            self.embed_color_btn.configure(bg=hex_color)

    def _register_attachment(self, path):
        if path in self.attachments or not os.path.isfile(path):
            return
        self.attachments.append(path)
        size = os.path.getsize(path)
        label = f"{os.path.basename(path)}  ({self._human_size(size)})"
        if size > SOFT_FILE_SIZE_WARNING:
            label += "  \u26a0 may exceed Discord's upload limit"
        self.file_listbox.insert(tk.END, label)

    def _add_files(self):
        paths = filedialog.askopenfilenames(title="Choose files to attach")
        for p in paths:
            self._register_attachment(p)

    def _on_drop_files(self, event):
        try:
            paths = self.root.tk.splitlist(event.data)
        except Exception:
            paths = [event.data]
        added = 0
        for p in paths:
            if os.path.isfile(p):
                self._register_attachment(p)
                added += 1
        if added:
            self.status_var.set(f"Attached {added} file(s) via drag-and-drop.")

    def _remove_selected_file(self):
        selected = list(self.file_listbox.curselection())
        for i in reversed(selected):
            self.file_listbox.delete(i)
            del self.attachments[i]

    def _clear_files(self):
        self.file_listbox.delete(0, tk.END)
        self.attachments = []

    @staticmethod
    def _human_size(n):
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024:
                return f"{n:.0f}{unit}"
            n /= 1024
        return f"{n:.1f}TB"

    def _on_send_clicked(self):
        broadcasting = self.broadcast_var.get()

        if broadcasting:
            targets = self._get_broadcast_targets()
            if not targets:
                messagebox.showwarning(
                    "No profiles selected",
                    "Select one or more saved profiles in the broadcast list "
                    "(or save some via 'Save as...' first)."
                )
                return
        else:
            url = self.webhook_var.get().strip()
            if not url:
                messagebox.showwarning("Missing webhook URL", "Enter (or select) a webhook URL first.")
                return
            if "discord.com/api/webhooks" not in url and "discordapp.com/api/webhooks" not in url:
                if not messagebox.askyesno("Unusual URL", "That doesn't look like a Discord webhook URL. Send anyway?"):
                    return
            targets = [(None, url)]

        content = self.text.get("1.0", "end-1c")

        if len(content) > DISCORD_CONTENT_LIMIT and not self.auto_split_var.get():
            messagebox.showwarning(
                "Message too long",
                f"Your message is {len(content)} characters. Discord's limit is "
                f"{DISCORD_CONTENT_LIMIT}. Turn on 'Auto-split long messages' or trim it.",
            )
            return

        chunks = split_message(content) if self.auto_split_var.get() else [content]

        base_payload = {}
        username = self.username_var.get().strip()
        if username:
            base_payload["username"] = username
        avatar = self.avatar_var.get().strip()
        if avatar:
            base_payload["avatar_url"] = avatar
        if self.tts_var.get():
            base_payload["tts"] = True

        if self.embed_enabled_var.get():
            embed = {}
            title = self.embed_title_var.get().strip()
            desc = self.embed_desc_text.get("1.0", "end-1c").strip()
            if title:
                embed["title"] = title
            if desc:
                embed["description"] = desc
            if self.embed_color:
                embed["color"] = int(self.embed_color.lstrip("#"), 16)
            if embed:
                base_payload["embeds"] = [embed]

        if not content.strip() and not base_payload.get("embeds") and not self.attachments:
            messagebox.showwarning("Nothing to send", "Write a message, add an embed, or attach a file first.")
            return

        self.cfg["username"] = username
        self.cfg["avatar_url"] = avatar
        save_config(self.cfg)

        self.send_btn.configure(state="disabled")
        self.status_var.set("Sending...")
        threading.Thread(
            target=self._send_worker,
            args=(targets, chunks, base_payload, list(self.attachments)),
            daemon=True,
        ).start()

    def _send_worker(self, targets, chunks, base_payload, attachment_paths):
        total_steps = len(targets) * len(chunks)
        step = 0
        failures = []

        for name, url in targets:
            label = name or "webhook"
            for i, chunk in enumerate(chunks):
                step += 1
                self.root.after(0, self.status_var.set, f"Sending to {label} ({step}/{total_steps})...")

                payload = dict(base_payload)
                if chunk:
                    payload["content"] = chunk
                if i != 0:
                    payload.pop("embeds", None)
                files_for_call = attachment_paths if i == 0 else []

                ok, err = self._send_once(url, payload, files_for_call)
                if not ok:
                    failures.append(f"{label} (part {i + 1}/{len(chunks)}): {err}")

                time.sleep(SEND_DELAY)

        self.root.after(0, self._send_done, failures)

    def _send_once(self, url, payload, file_paths):
        opened_files = []
        try:
            if file_paths:
                files = {}
                for i, path in enumerate(file_paths):
                    fh = open(path, "rb")
                    opened_files.append(fh)
                    files[f"file{i}"] = (os.path.basename(path), fh)
                data = {"payload_json": json.dumps(payload)}
                resp = requests.post(url, data=data, files=files, timeout=30)
            else:
                resp = requests.post(url, json=payload, timeout=30)

            if resp.status_code in (200, 204):
                return True, None
            if resp.status_code == 429:
                retry_after = "a few"
                try:
                    retry_after = resp.json().get("retry_after", retry_after)
                except (ValueError, json.JSONDecodeError):
                    pass
                return False, f"rate limited, retry in {retry_after}s"
            detail = resp.text[:200] if resp.content else str(resp.status_code)
            return False, f"HTTP {resp.status_code}: {detail}"
        except requests.exceptions.RequestException as e:
            return False, f"network error: {e}"
        finally:
            for fh in opened_files:
                fh.close()

    def _send_done(self, failures):
        self.send_btn.configure(state="normal")
        if not failures:
            self.status_var.set("Sent \u2713")
            self._clear_message()
            self._clear_files()
        else:
            self.status_var.set(f"Completed with {len(failures)} failure(s).")
            detail = "\n".join(failures[:10])
            if len(failures) > 10:
                detail += f"\n...and {len(failures) - 10} more."
            messagebox.showerror("Some sends failed", detail)


def main():
    root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
    app = DiscordWebhookGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
