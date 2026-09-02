"""Publish a mirrored copy of My Mom Messenger's connect directory.

    python scripts/bootstrap.py

Unrelated to the proxy configs this repository is otherwise about, and it does
not touch them. It borrows one thing from this repository: the fact that its
files are already published, on a daily schedule, through four independent
public CDN fronts (raw.githubusercontent.com, jsDelivr, Statically, raw.githack)
that are widely reachable from Iran.

## What it is for

My Mom Messenger fetches a small JSON document before every connect that lists
the signaling servers it may use. Normally that comes from a Cloud Function.
When the function's hostname is blocked -- which is the situation the whole
mechanism exists for -- the app needs somewhere else to read the same document,
and "a static file on a code-hosting CDN" is about the most durable answer
available: those hosts serve far too much unrelated traffic to null-route
casually, and there are several of them, blocked by different lists.

So this fetches the live directory and commits it. The app's copy is then at
most a day old, which is fine: a stale endpoint list still beats no endpoint
list, and the app merges it with everything else it knows rather than replacing
anything.

## What it will not do

Overwrite a good file with a bad fetch. Every response is validated (schema
version, at least one usable endpoint, sane size) and anything that fails --
including the block page a censored network returns with a cheerful 200 -- leaves
the committed copy untouched. A missing update is invisible to the app; a
corrupted one would take out the fallback it exists to be.

It also strips any credential from the ICE block before writing. The live
directory only mints those for an authenticated caller, so an anonymous fetch
should never see one; this file is public and permanent in git history, so
"should never" is not a good enough reason to skip the check.

Environment overrides:
    BOOTSTRAP_SOURCES  one or more URLs (comma- or whitespace-separated),
                       overriding bootstrap/source.txt.
    BOOTSTRAP_OUTPUT   where endpoints.json is written
                       (default: bootstrap/endpoints.json)
"""

from __future__ import annotations

import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES_FILE = os.path.join(REPO_ROOT, "bootstrap", "source.txt")
OUTPUT_FILE = os.environ.get(
    "BOOTSTRAP_OUTPUT", os.path.join(REPO_ROOT, "bootstrap", "endpoints.json")
)

# Kept in step with SCHEMA in the app's functions/signalingDirectory.js. A
# document from a schema this script doesn't know is refused rather than
# published: the app would ignore it anyway, and publishing it would replace a
# copy the app *can* use with one it can't.
SCHEMA = 1

# A directory is a few hundred bytes. Anything remotely near this is not one.
MAX_BYTES = 64 * 1024

FETCH_ATTEMPTS = 3
FETCH_TIMEOUT = 30

# Same retry class as build.py: HTTPException covers IncompleteRead and
# BadStatusLine, which are not OSError subclasses, and a truncated response is
# the likeliest transient failure here.
TRANSIENT = (urllib.error.URLError, http.client.HTTPException, OSError)


def sources() -> list[str]:
    """URLs to try, in order, from the environment or bootstrap/source.txt."""
    override = os.environ.get("BOOTSTRAP_SOURCES") or os.environ.get("BOOTSTRAP_SOURCE")
    if override:
        return [url for url in override.replace(",", " ").split() if url]

    if not os.path.exists(SOURCES_FILE):
        return []
    with open(SOURCES_FILE, encoding="utf-8") as handle:
        return [
            line.strip()
            for line in handle
            if line.strip() and not line.lstrip().startswith("#")
        ]


def fetch(url: str) -> bytes | None:
    """Fetches [url], retrying transient failures. None when it never answered."""
    for attempt in range(1, FETCH_ATTEMPTS + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Free-Configs-bootstrap/1.0",
                    "Cache-Control": "no-cache",
                },
            )
            with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as response:
                # Bounded read: a block page can be arbitrarily large, and
                # nothing past the ceiling could be a directory anyway.
                return response.read(MAX_BYTES + 1)
        except TRANSIENT as error:
            print(f"  attempt {attempt}/{FETCH_ATTEMPTS} failed: {error}")
            if attempt < FETCH_ATTEMPTS:
                time.sleep(2 * attempt)
    return None


def validate(raw: bytes) -> dict | None:
    """The parsed directory, or None if [raw] isn't one.

    Deliberately strict. This is the one gate between "whatever the network
    handed back" and a file the app will trust, and the failure it has to catch
    is not malformed JSON -- it is a perfectly well-formed 200 that isn't the
    document, which is what a censored network usually returns.
    """
    if raw is None or len(raw) > MAX_BYTES:
        print("  rejected: response missing or over the size ceiling")
        return None
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        print(f"  rejected: not JSON ({error})")
        return None
    if not isinstance(document, dict):
        print("  rejected: not a JSON object")
        return None
    if document.get("schema") != SCHEMA:
        print(f"  rejected: schema {document.get('schema')!r}, expected {SCHEMA}")
        return None

    endpoints = document.get("signaling")
    if not isinstance(endpoints, list):
        print("  rejected: no signaling list")
        return None
    usable = [
        entry
        for entry in endpoints
        if isinstance(entry, dict) and str(entry.get("url", "")).strip()
    ]
    if not usable:
        print("  rejected: no usable endpoint")
        return None
    return document


def strip_credentials(document: dict) -> dict:
    """Removes anything credential-shaped from the ICE block.

    The live directory only mints TURN credentials for an authenticated caller,
    so an anonymous fetch should never receive one. But this file is public and
    lands in git history permanently, and a credential committed by accident
    cannot be unpublished -- so the ICE entries are rewritten to their URLs
    alone. The app treats a directory carrying no credentialed relay as "told me
    nothing about relays" and keeps its own bundled pool, which is exactly right
    for a mirrored copy.
    """
    ice = document.get("ice")
    if not isinstance(ice, list):
        return document
    document["ice"] = [
        {"urls": entry.get("urls", [])}
        for entry in ice
        if isinstance(entry, dict) and entry.get("urls")
    ]
    return document


def main() -> int:
    urls = sources()
    if not urls:
        print("No bootstrap source configured; see bootstrap/README.md.")
        return 0

    document = None
    for url in urls:
        print(f"Fetching {url}")
        document = validate(fetch(url))
        if document is not None:
            print("  ok")
            break

    if document is None:
        # Not an error. The committed copy stays as it is, the app keeps using
        # it, and tomorrow's run tries again. Failing the build here would turn
        # an unreachable third-party URL into a red workflow on a repository
        # whose actual job is something else entirely.
        print("No source produced a usable directory; leaving the published copy alone.")
        return 0

    document = strip_credentials(document)
    serialized = json.dumps(document, indent=2, sort_keys=True) + "\n"

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    previous = None
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, encoding="utf-8") as handle:
            previous = handle.read()
    if previous == serialized:
        print(f"{os.path.relpath(OUTPUT_FILE, REPO_ROOT)} unchanged.")
        return 0

    with open(OUTPUT_FILE, "w", encoding="utf-8") as handle:
        handle.write(serialized)
    endpoints = len(document.get("signaling", []))
    print(f"Wrote {os.path.relpath(OUTPUT_FILE, REPO_ROOT)} ({endpoints} endpoints).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
