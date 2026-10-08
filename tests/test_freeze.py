import hashlib
import json

from spot_trd.config import ROOT


def test_live_strategy_and_preregistrations_are_frozen():
    changed = []
    freezes = sorted((ROOT / "reports").glob("*freeze*.json"))
    assert freezes
    for path in freezes:
        for f, digest in json.loads(path.read_text(encoding="utf-8"))["sha256"].items():
            if hashlib.sha256((ROOT / f).read_bytes()).hexdigest() != digest:
                changed.append(f"{f} (per {path.name})")
    assert not changed, (
        f"Frozen files changed: {changed}. The live paper strategy must stay frozen so paper results remain forward "
        "evidence. If the change is deliberate, write a new freeze file and say why.")
