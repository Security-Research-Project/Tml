import logging
import os
import subprocess
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from . import config, installer, settings
from .browsers import ORDER, REGISTRY

log = logging.getLogger("tml.gui")

SANDBOX_MODES = ["apparmor", "none"]
SANDBOX_LABELS = ["AppArmor only", "None"]

_CARD_GAP = 28
_BADGE_SIZE = 40

_ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "icons")


def _install_css():
    provider = Gtk.CssProvider()
    css_path = os.path.join(os.path.dirname(__file__), "data", "style.css")
    try:
        with open(css_path, "rb") as f:
            provider.load_from_data(f.read())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
    except FileNotFoundError:
        log.info("No custom CSS found at %s; skipping", css_path)
    except Exception:
        log.exception("Failed to install CSS")


def browser_badge(key):
  
    svg_path = os.path.join(_ICON_DIR, f"badge-{key}.svg")
    if not os.path.isfile(svg_path):
        log.warning("Missing badge asset for %s at %s; showing no icon", key, svg_path)
        return None
    image = Gtk.Image.new_from_file(svg_path)
    image.set_pixel_size(_BADGE_SIZE)
    return image


def format_size(num_bytes):
    if not num_bytes:
        return "unknown size"
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def sandbox_short_label(browser):
    from . import sandbox as sandbox_mod
    mode = settings.load().get("sandbox_mode", "apparmor")
    install_dir = os.path.join(config.INSTALL_ROOT, browser.key)
    try:
        exe = installer.find_launch_script(browser, install_dir)
    except Exception:
        return "unknown"
    _argv, description = sandbox_mod.build_launch_command(browser, exe, mode=mode)
    return "AppArmor" if description.startswith("AppArmor") else "unsandboxed"


def sandbox_mode_label():
    mode = settings.load().get("sandbox_mode", "apparmor")
    return SANDBOX_LABELS[SANDBOX_MODES.index(mode)] if mode in SANDBOX_MODES else mode


def card_for_row(row):
    wrapper = Gtk.Box()
    wrapper.add_css_class("card")
    wrapper.append(row)
    return wrapper


def _open_folder(path):
    os.makedirs(path, exist_ok=True)
    try:
        subprocess.Popen(["xdg-open", path])
    except FileNotFoundError:
        log.warning("xdg-open not found; cannot open %s", path)


def show_about(parent):
    about = Adw.AboutWindow(
        transient_for=parent,
        modal=True,
        application_name=config.APP_NAME,
        application_icon=config.APP_ID,
        version=config.VERSION,
        developer_name="Tml contributors",
        comments="Downloads, GPG-verifies, and installs Tor Browser, "
                 "Mullvad Browser, and LibreWolf from their official "
                 "sources.",
        license_type=Gtk.License.MIT_X11,
    )
    about.present()


class SettingsWindow(Adw.PreferencesWindow):
    def __init__(self, parent, on_sandbox_changed=None):
        super().__init__(transient_for=parent, modal=True, title="Preferences")
        self.set_default_size(440, 320)
        self.current = settings.load()
        self.on_sandbox_changed = on_sandbox_changed

        page = Adw.PreferencesPage()
        self.add(page)

        sandbox_group = Adw.PreferencesGroup(
            title="Sandbox",
            description="Confines each browser at launch. Changing this "
                         "updates every already-installed browser's menu "
                         "entry immediately.",
        )
        page.add(sandbox_group)

        self.sandbox_row = Adw.SwitchRow(
            title="Use AppArmor",
            subtitle="Falls back to unsandboxed if no profile is active",
            active=self.current.get("sandbox_mode", "apparmor") == "apparmor",
        )
        self.sandbox_row.connect("notify::active", self._on_sandbox_change)
        sandbox_group.add(self.sandbox_row)

        data_group = Adw.PreferencesGroup(title="Data")
        page.add(data_group)

        open_row = Adw.ActionRow(
            title="Open data folder",
            subtitle=config.DATA_DIR,
            activatable=True,
        )
        open_row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        open_row.connect("activated", lambda _r: _open_folder(config.DATA_DIR))
        data_group.add(open_row)

    def _on_sandbox_change(self, *_a):
        old_mode = self.current.get("sandbox_mode", "apparmor")
        new_mode = "apparmor" if self.sandbox_row.get_active() else "none"
        self.current["sandbox_mode"] = new_mode
        settings.save(self.current)
        if new_mode == old_mode:
            return

        if new_mode == "apparmor":
            def worker():
                # _finish_sandbox_change must always run: it regenerates
                # every installed browser's .desktop entry and refreshes
                # each row's visible sandbox label.
                try:
                    from . import apparmor
                    if apparmor.apparmor_available():
                        for key in ORDER:
                            b = REGISTRY[key]
                            try:
                                if installer.install_state(b) == installer.STATE_TML:
                                    apparmor.install_profile(b)
                            except Exception as e:
                                log.warning("Could not load AppArmor profile for %s: %s", key, e)
                except Exception:
                    log.exception("AppArmor availability/profile-install step failed")
                finally:
                    GLib.idle_add(self._finish_sandbox_change)

            threading.Thread(target=worker, daemon=True).start()
        else:
            self._finish_sandbox_change()

    def _finish_sandbox_change(self):
        from . import desktop_entry
        desktop_entry.regenerate_all_installed()
        if self.on_sandbox_changed:
            self.on_sandbox_changed()
        return False


class BrowserRow(Adw.ActionRow):
    def __init__(self, app, browser):
        super().__init__(title=browser.display_name)
        self.app = app
        self.browser = browser
        self.update_available_version = None

        badge = browser_badge(browser.key)
        if badge is not None:
            self.add_prefix(badge)

        self.action_stack = Gtk.Stack(valign=Gtk.Align.CENTER)
        self.action_stack.add_named(Gtk.Box(), "none")

        self.spinner = Gtk.Spinner()
        self.action_stack.add_named(self.spinner, "spinner")

        self.progress_bar = Gtk.ProgressBar(valign=Gtk.Align.CENTER)
        self.action_stack.add_named(self.progress_bar, "progress")

        self.install_btn = Gtk.Button(label="Install", valign=Gtk.Align.CENTER, halign=Gtk.Align.END)
        self.install_btn.add_css_class("suggested-action")
        self.install_btn.connect("clicked", lambda _b: self.install())
        self.action_stack.add_named(self.install_btn, "install")

        self.menu_btn = Gtk.MenuButton(valign=Gtk.Align.CENTER, halign=Gtk.Align.END)
        self.menu_btn.set_icon_name("view-more-symbolic")
        self.menu_btn.add_css_class("flat")
        self.menu_btn.set_popover(self._build_popover())
        self.action_stack.add_named(self.menu_btn, "menu")

        self.add_suffix(self.action_stack)

        self.refresh_state()

    def _build_popover(self):
        menu = Gio.Menu()
        menu.append("Open install folder", "row.open-folder")
        menu.append("Verify integrity", "row.verify")
        menu.append("Reinstall", "row.reinstall")
        menu.append("Uninstall", "row.uninstall")

        actions = Gio.SimpleActionGroup()
        for name, handler in (
            ("open-folder", lambda *_a: self.open_folder()),
            ("verify", lambda *_a: self.verify_integrity_action()),
            ("reinstall", lambda *_a: self.install()),
            ("uninstall", lambda *_a: self.uninstall_action()),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", handler)
            actions.add_action(action)
        self.insert_action_group("row", actions)

        return Gtk.PopoverMenu.new_from_model(menu)

    def refresh_state(self):
        # Window construction runs synchronously and before any window
        # exists, so a read failure here must degrade this one row
        # rather than abort the whole app.
        try:
            self._refresh_state_unguarded()
        except Exception as e:
            log.exception("Could not read install state for %s", self.browser.key)
            self.remove_css_class("error")
            self.spinner.stop()
            self.set_subtitle(f"Could not read install status ({e})")
            self.action_stack.set_visible_child_name("install")
            self.install_btn.set_label("Retry")
            self.install_btn.set_sensitive(True)

    def _refresh_state_unguarded(self):
        installed = installer.install_state(self.browser) == installer.STATE_TML
        self.remove_css_class("error")
        self.spinner.stop()
        self.update_available_version = None

        if installed:
            meta = installer.get_metadata(self.browser) or {}
            version = meta.get("version", "?")
            size = format_size(meta.get("size_bytes"))
            sandbox_label = sandbox_short_label(self.browser)
            self.set_subtitle(f"v{version} \u00b7 {size} \u00b7 {sandbox_label}")
            self.action_stack.set_visible_child_name("menu")
        else:
            self.set_subtitle("Not installed \u00b7 GPG signature required")
            self.install_btn.set_label("Install")
            self.action_stack.set_visible_child_name("install")

        self.install_btn.set_sensitive(True)

    def fetch_update_info(self):
        """Network only; safe to call off the main thread."""
        if installer.install_state(self.browser) != installer.STATE_TML:
            return None
        try:
            return installer.check_for_update(self.browser)
        except Exception as e:
            log.info("Update check failed for %s: %s", self.browser.key, e)
            return None

    def apply_update_available(self, version):
        """Widget mutation; main thread only."""
        self.update_available_version = version
        self.install_btn.set_label(f"Update to v{version}")
        self.action_stack.set_visible_child_name("install")

    def check_for_update(self):
        newer = self.fetch_update_info()
        if newer:
            self.apply_update_available(newer)

    def install(self):
        self.install_btn.set_sensitive(False)
        self.action_stack.set_visible_child_name("spinner")
        self.spinner.start()

        def worker():
            def progress_cb(stage, pct):
                GLib.idle_add(self._on_progress, stage, pct)
            try:
                installer.install(self.browser, progress=progress_cb)
                GLib.idle_add(self._on_install_done, None)
            except Exception as e:
                log.exception("install failed")
                GLib.idle_add(self._on_install_done, e)

        threading.Thread(target=worker, daemon=True).start()

    def _on_progress(self, stage, pct):
        if pct is not None:
            self.progress_bar.set_fraction(min(pct, 100) / 100)
            self.action_stack.set_visible_child_name("progress")
            self.set_subtitle(f"{stage} {pct}%")
        else:
            self.action_stack.set_visible_child_name("spinner")
            self.set_subtitle(stage)
        return False

    def _on_install_done(self, error):
        if error:
            self.add_css_class("error")
            self.set_subtitle("Install failed")
            self.app.show_error(f"Could not install {self.browser.display_name}", str(error))
        else:
            self.app.notify(
                f"{self.browser.display_name} installed",
                f"{self.browser.display_name} is now in your applications menu.",
            )
        self.refresh_state()
        self.app.refresh_footer()
        return False

    def open_folder(self):
        _open_folder(os.path.join(config.INSTALL_ROOT, self.browser.key))

    def verify_integrity_action(self):
        ok, detail = installer.verify_integrity(self.browser)
        if ok:
            self.app.toast("Integrity OK")
        else:
            self.app.show_error("Integrity check - difference found", detail)

    def uninstall_action(self):
        def on_response(_dialog, response):
            if response != "uninstall":
                return
            try:
                installer.uninstall(self.browser)
            except Exception as e:
                self.app.show_error(f"Could not uninstall {self.browser.display_name}", str(e))
            self.refresh_state()

        install_dir = os.path.join(config.INSTALL_ROOT, self.browser.key)
        has_profile_inside = installer.find_profile_dir(install_dir) is not None
        if has_profile_inside:
            profile_note = ("Your browser profile and bookmarks, which this "
                             "browser stores inside its own install folder, "
                             "are deleted too. ")
        else:
            profile_note = ("This browser doesn't store its profile inside "
                             "its install folder, so your bookmarks and "
                             "settings elsewhere on your system aren't "
                             "touched. ")

        dialog = Adw.MessageDialog(
            transient_for=self.app.window,
            heading=f"Uninstall {self.browser.display_name}?",
            body="This removes the installed browser, its application-menu "
                 f"entry, and its install record. {profile_note}"
                 "This cannot be undone.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("uninstall", "Uninstall")
        dialog.set_response_appearance("uninstall", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", on_response)
        dialog.present()


class TmlWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=config.APP_NAME)
        self.app = app
        self.set_default_size(680, 800)
        self.set_size_request(460, 560)

        toolbar_view = Adw.ToolbarView()
        self.set_content(toolbar_view)

        header = Adw.HeaderBar()
        title = Adw.WindowTitle(title=config.APP_NAME, subtitle="Browser installer")
        header.set_title_widget(title)

        primary_menu = Gio.Menu()
        primary_menu.append("Check for updates", "win.check-updates")
        primary_menu.append("Preferences", "win.preferences")
        primary_menu.append("About", "win.about")

        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic")
        menu_btn.set_tooltip_text("Main Menu")
        menu_btn.set_menu_model(primary_menu)
        header.pack_end(menu_btn)

        check_updates_action = Gio.SimpleAction.new("check-updates", None)
        check_updates_action.connect("activate", lambda *_a: self.check_for_updates())
        self.add_action(check_updates_action)

        preferences_action = Gio.SimpleAction.new("preferences", None)
        preferences_action.connect(
            "activate",
            lambda *_a: SettingsWindow(self, on_sandbox_changed=self.refresh_all).present(),
        )
        self.add_action(preferences_action)

        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", lambda *_a: show_about(self))
        self.add_action(about_action)

        toolbar_view.add_top_bar(header)

        self.toast_overlay = Adw.ToastOverlay()
        toolbar_view.set_content(self.toast_overlay)

        scroller = Gtk.ScrolledWindow(vexpand=True)
        clamp = Adw.Clamp(maximum_size=680, tightening_threshold=460)
        clamp.set_margin_top(24)
        clamp.set_margin_bottom(24)
        clamp.set_margin_start(16)
        clamp.set_margin_end(16)
        scroller.set_child(clamp)
        self.toast_overlay.set_child(scroller)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        clamp.set_child(outer)

        section_label = Gtk.Label(label="Browsers", xalign=0)
        section_label.add_css_class("title-4")
        section_label.set_margin_bottom(4)
        outer.append(section_label)

        cards = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=_CARD_GAP)
        outer.append(cards)

        self.rows = []
        for key in ORDER:
            row = BrowserRow(self.app, REGISTRY[key])
            self.rows.append(row)
            cards.append(card_for_row(row))

        self.footer = Gtk.Label(xalign=0, wrap=True)
        self.footer.add_css_class("dim-label")
        self.footer.add_css_class("body")
        self.footer.set_margin_top(20)
        outer.append(self.footer)

        disclaimer = Gtk.Label(
    label=(
        "Tml does not detect whether you already have any of these browsers "
        "installed on your system. Tml is an independent project and is not "
        "affiliated with, endorsed by, or sponsored by the Tor Project, Mullvad, "
        "or LibreWolf. “Tor”, “Mullvad”, and “LibreWolf” are trademarks of their "
        "respective owners."
    ),
    xalign=0,
    wrap=True,
)
        disclaimer.add_css_class("dim-label")
        disclaimer.add_css_class("body")
        disclaimer.set_margin_top(8)
        outer.append(disclaimer)

        self.refresh_footer()

    def refresh_footer(self):
        self.footer.set_label(f"Sandbox: {sandbox_mode_label()} \u00b7 change it in the menu")

    def refresh_all(self):
        for row in self.rows:
            row.refresh_state()
        self.refresh_footer()

    def check_for_updates(self):
        self.app.toast("Checking for updates...")

        def worker():
            results = [(row, row.fetch_update_info()) for row in self.rows]
            GLib.idle_add(self._apply_update_check_results, results)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_update_check_results(self, results):
        found_any = False
        for row, newer in results:
            if newer:
                row.apply_update_available(newer)
                found_any = True
        self.app.toast("Update(s) available." if found_any else "Everything is up to date.")
        return False


class TmlApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=config.APP_ID)
        self.window = None

    def do_activate(self):
        if not self.window:
            try:
                _install_css()
            except Exception:
             
                log.exception(
                    "Could not install custom CSS; continuing to launch "
                    "with default styling"
                )
            try:
                self.window = TmlWindow(self)
            except Exception as e:
            
                log.exception("Could not build the main window")
                error = Adw.MessageDialog(
                    heading="Tml could not start",
                    body=f"{e}\n\nSee {config.LOG_FILE} for details.",
                )
                error.add_response("ok", "OK")
                error.present()
                return
        self.window.present()

    def show_error(self, title, detail):
        dialog = Adw.MessageDialog(
            transient_for=self.window,
            heading=title,
            body=detail,
        )
        dialog.add_response("ok", "OK")
        dialog.present()

    def toast(self, text):
        self.window.toast_overlay.add_toast(Adw.Toast(title=text, timeout=3))

    def refresh_footer(self):
        self.window.refresh_footer()

    def notify(self, title, body):
        try:
            note = Gio.Notification.new(title)
            note.set_body(body)
            self.send_notification(f"tml-{title}", note)
        except Exception as e:
            log.info("Desktop notifications unavailable, skipping (%s)", e)


def main():
    config.ensure_dirs()
    logging.basicConfig(
        level=logging.INFO,
        filename=config.LOG_FILE,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = TmlApp()
    return app.run()
