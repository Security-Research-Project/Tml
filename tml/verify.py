import hashlib
import logging
import os
import shutil
import subprocess

import requests

from . import config

log = logging.getLogger("tml.verify")


class VerificationError(Exception):
    pass


def _gpg_base_cmd():
    return [
        "gpg",
        "--batch",
        "--yes",
        "--status-fd", "1",
        "--homedir", config.GNUPG_HOMEDIR,
    ]


def _run(cmd, timeout=60, **kw):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kw)
    except subprocess.TimeoutExpired:
        log.warning("Command timed out after %ss: %s", timeout, " ".join(cmd))
        return None
    except OSError as e:
        log.warning("Command failed to start: %s (%s)", " ".join(cmd), e)
        return None


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_sha256(path, expected_hex):
    actual = sha256_of(path)
    if actual.lower() != expected_hex.lower():
        raise VerificationError(
            f"SHA-256 mismatch for {os.path.basename(path)}: "
            f"expected {expected_hex}, got {actual}"
        )
    log.info("sha256 OK for %s", os.path.basename(path))


def _fingerprint_of_imported_key(homedir):
    res = _run(["gpg", "--batch", "--homedir", homedir,
                "--with-colons", "--fingerprint"])
    if res is None:
        return []
    fprs = []
    for line in res.stdout.splitlines():
        if line.startswith("fpr:"):
            fprs.append(line.split(":")[9])
    return fprs


def ensure_key(pinned_fingerprint):
    os.makedirs(config.GNUPG_HOMEDIR, mode=0o700, exist_ok=True)
    os.chmod(config.GNUPG_HOMEDIR, 0o700)

    if pinned_fingerprint in _fingerprint_of_imported_key(config.GNUPG_HOMEDIR):
        return

    keyfile = config.BUNDLED_KEY_FILES.get(pinned_fingerprint)
    if keyfile:
        bundled_path = os.path.join(_data_dir(), "keys", keyfile)
        if os.path.exists(bundled_path):
            _import_key(bundled_path)
            if pinned_fingerprint in _fingerprint_of_imported_key(config.GNUPG_HOMEDIR):
                return

    refresh_key(pinned_fingerprint)

    if pinned_fingerprint not in _fingerprint_of_imported_key(config.GNUPG_HOMEDIR):
        raise VerificationError(
            f"Could not obtain a key matching pinned fingerprint "
            f"{pinned_fingerprint}. Refusing to continue."
        )


def refresh_key(pinned_fingerprint):
    """Re-fetch a pinned key to pick up subkey rotation (primary key and
    fingerprint unchanged, new signing subkey). Tries a keyserver first
    with a short timeout, then falls back to config.KEY_SOURCES.
    """
    log.info("Refreshing key %s...", pinned_fingerprint)

    res = _run([
        "gpg", "--batch", "--homedir", config.GNUPG_HOMEDIR,
        "--keyserver", "keys.openpgp.org",
        "--recv-keys", pinned_fingerprint,
    ], timeout=15)
    if res is not None and res.returncode == 0 and pinned_fingerprint in _fingerprint_of_imported_key(config.GNUPG_HOMEDIR):
        log.info("Refreshed key %s from keys.openpgp.org", pinned_fingerprint)
        return

    sources = config.KEY_SOURCES.get(pinned_fingerprint, [])
    if not sources:
        raise VerificationError(f"No known key source for {pinned_fingerprint}")

    staging = os.path.join(config.CACHE_DIR, "gnupg_staging")
    if os.path.exists(staging):
        shutil.rmtree(staging)
    os.makedirs(staging, mode=0o700)

    last_err = None
    try:
        for url in sources:
            try:
                r = requests.get(url, timeout=20, headers={"User-Agent": config.USER_AGENT})
                r.raise_for_status()
            except Exception as e:
                last_err = e
                continue

            keypath = os.path.join(staging, "candidate.key")
            with open(keypath, "wb") as f:
                f.write(r.content)

            _run(["gpg", "--batch", "--homedir", staging, "--import", keypath])
            fprs = _fingerprint_of_imported_key(staging)

            if pinned_fingerprint in fprs:
                imp = _run(["gpg", "--batch", "--homedir", config.GNUPG_HOMEDIR,
                            "--import", keypath])
                if imp is not None and imp.returncode == 0:
                    log.info("Refreshed key %s from %s", pinned_fingerprint, url)
                    return
            else:
                log.warning("Fetched key from %s did not match pin %s", url, pinned_fingerprint)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    detail = f" ({last_err})" if last_err else ""
    raise VerificationError(
        f"Failed to refresh a key matching {pinned_fingerprint}{detail}. "
        f"Checked keys.openpgp.org and {len(sources)} configured URL "
        f"source(s)."
    )


def _import_key(keyfile_path):
    _run(["gpg", "--batch", "--homedir", config.GNUPG_HOMEDIR,
          "--import", keyfile_path])


def _parse_status_lines(status_text):
    parsed = {}
    for line in status_text.splitlines():
        if not line.startswith("[GNUPG:] "):
            continue
        parts = line[len("[GNUPG:] "):].split()
        if not parts:
            continue
        parsed[parts[0]] = parts[1:]
    return parsed


def verify_signature(data_path, sig_path, pinned_fingerprint):
    ensure_key(pinned_fingerprint)

    ok, status = _try_verify(data_path, sig_path)
    if not ok and ("NO_PUBKEY" in status or "EXPKEYSIG" in status or "REVKEYSIG" in status):
        refresh_key(pinned_fingerprint)
        ok, status = _try_verify(data_path, sig_path)

    if not ok:
        reason = ""
        if "EXPKEYSIG" in status:
            reason = " (signing key has expired)"
        elif "REVKEYSIG" in status:
            reason = " (signing key has been revoked)"
        raise VerificationError(
            f"GPG signature is NOT valid for {os.path.basename(data_path)}{reason}."
        )

    validsig = status.get("VALIDSIG")
    signer_ok = bool(validsig) and validsig[-1] == pinned_fingerprint

    if not signer_ok:
        raise VerificationError(
            "GPG signature is valid but was NOT made by the pinned key "
            f"{pinned_fingerprint}. Refusing to install. This could mean "
            "tampering, or that the vendor rotated their signing key and "
            "Tml's pin is out of date - check for a Tml update."
        )
    log.info("GPG signature OK for %s (signed by %s)",
              os.path.basename(data_path), pinned_fingerprint)


def _try_verify(data_path, sig_path):
    """Only GOODSIG counts - VALIDSIG alone can also mean an expired
    or revoked key, which would defeat pinning."""
    res = _run(_gpg_base_cmd() + ["--verify", sig_path, data_path])
    if res is None:
        return False, {}
    status = _parse_status_lines(res.stdout)
    return "GOODSIG" in status, status


def _data_dir():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "data")
