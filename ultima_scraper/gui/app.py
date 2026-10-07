"""Main window of the UltimaScraper GUI."""

from __future__ import annotations

import queue
import sys
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk
from typing import Any

from ultima_scraper import dynamic_rules
from ultima_scraper.gui import config_store as store
from ultima_scraper.gui import paths
from ultima_scraper.gui.bridge import BridgeStream, UiBridge, install_patches
from ultima_scraper.gui.runner import RunOptions, ScraperRunner

VERSION = "8.0.0"
POLL_MS = 80

CONTENT_LABELS = {
    "Stories": "Stories",
    "Posts": "Posts",
    "Messages": "Messages",
    "Chats": "Discussions",
    "Highlights": "À la une",
    "MassMessages": "Messages groupés",
}
IGNORE_LABELS = {"": "Aucun", "paid": "Payants", "free": "Gratuits"}
IGNORE_VALUES = {label: value for value, label in IGNORE_LABELS.items()}
MEDIA_LABELS = {
    "Images": "Images",
    "Videos": "Vidéos",
    "Audios": "Audios",
    "Texts": "Textes",
}

AUTH_HELP = {
    "OnlyFans": (
        "1. Connectez-vous sur onlyfans.com avec Chrome/Edge/Firefox.\n"
        "2. Ouvrez les outils de développement (F12) > onglet Réseau (Network), filtrez « api2 ».\n"
        "3. Rechargez la page, clic droit sur une requête > Copier > Copier en tant que cURL.\n"
        "4. Cliquez sur « Coller depuis cURL » : cookie, x-bc et user-agent sont remplis automatiquement."
    ),
    "Fansly": (
        "1. Connectez-vous sur fansly.com.\n"
        "2. F12 > onglet Réseau, filtrez « apiv3 », rechargez la page.\n"
        "3. Clic droit sur une requête > Copier > Copier en tant que cURL.\n"
        "4. Cliquez sur « Coller depuis cURL » : authorization et user-agent sont remplis automatiquement."
    ),
}


class ChoiceDialog(tk.Toplevel):
    """Modal checklist used when the scraper asks to pick profiles/creators/etc."""

    def __init__(self, master: tk.Misc, title: str, items: list[str]) -> None:
        super().__init__(master)
        self.title(title)
        self.transient(master)  # type: ignore[arg-type]
        self.result: list[str] = []
        self.items = items
        self.geometry("420x520")
        self.minsize(320, 300)

        ttk.Label(self, text=title, style="Title.TLabel").pack(
            anchor="w", padx=12, pady=(12, 4)
        )
        self.filter_var = tk.StringVar()
        search = ttk.Entry(self, textvariable=self.filter_var)
        search.pack(fill="x", padx=12)
        self.filter_var.trace_add("write", lambda *_: self._refresh())

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=12, pady=8)
        self.listbox = tk.Listbox(
            frame, selectmode="multiple", activestyle="none", exportselection=False
        )
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.listbox.bind("<<ListboxSelect>>", lambda _e: self._sync_from_listbox())

        self.selected: set[str] = set()
        self.visible: list[str] = []
        self.count_var = tk.StringVar()
        ttk.Label(self, textvariable=self.count_var).pack(anchor="w", padx=12)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=12, pady=12)
        ttk.Button(buttons, text="Tout", command=self._select_all).pack(side="left")
        ttk.Button(buttons, text="Aucun", command=self._select_none).pack(
            side="left", padx=6
        )
        ttk.Button(buttons, text="Annuler", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Valider", command=self._ok).pack(side="right", padx=6)

        self._refresh()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.update_idletasks()
        x = master.winfo_rootx() + max(
            0, (master.winfo_width() - self.winfo_width()) // 2
        )
        y = master.winfo_rooty() + max(
            0, (master.winfo_height() - self.winfo_height()) // 3
        )
        self.geometry(f"+{x}+{y}")
        self.grab_set()
        search.focus_set()

    def _refresh(self) -> None:
        needle = self.filter_var.get().strip().lower()
        self.visible = [item for item in self.items if needle in item.lower()]
        self.listbox.delete(0, "end")
        for index, item in enumerate(self.visible):
            self.listbox.insert("end", item)
            if item in self.selected:
                self.listbox.selection_set(index)
        self._update_count()

    def _sync_from_listbox(self) -> None:
        current = {self.visible[i] for i in self.listbox.curselection()}
        self.selected = (self.selected - set(self.visible)) | current
        self._update_count()

    def _update_count(self) -> None:
        self.count_var.set(f"{len(self.selected)} / {len(self.items)} sélectionné(s)")

    def _select_all(self) -> None:
        self.selected |= set(self.visible)
        self._refresh()

    def _select_none(self) -> None:
        self.selected -= set(self.visible)
        self._refresh()

    def _ok(self) -> None:
        self.result = [item for item in self.items if item in self.selected]
        self.destroy()


class CurlDialog(simpledialog.Dialog):
    def body(self, master: tk.Frame) -> tk.Widget:
        ttk.Label(
            master,
            text="Collez ici la requête copiée avec « Copier en tant que cURL » (bash ou cmd) :",
        ).pack(anchor="w")
        self.text = scrolledtext.ScrolledText(master, width=80, height=14, wrap="word")
        self.text.pack(fill="both", expand=True, pady=6)
        try:
            clipboard = self.clipboard_get()
            if "curl" in clipboard.lower():
                self.text.insert("1.0", clipboard)
        except tk.TclError:
            pass
        return self.text

    def apply(self) -> None:
        self.result = self.text.get("1.0", "end")


class App(tk.Tk):
    def __init__(self, bridge: UiBridge) -> None:
        super().__init__()
        self.bridge = bridge
        self.runner: ScraperRunner | None = None
        self.title(f"UltimaScraper {VERSION}")
        self.geometry("980x700")
        self.minsize(820, 560)
        self._set_icon()
        self._setup_style()

        self.config_data: dict[str, Any] = store.ensure_config()
        self.gui_settings = store.load_gui_settings()

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        self.notebook = notebook
        self.run_tab = ttk.Frame(notebook, padding=10)
        self.accounts_tab = ttk.Frame(notebook, padding=10)
        self.settings_tab = ttk.Frame(notebook, padding=10)
        notebook.add(self.run_tab, text="  Téléchargement  ")
        notebook.add(self.accounts_tab, text="  Comptes  ")
        notebook.add(self.settings_tab, text="  Paramètres  ")

        self._build_run_tab()
        self._build_accounts_tab()
        self._build_settings_tab()
        self._build_status_bar()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(POLL_MS, self._poll_events)
        if not self._has_active_profile(self._selected_sites() or list(store.SITES)):
            self.notebook.select(self.accounts_tab)
            self.status_var.set(
                "Commencez par ajouter les identifiants de votre compte dans l'onglet Comptes."
            )

    # ------------------------------------------------------------ setup
    def _set_icon(self) -> None:
        icon = paths.resource_path(
            "ultima_scraper", "docs", "assets", "img", "icon.ico"
        )
        if sys.platform == "win32" and icon.exists():
            try:
                self.iconbitmap(default=str(icon))
            except tk.TclError:
                pass

    def _setup_style(self) -> None:
        style = ttk.Style(self)
        for theme in ("vista", "clam"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break
        bold = tkfont.nametofont("TkDefaultFont").copy()
        bold.configure(weight="bold")
        title = bold.copy()
        title.configure(
            size=(
                bold.cget("size") + 2
                if bold.cget("size") > 0
                else bold.cget("size") - 2
            )
        )
        self._fonts = (bold, title)  # keep references alive
        style.configure("Accent.TButton", font=bold, padding=(14, 6))
        style.configure("Title.TLabel", font=title)
        style.configure("Hint.TLabel", foreground="#666666")

    def _build_status_bar(self) -> None:
        bar = ttk.Frame(self, padding=(10, 4))
        bar.pack(fill="x", side="bottom")
        self.status_var = tk.StringVar(value=f"Dossier des données : {Path.cwd()}")
        ttk.Label(bar, textvariable=self.status_var).pack(
            side="left", fill="x", expand=True
        )
        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=160)
        self.progress.pack(side="right")

    # ------------------------------------------------------------ run tab
    def _build_run_tab(self) -> None:
        tab = self.run_tab
        options = ttk.Frame(tab)
        options.pack(fill="x")

        sites_box = ttk.LabelFrame(options, text="Sites", padding=8)
        sites_box.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.site_vars: dict[str, tk.BooleanVar] = {}
        for site in store.SITES:
            var = tk.BooleanVar(value=site in self.gui_settings["sites"])
            ttk.Checkbutton(sites_box, text=site, variable=var).pack(anchor="w")
            self.site_vars[site] = var

        models_box = ttk.LabelFrame(options, text="Créateurs", padding=8)
        models_box.grid(row=0, column=1, sticky="nsew", padx=(0, 8))
        self.models_var = tk.StringVar(value=self.gui_settings.get("models", "ask"))
        ttk.Radiobutton(
            models_box,
            text="Choisir dans la liste",
            value="ask",
            variable=self.models_var,
        ).pack(anchor="w")
        ttk.Radiobutton(
            models_box,
            text="Tous mes abonnements",
            value="all",
            variable=self.models_var,
        ).pack(anchor="w")

        content_box = ttk.LabelFrame(options, text="Contenus", padding=8)
        content_box.grid(row=0, column=2, sticky="nsew", padx=(0, 8))
        self.content_vars: dict[str, tk.BooleanVar] = {}
        for index, key in enumerate(store.CONTENT_TYPES):
            var = tk.BooleanVar(value=key in self.gui_settings["contents"])
            ttk.Checkbutton(content_box, text=CONTENT_LABELS[key], variable=var).grid(
                row=index % 3, column=index // 3, sticky="w", padx=(0, 10)
            )
            self.content_vars[key] = var

        media_box = ttk.LabelFrame(options, text="Médias", padding=8)
        media_box.grid(row=0, column=3, sticky="nsew")
        self.media_vars: dict[str, tk.BooleanVar] = {}
        for index, key in enumerate(store.MEDIA_TYPES):
            var = tk.BooleanVar(value=key in self.gui_settings["medias"])
            ttk.Checkbutton(media_box, text=MEDIA_LABELS[key], variable=var).grid(
                row=index % 2, column=index // 2, sticky="w", padx=(0, 10)
            )
            self.media_vars[key] = var

        actions = ttk.Frame(tab)
        actions.pack(fill="x", pady=10)
        self.start_button = ttk.Button(
            actions, text="Démarrer", style="Accent.TButton", command=self._start
        )
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(
            actions, text="Arrêter", command=self._stop, state="disabled"
        )
        self.stop_button.pack(side="left", padx=6)
        self.verbose_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            actions, text="Journal détaillé", variable=self.verbose_var
        ).pack(side="left", padx=12)
        ttk.Button(
            actions, text="Ouvrir les téléchargements", command=self._open_downloads
        ).pack(side="right")
        ttk.Button(actions, text="Enregistrer le journal", command=self._save_log).pack(
            side="right", padx=6
        )
        ttk.Button(actions, text="Effacer", command=self._clear_log).pack(side="right")

        self.log = scrolledtext.ScrolledText(
            tab,
            wrap="word",
            height=20,
            font=("Consolas" if sys.platform == "win32" else "TkFixedFont", 9),
        )
        self.log.pack(fill="both", expand=True)
        self.log.configure(state="disabled")
        self._append_log(
            "Bienvenue dans UltimaScraper.\n"
            "1) Onglet Comptes : ajoutez vos identifiants.\n"
            "2) Choisissez les sites / contenus ci-dessus puis cliquez sur Démarrer.\n\n"
        )

    def _selected_sites(self) -> list[str]:
        return [site for site, var in self.site_vars.items() if var.get()]

    def _has_active_profile(self, sites: list[str]) -> bool:
        for site in sites:
            for name in store.list_profiles(site):
                auth = store.load_profile(site, name)
                credential_keys = [
                    key
                    for key, _label, _multi in store.AUTH_FIELDS[site]
                    if key != "user_agent"
                ]
                if auth.get("active") and all(auth.get(key) for key in credential_keys):
                    return True
        return False

    def _start(self) -> None:
        if self.runner and self.runner.is_alive():
            return
        sites = self._selected_sites()
        contents = [key for key, var in self.content_vars.items() if var.get()]
        medias = [key for key, var in self.media_vars.items() if var.get()]
        if not sites:
            messagebox.showwarning(
                "UltimaScraper", "Sélectionnez au moins un site.", parent=self
            )
            return
        if not contents or not medias:
            messagebox.showwarning(
                "UltimaScraper",
                "Sélectionnez au moins un contenu et un type de média.",
                parent=self,
            )
            return
        if not self._has_active_profile(sites):
            if not messagebox.askyesno(
                "UltimaScraper",
                "Aucun compte actif avec des identifiants n'a été trouvé pour ce site.\n"
                "Dans l'onglet Comptes, remplissez les identifiants puis cochez "
                "« Actif » et cliquez sur Enregistrer.\n\nOuvrir l'onglet Comptes ?",
                parent=self,
            ):
                return
            self.notebook.select(self.accounts_tab)
            return

        self.gui_settings.update(
            {
                "sites": sites,
                "models": self.models_var.get(),
                "contents": contents,
                "medias": medias,
            }
        )
        store.save_gui_settings(self.gui_settings)

        options = RunOptions(
            sites=sites,
            all_models=self.models_var.get() == "all",
            contents=contents,
            medias=medias,
            verbose=self.verbose_var.get(),
        )
        self._append_log(f"\n===== Démarrage : {', '.join(sites)} =====\n")
        self.runner = ScraperRunner(self.bridge, options)
        self.runner.start()
        self._set_running(True)

    def _stop(self) -> None:
        if self.runner and self.runner.is_alive():
            self.status_var.set("Arrêt en cours…")
            self.runner.stop()

    def _set_running(self, running: bool) -> None:
        self.start_button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")
        if running:
            self.progress.start(12)
            self.status_var.set("Téléchargement en cours…")
        else:
            self.progress.stop()

    def _open_downloads(self) -> None:
        config = store.read_json(store.config_path())
        site = (self._selected_sites() or ["OnlyFans"])[0]
        directories = store.site_settings(config, site).get("download_directories") or [
            "__user_data__/sites"
        ]
        paths.open_in_file_manager(Path(directories[0]).expanduser().resolve())

    def _clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _save_log(self) -> None:
        target = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".txt",
            initialfile="ultimascraper-log.txt",
            filetypes=[("Texte", "*.txt")],
        )
        if target:
            Path(target).write_text(self.log.get("1.0", "end"), encoding="utf-8")

    def _append_log(self, text: str) -> None:
        """Append text, honouring carriage returns so tqdm bars update in place."""
        self.log.configure(state="normal")
        parts = text.split("\r")
        for index, part in enumerate(parts):
            if index > 0:
                self.log.delete("end-1c linestart", "end-1c")
            if part:
                self.log.insert("end", part)
        # Keep the widget responsive on very long sessions.
        line_count = int(self.log.index("end-1c").split(".")[0])
        if line_count > 5000:
            self.log.delete("1.0", f"{line_count - 4000}.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    # ------------------------------------------------------- accounts tab
    def _build_accounts_tab(self) -> None:
        tab = self.accounts_tab
        top = ttk.Frame(tab)
        top.pack(fill="x")
        ttk.Label(top, text="Site :").pack(side="left")
        self.account_site_var = tk.StringVar(value=store.SITES[0])
        site_combo = ttk.Combobox(
            top,
            textvariable=self.account_site_var,
            values=store.SITES,
            state="readonly",
            width=12,
        )
        site_combo.pack(side="left", padx=6)
        site_combo.bind("<<ComboboxSelected>>", lambda _e: self._reload_accounts())

        body = ttk.Frame(tab)
        body.pack(fill="both", expand=True, pady=10)

        left = ttk.Frame(body)
        left.pack(side="left", fill="y")
        ttk.Label(left, text="Profils").pack(anchor="w")
        self.profile_list = tk.Listbox(left, width=24, height=14, exportselection=False)
        self.profile_list.pack(fill="y", expand=True, pady=4)
        self.profile_list.bind(
            "<<ListboxSelect>>", lambda _e: self._load_selected_profile()
        )
        buttons = ttk.Frame(left)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Nouveau", command=self._new_profile).pack(side="left")
        ttk.Button(buttons, text="Supprimer", command=self._delete_profile).pack(
            side="left", padx=4
        )

        self.account_form = ttk.Frame(body, padding=(16, 0, 0, 0))
        self.account_form.pack(side="left", fill="both", expand=True)
        self.account_help = ttk.Label(tab, style="Hint.TLabel", justify="left")
        self.account_help.pack(fill="x", anchor="w")

        self.current_profile: str | None = None
        self.account_widgets: dict[str, Any] = {}
        self._reload_accounts()

    def _reload_accounts(self, select: str | None = None) -> None:
        site = self.account_site_var.get()
        self.account_help.configure(text=AUTH_HELP[site])
        profiles = store.list_profiles(site)
        self.profile_list.delete(0, "end")
        for name in profiles:
            self.profile_list.insert("end", name)
        target = select if select in profiles else (profiles[0] if profiles else None)
        if target:
            index = profiles.index(target)
            self.profile_list.selection_clear(0, "end")
            self.profile_list.selection_set(index)
        self.current_profile = target
        self._build_account_form()

    def _build_account_form(self) -> None:
        for child in self.account_form.winfo_children():
            child.destroy()
        self.account_widgets = {}
        site = self.account_site_var.get()
        form = self.account_form
        if not self.current_profile:
            ttk.Label(
                form, text="Aucun profil. Cliquez sur « Nouveau » pour en créer un."
            ).pack(anchor="w")
            return
        auth = store.load_profile(site, self.current_profile)
        ttk.Label(
            form,
            text=f"{site} — profil « {self.current_profile} »",
            style="Title.TLabel",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        active = tk.BooleanVar(value=bool(auth.get("active")))
        ttk.Checkbutton(
            form, text="Actif (utilisé lors du téléchargement)", variable=active
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 6))
        self.account_widgets["active"] = active
        row = 2
        for key, label, multiline in store.AUTH_FIELDS[site]:
            ttk.Label(form, text=label).grid(
                row=row, column=0, sticky="nw", pady=3, padx=(0, 8)
            )
            if multiline:
                widget: Any = tk.Text(form, height=4, wrap="char", width=60)
                widget.insert("1.0", auth.get(key) or "")
            else:
                widget = ttk.Entry(form, width=60)
                widget.insert(0, auth.get(key) or "")
            widget.grid(row=row, column=1, sticky="ew", pady=3)
            self.account_widgets[key] = widget
            row += 1
        form.columnconfigure(1, weight=1)
        actions = ttk.Frame(form)
        actions.grid(row=row, column=1, sticky="w", pady=10)
        ttk.Button(actions, text="Coller depuis cURL", command=self._paste_curl).pack(
            side="left"
        )
        ttk.Button(
            actions,
            text="Enregistrer",
            style="Accent.TButton",
            command=self._save_profile,
        ).pack(side="left", padx=8)

    def _load_selected_profile(self) -> None:
        selection = self.profile_list.curselection()
        if selection:
            self.current_profile = self.profile_list.get(selection[0])
            self._build_account_form()

    def _form_values(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for key, widget in self.account_widgets.items():
            if key == "active":
                values[key] = bool(widget.get())
            elif isinstance(widget, tk.Text):
                values[key] = widget.get("1.0", "end").strip()
            else:
                values[key] = widget.get().strip()
        return values

    def _set_form_value(self, key: str, value: str) -> None:
        widget = self.account_widgets.get(key)
        if widget is None:
            return
        if isinstance(widget, tk.Text):
            widget.delete("1.0", "end")
            widget.insert("1.0", value)
        else:
            widget.delete(0, "end")
            widget.insert(0, value)

    def _paste_curl(self) -> None:
        dialog = CurlDialog(self, title="Coller depuis cURL")
        if not dialog.result:
            return
        site = self.account_site_var.get()
        values = store.auth_values_from_headers(site, store.parse_curl(dialog.result))
        if not values:
            messagebox.showerror(
                "UltimaScraper",
                "Aucun identifiant trouvé dans le texte collé.",
                parent=self,
            )
            return
        for key, value in values.items():
            self._set_form_value(key, value)
        self.account_widgets["active"].set(True)
        found = ", ".join(
            label for key, label, _m in store.AUTH_FIELDS[site] if key in values
        )
        missing = [
            label for key, label, _m in store.AUTH_FIELDS[site] if key not in values
        ]
        message = f"Champs remplis : {found}."
        if missing:
            message += f"\nIntrouvables : {', '.join(missing)} — copiez une requête vers l'API du site."
        message += "\nN'oubliez pas de cliquer sur Enregistrer."
        messagebox.showinfo("UltimaScraper", message, parent=self)

    def _save_profile(self) -> None:
        if not self.current_profile:
            return
        site = self.account_site_var.get()
        store.save_profile(site, self.current_profile, self._form_values())
        self.status_var.set(f"Profil {site}/{self.current_profile} enregistré.")

    def _new_profile(self) -> None:
        site = self.account_site_var.get()
        existing = store.list_profiles(site)
        suggestion = (
            "default" if "default" not in existing else f"compte{len(existing) + 1}"
        )
        name = simpledialog.askstring(
            "Nouveau profil",
            "Nom du profil (lettres, chiffres, - _ .) :",
            initialvalue=suggestion,
            parent=self,
        )
        if not name:
            return
        name = name.strip()
        if not store.valid_profile_name(name):
            messagebox.showerror(
                "UltimaScraper", "Nom de profil invalide.", parent=self
            )
            return
        if name in existing:
            messagebox.showerror("UltimaScraper", "Ce profil existe déjà.", parent=self)
            return
        store.save_profile(site, name, {"active": True})
        self._reload_accounts(select=name)

    def _delete_profile(self) -> None:
        if not self.current_profile:
            return
        site = self.account_site_var.get()
        if messagebox.askyesno(
            "UltimaScraper",
            f"Supprimer le profil « {self.current_profile} » ({site}) ?",
            parent=self,
        ):
            store.delete_profile(site, self.current_profile)
            self._reload_accounts()

    # ------------------------------------------------------- settings tab
    def _build_settings_tab(self) -> None:
        tab = self.settings_tab
        site_settings = store.site_settings(self.config_data, "onlyfans")
        global_settings = self.config_data.get("settings", {})
        self.setting_vars: dict[str, tk.Variable] = {}

        def add_row(row: int, label: str, widget: tk.Widget, hint: str = "") -> None:
            ttk.Label(tab, text=label).grid(
                row=row, column=0, sticky="w", pady=4, padx=(0, 10)
            )
            widget.grid(row=row, column=1, sticky="ew", pady=4)
            if hint:
                ttk.Label(tab, text=hint, style="Hint.TLabel").grid(
                    row=row, column=2, sticky="w", padx=8
                )

        directories = site_settings.get("download_directories") or [
            "__user_data__/sites"
        ]
        download_var = tk.StringVar(value=directories[0])
        self.setting_vars["download_directory"] = download_var
        download_frame = ttk.Frame(tab)
        ttk.Entry(download_frame, textvariable=download_var).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(
            download_frame, text="Parcourir…", command=self._browse_download_directory
        ).pack(side="left", padx=(6, 0))
        add_row(0, "Dossier de téléchargement", download_frame)

        quality_var = tk.StringVar(
            value=str(site_settings.get("video_quality", "source"))
        )
        self.setting_vars["video_quality"] = quality_var
        add_row(
            1,
            "Qualité vidéo",
            ttk.Combobox(
                tab,
                textvariable=quality_var,
                values=["source", "720", "240"],
                state="readonly",
                width=12,
            ),
        )

        directory_format_var = tk.StringVar(
            value=site_settings.get("file_directory_format", "")
        )
        self.setting_vars["file_directory_format"] = directory_format_var
        add_row(
            2,
            "Organisation des dossiers",
            ttk.Entry(tab, textvariable=directory_format_var),
            "{site_name} {model_username} {api_type} {value} {media_type}",
        )

        filename_format_var = tk.StringVar(
            value=site_settings.get("filename_format", "")
        )
        self.setting_vars["filename_format"] = filename_format_var
        add_row(
            3,
            "Nom des fichiers",
            ttk.Entry(tab, textvariable=filename_format_var),
            "{filename} {media_id} {post_id} {date} {ext}",
        )

        date_format_var = tk.StringVar(
            value=site_settings.get("date_format", "%d-%m-%Y")
        )
        self.setting_vars["date_format"] = date_format_var
        add_row(
            4,
            "Format de date",
            ttk.Entry(tab, textvariable=date_format_var, width=16),
            "%d-%m-%Y",
        )

        ignore_var = tk.StringVar(
            value=IGNORE_LABELS.get(site_settings.get("ignore_type", "") or "", "Aucun")
        )
        self.setting_vars["ignore_type"] = ignore_var
        add_row(
            5,
            "Ignorer les abonnements",
            ttk.Combobox(
                tab,
                textvariable=ignore_var,
                values=list(IGNORE_LABELS.values()),
                state="readonly",
                width=12,
            ),
        )

        threads_var = tk.StringVar(value=str(global_settings.get("max_threads", -1)))
        self.setting_vars["max_threads"] = threads_var
        add_row(
            6,
            "Threads max.",
            ttk.Spinbox(tab, from_=-1, to=64, textvariable=threads_var, width=8),
            "-1 = automatique",
        )

        space_var = tk.StringVar(value=str(global_settings.get("min_drive_space", 0)))
        self.setting_vars["min_drive_space"] = space_var
        add_row(
            7,
            "Espace disque min. (Go)",
            ttk.Entry(tab, textvariable=space_var, width=10),
        )

        jobs = site_settings.get("jobs", {}).get("scrape", {})
        jobs_frame = ttk.Frame(tab)
        for key, label in (
            ("subscriptions", "Abonnements"),
            ("messages", "Messages"),
            ("paid_contents", "Contenus achetés"),
        ):
            var = tk.BooleanVar(value=bool(jobs.get(key, True)))
            self.setting_vars[f"job_{key}"] = var
            ttk.Checkbutton(jobs_frame, text=label, variable=var).pack(
                side="left", padx=(0, 12)
            )
        add_row(8, "Récupérer", jobs_frame)

        overwrite_var = tk.BooleanVar(
            value=bool(site_settings.get("overwrite_files", False))
        )
        self.setting_vars["overwrite_files"] = overwrite_var
        add_row(
            9,
            "Fichiers existants",
            ttk.Checkbutton(
                tab, text="Re-télécharger / écraser", variable=overwrite_var
            ),
        )

        ttk.Label(tab, text="Proxys (un par ligne)").grid(
            row=10, column=0, sticky="nw", pady=4
        )
        self.proxies_text = tk.Text(tab, height=4, width=50)
        self.proxies_text.insert(
            "1.0", "\n".join(global_settings.get("proxies", []) or [])
        )
        self.proxies_text.grid(row=10, column=1, sticky="ew", pady=4)

        rules_var = tk.StringVar(
            value=dynamic_rules.resolve(global_settings.get("dynamic_rules_link"))
        )
        self.setting_vars["dynamic_rules_link"] = rules_var
        add_row(
            11,
            "Règles de signature OnlyFans",
            ttk.Entry(tab, textvariable=rules_var),
            "URL du fichier dynamic rules",
        )

        tab.columnconfigure(1, weight=1)
        ttk.Label(
            tab,
            text="Ces réglages s'appliquent à OnlyFans et Fansly. Pour les options avancées, éditez config.json.",
            style="Hint.TLabel",
        ).grid(row=12, column=0, columnspan=3, sticky="w", pady=(12, 4))
        buttons = ttk.Frame(tab)
        buttons.grid(row=13, column=0, columnspan=3, sticky="w", pady=6)
        ttk.Button(
            buttons,
            text="Enregistrer",
            style="Accent.TButton",
            command=self._save_settings,
        ).pack(side="left")
        ttk.Button(
            buttons,
            text="Ouvrir config.json",
            command=lambda: paths.open_in_file_manager(store.config_path()),
        ).pack(side="left", padx=8)
        ttk.Button(
            buttons,
            text="Ouvrir le dossier des données",
            command=lambda: paths.open_in_file_manager(Path.cwd()),
        ).pack(side="left")

    def _browse_download_directory(self) -> None:
        directory = filedialog.askdirectory(
            parent=self, title="Dossier de téléchargement"
        )
        if directory:
            self.setting_vars["download_directory"].set(directory)

    def _save_settings(self) -> None:
        values = {key: var.get() for key, var in self.setting_vars.items()}
        try:
            max_threads = int(values["max_threads"])
            min_drive_space = float(str(values["min_drive_space"]).replace(",", "."))
        except ValueError:
            messagebox.showerror(
                "UltimaScraper",
                "Threads / espace disque : valeur numérique attendue.",
                parent=self,
            )
            return
        config = store.read_json(store.config_path()) or store.ensure_config()
        download_directory = (
            str(values["download_directory"]).strip() or "__user_data__/sites"
        )
        download_directory = download_directory.replace("\\", "/")
        for site in store.SITES:
            settings = store.site_settings(config, site)
            settings["download_directories"] = [download_directory]
            settings["metadata_directories"] = [download_directory]
            settings["video_quality"] = values["video_quality"]
            settings["file_directory_format"] = values["file_directory_format"]
            settings["filename_format"] = values["filename_format"]
            settings["date_format"] = values["date_format"]
            settings["ignore_type"] = IGNORE_VALUES.get(values["ignore_type"], "")
            settings["overwrite_files"] = bool(values["overwrite_files"])
            scrape = settings.setdefault("jobs", {}).setdefault("scrape", {})
            for key in ("subscriptions", "messages", "paid_contents"):
                scrape[key] = bool(values[f"job_{key}"])
        global_settings = config.setdefault("settings", {})
        global_settings["max_threads"] = max_threads
        global_settings["min_drive_space"] = min_drive_space
        global_settings["dynamic_rules_link"] = dynamic_rules.resolve(
            str(values["dynamic_rules_link"])
        )
        global_settings["proxies"] = [
            line.strip()
            for line in self.proxies_text.get("1.0", "end").splitlines()
            if line.strip()
        ]
        store.write_json(store.config_path(), config)
        self.config_data = config
        self.status_var.set("Paramètres enregistrés.")

    # ------------------------------------------------------- event pump
    def _poll_events(self) -> None:
        try:
            for _ in range(500):
                kind, payload = self.bridge.events.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                elif kind == "status":
                    self.status_var.set(payload)
                elif kind == "request":
                    self._answer_request(*payload)
                elif kind == "finished":
                    self._set_running(False)
                    self.status_var.set("Terminé." if payload else "Arrêté.")
        except queue.Empty:
            pass
        self.after(POLL_MS, self._poll_events)

    def _answer_request(
        self, kind: str, data: dict[str, Any], reply: queue.Queue[Any]
    ) -> None:
        answer: Any = None
        try:
            if kind == "choice":
                self.deiconify()
                dialog = ChoiceDialog(self, data["title"], data["items"])
                self.wait_window(dialog)
                answer = dialog.result
            elif kind == "input":
                answer = simpledialog.askstring(
                    "UltimaScraper", data["prompt"], parent=self
                )
        finally:
            reply.put(answer)

    def _on_close(self) -> None:
        if self.runner and self.runner.is_alive():
            if not messagebox.askyesno(
                "UltimaScraper",
                "Un téléchargement est en cours. Quitter quand même ?",
                parent=self,
            ):
                return
            self.runner.stop()
        self.destroy()


def main() -> None:
    import multiprocessing

    multiprocessing.freeze_support()
    paths.prepare_data_directory()

    bridge = UiBridge()
    install_patches(bridge)
    if "--self-test" in sys.argv:
        from ultima_scraper.gui.selftest import run_self_test

        sys.exit(run_self_test())
    sys.stdout = BridgeStream(bridge, sys.__stdout__)  # type: ignore[assignment]
    sys.stderr = BridgeStream(bridge, sys.__stderr__)  # type: ignore[assignment]

    from ultima_scraper_collection.managers.filesystem_manager import FilesystemManager

    from tests import main_test

    FilesystemManager().check()
    main_test.check_profiles(Path("__settings__"), Path("__user_data__", "profiles"))

    app = App(bridge)
    bridge.main_thread_input = lambda prompt: simpledialog.askstring(
        "UltimaScraper", prompt, parent=app
    )
    app.mainloop()
    # Downloads run on a daemon thread; make sure nothing keeps the process alive.
    import os

    os._exit(0)


if __name__ == "__main__":
    main()
