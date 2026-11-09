# Good first issues

Seeded issues for new contributors. File each one on GitHub with the
`good first issue` and `help wanted` labels.

## 1. Treat a full backup as covering all three components

Title: Count a full backup toward database, uploads, and plugins-themes

Description: Some backup plugins write one full-site archive instead
of three separate files. Today such an entry gets an
`unknown-component` warning and satisfies nothing. Add a recognized
type `full` (with alias `full-backup`) that counts as present for
all three required components, and make name inference recognize
common full backup names such as `site-full-2026-11-04.zip`.

Difficulty: easy

Acceptance criteria:

* A manifest with a single non-empty `full` entry passes with status
  PASS and no `missing-component` findings.
* A stale `full` entry still produces a `stale-backup` error.
* An empty `full` entry still produces an `empty-file` warning and
  still counts as missing for all three components.
* A test covers the full pass case and the empty full case.
* The rule is documented in the README rule list.

## 2. Warn when the newest backup per component is much older than the rest

Title: Warn on an uneven backup set

Description: A set can pass today while one component lags behind:
the database is from today but uploads are 6 days old. Add a warning
when the newest backup of one component is more than 3 days older
than the newest backup of another component, naming both components
and both dates. This is a warning only, so it never fails `--check`
on its own.

Difficulty: easy

Acceptance criteria:

* A set where uploads lag the database by more than 3 days gets an
  `uneven-backup-set` warning naming both components.
* A set where all components are within 3 days gets no such warning.
* A set with a missing component gets no such warning for that
  component (the missing error already covers it).
* A test covers the lag case and the even case.
* The rule is documented in the README rule list.

## 3. Add a --since flag that only audits backups after a date

Title: Add --since to ignore backups older than a given ISO date

Description: When checking a fresh backup run, old archives in the
same folder are noise. Add a `--since YYYY-MM-DD` flag that drops
entries modified before that date before auditing, so a folder with
old archives plus one fresh set can pass. The flag must accept the
same ISO formats as entry dates, and an invalid value must exit 2
with a clear message.

Difficulty: medium

Acceptance criteria:

* Running with `--since` on a folder with old and fresh backups
  audits only the fresh ones.
* A set whose only fresh backup is a database backup still reports
  missing uploads and plugins-themes.
* An invalid `--since` value exits 2 with an error message.
* Tests cover the filtering, the missing case, and the invalid value.
* The flag is documented in the README options table.

## 4. Support a directory as input, reading the files directly

Title: Accept a backup folder path and build the listing from disk

Description: Today the tool reads a manifest or listing file the
user prepared. Accept a directory path as input: read the files in
it, use each file name, its real size, and its real modification
time, and infer or read the component type the same way listing
input does. Hidden files and subdirectories must be skipped, and an
empty directory must report all three components missing.

Difficulty: medium

Acceptance criteria:

* A directory with a recent database, uploads, and plugins-themes
  file passes with status PASS.
* A directory with only a database file reports missing uploads and
  plugins-themes.
* Hidden files and subdirectories are skipped, not audited.
* An empty directory reports 3 `missing-component` errors.
* Tests cover the pass case, the partial case, and the empty case.
* The README documents directory input alongside manifest input.
