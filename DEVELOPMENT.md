# Development Guide

Reference documentation for working on Tml. `README.md` (shipped with
the app) covers what Tml does and how to install it; this document
covers how it's built and how to verify that claim yourself.

## Design decisions

A few choices that look like gaps are deliberate:

- **No install-detection heuristics.** Tml does not scan for browsers
  installed some other way (PATH, desktop entries, distro packages).
  Earlier attempts at this produced confident-looking but unreliable
  results. The GUI states this limitation directly rather than guessing.
- **No auto-update loop.** Version checks happen only when the user
  clicks Install or Check for Updates. Nothing polls in the background.
- **One official source per browser, no mirrors, no fallback chain.**
  A source change is a deliberate edit to `browsers/*.py`, not runtime
  logic.
  
## Security model

Verified properties of the current codebase, not just design intent:

| Property | Where enforced |
|---|---|
| Downloads use HTTPS only; a redirect to plain HTTP fails instead of silently downgrading | `network.py` (`get_session()` removes the default `http://` adapter) |
| TLS verification cannot be disabled, only pointed at an alternate CA bundle | `network.py` (`_verify_arg()` never returns `False`) |
| Every install is checked against a hardcoded GPG fingerprint in an isolated keyring, never the system's default | `config.py` (`FPR_TORPROJECT`, `FPR_LIBREWOLF`), `verify.py` |
| A failed GPG check deletes the download; nothing unverified is ever extracted | `verify.py`, `installer.py` |
| Tar extraction is guarded against path traversal and malicious symlinks, with a per-file size ceiling | `installer.py` |
| Privileged operations (`apparmor.py`) use `pkexec` exclusively, with plain argv lists, never a shell string | `apparmor.py` |
| No telemetry, analytics, or tracking of any kind | verified by source grep, not an SDK to disable |
| `User-Agent` identifies the app and version only, no device or install identifier | `config.py` (`USER_AGENT`) |
| Sources are official vendor domains only, no mirrors | `browsers/tor.py`, `browsers/mullvad.py`, `browsers/librewolf.py` |
| Version metadata is not the trust boundary for any download | GPG signature verification (`verify.py`) is what's actually checked, regardless of which URL or CDN a release's own metadata points to |

`browsers/tor.py` parses an XML version feed from a pinned, HTTPS-only,
official Tor Project domain with the standard library's
`xml.etree.ElementTree`, capped at 200KB by `network.fetch_bytes`'s
`max_bytes`. Reviewed for XML entity-expansion risk: Python's bundled
Expat parser (3.9+, this project's floor) has built-in amplification
limits, and `ElementTree` does not resolve external entities by
default. No additional XML-hardening dependency was added; the
practical risk is already low given the endpoint is pinned and
HTTPS-verified, and the actual browser download is independently
GPG-verified regardless of what this feed says.

**Key fingerprints** (`config.py`):

| Project | Fingerprint | Covers |
|---|---|---|
| Tor Project | `EF6E286DDA85EA2A4BA7DE684E2C6E8793298290` | Tor Browser, Mullvad Browser (same signing key) |
| LibreWolf | `662E3CDD6FE329002D0CA5BB40339DD82B12EF16` | LibreWolf |

**Key refresh, compared against a real historical incident:**
`torbrowser-launcher` was affected by the 2019 SKS-keyserver signature-flooding
attack: a broad `--refresh-keys` against old-style SKS pool servers let
an attacker attach an unbounded number of signatures to a public key,
corrupting or crashing the refresh (`gpg: error writing keyring:
Provided object is too large`, a real reported failure mode). `verify.py`'s
`refresh_key()` avoids this class of issue by construction: it fetches
one specific fingerprint (`--recv-keys <fingerprint>`, never
`--refresh-keys`) from `keys.openpgp.org`, a keyserver that verifies UID
ownership and does not accept arbitrary third-party signature flooding.
Key refresh is also only triggered by `NO_PUBKEY`, `EXPKEYSIG`, or
`REVKEYSIG` - legitimate rotation cases - never by a bad signature
itself, so a genuinely tampered download cannot trigger a refresh-and-retry
loophole.

## Known limitations

- No install-detection for browsers installed outside Tml (deliberate;
  see "Design decisions").

