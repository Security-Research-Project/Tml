import logging
import os
import shutil
import string
import subprocess

from . import config, installer

log = logging.getLogger("tml.apparmor")

PROFILE_DIR_SYSTEM = "/etc/apparmor.d"
GENERATED_DIR = os.path.join(config.DATA_DIR, "apparmor")


def profile_name(browser_key):
    return f"tml_{browser_key}"


def _template_path():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "data", "apparmor", "browser.profile.template")


def generate_profile(browser):
    install_dir = os.path.join(config.INSTALL_ROOT, browser.key)
    exe = installer.find_launch_script(browser, install_dir)
    profile_dir = os.path.join(install_dir, "*Data*")

    with open(_template_path()) as f:
        tmpl = string.Template(f.read())

    rendered = tmpl.substitute(
        display_name=browser.display_name,
        key=browser.key,
        executable_path=exe,
        install_dir=install_dir + "/**",
        profile_dir=profile_dir,
    )

    os.makedirs(GENERATED_DIR, mode=0o700, exist_ok=True)
    out_path = os.path.join(GENERATED_DIR, f"tml.{browser.key}")
    with open(out_path, "w") as f:
        f.write(rendered)
    return out_path


def apparmor_available():
    return shutil.which("apparmor_parser") is not None and os.path.isdir("/sys/kernel/security/apparmor")


def profile_active(browser_key):
    profiles_file = "/sys/kernel/security/apparmor/profiles"
    if not os.path.exists(profiles_file):
        return False
    try:
        with open(profiles_file) as f:
            return any(line.startswith(profile_name(browser_key) + " ") for line in f)
    except PermissionError:
        return False


def _pkexec(pkexec_bin="pkexec"):
    if not shutil.which(pkexec_bin):
        raise RuntimeError(
            f"'{pkexec_bin}' was not found. AppArmor profile changes need "
            f"polkit's pkexec - install your distro's polkit package "
            f"and try again."
        )
    return pkexec_bin


def install_profile(browser, pkexec_bin="pkexec"):
    if not apparmor_available():
        raise RuntimeError("AppArmor is not available on this system.")

    src = generate_profile(browser)
    dest = os.path.join(PROFILE_DIR_SYSTEM, f"tml.{browser.key}")

    escalate = _pkexec(pkexec_bin)

    log.info("Requesting privileges to install AppArmor profile for %s", browser.key)
    res = subprocess.run([escalate, "cp", src, dest], capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Failed to install AppArmor profile: {res.stderr.strip()}")

    res = subprocess.run([escalate, "apparmor_parser", "-r", dest], capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Failed to load AppArmor profile: {res.stderr.strip()}")
    return dest


def remove_profile(browser, pkexec_bin="pkexec"):
    dest = os.path.join(PROFILE_DIR_SYSTEM, f"tml.{browser.key}")
    if not os.path.exists(dest):
        return
    escalate = _pkexec(pkexec_bin)
    subprocess.run([escalate, "apparmor_parser", "-R", dest], capture_output=True, text=True)
    subprocess.run([escalate, "rm", "-f", dest], capture_output=True, text=True)
