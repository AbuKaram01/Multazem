# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""The About dialog and the welcome guide, opened from the main menu of the real application (under Xvfb)."""

import textwrap

import pytest

from gui_support import run_scenario

pytestmark = pytest.mark.gui

MENU_LABELS = textwrap.dedent(
    """
def menu_labels(model):
    labels = []
    for index in range(model.get_n_items()):
        label = model.get_item_attribute_value(index, "label", None)
        if label is not None:
            labels.append(label.get_string())
        section = model.get_item_link(index, "section")
        if section is not None:
            labels += menu_labels(section)
    return labels
"""
)


MENU_SCENARIO = MENU_LABELS + textwrap.dedent(
    """
    def check():
        out["labels"] = menu_labels(app._window._build_menu())
        return finish()
    GLib.timeout_add(1500, check)
    """
)


def test_the_english_menu_lists_the_welcome_guide_between_preferences_and_about(tmp_path):
    out, err = run_scenario(tmp_path, MENU_SCENARIO)
    assert out["labels"] == ["Preferences", "Welcome Guide", "About", "Quit"]
    assert "Traceback" not in err


def test_the_arabic_menu_lists_the_welcome_guide_too(tmp_path):
    out, err = run_scenario(tmp_path, MENU_SCENARIO, settings={"language": "ar"})
    assert out["labels"] == ["الإعدادات", "دليل البداية", "حول البرنامج", "إنهاء"]
    assert "Traceback" not in err


def test_the_about_dialog_has_every_field_the_other_programs_fill_in(tmp_path):
    out, err = run_scenario(
        tmp_path,
        """
        def check():
            app.activate_action("about", None)
            about = app._window.get_visible_dialog()
            out["is_about"] = isinstance(about, Adw.AboutDialog)
            out["name"] = about.get_application_name()
            out["developer_name"] = about.get_developer_name()
            out["developers"] = list(about.get_developers())
            out["copyright"] = about.get_copyright()
            out["website"] = about.get_website()
            out["issue_url"] = about.get_issue_url()
            out["license"] = about.get_license_type() == Gtk.License.MIT_X11
            out["comments"] = about.get_comments()
            return finish()
        GLib.timeout_add(1500, check)
    """,
    )
    assert out["is_about"] and out["name"] == "Multazem" and out["developer_name"] == "AbuKaram01"
    assert out["developers"] == ["AbuKaram01"] and out["copyright"] == "© 2026 AbuKaram01"
    assert out["website"] == "https://github.com/AbuKaram01/Multazem"
    assert out["issue_url"] == "https://github.com/AbuKaram01/Multazem/issues"
    assert out["license"] and out["comments"]
    assert "Traceback" not in err


def test_the_welcome_guide_walks_through_three_pages_and_opens_only_once(tmp_path):
    out, err = run_scenario(
        tmp_path,
        """
        from multazem.ui.welcome import WelcomeDialog
        def labels(root):
            return [w.get_label() for w in walk(root, []) if isinstance(w, Gtk.Label)]
        def step():
            window = app._window
            window.lookup_action("welcome").activate(None)
            guide = window.get_visible_dialog()
            out["is_guide"] = isinstance(guide, WelcomeDialog)
            out["first"] = (guide._next.get_label(), guide._back.get_visible())
            guide._next.emit("clicked")
            out["second"] = (guide._index, guide._next.get_label(), guide._back.get_visible())
            guide._next.emit("clicked")
            out["third"] = (guide._index, guide._next.get_label(), guide._back.get_visible())
            out["finish_text"] = " ".join(labels(guide._pages[2]))
            guide._back.emit("clicked")
            out["back"] = guide._index
            window.lookup_action("welcome").activate(None)
            out["same_guide"] = window._welcome_dialog is guide
            GLib.timeout_add(700, close_it)
            return False
        def close_it():
            window = app._window
            out["visible_before_closing"] = window._welcome_dialog is window.get_visible_dialog()
            window._welcome_dialog.close()
            GLib.timeout_add(1200, again)
            return False
        def again():
            window = app._window
            out["forgotten"] = window._welcome_dialog is None
            window.lookup_action("welcome").activate(None)
            out["reopened"] = isinstance(window.get_visible_dialog(), WelcomeDialog)
            return finish()
        GLib.timeout_add(1500, step)
    """,
    )
    assert out["is_guide"]
    assert out["first"] == ["Next", False]
    assert out["second"] == [1, "Next", True]
    assert out["third"] == [2, "Get Started", True]
    assert "You're all set" in out["finish_text"]
    assert out["back"] == 1
    assert out["same_guide"] and out["visible_before_closing"] and out["forgotten"] and out["reopened"]
    assert "Traceback" not in err


def test_the_welcome_guide_speaks_arabic_when_the_language_is_arabic(tmp_path):
    out, err = run_scenario(
        tmp_path,
        """
        from multazem.ui.welcome import WelcomeDialog
        def check():
            app._window.lookup_action("welcome").activate(None)
            guide = app._window.get_visible_dialog()
            texts = [w.get_label() for p in guide._pages for w in walk(p, []) if isinstance(w, Gtk.Label)]
            texts += [w.get_title() for p in guide._pages for w in walk(p, []) if isinstance(w, Adw.StatusPage)]
            out["title"] = guide.get_title()
            out["next"] = guide._next.get_label()
            out["has_arabic"] = any(ARABIC.search(text or "") for text in texts)
            out["english_leftovers"] = [t for t in texts if t and not ARABIC.search(t) and re.search("[A-Za-z]{4,}", t)]
            return finish()
        GLib.timeout_add(1500, check)
    """,
        settings={"language": "ar"},
    )
    assert out["title"] == "أهلاً بك" and out["next"] == "التالي" and out["has_arabic"]
    assert out["english_leftovers"] == []
    assert "Traceback" not in err
