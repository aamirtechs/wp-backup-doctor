"""wp-backup-doctor: audit a WordPress backup set for age and completeness.

Input is either a JSON manifest or a plain text directory listing.
Each entry has a name, a size in bytes, a modified date in ISO format,
and a component type. The required components are database, uploads,
and plugins-themes. A backup set passes when every required component
has at least one entry and no entry is older than --max-age days.

Zero dependencies, Python 3.10 or newer. Run as a script or a module:

    python3 wp_backup_doctor.py examples/good-manifest.json
    python3 -m wp_backup_doctor examples/good-manifest.json --check
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

REQUIRED_COMPONENTS = ("database", "uploads", "plugins-themes")

TYPE_ALIASES = {
    "db": "database",
    "database": "database",
    "sql": "database",
    "database-backup": "database",
    "uploads": "uploads",
    "media": "uploads",
    "uploads-backup": "uploads",
    "plugins": "plugins-themes",
    "plugin": "plugins-themes",
    "themes": "plugins-themes",
    "theme": "plugins-themes",
    "plugins-themes": "plugins-themes",
    "plugins_themes": "plugins-themes",
    "wp-content": "plugins-themes",
}


class InputError(Exception):
    """Raised when the input cannot be parsed or an entry is invalid."""


@dataclass
class Entry:
    name: str
    size: int | None
    modified: datetime
    modified_text: str
    component: str | None
    raw_type: str | None = None


@dataclass
class Finding:
    rule: str
    severity: str
    message: str

    def as_dict(self):
        return {"rule": self.rule, "severity": self.severity, "message": self.message}


@dataclass
class Report:
    findings: list = field(default_factory=list)
    entries: list = field(default_factory=list)
    components: tuple = REQUIRED_COMPONENTS

    @property
    def errors(self):
        return sum(1 for f in self.findings if f.severity == "error")

    @property
    def warnings(self):
        return sum(1 for f in self.findings if f.severity == "warning")

    @property
    def status(self):
        if self.errors:
            return "FAIL"
        if self.warnings:
            return "WARN"
        return "PASS"

    def component_summary(self):
        summary = {}
        for component in self.components:
            members = [e for e in self.entries if e.component == component]
            newest = max((e.modified for e in members), default=None)
            summary[component] = {
                "entries": len(members),
                "newest": newest.isoformat() if newest else None,
                "present": bool(members),
            }
        return summary

    def as_dict(self, source):
        return {
            "file": source,
            "status": self.status,
            "errors": self.errors,
            "warnings": self.warnings,
            "findings": [f.as_dict() for f in self.findings],
            "components": self.component_summary(),
            "entry_count": len(self.entries),
        }


def parse_iso_date(text, where):
    """Parse an ISO date or datetime. Naive values are read as UTC."""
    if not isinstance(text, str) or not text.strip():
        raise InputError(f"{where}: modified date is missing or not a string")
    cleaned = text.strip()
    if cleaned.endswith(("Z", "z")):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        raise InputError(
            f"{where}: modified date is not a valid ISO date: {text!r}"
        ) from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def normalize_type(raw, where):
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None, None
    if not isinstance(raw, str):
        raise InputError(f"{where}: type must be a string, got {raw!r}")
    key = raw.strip().lower()
    return TYPE_ALIASES.get(key), raw.strip()


def infer_component(name):
    lowered = name.lower()
    if (
        "database" in lowered
        or lowered.endswith(".sql")
        or lowered.endswith(".sql.gz")
        or lowered.endswith(".sql.zip")
        or "-db-" in lowered
        or lowered.startswith("db-")
        or lowered.startswith("db_")
    ):
        return "database"
    if "uploads" in lowered:
        return "uploads"
    if "plugin" in lowered or "theme" in lowered:
        return "plugins-themes"
    return None


def build_entry(raw, where):
    if not isinstance(raw, dict):
        raise InputError(f"{where}: each entry must be an object")
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise InputError(f"{where}: entry name is missing or not a string")
    name = name.strip()
    size = raw.get("size")
    if size is not None:
        if isinstance(size, bool) or not isinstance(size, int):
            raise InputError(f"{where}: size for {name!r} must be an integer")
        if size < 0:
            raise InputError(f"{where}: size for {name!r} must not be negative")
    modified_raw = None
    for key in ("modified", "modified_date", "date", "mtime"):
        if key in raw:
            modified_raw = raw[key]
            break
    modified = parse_iso_date(modified_raw, where)
    modified_text = modified_raw.strip() if isinstance(modified_raw, str) else str(modified_raw)
    type_raw = None
    for key in ("type", "component", "kind"):
        if key in raw:
            type_raw = raw[key]
            break
    component, raw_type = normalize_type(type_raw, where)
    if component is None and type_raw is not None and str(type_raw).strip():
        component = None
    elif component is None:
        component = infer_component(name)
    return Entry(
        name=name,
        size=size,
        modified=modified,
        modified_text=modified_text,
        component=component,
        raw_type=raw_type,
    )


def parse_json_manifest(text, source):
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InputError(f"{source}: invalid JSON: {exc}") from None
    if isinstance(data, dict):
        for key in ("entries", "backups", "files"):
            if key in data:
                data = data[key]
                break
        else:
            raise InputError(
                f"{source}: JSON object must contain an 'entries' list"
            )
    if not isinstance(data, list):
        raise InputError(f"{source}: JSON manifest must be a list of entries")
    return [build_entry(raw, f"{source} entry {i}") for i, raw in enumerate(data)]


def parse_listing(text, source):
    entries = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) < 3:
            raise InputError(
                f"{source} line {line_no}: expected 'name size ISO-date [type]', "
                f"got: {line!r}"
            )
        name, size_text, date_text = parts[0], parts[1], parts[2]
        try:
            size = int(size_text)
        except ValueError:
            raise InputError(
                f"{source} line {line_no}: size is not an integer: {size_text!r}"
            ) from None
        if size < 0:
            raise InputError(
                f"{source} line {line_no}: size must not be negative"
            )
        modified = parse_iso_date(date_text, f"{source} line {line_no}")
        type_raw = parts[3] if len(parts) > 3 else None
        if len(parts) > 4:
            raise InputError(
                f"{source} line {line_no}: too many fields, expected at most "
                f"'name size ISO-date [type]', got: {line!r}"
            )
        component, raw_type = normalize_type(type_raw, f"{source} line {line_no}")
        if component is None and type_raw is None:
            component = infer_component(name)
        entries.append(
            Entry(
                name=name,
                size=size,
                modified=modified,
                modified_text=date_text,
                component=component,
                raw_type=raw_type,
            )
        )
    return entries


def parse_input(text, source):
    """Detect JSON by its first non-space character, else parse a listing."""
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return parse_json_manifest(text, source)
    return parse_listing(text, source)


def audit(entries, max_age_days, now, components=REQUIRED_COMPONENTS):
    """Audit entries. Returns a Report. Entries outside the filter are ignored."""
    if max_age_days < 0:
        raise InputError("--max-age must not be negative")
    wanted = tuple(components)
    kept = [e for e in entries if e.component in wanted or e.component is None]
    if len(wanted) == 1:
        kept = [e for e in entries if e.component == wanted[0]]
    report = Report(entries=kept, components=wanted)
    seen_names = {}
    for entry in kept:
        age_days = (now - entry.modified).total_seconds() / 86400
        if age_days > max_age_days:
            report.findings.append(
                Finding(
                    "stale-backup",
                    "error",
                    f"backup {entry.name!r} is older than max age "
                    f"{max_age_days} days (modified {entry.modified_text})",
                )
            )
        if entry.size == 0:
            report.findings.append(
                Finding(
                    "empty-file",
                    "warning",
                    f"backup {entry.name!r} is empty (0 bytes)",
                )
            )
        lowered = entry.name.lower()
        if lowered in seen_names:
            report.findings.append(
                Finding(
                    "duplicate-backup",
                    "warning",
                    f"backup {entry.name!r} is a duplicate of an earlier entry",
                )
            )
        else:
            seen_names[lowered] = entry
        if entry.component is None:
            report.findings.append(
                Finding(
                    "unknown-component",
                    "warning",
                    f"backup {entry.name!r} has no recognized component type, "
                    "so it does not count toward database, uploads, or "
                    "plugins-themes",
                )
            )
    for component in wanted:
        members = [e for e in kept if e.component == component]
        non_empty = [e for e in members if e.size != 0]
        if not non_empty:
            report.findings.append(
                Finding(
                    "missing-component",
                    "error",
                    f"no non-empty backup found for component {component!r}",
                )
            )
    return report


def render_text(report):
    lines = []
    for finding in report.findings:
        lines.append(f"{finding.severity.upper()} [{finding.rule}]: {finding.message}")
    if report.errors:
        lines.append(f"FAIL: {report.errors} error(s), {report.warnings} warning(s)")
    elif report.warnings:
        lines.append(f"WARN: 0 error(s), {report.warnings} warning(s)")
    else:
        lines.append("OK: backups pass all checks")
    return "\n".join(lines)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="wp-backup-doctor",
        description=(
            "Audit a WordPress backup folder listing for age and completeness."
        ),
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="-",
        help="JSON manifest or listing file, or '-' / omitted for stdin",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 on any error, 0 if only warnings or clean",
    )
    parser.add_argument(
        "--max-age",
        type=float,
        default=7,
        help="Maximum backup age in days (default: 7)",
    )
    parser.add_argument(
        "--component",
        choices=list(REQUIRED_COMPONENTS),
        default=None,
        help="Audit only one component: database, uploads, or plugins-themes",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.max_age < 0:
        print("error: --max-age must not be negative", file=sys.stderr)
        return 2
    source = args.input
    try:
        if source == "-":
            text = sys.stdin.read()
            source_label = "stdin"
        else:
            with open(source, "r", encoding="utf-8") as handle:
                text = handle.read()
            source_label = source
        entries = parse_input(text, source_label)
    except FileNotFoundError:
        print(f"error: input file not found: {source}", file=sys.stderr)
        return 2
    except (InputError, OSError, UnicodeDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    components = (args.component,) if args.component else REQUIRED_COMPONENTS
    try:
        report = audit(entries, args.max_age, datetime.now(timezone.utc), components)
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report.as_dict(source_label), indent=2))
    else:
        print(render_text(report))
    if args.check and report.errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
