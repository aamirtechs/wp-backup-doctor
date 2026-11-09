# Changelog

## 1.0.0 - 2026-11-05

Initial release.

* Audits a WordPress backup set from a JSON manifest or a plain text
  directory listing, offline, with zero dependencies.
* Required components: database, uploads, and plugins-themes. A
  component counts as present only when it has a non-empty backup.
* Errors for a missing component and for any backup older than
  --max-age days (default 7).
* Warnings for empty (0 byte) files, duplicate backup names, and
  entries with no recognized component type.
* Text and --json output, --check CI gate (exit 1 on any error, 0 if
  only warnings or clean), --max-age override, and --component filter
  to audit a single component.
* ISO dates only: a full date (2026-11-04), a datetime with a
  timezone, or a datetime ending in Z. Naive datetimes are read as
  UTC. Bad JSON, bad dates, negative sizes, and missing names exit 2
  with a message naming the entry or line.
* Component types accept aliases (db, sql, media, plugins, themes,
  wp-content) and are inferred from the file name when no type is
  given. An explicit but unrecognized type does not get inferred.
* Zero dependencies, Python 3.10 or newer.
