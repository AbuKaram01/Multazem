# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT
#
# shellcheck shell=bash
# Shared by build.sh (deb, rpm) and PKGBUILD (Arch): lays out the files every package installs.
# The caller sets PROJECT_ROOT, PKG_NAME and APP_ID before sourcing this file.

# Globals the sourcing script can rely on after this file is loaded.
VENDOR_DIR="$PROJECT_ROOT/packaging/vendor"
TEMPLATES_DIR="$PROJECT_ROOT/packaging/templates"

# Makes every directory under $1 mode 755 and every file 755 if it is executable, 644 if not,
# so the packages do not depend on the umask of the build machine.
normalize_perms() {
    find "$1" -type d -exec chmod 755 {} +
    find "$1" -type f -perm -u=x -exec chmod 755 {} +
    find "$1" -type f ! -perm -u=x -exec chmod 644 {} +
}

# Copies the application package and the vendored adhanpy into $1/opt/$PKG_NAME. Bytecode
# caches are left out because the package manager does not track files created at run time.
stage_application() {
    local payload="$1/opt/$PKG_NAME"
    mkdir -p "$payload"
    cp -r "$PROJECT_ROOT/src/multazem" "$VENDOR_DIR/adhanpy" "$payload/"
    find "$payload" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    find "$payload" -type d -exec chmod 755 {} +
    find "$payload" -type f -exec chmod 644 {} +
}

# Installs the desktop entry under $1/usr/share/applications with its Exec placeholder
# replaced by the installed launcher's name. Fails when the placeholder is not found.
stage_desktop_entry() {
    local target="$1/usr/share/applications/${APP_ID}.desktop"
    mkdir -p "$(dirname "$target")"
    sed "s|^Exec=multazem-exec-placeholder|Exec=$PKG_NAME|" "$PROJECT_ROOT/data/${APP_ID}.desktop" >"$target"
    if grep -q 'exec-placeholder' "$target"; then
        echo "data/${APP_ID}.desktop: the Exec placeholder was not replaced." >&2
        return 1
    fi
    chmod 644 "$target"
}

# Installs the application icon and the AppStream metadata under $1/usr/share.
stage_data_files() {
    install -Dm644 "$PROJECT_ROOT/data/icons/hicolor/scalable/apps/${APP_ID}.svg" \
        "$1/usr/share/icons/hicolor/scalable/apps/${APP_ID}.svg"
    install -Dm644 "$PROJECT_ROOT/data/${APP_ID}.metainfo.xml" \
        "$1/usr/share/metainfo/${APP_ID}.metainfo.xml"
}

# Installs everything the three package formats have in common under the root directory $1.
stage_payload() {
    local root="$1"
    stage_application "$root"
    install -Dm755 "$TEMPLATES_DIR/launcher.sh" "$root/usr/bin/$PKG_NAME"
    stage_desktop_entry "$root"
    stage_data_files "$root"
    normalize_perms "$root"
}
