from airdropd.localsend import resolve_collision, sanitize_filename


def test_plain_name_unchanged():
    assert sanitize_filename("photo.jpg") == "photo.jpg"


def test_path_traversal_unix():
    assert sanitize_filename("../../../etc/passwd") == "passwd"


def test_path_traversal_windows():
    assert sanitize_filename("..\\..\\..\\etc\\passwd") == "passwd"


def test_dotfiles_stripped():
    assert sanitize_filename(".hidden") == "hidden"
    assert sanitize_filename("..") == "unnamed"
    assert sanitize_filename(".") == "unnamed"


def test_empty_and_whitespace():
    assert sanitize_filename("") == "unnamed"
    assert sanitize_filename("   ") == "unnamed"
    assert sanitize_filename("  a  b ") == "a b"


def test_slash_only():
    assert sanitize_filename("/") == "unnamed"
    assert sanitize_filename("////") == "unnamed"


def test_control_chars_stripped():
    assert sanitize_filename("bad\x00name.txt") == "badname.txt"
    assert sanitize_filename("x\x1f\x7fy") == "xy"


def test_long_name_truncated():
    name = "a" * 500 + ".txt"
    out = sanitize_filename(name)
    assert len(out.encode()) <= 200
    assert out.endswith(".txt")


def test_collision(tmp_path):
    first = resolve_collision(str(tmp_path), "file.txt")
    assert first == "file.txt"
    (tmp_path / first).touch()
    second = resolve_collision(str(tmp_path), "file.txt")
    assert second == "file (1).txt"
    (tmp_path / second).touch()
    third = resolve_collision(str(tmp_path), "file.txt")
    assert third == "file (2).txt"
