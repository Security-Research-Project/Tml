import logging

from . import apparmor

log = logging.getLogger("tml.sandbox")


def build_launch_command(browser, exe, mode="apparmor"):
    """Decide the Exec= command for a browser. Never runs anything itself.

    Modes:
      none      - launch unsandboxed, unconditionally.
      apparmor  - launch under AppArmor if a profile is actually loaded and
                  enforced for this browser; otherwise fall back to
                  unsandboxed and say so plainly.
    """
    if mode == "none":
        return ([exe], "unsandboxed (by your setting)")

    if apparmor.apparmor_available() and apparmor.profile_active(browser.key):
        profile = apparmor.profile_name(browser.key)
        return (["aa-exec", "-p", profile, exe], f"AppArmor profile {profile}")

    return ([exe], "AppArmor requested but no active profile was found - unsandboxed")
