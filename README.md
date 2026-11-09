# wp-backup-doctor
**Live tool:** https://aamirtechs.github.io/wp-backup-doctor/ (runs in your browser, no install)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/aamirtechs/wp-backup-doctor/blob/main/LICENSE) [![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/aamirtechs/wp-backup-doctor/issues)

A zero-dependency Python CLI that audits a WordPress backup set for
age and completeness, offline, before you find out the hard way that
a restore is missing a piece. It reads a backup folder listing, a
JSON manifest or a plain text listing file, and checks that the set
has a database backup, an uploads backup, and a plugins/themes
backup, that none of them is stale, and that none of them is empty
or duplicated.

A backup folder that looks full can still fail a restore: the
uploads archive is missing, the only database dump is two weeks
old, or the plugins archive is 0 bytes because the backup job died
halfway through. This tool catches all three before you need the
restore, and it doubles as a CI gate with `--check`.

## Install

Requires Python 3.10 or newer. No dependencies beyond the standard library.

```bash
pip install wp-backup-doctor
```

Or run it straight from the source checkout:

```bash
python3 wp_backup_doctor.py examples/good-manifest.json
```

It also runs as a module:

```bash
python3 -m wp_backup_doctor examples/good-manifest.json
```

## Input formats

JSON manifest: a list of entries, or an object with an `entries`,
`backups`, or `files` list. Each entry has a `name`, a `size` in
bytes, a `modified` date in ISO format, and a `type`. The date and
type keys also accept `modified_date`, `date`, and `mtime`, and
`component` or `kind` in place of `type`.

`examples/good-manifest.json`:

```json
[
    {
        "modified": "2026-11-04T02:15:00+00:00",
        "name": "example-com-db-2026-11-04.sql.gz",
        "size": 48291344,
        "type": "database"
    },
    {
        "modified": "2026-11-04T02:20:00+00:00",
        "name": "example-com-uploads-2026-11-04.zip",
        "size": 312884120,
        "type": "uploads"
    },
    {
        "modified": "2026-11-04T02:18:00+00:00",
        "name": "example-com-plugins-themes-2026-11-04.zip",
        "size": 87452110,
        "type": "plugins-themes"
    }
]
```

Plain text listing: one entry per line, `name size ISO-date [type]`.
Lines starting with `#` and blank lines are ignored.
`examples/good-listing.txt` holds the same three backups in this
format.

Component types: `database` (aliases `db`, `sql`), `uploads`
(alias `media`), and `plugins-themes` (aliases `plugins`,
`themes`, `wp-content`). When no type is given, the component is
inferred from the file name: a `.sql` name or a name containing
`database` counts as database, a name containing `uploads` counts
as uploads, and a name containing `plugin` or `theme` counts as
plugins-themes. An explicit but unrecognized type is not inferred;
it gets an `unknown-component` warning and satisfies nothing.

Dates must be ISO: a plain date such as `2026-11-04`, a datetime
with a timezone, or a datetime ending in `Z`. A datetime with no
timezone is read as UTC.

## Usage

Audit a manifest or listing:

```bash
python3 wp_backup_doctor.py examples/good-manifest.json
```

Audit from stdin (omit the argument, or pass `-`):

```bash
cat examples/good-manifest.json | python3 wp_backup_doctor.py -
```

Gate a CI job on it (exit 1 on any error, exit 0 if only warnings
or clean):

```bash
python3 wp_backup_doctor.py examples/good-manifest.json --check
```

Allow older backups, for example a monthly archive folder:

```bash
python3 wp_backup_doctor.py backups.json --max-age 30
```

Audit only one component:

```bash
python3 wp_backup_doctor.py backups.json --component database
```

Emit JSON instead of text:

```bash
python3 wp_backup_doctor.py examples/good-manifest.json --json
```

## Captured output: a healthy backup set

```bash
python3 wp_backup_doctor.py examples/good-manifest.json
```

Captured output:

```
OK: backups pass all checks
```

The same set passes the CI gate:

```bash
python3 wp_backup_doctor.py examples/good-manifest.json --check
```

Captured output (exit code 0):

```
OK: backups pass all checks
```

The plain text listing of the same set passes too:

```bash
python3 wp_backup_doctor.py examples/good-listing.txt
```

Captured output:

```
OK: backups pass all checks
```

## Captured output: a broken backup set

`examples/bad-manifest.json` has a stale database backup listed
twice, no uploads backup at all, and a plugins/themes backup that
is 0 bytes. Because an empty file does not count as a backup, the
set is also missing plugins-themes, not just uploads.

```bash
python3 wp_backup_doctor.py examples/bad-manifest.json
```

Captured output:

```
ERROR [stale-backup]: backup 'example-com-db-2026-10-20.sql.gz' is older than max age 7 days (modified 2026-10-20T02:15:00+00:00)
ERROR [stale-backup]: backup 'example-com-db-2026-10-20.sql.gz' is older than max age 7 days (modified 2026-10-20T02:15:00+00:00)
WARNING [duplicate-backup]: backup 'example-com-db-2026-10-20.sql.gz' is a duplicate of an earlier entry
WARNING [empty-file]: backup 'example-com-plugins-themes-2026-11-04.zip' is empty (0 bytes)
ERROR [missing-component]: no non-empty backup found for component 'uploads'
ERROR [missing-component]: no non-empty backup found for component 'plugins-themes'
FAIL: 4 error(s), 2 warning(s)
```

Without `--check`, that run still exits 0, so a report never breaks
a script that did not ask for gating. With `--check` it exits 1:

```bash
python3 wp_backup_doctor.py examples/bad-manifest.json --check
```

Captured output (exit code 1): the same 4 errors and 2 warnings,
ending in `FAIL: 4 error(s), 2 warning(s)`.

```bash
python3 wp_backup_doctor.py examples/bad-manifest.json --json
```

Captured output:

```
{
  "file": "examples/bad-manifest.json",
  "status": "FAIL",
  "errors": 4,
  "warnings": 2,
  "findings": [
    {
      "rule": "stale-backup",
      "severity": "error",
      "message": "backup 'example-com-db-2026-10-20.sql.gz' is older than max age 7 days (modified 2026-10-20T02:15:00+00:00)"
    },
    {
      "rule": "stale-backup",
      "severity": "error",
      "message": "backup 'example-com-db-2026-10-20.sql.gz' is older than max age 7 days (modified 2026-10-20T02:15:00+00:00)"
    },
    {
      "rule": "duplicate-backup",
      "severity": "warning",
      "message": "backup 'example-com-db-2026-10-20.sql.gz' is a duplicate of an earlier entry"
    },
    {
      "rule": "empty-file",
      "severity": "warning",
      "message": "backup 'example-com-plugins-themes-2026-11-04.zip' is empty (0 bytes)"
    },
    {
      "rule": "missing-component",
      "severity": "error",
      "message": "no non-empty backup found for component 'uploads'"
    },
    {
      "rule": "missing-component",
      "severity": "error",
      "message": "no non-empty backup found for component 'plugins-themes'"
    }
  ],
  "components": {
    "database": {
      "entries": 2,
      "newest": "2026-10-20T02:15:00+00:00",
      "present": true
    },
    "uploads": {
      "entries": 0,
      "newest": null,
      "present": false
    },
    "plugins-themes": {
      "entries": 1,
      "newest": "2026-11-04T02:18:00+00:00",
      "present": true
    }
  },
  "entry_count": 3
}
```

## Captured output: --max-age and --component

Raising the age limit clears the stale errors, but the missing
components remain:

```bash
python3 wp_backup_doctor.py examples/bad-manifest.json --max-age 30
```

Captured output:

```
WARNING [duplicate-backup]: backup 'example-com-db-2026-10-20.sql.gz' is a duplicate of an earlier entry
WARNING [empty-file]: backup 'example-com-plugins-themes-2026-11-04.zip' is empty (0 bytes)
ERROR [missing-component]: no non-empty backup found for component 'uploads'
ERROR [missing-component]: no non-empty backup found for component 'plugins-themes'
FAIL: 2 error(s), 2 warning(s)
```

Filtering to one component audits only that component:

```bash
python3 wp_backup_doctor.py examples/bad-manifest.json --component database
```

Captured output:

```
ERROR [stale-backup]: backup 'example-com-db-2026-10-20.sql.gz' is older than max age 7 days (modified 2026-10-20T02:15:00+00:00)
ERROR [stale-backup]: backup 'example-com-db-2026-10-20.sql.gz' is older than max age 7 days (modified 2026-10-20T02:15:00+00:00)
WARNING [duplicate-backup]: backup 'example-com-db-2026-10-20.sql.gz' is a duplicate of an earlier entry
FAIL: 2 error(s), 1 warning(s)
```

## Captured output: bad input

A missing file, bad JSON, a bad date, a negative size, or a missing
name exits 2 with a message on stderr naming the problem:

```bash
python3 wp_backup_doctor.py /nonexistent.json
```

Captured output on stderr (exit code 2):

```
error: input file not found: /nonexistent.json
```

A manifest entry with a non-ISO date, read from stdin:

```bash
printf '[{"name":"x.sql","size":1,"modified":"not-a-date","type":"database"}]' | python3 wp_backup_doctor.py -
```

Captured output on stderr (exit code 2):

```
error: stdin entry 0: modified date is not a valid ISO date: 'not-a-date'
```

## Options

| Flag | Meaning |
| --- | --- |
| `input` | JSON manifest or listing file, or `-` / omitted for stdin |
| `--json` | Emit JSON instead of text |
| `--check` | Exit 1 on any error, 0 if only warnings or clean |
| `--max-age` | Maximum backup age in days (default: 7) |
| `--component` | Audit only one component: database, uploads, or plugins-themes |

Exit codes: 0 for a passing report, or for any report without
`--check`; 1 with `--check` when any error is present; 2 for a
usage or input error (missing file, bad JSON, bad date, bad size,
bad `--component`, or a negative `--max-age`).

## Rule list

### Errors

| Rule | Check |
| --- | --- |
| `missing-component` | A required component has no non-empty backup: database, uploads, or plugins-themes |
| `stale-backup` | A backup is older than `--max-age` days (default 7) |

### Warnings

| Rule | Check |
| --- | --- |
| `empty-file` | A backup is 0 bytes; it also does not count toward its component |
| `duplicate-backup` | A backup name repeats an earlier entry, compared case-insensitively |
| `unknown-component` | An entry has no recognized type and its name matches no known component, so it satisfies nothing |

With `--check`, only errors fail the gate. Warnings alone still
exit 0, so a duplicate or an empty extra file is reported but does
not block a run that asked only for missing or stale failures. An
empty file that is the only backup for its component still fails,
because that component is then missing.

## Edge cases

* Age is measured against the current UTC time, so a backup dated
  today in any timezone is fresh, and a naive datetime is read as UTC.
* A backup exactly `--max-age` days old is not stale; only older
  ones are flagged.
* Duplicate detection compares names case-insensitively, so
  `Db.sql.gz` and `db.SQL.gz` count as duplicates.
* An empty plugins/themes file in the bad example produces both an
  `empty-file` warning and a `missing-component` error, because an
  empty file is not a usable backup.
* A JSON manifest may be a bare list or an object with `entries`,
  `backups`, or `files`. Input format is detected from content, not
  from the file extension: content starting with `{` or `[` is
  parsed as JSON, anything else as a listing.
* A manifest read from stdin reports its file as `stdin` in JSON output.
* With `--component`, entries for other components are ignored
  entirely, including their stale, empty, and duplicate findings.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

25 tests, all passing: a good manifest passes, missing components,
an empty manifest, stale backups, the `--max-age` override, empty
files, case-insensitive duplicates, type aliases, name inference,
unknown types, ISO date forms, listing parsing, bad JSON, bad dates,
negative sizes, missing names, `--check` exit codes for good, bad,
and warnings-only sets, `--component` filtering, JSON output shape,
stdin input, and the exit code 2 for a missing file and a negative
`--max-age`. The CLI tests build their manifests from the current
date, so they do not rot as the bundled examples age; the bundled
examples are dated 2026-11-04 and 2026-10-20.

## License

MIT. See [LICENSE](LICENSE).
