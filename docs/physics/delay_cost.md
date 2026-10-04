# The expected delay and its cost (spec II.9 iv)

Status: SKETCHED, as the spec marks it. This is a counting argument on independent daily
success probabilities. It does not enter the window equation, `p_success` or any ranking.

## What it computes

The engine already gives each day a success probability. The decision layer takes one number per
day, the best usable `p_success` of that day (0 when the day has no usable window), and asks how
many extra days a launch campaign should expect to wait for its first success, compared with
succeeding at the first opportunity.

Let `T` be the index of the first successful day, counted from 1, with independent successes of
probability `p_1, p_2, ...`. Then

    P(T > j) = prod_{s=1..j} (1 - p_s)
    E[T]     = sum_{j>=0} P(T > j)
    E[extra days] = E[T] - 1 = sum_{j>=1} prod_{s=1..j} (1 - p_s)
    E[cost]       = C_day * E[extra days]                                   (II.28)

With a constant `p` the sum is `(1 - p) / p`. For `p = 0.5` that is 1 extra day, which is the
mean of a geometric tail and is one of the checks in `backend/engine/tests/test_decision.py`.

## A correction to (II.27) as printed

The spec prints the summand as `1 - prod_{s=1..j} (1 - p_s)`. That is `P(T <= j)`, not
`P(T > j)`. Summed over `j` it grows with the horizon (about `N - 1/p` for constant `p`), so it
cannot be an expected time. The survival form above is the one whose constant-`p` case gives the
geometric mean, so it is the one implemented. The test
`test_the_printed_form_of_ii27_diverges_and_the_survival_form_does_not` records both. The spec text
itself was not edited; this note is the record.

## What it does not claim

- **A finite horizon.** A window response covers a few days. Nothing is extrapolated beyond it, so
  the result is a lower bound on the expected extra days, and it is exact only when the probability
  of no success inside the horizon is 0. The service returns that probability and the word
  `lower` or `exact`.
- **Independent days.** Weather persists from one day to the next, so independence is an assumption.
  A run of bad weather is more likely than independence says, so the true wait is probably longer.
- **One decision per day.** Two daily crossings are reduced to the better one.
- **No cost figure.** `C_day` is the user's own number and has no default. The genre reference
  (O'Neill and Davidheiser, J. Spacecraft and Rockets, doi 10.2514/1.a36618) supplies a form for a
  cost model, not a value for Canso, and nothing here pretends otherwise. Without `C_day` the
  service returns the expected delay in days and no cost.

## Where it lives

- `backend/engine/decision.py` and `backend/engine/tests/test_decision.py`
- `GET /v1/decision/delay-cost` in `backend/api/routes/decision.py`, tests in
  `backend/api/tests/test_delay_cost.py`. It is an extension endpoint: no frozen response schema
  was changed and `POST /v1/windows` answers exactly as before.
- The "Expected delay" panel of `Canso Launch Prototype.html`. It is live-only, because the
  endpoint is not part of the offline fixtures, and it says so offline.
