from jobtracker.http import RateLimiter


def test_rate_limiter_spaces_calls_per_host():
    t = [0.0]
    slept = []
    rl = RateLimiter(2.0, clock=lambda: t[0], sleep=lambda d: (slept.append(d), t.__setitem__(0, t[0] + d)))
    rl.wait("a.com")
    t[0] += 0.5
    rl.wait("a.com")
    assert slept == [1.5]
    rl.wait("b.com")          # other host: no wait
    assert slept == [1.5]
