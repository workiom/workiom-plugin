#!/usr/bin/env python3
"""
vibe-pack — validate a vibe app bundle and assemble the zip.

Usage:
    vibe-pack.py <source-dir> [-o out.zip]     validate folder, write zip
    vibe-pack.py <existing.zip> --check        validate a zip someone else made
    vibe-pack.py <source-dir> --json           validate, print the files map

Exit 0 = valid (zip written if input was a folder). Exit 1 = violations listed.

--json prints the bundle as {"path": "content"} on stdout, ready to hand to the
create_vibe_app / add_vibe_version MCP tools. Nothing is written to disk and no
zip is made: the tools take the files themselves, and round-tripping a binary
through a tool call would cost context for nothing. Diagnostics go to stderr so
stdout stays parseable.

This is the executable form of the Phase-1 self-check: everything vibe-admin
will reject, plus the HTML-content rules the Worker cannot see (asset paths,
innerHTML, external resources). Passing here means the upload will be accepted
AND the page won't be broken by the CSP or the trailing-slash asset rules.
"""

import base64, io, json, os, re, sys, zipfile, argparse

MAX_FILES = 200
MAX_FILE = 5 * 1024 * 1024
MAX_TOTAL = 25 * 1024 * 1024
MAX_PATH = 255
ALLOWED_EXT = {"html","css","js","json","svg","png","jpg","jpeg","webp",
               "gif","ico","woff","woff2","txt","map"}
PATH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")

# HTML/JS content rules — each maps to a deployed constraint.
CONTENT_RULES = [
    # (pattern, flags, message)
    (r'(?:src|href)\s*=\s*["\']/(?!/)',
     re.I,
     "root-relative asset path (leading /) — resolves outside the app and 404s; use relative paths"),
    (r'<base\b',
     re.I,
     "<base> tag — CSP sets base-uri 'none'; it is silently ignored"),
    (r'(?:src|href)\s*=\s*["\']https?://(?!api\.workiom\.com)',
     re.I,
     "external resource — CSP is default-src 'none'; CDN/scripts/fonts will not load"),
    (r'\.innerHTML\s*=\s*(?!["\']\s*["\'])',
     0,
     "innerHTML assignment with non-empty value — XSS risk; use textContent/createElement"),
    (r'\blocalStorage\b|\bsessionStorage\b',
     0,
     "browser storage — not permitted in vibe apps; keep state in JS variables"),
    (r'\beval\s*\(|\bnew\s+Function\s*\(',
     0,
     "eval / new Function — not permitted"),
    (r'url\(\s*["\']?/(?!/)',
     re.I,
     "root-relative url() in CSS — same trailing-slash problem as src=\"/\""),
]

# Softer signals worth a warning, not a failure.
WARN_RULES = [
    (r'console\.log\([^)]*[Tt]oken', 0,
     "possible token logging — the auth token must never appear in console output"),
    (r'Abp\.AuthToken', 0,
     "token cookie referenced — fine if only inside getCookie/workiomHeaders; verify it is never displayed or logged"),
]

TEXT_EXT = {"html","css","js","json","svg","txt","map"}


def ext_of(path):
    i = path.rfind(".")
    return path[i+1:].lower() if i != -1 else ""


def validate_entries(entries):
    """entries: list of (path, bytes). Returns (errors, warnings)."""
    errors, warnings = [], []

    if not entries:
        return ["bundle is empty"], []
    if len(entries) > MAX_FILES:
        errors.append(f"too many files: {len(entries)} (max {MAX_FILES})")

    seen = set()
    total = 0
    paths = [p for p, _ in entries]

    if "index.html" not in paths:
        errors.append("index.html missing at bundle root (required)")

    for path, data in entries:
        where = f"[{path}]"
        if len(path) > MAX_PATH:
            errors.append(f"{where} path exceeds {MAX_PATH} chars")
        if "\\" in path:
            errors.append(f"{where} backslash in path — use forward slashes")
        if path.startswith("/"):
            errors.append(f"{where} absolute path")
        if any(seg in ("", ".", "..") for seg in path.split("/")):
            errors.append(f"{where} invalid path segment ('..', '.', or empty)")
        if not PATH_RE.match(path):
            errors.append(f"{where} disallowed characters (allowed: A-Z a-z 0-9 . _ / -)")
        if path in seen:
            errors.append(f"{where} duplicate path")
        seen.add(path)

        e = ext_of(path)
        if e not in ALLOWED_EXT:
            errors.append(f"{where} extension '.{e}' not allowed "
                          f"(allowed: {' '.join(sorted(ALLOWED_EXT))})")

        if len(data) > MAX_FILE:
            errors.append(f"{where} {len(data):,} bytes exceeds per-file max {MAX_FILE:,}")
        total += len(data)

        # Content lint on text files
        if e in TEXT_EXT:
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                errors.append(f"{where} not valid UTF-8")
                continue
            for pattern, flags, msg in CONTENT_RULES:
                for m in re.finditer(pattern, text, flags):
                    line = text.count("\n", 0, m.start()) + 1
                    errors.append(f"{where}:{line} {msg}")
            for pattern, flags, msg in WARN_RULES:
                for m in re.finditer(pattern, text, flags):
                    line = text.count("\n", 0, m.start()) + 1
                    warnings.append(f"{where}:{line} {msg}")

    if total > MAX_TOTAL:
        errors.append(f"bundle total {total:,} bytes exceeds max {MAX_TOTAL:,}")

    return errors, warnings


def entries_from_dir(root):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in filenames:
            if fn.startswith("."):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            with open(full, "rb") as f:
                out.append((rel, f.read()))
    return sorted(out)


def entries_from_zip(path):
    out = []
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            out.append((info.filename, z.read(info)))
    return sorted(out)


def write_zip(entries, out_path):
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for path, data in entries:
            z.writestr(path, data)


def files_map(entries):
    """Bundle as {path: content} for the MCP tools.

    Text files stay readable; binaries are base64. Extension decides which, matching
    decodeAndValidateVibeFiles in the MCP server so neither side needs an encoding flag.
    """
    out = {}
    for path, data in entries:
        if ext_of(path) in TEXT_EXT:
            out[path] = data.decode("utf-8")
        else:
            out[path] = base64.b64encode(data).decode("ascii")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help="source folder, or an existing zip with --check")
    ap.add_argument("-o", "--output", help="output zip path (default: <folder-name>.zip)")
    ap.add_argument("--check", action="store_true", help="validate only, write nothing")
    ap.add_argument("--json", action="store_true",
                    help="print the files map for the MCP tools instead of writing a zip")
    args = ap.parse_args()

    # stdout carries the payload under --json, so every diagnostic goes to stderr.
    out_stream = sys.stderr if args.json else sys.stdout

    if os.path.isdir(args.source):
        entries = entries_from_dir(args.source)
        default_out = os.path.basename(os.path.abspath(args.source)) + ".zip"
    elif zipfile.is_zipfile(args.source):
        entries = entries_from_zip(args.source)
        args.check = True  # a zip input is always check-only
        default_out = None
    else:
        print(f"error: {args.source} is neither a directory nor a zip", file=out_stream)
        sys.exit(2)

    errors, warnings = validate_entries(entries)

    for w in warnings:
        print(f"  WARN  {w}", file=out_stream)
    for e in errors:
        print(f"  FAIL  {e}", file=out_stream)

    total = sum(len(d) for _, d in entries)
    print(f"\n{len(entries)} files, {total:,} bytes decoded"
          f" (~{int(total*1.34):,} as base64 upload)", file=out_stream)

    if errors:
        print(f"\nINVALID — {len(errors)} violation(s). Nothing written.", file=out_stream)
        sys.exit(1)

    if args.json:
        print("\nVALID — files map on stdout.", file=out_stream)
        json.dump(files_map(entries), sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        sys.exit(0)

    if args.check:
        print("\nVALID.")
        sys.exit(0)

    out = args.output or default_out
    write_zip(entries, out)
    print(f"\nVALID — wrote {out}")
    sys.exit(0)


if __name__ == "__main__":
    main()
