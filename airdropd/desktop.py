from __future__ import annotations

import logging
import shutil
import subprocess

log = logging.getLogger(__name__)


def has_command(name: str) -> bool:
    return shutil.which(name) is not None


def notify(title: str, body: str, urgency: str = "normal") -> bool:
    if has_command("omarchy-notification-send"):
        cmd = ["omarchy-notification-send", "--app-name", "airdrop",
               "-u", urgency, "-t", "5000", title, body]
    elif has_command("notify-send"):
        cmd = ["notify-send", "-a", "airdrop", "-u", urgency,
               "-t", "5000", title, body]
    else:
        return False
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return proc.returncode == 0
    except (subprocess.SubprocessError, OSError) as exc:
        log.debug("notification failed: %s", exc)
        return False


def menu_select(prompt: str, options: list[str], timeout: float = 60) -> str | None:
    """Show a selection menu; returns the chosen option or None."""
    try:
        if has_command("omarchy-menu-select"):
            proc = subprocess.run(
                ["omarchy-menu-select", prompt, *options],
                capture_output=True, text=True, timeout=timeout,
            )
        elif has_command("rofi"):
            proc = subprocess.run(
                ["rofi", "-dmenu", "-p", prompt, "-no-custom"],
                capture_output=True, text=True, timeout=timeout,
                input="\n".join(options),
            )
        else:
            return None
    except (subprocess.SubprocessError, OSError) as exc:
        log.debug("menu command failed: %s: %s", prompt, exc)
        return None
    if proc.returncode != 0:
        return None
    out = (proc.stdout or "").strip()
    return out or None


def make_prompt(ui: str = "auto"):
    """Return a prompt callback (alias, summary) -> bool, or None to deny."""
    if ui == "stdin":
        return None
    if ui in ("auto", "menu"):
        if has_command("omarchy-menu-select") or has_command("rofi"):
            return _menu_prompt
        return None
    return None


def _menu_prompt(sender_alias: str, summary: str) -> bool:
    choice = menu_select(
        f"Accept file from {sender_alias}?",
        [f"Accept: {summary}", "Deny"],
    )
    if choice is None:
        return False
    return choice.startswith("Accept")
