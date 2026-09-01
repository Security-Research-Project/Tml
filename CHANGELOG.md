# Changelog

## Security
## v0.1.0

- GPG signature verification
  - Signatures are verified against pinned fingerprints stored in an isolated keyring at `~/.local/share/tml/gnupg`. The system keyring is never used.
  - If verification fails the download is deleted and the operation aborts.
  - Verification logs the fingerprint checked to aid troubleshooting.

- Key refresh and rotation
  - When a public-key issue is detected (e.g., `NO_PUBKEY`, `EXPKEYSIG`, or `REVKEYSIG`), the tool refreshes only the specific pinned fingerprint using `gpg --recv-keys` against `keys.openpgp.org`.
  - The tool does not perform broad `--refresh-keys` operations against an open keyserver pool to avoid the class of signature-flooding attacks documented in past incidents.
  - Key refresh is triggered only by legitimate key-rotation indicators, not by a generic bad signature.

- Safe archive extraction
  - Tar extraction defends against path traversal and malicious symlinks. Every extracted path is validated to remain inside the intended destination directory; symlinks are handled or rejected based on safe resolution rules.
  - Per-file size ceilings are enforced; extraction aborts if a file exceeds configured limits or if archive structure appears malicious.

- HTTPS-only networking
  - The default plain-HTTP transport adapter has been removed from the request session. Redirects to `http://` now fail rather than silently downgrading the connection.
  - TLS validation and strict host verification are enforced for network requests.

- Privacy
  - No telemetry, analytics, or tracking is collected by the application.
  - The `User-Agent` header contains only the application name and version; no unique identifiers are sent.

### Known limitations and operational notes

- Browser detection: the tool does not attempt to detect browsers installed by other means than Tml (deliberate design choice; see `DEVELOPMENT.md` for rationale).
- Keyserver availability: key refresh depends on `keys.openpgp.org`. In environments where that service is blocked or unavailable, manual key management may be required.
- Conservative extraction limits: strict per-file size limits and symlink checks can reject unusually large or uncommon-but-legitimate archives; these limits are configurable.
- No absolute guarantees: these mitigations substantially reduce common attack vectors but do not eliminate all risk. Follow standard operational security practices (verify sources, use up-to-date dependencies, test upgrades in a controlled environment).
