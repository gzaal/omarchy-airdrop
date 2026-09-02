from __future__ import annotations

import logging
import os
import shutil
import subprocess

log = logging.getLogger(__name__)


def has_command(name: str) -> bool:
    return shutil.which(name) is not None


def session_available() -> bool:
    return bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"))


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
    """Show a selection menu; returns the chosen option or None.

    Runs via Popen + terminate() so the menu script's traps fire on timeout
    instead of leaking the summoned menu.
    """
    if not has_command("omarchy-menu-select") and not has_command("rofi"):
        return None
    if not session_available():
        log.warning("no graphical session detected; menu prompts disabled")
        return None
    if has_command("omarchy-menu-select"):
        cmd = ["omarchy-menu-select", prompt, *options]
        input_text = None
    else:
        cmd = ["rofi", "-dmenu", "-p", prompt, "-no-custom"]
        input_text = "\n".join(options)
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
        text=True,
    )
    try:
        out, _ = proc.communicate(input=input_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        log.info("menu timed out for prompt %r", prompt)
        proc.terminate()
        try:
            proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
        return None
    if proc.returncode != 0:
        return None
    out = (out or "").strip()
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
