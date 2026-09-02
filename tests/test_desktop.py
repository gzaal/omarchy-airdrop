from airdropd import desktop


def test_notify_prefers_omarchy(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)

        class R:
            returncode = 0

        return R()

    monkeypatch.setattr(desktop, "has_command", lambda n: n == "omarchy-notification-send")
    monkeypatch.setattr(desktop.subprocess, "run", fake_run)
    assert desktop.notify("t", "b") is True
    assert calls[0][0] == "omarchy-notification-send"


def test_notify_falls_back_to_notify_send(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)

        class R:
            returncode = 0

        return R()

    monkeypatch.setattr(desktop, "has_command", lambda n: n == "notify-send")
    monkeypatch.setattr(desktop.subprocess, "run", fake_run)
    assert desktop.notify("t", "b") is True
    assert calls[0][0] == "notify-send"


def test_notify_none_available(monkeypatch):
    monkeypatch.setattr(desktop, "has_command", lambda n: False)
    assert desktop.notify("t", "b") is False


def test_menu_select_omarchy(monkeypatch):
    monkeypatch.setattr(desktop, "has_command", lambda n: n == "omarchy-menu-select")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-test")

    def fake_popen(cmd, **kw):
        class P:
            def __init__(self):
                self.returncode = 0

            def communicate(self, input=None, timeout=None):
                return ("Accept: photo.jpg\n", "")

        return P()

    monkeypatch.setattr(desktop.subprocess, "Popen", fake_popen)
    assert desktop.menu_select("p", ["a", "b"]) == "Accept: photo.jpg"


def test_menu_select_rofi_gets_input(monkeypatch):
    captured = {}
    monkeypatch.setattr(desktop, "has_command", lambda n: n == "rofi")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-test")

    def fake_popen(cmd, **kw):
        captured.update(cmd=cmd, stdin=kw.get("stdin"))

        class P:
            returncode = 0

            def communicate(self, input=None, timeout=None):
                captured["input"] = input
                return ("a\n", "")

        return P()

    monkeypatch.setattr(desktop.subprocess, "Popen", fake_popen)
    assert desktop.menu_select("p", ["a", "b"]) == "a"
    assert captured["input"] == "a\nb"
    assert captured["cmd"] == ["rofi", "-dmenu", "-p", "p", "-no-custom"]


def test_menu_select_cancelled(monkeypatch):
    monkeypatch.setattr(desktop, "has_command", lambda n: True)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-test")

    def fake_popen(cmd, **kw):
        class P:
            returncode = 1

            def communicate(self, input=None, timeout=None):
                return ("", "")

        return P()

    monkeypatch.setattr(desktop.subprocess, "Popen", fake_popen)
    assert desktop.menu_select("p", ["a"]) is None


def test_menu_select_timeout_terminates(monkeypatch):
    import subprocess as sp

    monkeypatch.setattr(desktop, "has_command", lambda n: True)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-test")
    events = []

    class P:
        returncode = None

        def communicate(self, input=None, timeout=None):
            if timeout is None:
                return ("", "")
            raise sp.TimeoutExpired(cmd="menu", timeout=timeout)

        def terminate(self):
            events.append("terminate")

        def kill(self):
            events.append("kill")

    monkeypatch.setattr(desktop.subprocess, "Popen", lambda cmd, **kw: P())
    assert desktop.menu_select("p", ["a"], timeout=0.01) is None
    assert events[0] == "terminate"


def test_menu_select_no_backend():
    assert desktop.menu_select("p", ["a"]) is None


def test_make_prompt_matrix(monkeypatch):
    monkeypatch.setattr(desktop, "has_command", lambda n: n in ("rofi",))
    assert desktop.make_prompt("auto") is not None
    assert desktop.make_prompt("menu") is not None
    assert desktop.make_prompt("stdin") is None
    monkeypatch.setattr(desktop, "has_command", lambda n: False)
    assert desktop.make_prompt("auto") is None


def test_menu_prompt_accept(monkeypatch):
    monkeypatch.setattr(desktop, "menu_select",
                        lambda prompt, options, timeout=60: "Accept: hello.txt (5 bytes)")
    assert desktop._menu_prompt("bob", "hello.txt (5 bytes)") is True


def test_menu_prompt_deny(monkeypatch):
    monkeypatch.setattr(desktop, "menu_select", lambda prompt, options, timeout=60: "Deny")
    assert desktop._menu_prompt("bob", "hello.txt") is False
    monkeypatch.setattr(desktop, "menu_select", lambda prompt, options, timeout=60: None)
    assert desktop._menu_prompt("bob", "hello.txt (5 bytes)") is False


def test_menu_select_no_backend(monkeypatch):
    monkeypatch.setattr(desktop, "has_command", lambda n: False)
    assert desktop.menu_select("p", ["a"]) is None


def test_menu_select_no_session(monkeypatch):
    monkeypatch.setattr(desktop, "has_command", lambda n: True)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    assert desktop.menu_select("p", ["a"]) is None
