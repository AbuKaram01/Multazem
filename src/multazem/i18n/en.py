# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""English message catalog (the default language and the fallback for missing keys)."""

from __future__ import annotations

MESSAGES: dict[str, str] = {
    # --- Application -------------------------------------------------------------
    "app.name": "Multazem",
    "app.description": "Prayer time reminders that run entirely offline",
    # --- Timetable entries and calculation methods ---------------------------------
    "prayer.fajr": "Fajr",
    "prayer.sunrise": "Sunrise",
    "prayer.dhuhr": "Dhuhr",
    "prayer.jumuah": "Jumu'ah",
    "prayer.asr": "Asr",
    "prayer.maghrib": "Maghrib",
    "prayer.isha": "Isha",
    "method.egyptian": "Egyptian Authority of Survey",
    "method.muslim_world_league": "Muslim World League",
    "method.north_america": "North America (ISNA)",
    "method.umm_al_qura": "Umm Al-Qura",
    "method.karachi": "Karachi",
    "method.kuwait": "Kuwait",
    "method.qatar": "Qatar",
    # --- Dates (index 0 is Monday, matching datetime.weekday()) -------------------
    "weekday.0": "Monday",
    "weekday.1": "Tuesday",
    "weekday.2": "Wednesday",
    "weekday.3": "Thursday",
    "weekday.4": "Friday",
    "weekday.5": "Saturday",
    "weekday.6": "Sunday",
    "hijri.month.1": "Muharram",
    "hijri.month.2": "Safar",
    "hijri.month.3": "Rabi' al-Awwal",
    "hijri.month.4": "Rabi' al-Thani",
    "hijri.month.5": "Jumada al-Ula",
    "hijri.month.6": "Jumada al-Akhirah",
    "hijri.month.7": "Rajab",
    "hijri.month.8": "Sha'ban",
    "hijri.month.9": "Ramadan",
    "hijri.month.10": "Shawwal",
    "hijri.month.11": "Dhu al-Qi'dah",
    "hijri.month.12": "Dhu al-Hijjah",
    "hijri.format": "{day} {month} {year} AH",
    # --- Main menu -------------------------------------------------------------------
    "menu.preferences": "Preferences",
    "menu.about": "About",
    "menu.quit": "Quit",
    # --- Main window -----------------------------------------------------------------
    "window.menu.tooltip": "Main menu",
    "window.detect_location.tooltip": "Detect location automatically (requires internet)",
    "window.service.start.label": "Autostart",
    "window.service.start.tooltip": "Run at login - notifications keep arriving even when the app is closed",
    "window.service.stop.label": "Stop",
    "window.service.stop.tooltip": "Stop running at login (notifications will only arrive while the app is open)",
    "window.next_prayer": "Next prayer",
    "window.times.title": "Prayer times",
    "window.countdown": "Time left {hours:02d}:{minutes:02d}:{seconds:02d}",
    "window.date_format": "{weekday}, {date}",
    "window.hijri.tooltip.estimated": (
        "Estimated Hijri date from an astronomical calculation - it may differ by a day from the official "
        "moon-sighting announcement"
    ),
    "window.hijri.tooltip.official": "Official Hijri date - synced with Dar al-Ifta al-Misriyyah",
    "window.bell.globally_off": "Notifications are turned off in Preferences",
    "window.bell.on": "{prayer} notifications: on (click to turn off)",
    "window.bell.off": "{prayer} notifications: off (click to turn on)",
    "window.toast.bell_on": "{prayer} notifications: on",
    "window.toast.bell_off": "{prayer} notifications: off",
    "window.toast.location_set": "📍 Location set: {city}",
    "window.toast.background_notice": (
        "The app keeps running in the background to deliver notifications (Ctrl+Q to quit completely)"
    ),
    # --- Notifications ---------------------------------------------------------------
    "notification.prayer.title": "{prayer} prayer time",
    "notification.prayer.body": "It is {time} \u2013 time for {prayer} prayer",
    "notification.sunrise.title": "Sunrise",
    "notification.sunrise.body": "It is {time} \u2013 the sun is rising now",
    "notification.reminder.title": "Reminder \u2013 {prayer} prayer",
    "notification.reminder.body": "{minutes} min until {prayer} prayer",
    "notification.sunrise_reminder.title": "Reminder \u2013 Sunrise",
    "notification.sunrise_reminder.body": "Sunrise in {minutes} min \u2013 the time for Fajr is about to end",
    # --- Preferences: general ----------------------------------------------------------
    "prefs.title": "Preferences",
    # --- Preferences: location ---------------------------------------------------------
    "prefs.location.title": "Location",
    "prefs.location.description": (
        "Pick a region from the list (works offline), add your own, or enter the coordinates manually"
    ),
    "prefs.picker.title": "Quick pick a region",
    "prefs.picker.subtitle": "{count} regions, searchable, works offline",
    "prefs.city_name": "City name",
    "prefs.latitude": "Latitude",
    "prefs.longitude": "Longitude",
    "prefs.timezone.title": "Time zone",
    "prefs.timezone.tooltip": "Example: Africa/Cairo or Asia/Riyadh",
    "prefs.timezone.invalid": "Time zone (invalid!)",
    "prefs.region.add.title": "Add a region",
    "prefs.region.add.subtitle": "Save a place to the offline regions list",
    "prefs.region.add.button": "Add",
    "prefs.region.name": "Region name",
    "prefs.region.latitude": "Latitude (-90 to 90)",
    "prefs.region.longitude": "Longitude (-180 to 180)",
    "prefs.region.timezone": "Time zone (optional)",
    "prefs.region.timezone.tooltip": "Leave it as is to use the current time zone. Example: Asia/Riyadh",
    "prefs.region.added": "Added “{name}” to the regions list and set it as your location",
    # --- Preferences: calculation ------------------------------------------------------
    "prefs.calculation.title": "Prayer time calculation",
    "prefs.calculation.method": "Method",
    "prefs.calculation.method.subtitle": "Affects Fajr and Isha times",
    "prefs.compare.title": "Compare methods",
    "prefs.compare.subtitle": "Find the method that matches your usual app",
    "prefs.compare.dialog.heading": "Calculation methods compared",
    "prefs.compare.dialog.body": "Compare Fajr and Isha with your usual app and choose the matching method",
    "prefs.compare.dialog.close": "Close",
    "prefs.compare.column.method": "Method",
    "prefs.compare.column.fajr": "Fajr",
    "prefs.compare.column.isha": "Isha",
    "prefs.asr.title": "Asr calculation",
    "prefs.asr.standard": "Shafi'i / Maliki / Hanbali",
    "prefs.asr.hanafi": "Hanafi",
    # --- Preferences: notifications ------------------------------------------------------
    "prefs.notifications.title": "Notifications",
    "prefs.notifications.at_prayer": "Notify at prayer time and sunrise",
    "prefs.notifications.reminder": "Remind before prayer and sunrise",
    "prefs.notifications.minutes.title": "Reminder lead time",
    "prefs.notifications.minutes.subtitle": "In minutes",
    "prefs.test.title": "Send a test notification",
    "prefs.test.subtitle": "Diagnose notification problems without waiting for a real prayer time",
    "prefs.test.button": "Test",
    "prefs.test.notification.title": "Multazem test",
    "prefs.test.notification.body": (
        "If you can see this notification, the connection to the notification system works ✅"
    ),
    "prefs.test.sent": "✓ Sent - if you do not see it, check your desktop's notification settings",
    "prefs.test.failed": "✗ Could not send: {detail}",
    # --- Preferences: appearance ---------------------------------------------------------
    "prefs.appearance.title": "Display",
    "prefs.language.title": "Language",
    "prefs.language.subtitle": "Applied immediately",
    "prefs.hijri.show": "Show Hijri date",
    "prefs.hijri.sync.title": "Sync Hijri date with Dar al-Ifta",
    "prefs.hijri.sync.subtitle": (
        "Instead of the approximate local calculation (needs internet; falls back to the local calculation if the "
        "connection fails)"
    ),
    # --- Errors ------------------------------------------------------------------------
    "error.timezone_unknown": 'Unknown time zone "{timezone}". Use an IANA name such as Africa/Cairo or Asia/Riyadh.',
    "error.latitude_out_of_range": "Latitude ({latitude}) is outside the valid range (-90 to 90)",
    "error.longitude_out_of_range": "Longitude ({longitude}) is outside the valid range (-180 to 180)",
    "error.sun_never_crosses": (
        "Cannot calculate prayer times at latitude {latitude}° on {date} (the sun does not rise or set there). "
        "Choose another location."
    ),
    "error.times_incomplete": "Could not calculate all prayer times at latitude {latitude}° on {date}.",
    "region.error.name_required": "Enter the region name",
    "region.error.name_too_long": "The name is too long (at most {max} characters)",
    "region.error.name_exists": "A region named “{name}” already exists",
    "region.error.latitude_invalid": "Latitude must be a number, for example 24.71",
    "region.error.latitude_range": "Latitude must be between -{limit} and {limit}",
    "region.error.longitude_invalid": "Longitude must be a number, for example 46.67",
    "region.error.longitude_range": "Longitude must be between -{limit} and {limit}",
    "region.error.timezone_invalid": "Unknown time zone - use a name such as Africa/Cairo",
    "region.error.save_failed": "Could not save the region: {detail}",
    # --- Location detection ----------------------------------------------------------------
    "location.default_city": "Your current location",
    "location.error.offline": "No internet connection \u2013 please set the location manually",
    "location.error.unreadable": (
        "Could not determine the location from the geojs.io response \u2013 please set the location manually"
    ),
    "location.error.with_hint": "{reason} \u2013 please set the location manually",
    "location.error.unexpected_response": "Unexpected response from the location service",
    "location.error.invalid_coordinates": "The service did not return valid coordinates",
    "location.error.coordinates_out_of_range": "The returned coordinates are outside the valid range",
    "location.error.invalid_timezone": "The service did not return a valid time zone",
    # --- Background service ----------------------------------------------------------------
    "service.installed": "✓ Service installed and started",
    "service.uninstalled": "✓ Service stopped and removed",
    "service.error.write_failed": "Could not write the service file: {detail}",
    "service.error.enable_failed": "Could not enable the service: {detail}",
    "service.error.remove_failed": "Could not remove the service file: {detail}",
}
