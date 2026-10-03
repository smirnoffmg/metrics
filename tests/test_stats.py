"""Tests for headline tiles and stuck-ticket rows."""

from __future__ import annotations

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
    clear_date_tile,
    date_check_note,
    diagnose_backtest,
    flow_tile,
    forecast_verdict,
    open_work_tile,
    recalibration_note,
    scope_forecast_tile,
    scope_verdict,
    trust,
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
        "p50": 40.0,
        "at_least_85": 31.0,
        "by_date": date(2024, 3, 1),
        "share": 0.4,
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


def test_build_headline_tiles_puts_the_scope_after_the_date():
    scope = scope_forecast_tile(
        {"p85": 3.0, "p85_date": date(2024, 2, 1)}, open_count=4, total=6
    )
    tiles = build_headline_tiles(
        scatter=_scatter_df(),
        aging=_aging_df(),
        open_work={},
        forecast={},
        flow_efficiency=0.0,
        scope_tile=scope,
    )
    assert tiles[3] == Tile(
        "all 6 issues of the scope done (85% chance)", "by 01 Feb 2024"
    )


def test_scope_forecast_tile_says_when_nothing_is_left():
    assert scope_forecast_tile({}, open_count=0, total=2) == Tile(
        "all 2 issues of the scope done (85% chance)", "all done"
    )
    assert scope_forecast_tile({}, open_count=3, total=3).value == "n/a"


def test_scope_forecast_tile_says_how_far_it_was_checked():
    forecast = {"p85": 3.0, "p85_date": date(2024, 2, 1)}
    tile = scope_forecast_tile(forecast, 4, 6, note="assumed, not checked")
    assert tile.delta_text == "assumed, not checked"
    assert tile.delta_good is None


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
        "4-week forecast errors drift over time (y-plot p = 0.035): the team's pace"
        " changes, so correcting forecasts by their past errors would not hold."
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


def test_date_check_note_says_none_judged_while_promises_are_not_due():
    note = date_check_note(DateSummary(held=0, judged=0, not_due=74))
    assert note == (
        "Clear dates: 0 judged; all 74 past promises fall beyond the data so far."
    )


def test_date_check_note_reads_held_of_judged():
    note = date_check_note(DateSummary(held=3, judged=4, not_due=10))
    assert note == (
        "Clear dates: held 3 of 4 independent past promises; 10 not yet due."
    )


def test_date_check_note_without_promises():
    note = date_check_note(DateSummary(held=0, judged=0, not_due=0))
    assert note == "Clear dates: too little history to replay past promises."


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
    )
    promise, trusted, date_line = verdict
    # the trust sentence follows the replayed promise, never the extrapolated date
    assert "8 of its 10 open issues done in 8 weeks" in promise
    assert "01 Jul 2024" not in promise
    assert "like this one held 11 of 12 times" in trusted
    assert "01 Jul 2024" in date_line
    assert "no past date like it has come due" in date_line


def test_scope_verdict_without_a_focus_says_the_whole_team_pace_is_not_checked():
    # no --forecast-focus: the whole team's pace is used, and no share was assumed
    verdict = scope_verdict(
        "fixVersion = 7.2",
        ScopeResult(
            _dated_forecast(backlog=10, p85=None, p85_date=None),
            {},
            {},
            None,
            "assumed",
        ),
        trust(None),
    )
    assert verdict == [
        "Release fixVersion = 7.2: not all 10 open issues done within 2 years"
        " (85% chance), at the whole team's pace, not checked.",
    ]


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
    )
    assert verdict == [
        "Release fixVersion = 7.2: all 10 open issues done by 01 Jul 2024"
        " (85% chance), at an assumed 50% of the team's pace, not checked.",
    ]


def test_assumed_pace_note_matches_the_verdict():
    assert assumed_pace_note(None) == "at the whole team's pace, not checked"
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
