<h1 align="center">Multazem</h1>
<p align="center"><em>Multazem — prayer time reminders for your desktop, calculated locally, fully offline</em></p>

**Today view:** the main window shows today's timetable — Fajr, Sunrise,
Dhuhr, Asr, Maghrib and Isha — with a live countdown to the next prayer and
today's Gregorian and Hijri dates. On Fridays the Dhuhr slot is shown as
Jumu'ah. Times are calculated on your own machine: pick one of seven
calculation methods and your Asr school, and use the built-in comparison
table to find the method that matches the app you are used to.

**Notifications:** a desktop notification at every prayer time and at
sunrise, plus an optional reminder a few minutes before (you choose how
many). Each row has a bell button to mute or unmute that prayer on its own.
Notifications keep arriving after you close the window: the Autostart button
in the header bar installs a lightweight background service in one click, and
a test button in Preferences helps diagnose notification problems.

**Locations:** a built-in table of 245 Egyptian cities that works without an
internet connection, or add your own region — a name, latitude and longitude,
and an optional time zone — and it is saved locally in the same offline list.
A button in the header bar can also detect your approximate position from your
IP address.

**Preferences** (main menu in the header bar): location, prayer time
calculation, notifications and display — including the interface language,
English (default) or Arabic with a right-to-left layout, applied immediately
and used for the notifications too.

Everything runs locally via [adhanpy](https://github.com/alphahm/adhanpy).
No paid API, and no internet connection required *unless* you use the
automatic location button or the optional Hijri date sync with Dar al-Ifta —
everything else works fully offline.

This is a GTK4 + libadwaita desktop app that runs on Linux (GNOME) and on
Windows 10/11. The only command you may ever need is `multazem --headless`,
which the Autostart button sets up for you: as a `systemd --user` service on
Linux, and as a sign-in entry plus a background process on Windows.

## License

MIT License.
