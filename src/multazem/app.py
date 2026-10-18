# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""The GTK application object (:class:`MultazemApp`) and the command-line entry point."""

from __future__ import annotations

import sys
import threading
from pathlib import Path

from . import winsupport

# On Windows the GTK runtime has to be made findable before gi is imported (this does nothing elsewhere).
winsupport.prepare_runtime()

try:
    import gi

    # The versions must be selected before anything is imported from gi.repository, which is why the
    # imports below are not at the top of the file.
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")

    from gi.repository import Adw, Gdk, Gio, GLib, Gtk
except (ImportError, ValueError) as error:
    winsupport.report_missing_toolkit(error)
    raise

from . import __version__  # noqa: E402
from .i18n import set_language, tr  # noqa: E402
from .logs import configure_logging  # noqa: E402
from .services.background_service import prepare_service  # noqa: E402
from .services.headless import run_headless  # noqa: E402
from .services.legacy_config import migrate_legacy_config  # noqa: E402
from .services.region_catalog import RegionCatalog  # noqa: E402
from .services.scheduler import NotificationScheduler  # noqa: E402
from .services.settings import Settings  # noqa: E402
from .services.single_instance import SingleInstance  # noqa: E402
from .ui.language import apply_ui_language  # noqa: E402
from .ui.window import MultazemWindow  # noqa: E402

APP_ID = "com.github.multazem"
ICONS_DIR = Path(__file__).resolve().parent / "icons"


class MultazemApp(Adw.Application):
    """The Multazem application: owns the settings, the region catalog, the scheduler and the window.

    Creating it migrates the configuration written under the former name, loads the settings,
    applies the saved language and prepares the (not yet started) notification scheduler. The
    window is created lazily on first activation, so a second launch just presents the existing one.

    Args:
        single_instance: The guard that lets a second launch on Windows activate this process; ``None`` when
            there is nothing to listen to (Linux, where the session bus does that, and the tests).
    """

    def __init__(self, single_instance: SingleInstance | None = None) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        migrate_legacy_config()
        self._settings = Settings()
        set_language(self._settings.language)
        self._catalog = RegionCatalog()
        self._scheduler = NotificationScheduler(self._settings, threaded=True)
        self._window: MultazemWindow | None = None
        self._single_instance = single_instance

        GLib.set_application_name(tr("app.name"))
        GLib.set_prgname(APP_ID)

    def do_activate(self) -> None:
        """Presents the main window, creating it on the first activation."""
        if self._window is None:
            self._window = MultazemWindow(self, self._settings, self._scheduler, self._catalog)
            # Windows has no icon API in GTK 4; this sets it once the native window exists (and does
            # nothing elsewhere).
            self._window.connect("map", lambda *_: winsupport.apply_icon_to_own_windows())
        self._window.present()

    def do_startup(self) -> None:
        """Prepares the process once, before the first activation.

        Applies the saved language, registers the bundled icons, starts the notification scheduler, prepares the
        background service (see :func:`prepare_service`), listens for launches that ask this process to show its
        window and registers the ``app.quit`` (Ctrl+Q) and ``app.about`` actions. The scheduler starts here
        rather than in ``do_activate`` so it runs once per process, however often the window is activated.
        """
        Adw.Application.do_startup(self)
        apply_ui_language(self._settings.language)
        self._register_bundled_icons()
        self._scheduler.start()
        # The service housekeeping runs external commands or touches the registry, so keep it off the UI thread.
        threading.Thread(target=prepare_service, daemon=True).start()
        if self._single_instance is not None:
            self._single_instance.listen(lambda: GLib.idle_add(self._activate_from_another_launch))

        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Primary>q"])

        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self._show_about)
        self.add_action(about_action)

    def _activate_from_another_launch(self) -> bool:
        """Presents the window because the application was started again; returns ``False`` to run once."""
        self.activate()
        return False

    @staticmethod
    def _register_bundled_icons() -> None:
        """Makes the bell icons shipped inside the package visible to GTK.

        They are bundled so the app does not depend on the user's Adwaita icon-theme
        version (``notifications-symbolic``, for example, is missing from older ones).
        """
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.IconTheme.get_for_display(display).add_search_path(str(ICONS_DIR))

    def _show_about(self, *_args: object) -> None:
        """Shows the About window; the signature accepts and ignores the signal arguments."""
        about = Adw.AboutWindow(
            transient_for=self._window,
            application_name=tr("app.name"),
            application_icon=APP_ID,
            version=__version__,
            developer_name="AbuKaram01",
            license_type=Gtk.License.MIT_X11,
            comments=tr("app.description"),
        )
        about.present()

    def do_shutdown(self) -> None:
        """Stops the scheduler before the application shuts down."""
        self._scheduler.stop()
        Adw.Application.do_shutdown(self)


def main() -> int:
    """Runs the command line: ``--version``, ``--headless`` or the GTK application.

    ``--version`` prints the version and returns. ``--headless`` runs only the notification scheduler
    without a window until it receives SIGTERM or SIGINT; this is what the systemd user service (or, on
    Windows, the autostart entry) starts. Anything else starts the application and passes the arguments on to
    GTK; on Windows a second launch only asks the running copy to show its window and returns.

    Returns:
        The process exit status.
    """
    if "--version" in sys.argv[1:]:
        sys.stdout.write(f"multazem {__version__}\n")
        return 0

    configure_logging()
    if "--headless" in sys.argv:
        run_headless()
        return 0

    instance = SingleInstance()
    if not instance.acquire():
        instance.request_activation()
        return 0
    return MultazemApp(instance).run(sys.argv)
