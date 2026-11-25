#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT
#
# Builds the installable packages (.deb, .rpm and the Arch package) from this checkout.
# A format is built only when its tool (dpkg-deb, rpmbuild, makepkg) is installed; the
# results end up in packaging/dist. The files all three formats share are staged by
# stage.sh, the format-specific text files live in packaging/templates.

set -euo pipefail

# Locations, resolved from this file so the script works from any current directory.
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="$PROJECT_ROOT/packaging/work"
OUT_DIR="$PROJECT_ROOT/packaging/dist"
# Package identity shared by the templates. LEGACY_PKG_NAME is the former name that the
# new package replaces on upgrade.
PKG_NAME="multazem"
LEGACY_PKG_NAME="salah-reminder"
APP_ID="com.github.multazem"
MAINTAINER="AbuKaram01 <abukaram01@proton.me>"

# shellcheck source=packaging/stage.sh
source "$PROJECT_ROOT/packaging/stage.sh"

# Prints $1 as a progress message.
info() { printf '\033[1;34m==>\033[0m %s\n' "$1"; }
# Prints $1 as a success message.
ok() { printf '\033[1;32m\xE2\x9C\x93\033[0m %s\n' "$1"; }
# Prints $1 as a warning; the build goes on.
warn() { printf '\033[1;33m! %s\033[0m\n' "$1"; }
# Prints $1 to stderr and aborts the script with status 1.
die() {
    printf '\033[1;31m\xE2\x9C\x97 %s\033[0m\n' "$1" >&2
    exit 1
}

# Succeeds when the command $1 is installed.
have() { command -v "$1" >/dev/null 2>&1; }

# Prints the application version from src/multazem/__init__.py, or nothing if it cannot be read.
read_version() {
    sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$PROJECT_ROOT/src/multazem/__init__.py" 2>/dev/null || true
}

# Stops the build unless this is a complete checkout: every file the packages are made from
# must exist and the version must be known.
# Globals:
#   VERSION: the application version, set by main.
check_sources() {
    local required=(
        "src/multazem/__init__.py"
        "LICENSE"
        "CHANGELOG.md"
        "data/${APP_ID}.desktop"
        "data/${APP_ID}.metainfo.xml"
        "data/icons/hicolor/scalable/apps/${APP_ID}.svg"
        "packaging/templates/launcher.sh"
        "packaging/templates/deb-control.in"
        "packaging/templates/deb-postinst.sh"
        "packaging/templates/deb-postrm.sh"
        "packaging/templates/rpm.spec.in"
    )
    local file
    for file in "${required[@]}"; do
        [ -f "$PROJECT_ROOT/$file" ] || die "Missing $file in $PROJECT_ROOT — run this from a full checkout of the project."
    done
    [ -n "$VERSION" ] || die "Could not read __version__ from src/multazem/__init__.py."
    [ -d "$VENDOR_DIR/adhanpy" ] || die "packaging/vendor/adhanpy is missing (the bundled prayer-time library)."
}

# Stops the build with installation hints when none of the three packaging tools is present.
require_a_packaging_tool() {
    if have dpkg-deb || have rpmbuild || have makepkg; then
        return 0
    fi
    {
        echo "None of dpkg-deb, rpmbuild, or makepkg found."
        echo "Install dpkg-dev to build the .deb (any Debian/Ubuntu system),"
        echo "rpm-build to build the .rpm (Fedora/RHEL/openSUSE),"
        echo "or run this script on Arch, where makepkg ships with base-devel."
    } >&2
    exit 1
}

# Escapes the characters that are special in the replacement part of a sed "s|||" command.
escape_sed_replacement() {
    printf '%s' "$1" | sed 's/[\\|&]/\\&/g'
}

# Fills the @NAME@ placeholders of packaging/templates/$1 and writes the result to $2.
# The common values are always available; further NAME=value pairs can be passed after $2.
# Aborts when a placeholder is left over, which means a template names a value nobody supplied.
# Arguments:
#   $1: template file name.
#   $2: destination path; its directory is created.
#   $3...: extra NAME=value pairs.
render_template() {
    local name="$1" destination="$2"
    local template="$TEMPLATES_DIR/$name"
    shift 2
    local substitutions=(
        "PKG_NAME=$PKG_NAME"
        "LEGACY_PKG_NAME=$LEGACY_PKG_NAME"
        "VERSION=$VERSION"
        "MAINTAINER=$MAINTAINER"
        "APP_ID=$APP_ID"
        "$@"
    )
    local sed_args=() pair
    for pair in "${substitutions[@]}"; do
        sed_args+=(-e "s|@${pair%%=*}@|$(escape_sed_replacement "${pair#*=}")|g")
    done
    mkdir -p "$(dirname "$destination")"
    sed "${sed_args[@]}" "$template" >"$destination"
    if grep -Eq '@[A-Z_]+@' "$destination"; then
        die "packaging/templates/$name: a placeholder was not replaced."
    fi
}

# Builds the .deb into $OUT_DIR, or skips with a warning when dpkg-deb is missing.
build_deb() {
    if ! have dpkg-deb; then
        warn "dpkg-deb not found — skipping .deb (install dpkg-dev to build it)."
        return 0
    fi
    local package="${PKG_NAME}_${VERSION}_all.deb"
    local root="$WORK_DIR/deb-root"
    local doc_dir="$root/usr/share/doc/$PKG_NAME"

    info "Building $package..."
    stage_payload "$root"
    install -Dm644 "$PROJECT_ROOT/LICENSE" "$doc_dir/copyright"
    gzip -9n -c "$PROJECT_ROOT/CHANGELOG.md" >"$doc_dir/changelog.gz"
    render_template deb-control.in "$root/DEBIAN/control"
    install -Dm755 "$TEMPLATES_DIR/deb-postinst.sh" "$root/DEBIAN/postinst"
    install -Dm755 "$TEMPLATES_DIR/deb-postrm.sh" "$root/DEBIAN/postrm"
    normalize_perms "$root"

    dpkg-deb --build --root-owner-group "$root" "$OUT_DIR/$package" >/dev/null
    ok "$package"
}

# Builds the .rpm into $OUT_DIR, or skips with a warning when rpmbuild is missing.
# A failing rpmbuild only warns, so a package built earlier is still delivered.
# rpmbuild gets a private database directory so it never needs the system RPM database
# (this is what lets it run on Debian-based machines).
build_rpm() {
    if ! have rpmbuild; then
        warn "rpmbuild not found — skipping .rpm (install rpm-build: 'sudo dnf install rpm-build' on Fedora/RHEL, 'sudo zypper install rpm-build' on openSUSE)."
        return 0
    fi
    local root="$WORK_DIR/rpm-root"
    local spec="$WORK_DIR/$PKG_NAME.spec"
    local log="$WORK_DIR/rpmbuild.log"

    info "Building ${PKG_NAME}-${VERSION}-1.noarch.rpm..."
    stage_payload "$root"
    install -Dm644 "$PROJECT_ROOT/LICENSE" "$root/usr/share/licenses/$PKG_NAME/LICENSE"
    normalize_perms "$root"
    mkdir -p "$WORK_DIR/rpmbuild"/{BUILD,RPMS,SOURCES,SPECS,SRPMS} "$WORK_DIR/rpmdb"
    render_template rpm.spec.in "$spec" "RPM_ROOT=$root"

    if rpmbuild --nodeps \
        --define "_dbpath $WORK_DIR/rpmdb" \
        --define "_topdir $WORK_DIR/rpmbuild" \
        -bb "$spec" >"$log" 2>&1; then
        find "$WORK_DIR/rpmbuild/RPMS" -name "*.rpm" -exec mv {} "$OUT_DIR/" \;
        local rpm
        for rpm in "$OUT_DIR"/*.rpm; do ok "$(basename "$rpm")"; done
    else
        cat "$log" >&2
        warn "rpmbuild failed — its output is shown above. The .deb above (if built) is unaffected."
    fi
}

# Builds the Arch package with makepkg into $OUT_DIR. Skipped with a warning when makepkg is
# missing or the script runs as root, because makepkg refuses to run as root.
build_arch() {
    if ! have makepkg; then
        warn "makepkg not found — skipping the Arch package. It's Arch-specific tooling (ships with base-devel); build it on an Arch machine, either by running this script there or directly with 'cd packaging && makepkg -si'."
        return 0
    fi
    if [ "$EUID" -eq 0 ]; then
        warn "makepkg refuses to run as root — skipping the Arch package. Re-run this script as a normal user to build it."
        return 0
    fi

    info "Building the Arch package with makepkg..."
    if (cd "$PROJECT_ROOT/packaging" && makepkg -f); then
        find "$PROJECT_ROOT/packaging" -maxdepth 1 -name "*.pkg.tar.*" -exec mv {} "$OUT_DIR/" \;
        ok "Arch package built."
    else
        warn "makepkg failed (see its output above) — the .deb above is still fine if it was built."
    fi
    rm -rf "$PROJECT_ROOT/packaging/pkg" "$PROJECT_ROOT/packaging/src"
}

# Builds every package whose tool is installed, starting from a clean work and output directory.
main() {
    VERSION="$(read_version)"
    check_sources
    require_a_packaging_tool

    rm -rf "$WORK_DIR" "$OUT_DIR"
    mkdir -p "$WORK_DIR" "$OUT_DIR"

    build_deb
    build_rpm
    build_arch

    echo
    ok "Done. Output in: $OUT_DIR"
    ls -la "$OUT_DIR" 2>/dev/null || true
}

# Sourcing the file (the tests do) only defines the functions.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main "$@"
fi
