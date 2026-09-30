from app.ratelimit import DailyBudget, SlidingWindowLimiter


def test_sliding_window():
    lim = SlidingWindowLimiter(3, 60)
    assert all(lim.allow("a", now=t)[0] for t in (0, 1, 2))
    ok, wait = lim.allow("a", now=3)
    assert not ok and wait > 0
    assert lim.allow("b", now=3)[0]
    assert lim.allow("a", now=61)[0]


def test_daily_budget():
    b = DailyBudget(2)
    assert b.take() and b.take() and not b.take()
