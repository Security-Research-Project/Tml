# Security Policy

Tml downloads and runs third-party browser binaries. Its own attack
surface is deliberately small: GPG signature verification, safe tar
extraction, and an isolated keyring. See README.md "Security model" for
the full design.

## Reporting a vulnerability

Do not open a public issue for a security vulnerability. Instead, contact
the maintainers privately and include:

- A description of the issue and its impact
- Steps to reproduce
- Affected version/commit

Allow a reasonable amount of time for a response and a fix before any
public disclosure.

## Scope

In scope: GPG verification bypass, tar-extraction path traversal, keyring
isolation failures, sandbox escapes in the generated AppArmor profile, and
any way a malicious download source could result
in unverified code being extracted or executed.

Out of scope: vulnerabilities in Tor Browser, Mullvad Browser, or
LibreWolf themselves - report those to the respective upstream projects.
declined, etc.
