from datetime import datetime
from app.shared.time import fmt_dt

def test_fmt_dt_no_seconds():
    dt = datetime(2024, 1, 2, 3, 4, 5)
    out = fmt_dt(dt)
    assert out.endswith('03:04')
    assert out.count(':') == 1
