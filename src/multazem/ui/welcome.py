# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""The welcome guide: what Multazem does, how to set it up and where to find the guide again.

The guide has three pages::

    1. Welcome   what the program does, in three lines
    2. Set up    the location, the calculation method and the background service
    3. Finish    where the prayer times are, and how to open the guide again

It opens from the main menu ("Welcome Guide") whenever the user wants it.
"""

from __future__ import annotations

from gi.repository import Adw, Gdk, Gtk

from ..i18n import tr

# Positions of the pages in the carousel.
_PAGE_WELCOME, _PAGE_SETUP, _PAGE_FINISH = 0, 1, 2
# Shown instead of the application icon when the icon theme does not provide it.
_FALLBACK_ICON = "preferences-system-time-symbolic"

_ICON_SIZE = 72
_DIALOG_WIDTH = 520
_DIALOG_HEIGHT = 680
_COLUMN_WIDTH = 460
_COLUMN_TIGHTENING = 340


def _scrolled(content: Gtk.Widget) -> Gtk.ScrolledWindow:
    """Wraps ``content`` as a page body: centred, in a comfortable column, scrolling when the dialog is short."""
    clamp = Adw.Clamp(
        maximum_size=_COLUMN_WIDTH, tightening_threshold=_COLUMN_TIGHTENING, margin_start=12, margin_end=12
    )
    clamp.set_child(content)
    # hexpand is needed because a carousel gives a page only its natural width unless the page asks for all of it.
    return Gtk.ScrolledWindow(child=clamp, hscrollbar_policy=Gtk.PolicyType.NEVER, hexpand=True, vexpand=True)


def _rows(rows: tuple[tuple[str, str, str], ...]) -> Adw.PreferencesGroup:
    """Builds a group of read-only rows from ``(icon name, title, description)`` triples."""
    group = Adw.PreferencesGroup(margin_top=6, margin_bottom=12)
    for icon_name, title, subtitle in rows:
        row = Adw.ActionRow(
            title=title, subtitle=subtitle, title_lines=0, subtitle_lines=0, use_markup=False, activatable=False
        )
        row.add_prefix(Gtk.Image(icon_name=icon_name, icon_size=Gtk.IconSize.LARGE))
        group.add(row)
    return group


class WelcomeDialog(Adw.Dialog):
    """The welcome guide dialog.

    Args:
        app_icon: Name of the application icon shown on the first page.
    """

    def __init__(self, app_icon: str) -> None:
        super().__init__(title=tr("welcome.title"), content_width=_DIALOG_WIDTH, content_height=_DIALOG_HEIGHT)
        self._app_icon = app_icon
        self._index = _PAGE_WELCOME

        self._carousel = Adw.Carousel(
            interactive=False, allow_scroll_wheel=False, allow_mouse_drag=False, allow_long_swipes=False, vexpand=True
        )
        self._pages = [self._welcome_page(), self._setup_page(), self._finish_page()]
        for page in self._pages:
            self._carousel.append(page)

        toolbar = Adw.ToolbarView(content=self._build_body())
        toolbar.add_top_bar(Adw.HeaderBar(show_title=False))
        toolbar.set_top_bar_style(Adw.ToolbarStyle.FLAT)
        self.set_child(toolbar)
        self.set_default_widget(self._next)
        self._sync_buttons()

    # --- Building ---

    def _build_body(self) -> Gtk.Box:
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        body.append(self._carousel)
        body.append(Adw.CarouselIndicatorDots(carousel=self._carousel, margin_top=6, margin_bottom=6))
        body.append(self._build_buttons())
        return body

    def _build_buttons(self) -> Gtk.Box:
        self._back = Gtk.Button(label=tr("welcome.back"), css_classes=["flat", "pill"])
        self._back.connect("clicked", lambda _button: self._go(self._index - 1))
        self._next = Gtk.Button(label=tr("welcome.next"), css_classes=["suggested-action", "pill"], width_request=180)
        self._next.connect("clicked", self._on_next)
        buttons = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER, margin_top=6, margin_bottom=24)
        buttons.append(self._back)
        buttons.append(self._next)
        return buttons

    # --- Pages ---

    def _welcome_page(self) -> Gtk.Widget:
        theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        icon = self._app_icon if theme.has_icon(self._app_icon) else _FALLBACK_ICON
        features = _rows(
            (
                ("preferences-system-time-symbolic", tr("welcome.times.title"), tr("welcome.times.text")),
                ("multazem-bell-symbolic", tr("welcome.reminders.title"), tr("welcome.reminders.text")),
                ("security-high-symbolic", tr("welcome.offline.title"), tr("welcome.offline.text")),
            )
        )
        # A plain column instead of a status page: its big icon would push the rows out of the small window.
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=12, margin_bottom=12)
        box.append(Gtk.Image(icon_name=icon, pixel_size=_ICON_SIZE))
        box.append(Gtk.Label(label=tr("welcome.heading"), css_classes=["title-1"], wrap=True))
        box.append(
            Gtk.Label(
                label=tr("welcome.tagline"), wrap=True, justify=Gtk.Justification.CENTER, css_classes=["dim-label"]
            )
        )
        box.append(features)
        return _scrolled(box)

    def _setup_page(self) -> Gtk.Widget:
        steps = _rows(
            (
                ("find-location-symbolic", tr("welcome.setup.location.title"), tr("welcome.setup.location.text")),
                ("emblem-system-symbolic", tr("welcome.setup.method.title"), tr("welcome.setup.method.text")),
                ("media-playback-start-symbolic", tr("welcome.setup.service.title"), tr("welcome.setup.service.text")),
            )
        )
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18, margin_top=12, margin_bottom=12)
        box.append(
            Gtk.Label(
                label=tr("welcome.setup.heading"), css_classes=["title-1"], wrap=True, justify=Gtk.Justification.CENTER
            )
        )
        box.append(
            Gtk.Label(
                label=tr("welcome.setup.description"),
                wrap=True,
                justify=Gtk.Justification.CENTER,
                css_classes=["dim-label"],
            )
        )
        box.append(steps)
        return _scrolled(box)

    def _finish_page(self) -> Gtk.Widget:
        page = Adw.StatusPage(
            icon_name="object-select-symbolic",
            title=tr("welcome.finish.heading"),
            description=tr("welcome.finish.description"),
        )
        page.add_css_class("compact")
        return _scrolled(page)

    # --- Moving between the pages ---

    def _go(self, index: int) -> None:
        self._index = min(max(index, _PAGE_WELCOME), _PAGE_FINISH)
        self._carousel.scroll_to(self._pages[self._index], True)
        self._sync_buttons()

    def _on_next(self, _button: Gtk.Button) -> None:
        if self._index == _PAGE_FINISH:
            self.close()
        else:
            self._go(self._index + 1)

    def _sync_buttons(self) -> None:
        self._back.set_visible(self._index != _PAGE_WELCOME)
        self._next.set_label(tr("welcome.start") if self._index == _PAGE_FINISH else tr("welcome.next"))
