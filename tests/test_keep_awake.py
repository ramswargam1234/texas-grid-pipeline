"""The keep-awake script must tell a sleeping app from a running one, and fail loudly when it can't wake it."""
from src import keep_awake
from src.keep_awake import APP_MARKER, SLEEP_MARKER, WAKE_BUTTON, classify


def test_dashboard_title_in_any_frame_means_awake():
    assert classify(["", f"⚡ {APP_MARKER}\nDemand vs temperature"]) == "awake"


def test_sleep_page_is_detected():
    assert classify([f"This app has {SLEEP_MARKER} due to inactivity.\n{WAKE_BUTTON}"]) == "asleep"
    assert classify([WAKE_BUTTON]) == "asleep"


def test_blank_or_spinner_page_is_still_loading():
    assert classify([]) == "loading"
    assert classify(["", "Please wait..."]) == "loading"


def test_main_returns_1_when_the_app_never_comes_up(monkeypatch):
    def never_up(url, timeout):
        raise RuntimeError("did not show the dashboard")
    monkeypatch.setattr(keep_awake, "keep_awake", never_up)
    assert keep_awake.main(["--url", "http://x", "--timeout", "1"]) == 1


def test_main_returns_0_when_up(monkeypatch):
    monkeypatch.setattr(keep_awake, "keep_awake", lambda url, timeout: "awake")
    assert keep_awake.main([]) == 0
