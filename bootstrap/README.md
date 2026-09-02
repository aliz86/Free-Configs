# bootstrap/

**This directory has nothing to do with the proxy configs.** Nothing here
affects `configs.txt`, `sources.txt`, the health check, or your subscription
link. If you came here for those, you want the [root README](../README.md).

## What it is

A mirrored copy of the small JSON document
[My Mom Messenger](https://github.com/aliz86/MyMomMessenger) reads before every
connect, listing the signaling servers it may use.

- `endpoints.json` — the published copy. This is the file the app fetches.
- `source.txt` — where `scripts/bootstrap.py` fetches it from.
- Refreshed by the daily *Build subscription* workflow, in the same run that
  rebuilds the node list.

## Why it lives in this repository

The app normally reads that document from a Google Cloud Function. In a country
that blocks `*.cloudfunctions.net`, it can't — and an app whose only address is
blocked is an app that is simply broken until an update ships through two app
store review queues, which is days at best.

What it needs instead is somewhere else to read the *same* document. This
repository already publishes files on a daily schedule through four independent
public CDN fronts:

```
https://raw.githubusercontent.com/aliz86/Free-Configs/main/bootstrap/endpoints.json
https://cdn.jsdelivr.net/gh/aliz86/Free-Configs@main/bootstrap/endpoints.json
https://cdn.statically.io/gh/aliz86/Free-Configs/main/bootstrap/endpoints.json
https://raw.githack.com/aliz86/Free-Configs/main/bootstrap/endpoints.json
```

None of those is unblockable. The point is that they are blocked *separately*,
by different lists, and that they serve far too much unrelated traffic to be
null-routed casually — the same property that makes this repository's own
subscription link work from inside Iran. A network that has all four is rarer
than a network that has one.

The app carries the same four URLs for a second repository
([Serverless-for-Iran](https://github.com/aliz86/Serverless-for-Iran)), so a
takedown or a rename here doesn't take the whole out-of-band channel with it.

## What is in the file, and what isn't

Hostnames: Realtime Database instances, HTTPS relay origins, public STUN
servers. Nothing secret — the app would reveal these on its first packet anyway.

**No credentials.** The live directory only mints TURN credentials for an
authenticated caller, so an anonymous fetch should never see one; `bootstrap.py`
strips the ICE block down to its URLs regardless, because this file is public and
permanent in git history and a credential committed by accident cannot be
unpublished.

## Failure is quiet on purpose

If the fetch fails, or returns something that isn't a valid directory — a captive
portal's login page, an ISP block notice, a 200 that is anything other than the
document — the script leaves the committed copy alone and the workflow carries on
green. A missed update is invisible to the app: it merges this file with
everything else it knows rather than replacing anything, so yesterday's endpoint
list still works. A corrupted one would break the fallback this exists to be.

## Running it by hand

```bash
python scripts/bootstrap.py
```

Environment overrides: `BOOTSTRAP_SOURCES` (URLs, comma- or space-separated) and
`BOOTSTRAP_OUTPUT` (where to write). The script prints what it fetched, what it
rejected and why.

## Turning it off

Delete this directory and the *Mirror the connect directory* step from
`.github/workflows/build.yml`. The subscription build is unaffected — it never
reads anything here.
