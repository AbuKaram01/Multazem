#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT
#
# Installs Multazem from this checkout on Debian/Ubuntu: system packages through apt, the
# app itself into a virtual environment in the project folder, and a launcher plus icon
# for the current user. Everything but the apt step stays inside the user's home folder.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ID="com.github.multazem"
REQUIRED_PYTHON="3.11"
REQUIRED_ADW="1.5"

info() { printf '\033[1;34m==>\033[0m %s\n' "$1"; }
ok() { printf '\033[1;32m\xE2\x9C\x93\033[0m %s\n' "$1"; }
fail() {
    printf '\033[1;31m\xE2\x9C\x97 %s\033[0m\n' "$1" >&2
    exit 1
}

# Prints $1 as the quoted Exec value of a desktop entry. Inside the quotes the Desktop Entry
# specification wants a backslash in front of \ " $ and `, and since a backslash is also the
# escape character of the entry's string syntax, each of those backslashes is written twice.
desktop_quote() {
    local value="$1"
    value="${value//\\/\\\\\\\\}"
    value="${value//\"/\\\\\"}"
    value="${value//\$/\\\\\$}"
    value="${value//\`/\\\\\`}"
    printf '"%s"' "$value"
}

# Prints the desktop entry template $1 with its Exec placeholder replaced by the program $2.
render_desktop_entry() {
    local template exec_value rendered
    template="$(cat "$1")"
    exec_value="$(desktop_quote "$2")"
    rendered="${template//Exec=multazem-exec-placeholder/"Exec=${exec_value}"}"
    case "$rendered" in
        *exec-placeholder*) return 1 ;;
    esac
    printf '%s\n' "$rendered"
}

check_environment() {
    case "$PROJECT_ROOT" in
        *%*) fail "This checkout's path contains a '%' character, which GNOME cannot represent in an application launcher. Move the project to a path without it and run this again." ;;
    esac

    if ! command -v apt >/dev/null 2>&1; then
        fail "This script is for Debian/Ubuntu-based systems (needs apt). Not found on this machine."
    fi

    if [ "$EUID" -eq 0 ]; then
        fail "Don't run this as root — it installs into your own \$HOME. Run it as your normal user; it will ask for sudo only for the system packages."
    fi
}

install_system_packages() {
    info "Installing system packages (GTK4, libadwaita, Python bindings, notify-send)..."
    sudo apt update -qq
    sudo apt install -y python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 python3-venv libnotify-bin tzdata
    ok "System packages installed."
}

check_libadwaita_version() {
    local version
    version="$(dpkg-query -W -f='${Version}' gir1.2-adw-1 2>/dev/null || true)"
    if [ -z "$version" ] || ! dpkg --compare-versions "$version" ge "$REQUIRED_ADW"; then
        fail "multazem needs libadwaita $REQUIRED_ADW or newer, but this system has ${version:-none}. Use a newer release (Debian 13 / Ubuntu 24.04 or later)."
    fi
    ok "libadwaita $version OK."
}

check_python_version() {
    local version
    version="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    if [ "$(printf '%s\n' "$REQUIRED_PYTHON" "$version" | sort -V | head -n1)" != "$REQUIRED_PYTHON" ]; then
        fail "Python $REQUIRED_PYTHON+ is required (see requires-python in pyproject.toml) — found $version. Upgrading your system Python (or your distro) is the straightforward fix."
    fi
    ok "Python $version OK."
}

install_python_package() {
    if [ ! -d .venv ]; then
        info "Creating virtual environment (.venv)..."
        python3 -m venv --system-site-packages .venv
        ok "Virtual environment created."
    else
        info "Reusing existing .venv"
    fi

    info "Installing multazem and its Python dependency (adhanpy)..."
    .venv/bin/pip install -q -e .
    ok "Python dependencies installed."
}

install_launcher_and_icon() {
    local data_dir="$HOME/.local/share"
    local icon_dir="$data_dir/icons/hicolor/scalable/apps"
    local entry="$data_dir/applications/${APP_ID}.desktop"

    info "Installing the desktop launcher and app icon for your user..."
    mkdir -p "$data_dir/applications" "$icon_dir"
    render_desktop_entry "data/${APP_ID}.desktop" "${PROJECT_ROOT}/.venv/bin/multazem" >"$entry" ||
        {
            rm -f "$entry"
            fail "The Exec placeholder was not replaced in the desktop entry."
        }
    cp "data/icons/hicolor/scalable/apps/${APP_ID}.svg" "$icon_dir/${APP_ID}.svg"
    gtk-update-icon-cache -q -t -f "$data_dir/icons/hicolor" >/dev/null 2>&1 || true
    ok "Desktop launcher and app icon installed."
}

print_usage() {
    echo
    ok "multazem is installed."
    echo
    echo "  Run it with:"
    echo "    ${PROJECT_ROOT}/.venv/bin/multazem"
    echo
    echo "  Or activate the virtual environment first:"
    echo "    source ${PROJECT_ROOT}/.venv/bin/activate"
    echo "    multazem"
    echo
    echo "  It should also now appear in your applications menu as \"Multazem\"."
    echo "  To get notifications even when the window is closed, use the autostart"
    echo "  button in the app's header bar (it sets up a systemd --user service)."
}

main() {
    cd "$PROJECT_ROOT"
    check_environment
    install_system_packages
    check_libadwaita_version
    check_python_version
    install_python_package
    install_launcher_and_icon
    print_usage
}

# Sourcing the file (the tests do) only defines the functions.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main "$@"
fi
