import yaml

from spot_trd.config import CONFIG_DIR, load_universe


def test_every_tradable_symbol_is_user_approved():
    screen = yaml.safe_load((CONFIG_DIR / "sharia_screen.yaml").read_text(encoding="utf-8"))["assets"]
    for symbol in load_universe()["allowed_symbols"]:
        assert symbol in screen, f"{symbol} has no Sharia screening record"
        assert screen[symbol]["user_decision"] == "approved", f"{symbol} is not approved by the user"


def test_decisions_use_known_values():
    screen = yaml.safe_load((CONFIG_DIR / "sharia_screen.yaml").read_text(encoding="utf-8"))["assets"]
    assert {a["user_decision"] for a in screen.values()} <= {"approved", "pending", "rejected"}
