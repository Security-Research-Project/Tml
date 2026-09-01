import hashlib
import json
import logging
import os
import re
import shutil
import stat
import tarfile

from . import config, network, verify

log = logging.getLogger("tml.installer")

STATE_FILE = os.path.join(config.CONFIG_DIR, "installed.json")

STATE_TML = "tml"   # downloaded, GPG-verified, and installed by Tml
STATE_NONE = "none"         # not installed by Tml


class InstallError(Exception):
    pass


class InstallCancelled(Exception):
    pass


def _load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Could not read install state, starting fresh: %s", e)
    return {}


def _save_state(state):
    os.makedirs(config.CONFIG_DIR, mode=0o700, exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_FILE)


def get_metadata(browser):
    return _load_state().get(browser.key)


def install_state(browser):
    return STATE_TML if is_installed(browser) else STATE_NONE


def _dir_size(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for fn in files:
            fp = os.path.join(root, fn)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total


def _tree_hash(install_dir):
    h = hashlib.sha256()
    for root, dirs, files in os.walk(install_dir):
        dirs.sort()
        for fn in sorted(files):
            fp = os.path.join(root, fn)
            rel = os.path.relpath(fp, install_dir)
            h.update(rel.encode("utf-8", "surrogateescape"))
            try:
                with open(fp, "rb") as f:
                    for chunk in iter(lambda: f.read(1024 * 1024), b""):
                        h.update(chunk)
            except OSError as e:
                h.update(f"<unreadable:{e}>".encode())
    return h.hexdigest()


def verify_integrity(browser):
    install_dir = os.path.join(config.INSTALL_ROOT, browser.key)
    meta = get_metadata(browser)
    if not meta or not os.path.isdir(install_dir):
        return False, "Not installed."
    current = _tree_hash(install_dir)
    if current == meta.get("tree_sha256"):
        return True, f"Matches the install-time baseline (v{meta.get('version', '?')})."
    return False, (
        "The installed files no longer match the hash recorded right "
        "after install. This does not necessarily mean anything is wrong "
        "- some browsers write into their own install directory during "
        "normal use - but if you didn't expect this, consider reinstalling."
    )


def _force_rmtree(path):
    """Removes read-only files/dirs instead of failing on them."""
    def _on_error(func, target_path, _exc_info):
        try:
            os.chmod(target_path, stat.S_IRWXU)
        except OSError:
            pass
        func(target_path)

    shutil.rmtree(path, onerror=_on_error)


def find_profile_dir(install_dir):
    """Locate a Firefox-style profile dir by finding profiles.ini,
    rather than hardcoding an internal path that can change between
    versions. Returns the path relative to install_dir, or None.
    """
    for root, _dirs, files in os.walk(install_dir):
        if "profiles.ini" in files:
            return os.path.relpath(root, install_dir)
    return None


def _preserve_profile(install_dir, browser_key):
    """If install_dir holds a real profile, move it out of the way and
    return (relative_path, staging_path) so it can be restored after a
    fresh extraction. Returns None if there's nothing to preserve.
    """
    rel = find_profile_dir(install_dir)
    if rel is None:
        return None
    staging = os.path.join(config.CACHE_DIR, "profile_preserve", browser_key)
    if os.path.exists(staging):
        _force_rmtree(staging)
    os.makedirs(os.path.dirname(staging), mode=0o700, exist_ok=True)
    shutil.move(os.path.join(install_dir, rel), staging)
    log.info("Preserved existing profile for %s (%s)", browser_key, rel)
    return rel, staging


def _restore_profile(install_dir, preserved):
    """Undo _preserve_profile once the new version is extracted."""
    if preserved is None:
        return
    rel, staging = preserved
    target = os.path.join(install_dir, rel)
    if os.path.exists(target):
        _force_rmtree(target)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.move(staging, target)
    log.info("Restored preserved profile to %s", rel)


def check_for_update(browser):
    """Fetch the latest official release version and compare to what's
    installed, without downloading. Returns the newer version string,
    or None if already current. Raises InstallError if not installed.
    """
    installed = get_metadata(browser)
    if not installed:
        raise InstallError(f"{browser.display_name} is not installed by Tml.")
    release = browser.latest_release(config.detect_arch())
    if _version_key(release.version) > _version_key(installed.get("version", "")):
        return release.version
    return None


def uninstall(browser, remove_sandbox_profile=True):
    install_dir = os.path.join(config.INSTALL_ROOT, browser.key)
    if os.path.isdir(install_dir):
        _force_rmtree(install_dir)

    state = _load_state()
    state.pop(browser.key, None)
    _save_state(state)

    from . import desktop_entry
    desktop_entry.remove_entry(browser)

    if remove_sandbox_profile:
        from . import apparmor
        try:
            apparmor.remove_profile(browser)
        except Exception as e:
            log.info("No AppArmor profile to remove for %s (%s)", browser.key, e)

    log.info("Uninstalled %s", browser.key)


def _safe_extract(tar_path, dest_dir):
    dest_dir = os.path.realpath(dest_dir)
    with tarfile.open(tar_path, "r:xz") as tf:
        members = tf.getmembers()
        for m in members:
            target = os.path.realpath(os.path.join(dest_dir, m.name))
            if not (target == dest_dir or target.startswith(dest_dir + os.sep)):
                raise InstallError(f"Refusing unsafe tar member: {m.name}")
            if m.issym() or m.islnk():
                link_target = os.path.realpath(os.path.join(os.path.dirname(target), m.linkname))
                if not link_target.startswith(dest_dir + os.sep):
                    raise InstallError(f"Refusing unsafe tar link: {m.name} -> {m.linkname}")
        # safe to extract after checks
        tf.extractall(dest_dir, members=members)


def _strip_single_top_dir(dest_dir):
    entries = os.listdir(dest_dir)
    if len(entries) != 1:
        return
    only = os.path.join(dest_dir, entries[0])
    if not os.path.isdir(only):
        return

    staging = dest_dir + ".unwrap-tmp"
    if os.path.exists(staging):
        shutil.rmtree(staging)
    os.rename(only, staging)
    try:
        for name in os.listdir(staging):
            shutil.move(os.path.join(staging, name), os.path.join(dest_dir, name))
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _version_key(version_string):
    parts = re.findall(r"\d+", version_string or "")
    if not parts:
        return (version_string,)
    return tuple(int(p) for p in parts)


def _check_not_a_downgrade(browser, new_version):
    existing = get_metadata(browser)
    if not existing:
        return
    old_key = _version_key(existing.get("version", ""))
    new_key = _version_key(new_version)
    if new_key < old_key:
        raise InstallError(
            f"Refusing to install {browser.display_name} {new_version}: "
            f"an already-installed version ({existing.get('version')}) is "
            f"newer. This could mean a stale or replayed response was "
            f"served instead of the current release - try again, and if "
            f"this keeps happening, treat it as suspicious rather than "
            f"retrying indefinitely."
        )


def install(browser, progress=None, should_cancel=None):
    def report(stage, pct=None):
        log.info("[%s] %s", browser.key, stage)
        if progress:
            progress(stage, pct)

    def check_cancelled():
        if should_cancel and should_cancel():
            raise InstallCancelled(f"{browser.display_name} install cancelled.")

    config.ensure_dirs()
    arch = config.detect_arch()

    report(f"Checking latest official {browser.display_name} release...")
    release = browser.latest_release(arch)
    _check_not_a_downgrade(browser, release.version)
    check_cancelled()

    tarball_path = os.path.join(config.DOWNLOAD_DIR, release.filename)
    sig_path = tarball_path + ".sig"

    report(f"Downloading {browser.display_name} {release.version}...")

    def _prog(done, total):
        if total:
            report("Downloading...", int(done * 100 / total))

    try:
        network.download_file(
            release.tarball_url, tarball_path, progress_cb=_prog, should_cancel=should_cancel
        )
        network.download_file(release.sig_url, sig_path, should_cancel=should_cancel)
    except network.DownloadCancelled:
        for p in (tarball_path, sig_path):
            if os.path.exists(p):
                os.remove(p)
        raise InstallCancelled(f"{browser.display_name} install cancelled.")
    except Exception as e:
        for p in (tarball_path, sig_path):
            if os.path.exists(p):
                os.remove(p)
        raise InstallError(
            f"Could not download {browser.display_name} {release.version} "
            f"from its official source ({release.tarball_url}): {e}"
        )

    report("Verifying GPG signature (fail-closed)...")
    tarball_sha256 = None
    try:
        verify.verify_signature(tarball_path, sig_path, release.fingerprint)
        if release.sha256_url:
            expected = network.fetch_bytes(release.sha256_url, max_bytes=4096).decode().split()[0]
            verify.verify_sha256(tarball_path, expected)
        tarball_sha256 = verify.sha256_of(tarball_path)
    except verify.VerificationError:
        for p in (tarball_path, sig_path):
            if os.path.exists(p):
                os.remove(p)
        raise

    check_cancelled()

    install_dir = os.path.join(config.INSTALL_ROOT, browser.key)
    preserved_profile = None
    if os.path.exists(install_dir):
        report("Preserving your existing browser profile, if any...")
        preserved_profile = _preserve_profile(install_dir, browser.key)
        _force_rmtree(install_dir)
    os.makedirs(install_dir, mode=0o700)

    try:
        report("Extracting (safely, no path traversal)...")
        _safe_extract(tarball_path, install_dir)
        if browser.strip_top_level_dir:
            _strip_single_top_dir(install_dir)
        browser.post_install(install_dir)
    except Exception:
        if preserved_profile:
            try:
                _restore_profile(install_dir, preserved_profile)
                log.warning(
                    "Install failed after the profile was preserved; "
                    "restored it to %s rather than leaving it staged", install_dir
                )
            except Exception as restore_err:
                log.error("Could not restore preserved profile after a failed install: %s", restore_err)
        raise

    if preserved_profile:
        report("Restoring your browser profile...")
        _restore_profile(install_dir, preserved_profile)

    exe = find_launch_script(browser, install_dir)
    st = os.stat(exe)
    os.chmod(exe, st.st_mode | stat.S_IEXEC)

    for p in (tarball_path, sig_path):
        if os.path.exists(p):
            os.remove(p)

    report("Recording install state...", 99)
    state = _load_state()
    state[browser.key] = {
        "version": release.version,
        "size_bytes": _dir_size(install_dir),
        "tarball_sha256": tarball_sha256,
        "tree_sha256": _tree_hash(install_dir),
    }
    _save_state(state)

    from . import settings
    if settings.load().get("sandbox_mode") == "apparmor":
        from . import apparmor
        if apparmor.apparmor_available():
            report("Loading AppArmor profile...")
            try:
                apparmor.install_profile(browser)
            except Exception as e:
                log.warning("Could not load AppArmor profile for %s: %s", browser.key, e)

    report("Creating independent application entry...", 100)
    from . import desktop_entry
    desktop_entry.write_entry(browser)

    report("Installed. Find it in your applications menu.", 100)
    return install_dir


def find_launch_script(browser, install_dir):
    direct = os.path.join(install_dir, browser.binary_name)
    if os.path.isfile(direct):
        return direct
    for root, _dirs, files in os.walk(install_dir):
        if browser.binary_name in files:
            return os.path.join(root, browser.binary_name)
    raise InstallError(f"Could not find {browser.binary_name} inside {install_dir}")


def is_installed(browser):
    install_dir = os.path.join(config.INSTALL_ROOT, browser.key)
    try:
        find_launch_script(browser, install_dir)
        return True
    except InstallError:
        return False
    except FileNotFoundError:
        return False
