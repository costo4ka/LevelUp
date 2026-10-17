from levelup.ui.geometry import ScreenArea, normalize_position

A = ScreenArea("A", 0, 0, 1920, 1040, primary=True)
B = ScreenArea("B", 1920, 0, 1280, 1024)
W, H = 290, 480


def test_default_is_bottom_right_of_primary():
    assert normalize_position(None, None, W, H, [A, B]) == (1920 - W - 24, 1040 - H - 24, "A")


def test_position_inside_a_screen_is_kept():
    assert normalize_position(100, 200, W, H, [A, B]) == (100, 200, "A")
    assert normalize_position(2000, 100, W, H, [A, B]) == (2000, 100, "B")


def test_partially_offscreen_window_is_pulled_in():
    assert normalize_position(1800, 900, W, H, [A]) == (1920 - W, 1040 - H, "A")
    assert normalize_position(-200, -50, W, H, [A]) == (0, 0, "A")


def test_disconnected_monitor_returns_to_primary():
    assert normalize_position(2500, 100, W, H, [A]) == (1920 - W, 100, "A")


def test_saved_monitor_is_used_when_center_is_off_every_screen():
    assert normalize_position(2500, 5000, W, H, [A, B], preferred_name="B") == (2500, 1024 - H, "B")
    assert normalize_position(2500, 5000, W, H, [A, B], preferred_name="Z")[2] == "A"


def test_no_screens_is_safe():
    assert normalize_position(10, 20, W, H, []) == (10, 20, None)
