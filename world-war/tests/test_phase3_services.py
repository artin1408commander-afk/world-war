"""Phase 3 pure-service tests (no production DB)."""
from modules.ng.inventory_service import whole_qty, format_qty_display
from modules.ng.store_service import to_whole_qty, acquire_checkout_lock
from modules.ng.menu_session import MenuSessionStore
from modules.ng.text_validate import validate_law_title, validate_statement
import time


def test_whole_qty():
    assert whole_qty(3.9) == 3
    assert whole_qty(0) == 0
    assert whole_qty(-1) == 0
    assert to_whole_qty(2.2) == 2


def test_format_qty():
    assert "عدد" in format_qty_display(5)
    assert "کمتر" in format_qty_display(0.4)


def test_checkout_lock():
    pid = 424242
    assert acquire_checkout_lock(pid) is True
    assert acquire_checkout_lock(pid) is False


def test_menu_session_owner_and_ttl():
    s = MenuSessionStore(ttl=0.05)
    s.touch(1, 99)
    assert s.owned_by(1, 99)
    assert s.is_alive(1, 99)
    assert s.owned_by(2, 99) is False
    time.sleep(0.06)
    assert s.is_alive(1, 99) is False


def test_validation():
    assert validate_law_title("قانون مالیات ملی")
    try:
        validate_statement("http://spam.example")
        assert False
    except ValueError:
        pass
