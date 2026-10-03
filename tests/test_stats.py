"""Tests for headline tiles and stuck-ticket rows."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

import pandas as pd

from metrics.services.backtest import BacktestSummary, DateSummary, ScopeResult
from metrics.services.calculator import BacklogFlow, Pace
from metrics.services.stats import (
    Tile,
    Trust,
    assumed_pace_note,
    backtest_tile,
    build_delivery_tiles,
    build_headline_tiles,
    build_stuck_rows,
    bulk_closure_note,
    clear_date_tile,
    date_check_note,
    diagnose_backtest,
    flow_tile,
    forecast_verdict,
    heeded_trust,
    narrow_spread,
    open_work_tile,
    promised_done,
    recalibration_note,
    scope_forecast_tile,
    scope_verdict,
    spread_note,
    trust,
    unmeasured_share_note,
)


def _scatter_df():
    return pd.DataFrame(
        {
            "key": ["A-1", "A-2", "A-3", "A-4"],
            "finished_at": [
                datetime(2024, 1, 5, tzinfo=UTC),
                datetime(2024, 1, 6, tzinfo=UTC),
                datetime(2024, 1, 15, tzinfo=UTC),
                datetime(2024, 1, 16, tzinfo=UTC),
            ],
            "cycle_time_days": [10.0, 10.0, 4.0, 4.0],
        },
    )


def _aging_df():
    return pd.DataFrame(
        {
            "key": ["B-1", "B-2", "B-3"],
            "status": ["Open", "In Progress", "Open"],
            "age_days": [3.0, 12.5, 8.0],
            "p85_days": [4.0, 9.0, 4.0],
        },
    )


def _open_work(**changes) -> dict:
    return {
        "horizon": 8,
        "n_open": 151,
        "at_least_85": 31.0,
        "by_date": date(2024, 3, 1),
        "recalibrated": False,
        **changes,
    }


def test_build_headline_tiles_values_and_deltas():
    backtest = Tile("past 8-week promises held", "11 of 12")
    tiles = build_headline_tiles(
        scatter=_scatter_df(),
        aging=_aging_df(),
        open_work=_open_work(),
        forecast={"p85": 5.0, "p85_date": date(2024, 3, 1), "backlog": 151},
        flow_efficiency=0.25,
        backtest=backtest,
        flow=BacklogFlow(arrived=3.0, finished=4.0, pace=Pace(window=12)),
    )
    # one "done per week" figure: the flow tile's, at the forecast's pace
    assert tiles == [
        Tile("of 151 open issues done in 8 weeks (85% chance)", "≥ 31"),
        backtest,
        Tile("all 151 open issues done (85% chance)", "by 01 Mar 2024"),
        Tile(
            "Arrivals and finishes, last 12 weeks",
            "3.0 in / 4.0 done per week",
            "more get done than arrive",
            delta_good=True,
        ),
        Tile("Cycle time p50", "4.0d", "↓ 6.0d", delta_good=True),
        Tile("Work in progress", "3", None, delta_good=None),
        Tile("Flow efficiency", "25%", None, delta_good=None),
    ]


def test_build_headline_tiles_without_forecast_or_history():
    tiles = build_headline_tiles(
        scatter=pd.DataFrame({"key": [], "finished_at": [], "cycle_time_days": []}),
        aging=_aging_df(),
        open_work={},
        forecast={},
        flow_efficiency=0.0,
    )
    assert [tile.value for tile in tiles[:3]] == ["n/a", "n/a", "n/a"]
    cycle_tile = tiles[[tile.label for tile in tiles].index("Cycle time p50")]
    assert cycle_tile.value == "n/a"
    assert cycle_tile.delta_text is None


def test_build_stuck_rows_sorted_and_linked():
    rows = build_stuck_rows(_aging_df(), "https://jira.example.com", limit=2)
    assert [(row.key, row.age_days) for row in rows] == [
        ("B-2", 12.5),
        ("B-3", 8.0),
    ]
    assert rows[0].url == "https://jira.example.com/browse/B-2"
    assert rows[0].status == "In Progress"


def test_build_stuck_rows_empty():
    empty = pd.DataFrame({"key": [], "status": [], "age_days": [], "p85_days": []})
    assert build_stuck_rows(empty, "https://x") == []


def _measured_scope(**changes) -> ScopeResult:
    scope = ScopeResult(
        {"backlog": 4, "p85": 3.0, "p85_date": date(2024, 2, 1)},
        _open_work(n_open=4, at_least_85=2.0),
        {},
        None,
        "measured",
    )
    return replace(scope, **changes)


def test_build_headline_tiles_puts_the_scope_after_the_date():
    tiles = build_headline_tiles(
        scatter=_scatter_df(),
        aging=_aging_df(),
        open_work={},
        forecast={},
        flow_efficiency=0.0,
        scope_tile=scope_forecast_tile(_measured_scope(), open_count=4, total=6),
    )
    # the same count promise as the team's, the all-done date only beside it
    assert tiles[3] == Tile(
        "of 4 open issues of the scope done in 8 weeks (85% chance)",
        "≥ 2",
        "all by 01 Feb 2024",
    )


def test_scope_forecast_tile_says_a_finished_release_is_done_without_a_chance():
    finished = ScopeResult({}, {}, {}, None, "measured")
    assert scope_forecast_tile(finished, open_count=0, total=2) == Tile(
        "none of its 2 issues open", "Release done"
    )


def test_scope_forecast_tile_counts_the_open_issue_and_late_additions():
    one_open = _measured_scope(
        forecast={"backlog": 1, "p85": None, "p85_date": None},
        open_work=_open_work(n_open=1, at_least_85=0.0),
        created_after_start=3,
    )
    tile = scope_forecast_tile(one_open, open_count=1, total=263)
    assert tile == Tile(
        "1 open issue of the scope",
        "n/a",
        "the 1 open issue cannot be promised done in 8 weeks;"
        " not all within 2 years; 3 created after its first finish",
    )


def test_scope_forecast_tile_shows_no_count_when_none_can_be_promised():
    # "≥ 0 of 4" read as a forecast while the CLI and verdict promise nothing
    nothing = _measured_scope(open_work=_open_work(n_open=4, at_least_85=0.0))
    assert scope_forecast_tile(nothing, open_count=4, total=6) == Tile(
        "4 open issues of the scope",
        "n/a",
        "none of 4 open issues can be promised done in 8 weeks; all by 01 Feb 2024",
    )


def test_scope_forecast_tile_says_why_there_is_no_forecast():
    young = ScopeResult({}, {}, {}, None, "measured", why_not="not forecastable yet")
    assert scope_forecast_tile(young, open_count=3, total=3) == Tile(
        "3 open issues of the scope", "n/a", "not forecastable yet"
    )


def test_scope_forecast_tile_says_how_far_it_was_checked():
    forecast = {"backlog": 4, "p85": 3.0, "p85_date": date(2024, 2, 1)}
    assumed = ScopeResult(forecast, {}, {}, None, "assumed")
    tile = scope_forecast_tile(assumed, 4, 6, note="assumed, not checked")
    assert tile == Tile(
        "all 4 open issues of the scope done (85% chance)",
        "by 01 Feb 2024",
        "assumed, not checked",
    )


def test_build_headline_tiles_leave_out_the_scope_tile_without_a_scope():
    tiles = build_headline_tiles(
        scatter=_scatter_df(),
        aging=_aging_df(),
        open_work={},
        forecast={},
        flow_efficiency=0.0,
    )
    assert not any("of the scope" in tile.label for tile in tiles)


def test_build_delivery_tiles():
    lead_times = pd.DataFrame({"lead_time_days": [1.0, 3.0, 5.0]})
    tiles = build_delivery_tiles(
        weekly={"2026W36": 1, "2026W37": 3},
        lead_times=lead_times,
        failure_rate=0.25,
        recovery_days=[0.5, 1.5],
    )
    assert tiles == [
        Tile("Deploys", "2.0/wk"),
        Tile("Change lead time p50", "3.0d"),
        Tile("Change fail rate", "25%"),
        Tile("Recovery time p50", "1.0d"),
    ]


def test_build_delivery_tiles_without_enough_deploys():
    tiles = build_delivery_tiles(
        weekly={},
        lead_times=pd.DataFrame({"lead_time_days": []}),
        failure_rate=None,
        recovery_days=[],
    )
    assert [tile.value for tile in tiles] == ["n/a", "n/a", "n/a", "no failures"]


def _summary(held_independent: int, independent: int) -> BacktestSummary:
    return BacktestSummary(
        horizon=8,
        count=40,
        independent=independent,
        held_85=0.9,
        kolmogorov=0.2,
        mean_crps=9.0,
        held_independent=held_independent,
    )


def test_backtest_tile_reads_natural_frequency():
    assert backtest_tile(_summary(4, independent=23)) == Tile(
        "past 8-week promises held",
        "4 of 23",
        "fewer than promised",
        delta_good=False,
    )
    assert backtest_tile(_summary(11, independent=12)) == Tile(
        "past 8-week promises held",
        "11 of 12",
        "as promised",
        delta_good=True,
    )


def test_backtest_tile_does_not_judge_on_few_independent_outcomes():
    tile = backtest_tile(_summary(1, independent=3))
    assert tile.value == "1 of 3"
    assert tile.delta_text == "only 3 independent outcomes"
    assert tile.delta_good is None


def test_backtest_tile_shows_the_shorter_horizon_the_verdict_heeds():
    # MDEV: 9 of 11 at 8 weeks is within chance, 16 of 23 at 4 weeks is not
    four = replace(_summary(16, independent=23), horizon=4)
    eight = _summary(9, independent=11)
    assert backtest_tile(eight, [four, eight]) == Tile(
        "past 4-week promises held",
        "16 of 23",
        "fewer than promised",
        delta_good=False,
    )
    held = replace(_summary(20, independent=23), horizon=4)
    assert backtest_tile(eight, [held, eight]).value == "9 of 11"


def test_backtest_tile_without_enough_history():
    assert backtest_tile(None).value == "n/a"


def test_open_work_tile_reads_at_least_of_open():
    assert open_work_tile(_open_work()) == Tile(
        "of 151 open issues done in 8 weeks (85% chance)", "≥ 31"
    )
    recalibrated = open_work_tile(_open_work(recalibrated=True))
    assert recalibrated.label.endswith(", recalibrated")
    assert open_work_tile({}).value == "n/a"


def test_clear_date_tile_says_not_within_two_years():
    assert clear_date_tile({"p85_date": None}, 151) == Tile(
        "all 151 open issues done (85% chance)", "not within 2 years"
    )
    assert clear_date_tile({"p85_date": date(2027, 6, 29)}, 151).value == (
        "by 29 Jun 2027"
    )
    assert clear_date_tile({}, 0).value == "n/a"


def test_flow_tile_flags_more_arriving_than_done():
    # discards leave the open list too, so finishes alone cannot say it grows
    assert flow_tile(BacklogFlow(arrived=21.0, finished=18.5)) == Tile(
        "Arrivals and finishes",
        "21.0 in / 18.5 done per week",
        "more arrive than get done",
        delta_good=False,
    )
    assert flow_tile(None).value == "n/a"


def test_flow_tile_names_the_weeks_its_figures_come_from():
    flow = BacklogFlow(arrived=3.0, finished=4.0, pace=Pace(half_life=8))
    assert flow_tile(flow).label == "Arrivals and finishes, half-life 8 weeks"


def test_flow_tile_claims_no_direction_within_weekly_noise():
    # Hibernate: 24.7 in, 24.5 done, while its open list fell by a sixth
    assert flow_tile(BacklogFlow(arrived=24.7, finished=24.5)) == Tile(
        "Arrivals and finishes",
        "24.7 in / 24.5 done per week",
    )


def _tested(
    horizon: int,
    independent: int,
    bias_p: float | None,
    trend_p: float | None,
) -> BacktestSummary:
    return BacktestSummary(
        horizon=horizon,
        count=90,
        independent=independent,
        held_85=0.78,
        kolmogorov=0.2,
        mean_crps=50.0,
        bias_p=bias_p,
        trend_p=trend_p,
    )


def test_diagnosis_finds_drift_at_any_horizon_with_enough_outcomes():
    note = diagnose_backtest(
        [
            _tested(4, 24, bias_p=0.052, trend_p=0.035),
            _tested(8, 12, bias_p=0.013, trend_p=0.298),
            _tested(41, 2, bias_p=0.5, trend_p=0.0),
        ],
    )
    assert note == (
        "4-week forecast errors drift over time (y-plot p = 0.035; at 8 weeks,"
        " the horizon judged, y-plot p = 0.298): the team's pace changes,"
        " so correcting forecasts by their past errors would not hold."
    )


def test_diagnosis_of_steady_bias():
    note = diagnose_backtest(
        [
            _tested(4, 24, bias_p=0.2, trend_p=0.4),
            _tested(8, 12, bias_p=0.011, trend_p=0.26),
        ],
    )
    assert note == (
        "8-week forecasts err the same way throughout (u-plot p = 0.011), with no"
        " sign of drift at 4 or 8 weeks:"
        " the case for recalibrating them by past errors."
    )


def test_diagnosis_without_evidence_of_bias_or_drift():
    note = diagnose_backtest(
        [
            _tested(4, 24, bias_p=0.4, trend_p=0.3),
            _tested(8, 12, bias_p=0.6, trend_p=0.2),
        ],
    )
    assert note == (
        "No sign that forecasts over 4 or 8 weeks are biased or drift over time"
        " (lowest u-plot p = 0.400, lowest y-plot p = 0.200)."
    )


def test_diagnosis_needs_enough_independent_outcomes():
    note = diagnose_backtest([_tested(8, 3, bias_p=0.01, trend_p=0.01)])
    assert (
        note
        == "Too few independent outcomes to test forecast errors for bias or drift."
    )


def _scored_crps(held_85: float, crps_mean: float) -> BacktestSummary:
    return BacktestSummary(
        horizon=8,
        count=74,
        independent=10,
        held_85=held_85,
        kolmogorov=0.2,
        mean_crps=crps_mean,
    )


def test_recalibration_note_when_the_correction_scores_worse():
    note = recalibration_note(_scored_crps(0.51, 37.6), _scored_crps(0.80, 40.2))
    assert note == (
        "Recalibrated by their past errors, 8-week forecasts kept 80% of their 85%"
        " promises instead of 51% but scored a worse CRPS (40.2 against 37.6),"
        " so the forecast is not recalibrated."
    )


def test_recalibration_note_when_the_correction_scores_better():
    note = recalibration_note(_scored_crps(0.51, 40.2), _scored_crps(0.80, 37.6))
    assert note == (
        "Recalibrated by their past errors, 8-week forecasts kept 80% of their 85%"
        " promises instead of 51% and scored a better CRPS (37.6 against 40.2),"
        " so the forecast is recalibrated."
    )


def test_date_check_note_tells_promises_past_the_cap_from_those_not_yet_due():
    note = date_check_note(DateSummary(held=0, judged=0, not_due=3, beyond_cap=87))
    assert note == (
        "Clear dates: none of 90 past promises judged; 3 not yet due,"
        " 87 past the 2-year cap and never due."
    )


def test_date_check_note_reads_held_of_judged():
    note = date_check_note(DateSummary(held=3, judged=4, not_due=10))
    assert note == (
        "Clear dates: held 3 of 4 independent past promises; 10 not yet due."
    )


def test_date_check_note_counts_one_promise_in_the_singular():
    note = date_check_note(DateSummary(held=0, judged=0, not_due=0, beyond_cap=1))
    assert note == (
        "Clear dates: none of 1 past promise judged;"
        " 1 past the 2-year cap and never due."
    )


def test_date_check_note_without_promises():
    note = date_check_note(DateSummary(held=0, judged=0, not_due=0))
    assert note == "Clear dates: too little history to replay past promises."


def test_unmeasured_share_note_only_when_the_share_was_assumed():
    assumed = _open_work(share_measured=False)
    assert unmeasured_share_note(assumed, "its open issues") == (
        "share of finishes going to its open issues not measured"
        " (too few past 8-week windows); assuming all of them"
    )
    assert unmeasured_share_note(_open_work(share_measured=True), "open issues") is None
    assert unmeasured_share_note({}, "open issues") is None


def test_bulk_closure_note_names_a_week_over_five_times_the_median():
    throughput = {f"2024W{w:02d}": 10 for w in range(1, 10)}
    assert bulk_closure_note(throughput, {}) is None
    assert bulk_closure_note({**throughput, "2024W05": 50}, {}) is None
    note = bulk_closure_note(
        {**throughput, "2024W05": 51, "2024W07": 400},
        {"2024W07": 200},
    )
    assert note == (
        "Bulk closure: 2024W07 finished 400 issues, over 5 times the median week's"
        " 10 (1 more such week); it inflates the pace. If these were not delivered,"
        " add their resolution to --discarded-resolutions."
    )


def test_bulk_closure_note_without_a_typical_week():
    # most weeks finish nothing: no median to measure a spike against
    assert bulk_closure_note({"2024W01": 0, "2024W02": 0, "2024W03": 9}, {}) is None
    assert bulk_closure_note({}, {}) is None


def test_bulk_closure_note_reads_a_delivered_batch_as_a_release():
    # CAMEL 2026W29: 162 of 183 closed as Fixed over three days of a release
    throughput = {f"2024W{w:02d}": 10 for w in range(1, 10)}
    note = bulk_closure_note({**throughput, "2024W07": 183}, {"2024W07": 162})
    assert note == (
        "Bulk closure: 2024W07 finished 183 issues, over 5 times the median week's"
        " 10; most were resolved as delivered, so a release closed in one week"
        " inflates the pace."
    )


def _dated_forecast(**changes) -> dict:
    return {"backlog": 151, "p85": 30.0, "p85_date": date(2024, 7, 1), **changes}


def test_trust_reads_held_of_independent_promises():
    assert trust(_summary(11, independent=12)) == Trust("holds", 11, 12)
    assert trust(_summary(4, independent=23)) == Trust("optimistic", 4, 23)
    assert trust(_summary(3, independent=3)) == Trust("unchecked", 3, 3)
    assert trust(None) == Trust("unchecked", 0, 0)


def test_trust_calls_optimistic_only_beyond_chance():
    # an honest 85% promise lands 9 or fewer of 11 about half the time
    assert trust(_summary(9, independent=11)) == Trust("holds", 9, 11)
    # P(X <= 17 | 23, 0.85) is about 0.12, still within chance
    assert trust(_summary(17, independent=23)) == Trust("holds", 17, 23)
    # P(X <= 16 | 23, 0.85) is about 0.046, just past chance
    assert trust(_summary(16, independent=23)) == Trust("optimistic", 16, 23)
    assert trust(_summary(14, independent=23)) == Trust("optimistic", 14, 23)


def test_backtest_tile_calls_short_of_85_within_chance_as_promised():
    tile = backtest_tile(_summary(9, independent=11))
    assert tile.delta_text == "as promised"
    assert tile.delta_good is True


def test_forecast_verdict_says_a_share_below_85_held_within_chance():
    verdict = forecast_verdict(
        _open_work(), _dated_forecast(), Trust("holds", 9, 11), None, None
    )
    assert verdict[1] == (
        "Past 8-week promises like this one held 9 of 11 times,"
        " in line with the 85% promised."
    )


def test_forecast_verdict_says_commit_when_held_as_promised():
    verdict = forecast_verdict(
        _open_work(),
        _dated_forecast(),
        Trust("holds", 17, 20),
        BacklogFlow(arrived=20.0, finished=24.0),
        DateSummary(held=0, judged=0, not_due=74),
    )
    assert verdict[0] == (
        "At least 31 of the 151 open issues will be done in 8 weeks,"
        " by 01 Mar 2024 (85% chance)."
    )
    assert "held 17 of 20 times" in verdict[1]
    assert "20.0 issues arrive and 24.0 get done a week" in " ".join(verdict)
    assert verdict[-1].startswith("Commit to the number")


def test_forecast_verdict_says_optimistic_when_fewer_held():
    verdict = forecast_verdict(
        _open_work(),
        _dated_forecast(),
        Trust("optimistic", 12, 20),
        None,
        None,
    )
    assert "held only 12 of 20 times" in verdict[1]
    assert "optimistic" in verdict[-1]
    assert "Commit to the number" not in verdict[-1]


def test_forecast_verdict_says_too_little_history():
    verdict = forecast_verdict(
        _open_work(),
        _dated_forecast(),
        Trust("unchecked", 2, 3),
        None,
        None,
    )
    assert "too little history" in verdict[1]
    assert "guess" in verdict[-1]


def test_forecast_verdict_advises_against_a_date_when_arrivals_outpace_finishes():
    verdict = forecast_verdict(
        _open_work(),
        _dated_forecast(p85=None, p85_date=None),
        Trust("holds", 17, 20),
        BacklogFlow(arrived=30.0, finished=24.0),
        DateSummary(held=0, judged=0, not_due=74),
    )
    text = " ".join(verdict)
    assert "Not all 151 open issues will be done within 2 years" in text
    assert "more arrive than get done" in text
    assert verdict[-1] == (
        "Commit to the number, but don't promise a date for all of it;"
        " forecast a specific release instead (--forecast-jql)."
    )


def test_forecast_verdict_without_a_forecast():
    assert forecast_verdict({}, {}, trust(None), None, None) == [
        "No forecast: no open issues, or fewer than 7 weeks of finished work.",
    ]


def test_verdict_has_no_method_jargon():
    verdicts = [
        forecast_verdict(
            _open_work(recalibrated=True),
            _dated_forecast(p85=None, p85_date=None),
            Trust(word, 12, 20),
            BacklogFlow(arrived=30.0, finished=24.0),
            DateSummary(held=3, judged=4, not_due=10),
            narrow=_tails(4, 11),
        )
        for word in ("holds", "optimistic", "unchecked")
    ]
    verdicts.append(
        scope_verdict(
            "fixVersion = 7.2",
            ScopeResult(
                _dated_forecast(backlog=10),
                _open_work(n_open=10, at_least_85=8.0),
                {},
                None,
                "measured",
            ),
            Trust("holds", 11, 12),
            open_count=10,
            total=42,
        ),
    )
    text = " ".join(" ".join(verdict) for verdict in verdicts)
    for jargon in ("CRPS", "u-plot", "y-plot", "Kolmogorov", "p =", "percentile"):
        assert jargon not in text


def test_scope_verdict_reads_the_release_date_and_its_trust():
    verdict = scope_verdict(
        "fixVersion = 7.2",
        ScopeResult(
            _dated_forecast(backlog=10),
            _open_work(n_open=10, at_least_85=8.0),
            {},
            None,
            "measured",
        ),
        Trust("holds", 11, 12),
        open_count=10,
        total=42,
    )
    assert verdict[0] == (
        "Release fixVersion = 7.2: at least 8 of its 10 open issues done"
        " in 8 weeks, by 01 Mar 2024 (85% chance), paced by its own finishes."
    )
    assert "held 11 of 12 times" in verdict[1]
    assert verdict[2] == (
        "All 10 of its open issues done by 01 Jul 2024 (85% chance);"
        " no past date like it has come due to check it."
    )


def test_scope_verdict_does_not_lend_the_replayed_trust_to_its_date():
    verdict = scope_verdict(
        "fixVersion = 7.2",
        ScopeResult(
            _dated_forecast(backlog=10),
            _open_work(n_open=10, at_least_85=8.0),
            {},
            DateSummary(held=0, judged=0, not_due=12),
            "measured",
        ),
        Trust("holds", 11, 12),
        open_count=10,
        total=42,
    )
    promise, trusted, date_line = verdict
    # the trust sentence follows the replayed promise, never the extrapolated date
    assert "8 of its 10 open issues done in 8 weeks" in promise
    assert "01 Jul 2024" not in promise
    assert "like this one held 11 of 12 times" in trusted
    assert "01 Jul 2024" in date_line
    assert "no past date like it has come due" in date_line


def test_scope_verdict_says_a_finished_release_is_done_without_a_chance():
    verdict = scope_verdict(
        "fixVersion = 7.2",
        ScopeResult({}, {}, {}, None, "measured"),
        trust(None),
        open_count=0,
        total=65,
    )
    assert verdict == ["Release fixVersion = 7.2 done: none of its 65 issues open."]


def test_scope_verdict_judges_a_finished_release_whose_replay_failed():
    # WFLY 39: done, yet its 4-week promises held 1 of 6, which the next
    # release's forecast inherits
    verdict = scope_verdict(
        "fixVersion = 39",
        ScopeResult({}, {}, {}, None, "measured"),
        Trust("optimistic", 1, 6, horizon=4),
        open_count=0,
        total=65,
    )
    assert verdict == [
        "Release fixVersion = 39 done: none of its 65 issues open.",
        "Its past 4-week forecasts held only 1 of 6 times, fewer than the 85%"
        " promised: treat release forecasts for this project as optimistic.",
    ]


def test_scope_verdict_judges_a_finished_release_at_its_judged_horizon():
    # IGNITE 3.1: its judged 4-week replay itself rejects, with no shorter one
    four = replace(_summary(6, 11), horizon=4)
    verdict = scope_verdict(
        "fixVersion = 3.1",
        ScopeResult({}, {}, {}, None, "measured"),
        heeded_trust(four, [four]),
        open_count=0,
        total=40,
    )
    assert verdict[1] == (
        "Its past 4-week forecasts held only 6 of 11 times, fewer than the 85%"
        " promised: treat release forecasts for this project as optimistic."
    )


def test_scope_verdict_leaves_a_finished_release_unjudged_when_its_replay_held():
    verdict = scope_verdict(
        "fixVersion = 7.2",
        ScopeResult({}, {}, {}, None, "measured"),
        Trust("holds", 10, 11),
        open_count=0,
        total=65,
    )
    assert verdict == ["Release fixVersion = 7.2 done: none of its 65 issues open."]


def test_scope_verdict_says_why_there_is_no_forecast():
    verdict = scope_verdict(
        "fixVersion = 7.2",
        ScopeResult({}, {}, {}, None, "measured", why_not="not forecastable yet"),
        trust(None),
        open_count=3,
        total=3,
    )
    assert verdict == ["Release fixVersion = 7.2: not forecastable yet."]


def test_scope_verdict_reads_one_open_issue_in_the_singular():
    verdict = scope_verdict(
        "fixVersion = 7.2",
        ScopeResult(
            _dated_forecast(backlog=1, p85=None, p85_date=None),
            _open_work(n_open=1, at_least_85=0.0),
            {},
            None,
            "measured",
        ),
        Trust("unchecked", 1, 1),
        open_count=1,
        total=167,
    )
    assert verdict[0].startswith(
        "Release fixVersion = 7.2: the 1 open issue cannot be promised done in 8 weeks"
    )
    assert "1 past 8-week promise could be replayed" in verdict[1]
    assert verdict[2].startswith(
        "The 1 open issue will not be done within 2 years at this pace"
    )


def test_scope_verdict_counts_issues_created_after_its_first_finish():
    verdict = scope_verdict(
        "fixVersion = 7.2",
        ScopeResult(
            _dated_forecast(backlog=10),
            _open_work(n_open=10, at_least_85=8.0),
            {},
            None,
            "measured",
            created_after_start=3,
        ),
        Trust("holds", 11, 12),
        open_count=10,
        total=42,
    )
    assert verdict[-1] == "3 of its 42 issues were created after its first finish."


def test_forecast_verdict_puts_the_release_before_the_action():
    release = ["Release fixVersion = 7.2: all 10 open issues done by 01 Jul 2024."]
    verdict = forecast_verdict(
        _open_work(),
        _dated_forecast(p85=None, p85_date=None),
        Trust("unchecked", 2, 3),
        BacklogFlow(arrived=30.0, finished=24.0),
        None,
        release,
    )
    assert verdict[-2] == release[0]
    assert "guess" in verdict[-1]
    assert "don't promise a date for all of it" in verdict[-1]
    # the release is already scoped, so advising to scope one is noise
    assert "--forecast-jql" not in " ".join(verdict)


def test_forecast_verdict_still_reads_the_release_without_a_forecast():
    release = ["Release fixVersion = 7.2: nothing left to forecast."]
    assert (
        forecast_verdict({}, {}, trust(None), None, None, release)[-1] == (release[0])
    )


def test_forecast_verdict_with_no_flow_does_not_say_more_arrive():
    verdict = forecast_verdict(
        _open_work(),
        _dated_forecast(),
        Trust("holds", 17, 20),
        BacklogFlow(arrived=0.0, finished=0.0),
        None,
    )
    assert "more arrive than get done" not in " ".join(verdict)
    assert "don't promise" not in verdict[-1]


def test_forecast_verdict_does_not_vouch_for_a_date_from_too_few_checks():
    verdict = forecast_verdict(
        _open_work(),
        _dated_forecast(),
        Trust("holds", 17, 20),
        None,
        DateSummary(held=1, judged=1, not_due=10),
    )
    text = " ".join(verdict)
    assert "held 1 of 1" not in text
    assert "only 1 past date like it has come due" in text


def test_scope_verdict_names_the_assumed_focus_once():
    verdict = scope_verdict(
        "fixVersion = 7.2",
        ScopeResult(
            _dated_forecast(backlog=10),
            {},
            {},
            None,
            "assumed",
        ),
        trust(None),
        focus=0.5,
        open_count=10,
        total=42,
    )
    assert verdict == [
        "Release fixVersion = 7.2: all 10 open issues done by 01 Jul 2024"
        " (85% chance), at an assumed 50% of the team's pace, not checked.",
    ]


def test_assumed_pace_note_matches_the_verdict():
    assert assumed_pace_note(0.4) == (
        "at an assumed 40% of the team's pace, not checked"
    )


def test_forecast_verdict_flow_keeps_the_decimal_that_decides_behind():
    verdict = forecast_verdict(
        _open_work(),
        _dated_forecast(),
        Trust("holds", 17, 20),
        BacklogFlow(arrived=5.4, finished=4.6),
        None,
    )
    assert (
        "About 5.4 issues arrive and 4.6 get done a week; more arrive than get done."
    ) in verdict


def test_trust_calls_far_more_held_than_promised_cautious():
    # P(X >= 55 | 55, 0.85) is about 1e-4: an 85% promise keeps fewer
    assert trust(_summary(55, independent=55)) == Trust("cautious", 55, 55)
    # P(X >= 11 | 11, 0.85) is about 0.17, within chance
    assert trust(_summary(11, independent=11)) == Trust("holds", 11, 11)


def test_trust_calls_optimistic_from_few_outcomes_beyond_chance():
    # P(X <= 0 | 3, 0.85) is about 0.003 and P(X <= 1 | 4, 0.85) about 0.012
    assert trust(_summary(0, independent=3)) == Trust("optimistic", 0, 3)
    assert trust(_summary(1, independent=4)) == Trust("optimistic", 1, 4)
    assert trust(_summary(5, independent=9)) == Trust("optimistic", 5, 9)
    # too few to confirm a promise kept, though
    assert trust(_summary(4, independent=4)) == Trust("unchecked", 4, 4)


def test_backtest_tile_says_fewer_than_promised_from_few_outcomes():
    tile = backtest_tile(_summary(0, independent=3))
    assert tile.delta_text == "fewer than promised"
    assert tile.delta_good is False


def test_backtest_tile_says_more_than_promised_when_cautious():
    tile = backtest_tile(_summary(108, independent=108))
    assert tile.delta_text == "more than promised"
    assert tile.delta_good is None


def test_forecast_verdict_calls_a_number_held_far_more_often_cautious():
    verdict = forecast_verdict(
        _open_work(), _dated_forecast(), Trust("cautious", 108, 108), None, None
    )
    assert verdict[1] == (
        "Past 8-week promises like this one held 108 of 108 times,"
        " more than the 85% promised: the number is cautious."
    )
    assert verdict[-1] == "Commit to the number and expect more."


def test_forecast_verdict_promising_none_does_not_say_commit():
    verdict = forecast_verdict(
        _open_work(at_least_85=0.0),
        _dated_forecast(p85=None, p85_date=None),
        Trust("holds", 17, 20),
        BacklogFlow(arrived=30.0, finished=24.0),
        None,
    )
    assert verdict[0] == (
        "None of the 151 open issues can be promised done in 8 weeks,"
        " by 01 Mar 2024 (85% chance)."
    )
    assert "Commit" not in " ".join(verdict)
    assert verdict[-1] == (
        "Don't commit to a number or a date yet:"
        " the forecast cannot promise any of the open issues."
    )


def test_forecast_verdict_does_not_say_commit_under_an_optimistic_release():
    verdict = forecast_verdict(
        _open_work(),
        _dated_forecast(),
        Trust("holds", 17, 20),
        None,
        None,
        ["Release fixVersion = 7.2: at least 3 of its 10 open issues done."],
        release_trust=Trust("optimistic", 1, 4),
        release_at_least=3.0,
    )
    assert verdict[-1] == (
        "Treat the release's number as optimistic and commit to fewer of its issues."
    )


def test_scope_verdict_says_none_can_be_promised_for_at_least_zero():
    verdict = scope_verdict(
        "fixVersion = 7.2",
        ScopeResult(
            _dated_forecast(backlog=10),
            _open_work(n_open=10, at_least_85=0.0),
            {},
            None,
            "measured",
        ),
        Trust("unchecked", 0, 0),
        open_count=10,
        total=42,
    )
    assert verdict[0] == (
        "Release fixVersion = 7.2: none of its 10 open issues can be promised done"
        " in 8 weeks, by 01 Mar 2024 (85% chance), paced by its own finishes."
    )


def test_clear_date_says_fewer_than_promised_from_few_dates_beyond_chance():
    verdict = forecast_verdict(
        _open_work(),
        _dated_forecast(),
        Trust("holds", 17, 20),
        None,
        DateSummary(held=0, judged=5, not_due=3),
    )
    # P(X <= 0 | 5, 0.85) is about 8e-5
    assert verdict[-2] == (
        "All 151 open issues done by 01 Jul 2024 (85% chance);"
        " past dates like it held only 0 of 5, fewer than the 85% promised."
    )


def test_diagnosis_of_drift_cites_the_judged_horizon_too():
    note = diagnose_backtest(
        [
            _tested(4, 24, bias_p=0.5, trend_p=0.03),
            _tested(8, 12, bias_p=0.5, trend_p=0.2),
        ],
    )
    assert note == (
        "4-week forecast errors drift over time (y-plot p = 0.030;"
        " at 8 weeks, the horizon judged, y-plot p = 0.200): the team's pace"
        " changes, so correcting forecasts by their past errors would not hold."
    )


def test_forecast_verdict_ignores_the_trust_of_a_release_with_no_number():
    verdict = forecast_verdict(
        _open_work(),
        _dated_forecast(),
        Trust("holds", 8, 11),
        None,
        None,
        ["Release fixVersion = 2.7.0: nothing left to forecast."],
        release_trust=Trust("optimistic", 0, 3),
        release_at_least=None,
    )
    assert verdict[-1] == "Commit to the number."


def test_forecast_verdict_keeps_the_team_action_when_the_release_promises_none():
    verdict = forecast_verdict(
        _open_work(),
        _dated_forecast(),
        Trust("optimistic", 6, 11),
        None,
        None,
        ["Release fixVersion = 2.3.0: none of its 1 open issues can be promised."],
        release_trust=Trust("unchecked", 0, 0),
        release_at_least=0.0,
    )
    assert verdict[-2:] == [
        "Treat the number as optimistic and commit to fewer.",
        "For the release, don't commit to a number or a date yet:"
        " the forecast cannot promise any of its issues.",
    ]


def test_heeded_trust_takes_a_rejection_at_a_shorter_horizon():
    four = replace(_summary(0, independent=3), horizon=4)
    eight = _summary(0, independent=1)
    # P(X <= 0 | 3, 0.85) is about 0.003, while 0 of 1 is within chance
    assert heeded_trust(eight, [four, eight]) == Trust("optimistic", 0, 3, horizon=4)


def test_heeded_trust_keeps_the_judged_horizon_without_a_shorter_rejection():
    four = replace(_summary(4, independent=4), horizon=4)
    eight = _summary(11, independent=12)
    assert heeded_trust(eight, [four, eight]) == Trust("holds", 11, 12, horizon=8)
    longer = replace(_summary(0, independent=3), horizon=12)
    assert heeded_trust(eight, [eight, longer]) == Trust("holds", 11, 12, horizon=8)
    assert heeded_trust(None, []) == Trust("unchecked", 0, 0)


def test_forecast_verdict_names_the_shorter_horizon_that_rejects_it():
    verdict = forecast_verdict(
        _open_work(),
        _dated_forecast(),
        Trust("optimistic", 0, 3, horizon=4),
        None,
        None,
    )
    assert verdict[1] == (
        "Past 4-week promises of this forecast held only 0 of 3 times,"
        " fewer than the 85% promised."
    )
    assert verdict[-1] == "Treat the number as optimistic and commit to fewer."


def test_promised_done_says_none_for_at_least_zero():
    assert promised_done(_open_work()) == "at least 31 of 151 open issues done"
    assert promised_done(_open_work(at_least_85=0.0), "its ") == (
        "none of its 151 open issues can be promised done"
    )


def test_promised_done_names_one_open_issue_in_the_singular():
    assert promised_done(_open_work(n_open=1, at_least_85=0.0), "its ") == (
        "the 1 open issue cannot be promised done"
    )
    assert promised_done(_open_work(n_open=1, at_least_85=1.0)) == (
        "the 1 open issue done"
    )


def test_diagnosis_of_drift_cites_the_horizon_the_verdict_judges():
    # the verdict judges 12 weeks, whose drift is untestable: no other is named
    note = diagnose_backtest(
        [
            _tested(4, 24, bias_p=0.5, trend_p=0.03),
            _tested(8, 12, bias_p=0.5, trend_p=0.2),
            _tested(12, 12, bias_p=0.5, trend_p=None),
        ],
    )
    assert note == (
        "4-week forecast errors drift over time (y-plot p = 0.030):"
        " the team's pace changes, so correcting forecasts by their past"
        " errors would not hold."
    )


def _tails(outer_tails: int, independent: int, horizon: int = 8) -> BacktestSummary:
    return replace(
        _summary(independent, independent),
        horizon=horizon,
        outer_tails=outer_tails,
    )


def test_narrow_spread_needs_more_outer_tails_than_chance():
    # P(X >= 3 | 11, 0.1) is about 0.09, P(X >= 4 | 11, 0.1) about 0.019
    assert narrow_spread(_tails(3, 11), [_tails(3, 11)]) is None
    narrow = _tails(4, 11)
    assert narrow_spread(narrow, [narrow]) == narrow


def test_narrow_spread_heeds_a_shorter_horizon_as_the_trust_does():
    eight = _tails(2, 11)
    four = _tails(7, 23, horizon=4)
    assert narrow_spread(eight, [four, eight]) == four
    assert narrow_spread(eight, [_tails(4, 23, horizon=4), eight]) is None
    assert narrow_spread(None, [four]) is None


def test_forecast_verdict_says_the_range_is_too_narrow_after_the_trust():
    # SPARK: promises held as often as promised, yet outcomes kept landing
    # beyond either end of the forecast's range
    verdict = forecast_verdict(
        _open_work(),
        _dated_forecast(),
        Trust("holds", 9, 11),
        None,
        None,
        narrow=_tails(4, 11),
    )
    assert verdict[2] == (
        "The forecast's range is too narrow: past 8-week outcomes fell outside"
        " it 4 of 11 times, where 10% was expected."
    )
    plain = forecast_verdict(
        _open_work(), _dated_forecast(), Trust("holds", 9, 11), None, None
    )
    assert verdict[:2] + verdict[3:-1] == plain[:-1]


def test_forecast_verdict_does_not_say_commit_when_the_range_is_too_narrow():
    # MB: 7 of 11 held, within chance of 85%, yet 6 of 11 outcomes fell outside
    # the range, so the number is too high more often than it says
    verdict = forecast_verdict(
        _open_work(),
        _dated_forecast(),
        Trust("holds", 7, 11),
        None,
        None,
        narrow=_tails(6, 11),
    )
    assert verdict[-1] == "Commit to fewer than the number."


def test_backtest_tile_flags_a_range_too_narrow():
    narrow = _tails(6, 11)
    assert backtest_tile(narrow, [narrow]) == Tile(
        "past 8-week promises held",
        "11 of 11",
        "range too narrow",
        delta_good=False,
    )


def test_spread_note_gives_the_test_behind_the_verdict():
    assert spread_note(_tails(4, 11)) == (
        "8-week outcomes fell beyond the forecast's 5th or 95th percentile"
        " 4 of 11 times against 10% expected (binomial p = 0.019):"
        " the forecast's range is too narrow."
    )


def test_spread_note_does_not_round_a_strong_rejection_to_zero():
    # MB, SPARK and FLINK: 6 of 11 eight-week outcomes beyond either end
    assert "(binomial p = 0.0003)" in spread_note(_tails(6, 11))
