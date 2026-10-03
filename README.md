# Metrics - a Jira delivery forecast that honestly says how far you can trust it

[![Build Status](https://github.com/smirnoffmg/metrics/actions/workflows/test.yaml/badge.svg)](https://github.com/smirnoffmg/metrics/actions)
[![License](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)

Most forecasts give you a date. This one tells you how much of your open work gets done, replays that same promise from every past Monday, and says in plain words how often it came true - before you commit to it. Straight from Jira, in one command, into one self-contained `report.html` you can send to anyone. No servers, nothing leaves your machine.

## What it tells you

Every quote below is copied from the report on two years of the public [Hibernate ORM](https://hibernate.atlassian.net) and [Apache Kafka](https://issues.apache.org/jira) trackers.

**1. How much of our open work gets done, and when?**

> At least 31 of the 2093 open issues will be done in 8 weeks, by 28 Nov 2026 (85% chance).
>
> *- Hibernate*

The promise counts only issues open today. New work keeps arriving and takes its share of the team, so the forecast scales throughput by the share of past finishes that went to issues already open, measured over the same number of weeks.

**2. Can I trust that number?**

> Past 8-week promises like this one held 7 of 11 times, in line with the 85% promised.
>
> Commit to the number, but don't promise a date for all of it; forecast a specific release instead (--forecast-jql).
>
> *- Hibernate*

The same forecast is replayed from every past Monday, from only what Jira showed that day, and checked against what happened next. "7 of 11" counts promises whose outcomes don't overlap, so each one is real evidence. An honest 85% promise still misses now and then, so the count is judged against chance, not against a fixed 85% cutoff: only a count so low that an honest 85% promise would score it or fewer under 5% of the time (one-sided binomial test) makes the report call the number optimistic and say to commit to fewer. A count too high to be chance calls the number cautious; otherwise the report says to commit to the number, as here. A shorter horizon that already fails is heeded too:

> Past 4-week promises of this forecast held only 15 of 23 times, fewer than the 85% promised.
>
> *- Kafka*

**3. Will the open list ever clear?**

> About 35.4 issues arrive and 23.5 get done a week; more arrive than get done.
>
> Not all 5283 open issues will be done within 2 years at this pace; no past date like it has come due to check it.
>
> *- Kafka*

When arrivals keep up with finishes, a list may never return to zero, so the report would rather say "not within 2 years" than invent a date. For a date worth promising, forecast a release or an epic with `--forecast-jql`.

## Checked on 12 public trackers

The forecast was rebuilt and replayed on two years of 12 public Jira trackers: five run by companies (MariaDB, Couchbase, Red Hat WildFly, Percona, Atlassian Confluence), five Apache projects (Spark, Flink, Camel, NiFi, Ignite), plus Hibernate and Kafka.

- **The 8-week promise holds about 7 times in 10, where 85% was promised.** Pooled over all 12, 96 of 132 independent 8-week promises held (72.7%): 42 of 55 on the company-run trackers (76.4%), 38 of 55 on the Apache ones (69%). The Apache pool falls short of 85% by more than chance; the company-run pool falls short too, though not by enough to rule out chance (p = 0.06). 3 of the 12 reports call their own number optimistic: Kafka at 4 weeks (15 of 23) among them, while Hibernate holds 7 of 11 at 8 weeks, in line with 85%.
- **Assuming every finish goes to open work is far worse.** That baseline held 11% of the same 8-week promises.
- **The fan is too narrow.** Outcomes land far out on both sides of it much more often than they should. It is clearest on the community-run Apache projects, where 44% of outcomes fall in the outer 5% on either side against 10% expected; the company-run trackers show it too, at 36%.
- **A release forecast says what it doesn't know, but its promises are weak.** Replayed from 1,298 past Mondays on 20 releases, it now reads a finished release as done, and says "not forecastable yet" where it used to fall back on the team's pace, whose dates held 27 of 314 times (9%). What it cannot do is promise a release reliably: its count promises held 65% of the time before the release and 38% after, its clear dates 34-37%, and on 113 Mondays it called a release "not within 2 years" that then cleared. Stragglers and issues added late move a release; take its numbers as a guide, not a commitment.

## Try it in one minute - no account needed

Point it at any public Jira, like Hibernate's:

```sh
uv sync
uv run python -m metrics --anonymous \
  --jira-server https://hibernate.atlassian.net \
  --jira-jql 'project = HHH AND (resolved >= -365d OR resolution = Unresolved)' \
  --testing-statuses "In review, Waiting for review"

open output/report.html
```

Fetch a year of history: the replay needs it to measure how much of the work goes to issues already open, and to have enough past promises to judge. With less, the report says so - the share goes unmeasured, and too few past promises leave the forecast unchecked. The forecast itself needs seven weeks of finishes: the first is left out, since the query may start partway through it.

The history starts where the fetch does: at the earliest resolution date among the fetched issues. A query like the one above also brings in issues closed years ago without a resolution; their finishes are left out of throughput and of the replay rather than stretching the history back to before the window.

## Get started with your own Jira

```sh
uv run python -m metrics --jira-server https://your-jira --jira-token <token> \
  --jira-jql 'project = MYPROJ AND (resolved >= -365d OR resolution = Unresolved)'
```

Then open `output/report.html`.

- **Jira Cloud:** also pass `--jira-email you@company.com` together with an API token.
- **Jira Server / Data Center:** just a personal access token, no email needed.
- **Public instance?** `--anonymous` needs no credentials at all and figures out Cloud vs Server by itself.
- **When will this release or epic be done?** Name its issues with `--forecast-jql 'fixVersion = "9.0"'`. With seven weeks or more of its own finishes it is forecast from them, which already leave out the time the team spent on other work, and replayed like the main forecast. If you'd rather state how much of the team works on it, `--forecast-focus 0.5` forecasts at half the team's pace; the report marks that as an assumption it cannot check. With too few finishes of its own, or too few past windows to measure how much of them goes to its open issues, and no focus, the release is not forecast, and there is no fallback: the report says "not forecastable yet" or "no promise yet" and asks for `--forecast-focus`, since the whole team's pace and "all finishes go to the open issues" both promised far more than was done. Like the main forecast, the release leads with how many of its open issues get done; the date all of them are done comes second, since a straggler or an issue added late can push it out by months. A finished release reads as done, without a chance.
- **Your workflow ends differently?** Tell it what "finished" means, e.g. `--done-statuses "Resolved, Shipped"`. By default Jira's own status categories decide: statuses in the Done category finish an issue, statuses in To Do are backlog.
- **Dropped work isn't delivery.** Statuses like `--discarded-statuses "Rejected, Duplicate"` (default: cancelled, canceled, won't do) count neither as throughput nor as open work. The same goes for issues closed with a resolution like Won't Fix or Duplicate, and for triage closures such as Obsolete, Out of Date, Rejected, Timed Out or Later - `--help` lists them all. Set your own with `--discarded-resolutions "Won't Fix, Superseded"`; the list replaces the defaults.
- **A bulk closure is called out.** A week that finishes over 5 times the median week is named, since it inflates the pace, with the advice: "If these were not delivered, add their resolution to --discarded-resolutions." On Hibernate a triage sweep once closed 144 issues as Out of Date and 27 as Rejected in one week; both resolutions are discarded by default now, so it no longer counts as delivery. A release that closes its issues in one go trips the warning too; issues closed as Fixed or Done were delivered, so leave their resolution alone.
- **Cycle time starts at commitment, not at triage.** It runs from the moment an issue first leaves the backlog; by default, when it first leaves Jira's To Do category; name your pre-work statuses yourself with `--backlog-statuses "Open, Ready"`. Issues closed straight from the backlog have a lead time but no cycle time.
- **QA has its own name?** Same for the rework metric, e.g. `--testing-statuses "In review, QA"` (default: testing).
- **Curious how much time is real work vs waiting?** Tell it where work happens, e.g. `--active-statuses "In Progress, In Development"` (default: in progress) - that powers the flow-efficiency number: the share of cycle time spent in those statuses.
- **Iterating on settings?** Fetch once with `--save-raw issues.json`, then rebuild the report as often as you like with `--from-raw issues.json` - no network, seconds instead of minutes, and the same numbers every time, since time-based metrics are computed as of the fetch.
- Prefer environment variables or a config file? `uv run python -m metrics --help` shows every option.

Tip: let your JQL include both finished and still-open issues - the forecast and aging charts need the open ones. Select finished issues by when they were resolved: a window on `created` leaves out the old issues your team is finishing now and understates throughput, and one on `updated` pulls in issues closed years ago.

## Charts that explain the forecast

**The forecast as a fan.** How many of today's open issues stay open, week by week: the dashed line is the even bet, the solid line the 85% one, and the dot marks the horizon the replay could check. Beyond it the fan is extrapolated.

![Forecast fan](docs/images/forecast.png)

**Cumulative flow: arrivals vs departures.** Each band is a status. The top edge climbs with every issue that arrives, the done bands with every issue that leaves; while the open bands beneath them keep their height, the open list isn't shrinking, whatever the team's pace. Notable events annotate themselves, like a release closing a pile of issues in one day.

![Cumulative flow diagram](docs/images/cumulative_flow.png)

**Aging work-in-progress.** Started, unfinished Kafka issues by how long they've sat in their current status - anything above the dashed line has been waiting longer than 85% of past work ever did. The report also lists the longest-waiting tickets.

![Aging work-in-progress](docs/images/aging_wip.png)

**Cycle time, ticket by ticket.** Every dot is a finished Hibernate issue - the most recent in blue, the slowest named, and the "slow zone" beyond p85 tinted red. Hover a dot in the report for the ticket, click it to open it in Jira.

![Cycle time per issue](docs/images/cycle_time_scatter.png)

**Cycle time distribution.** The same story as a histogram with p50 and p85 marked.

![Cycle time](docs/images/cycle_time.png)

**Weekly throughput.** How many issues get finished each week, with the trend. The week still in progress is left out, and quiet weeks count as zero.

![Throughput](docs/images/throughput.png)

## Also in the report

**Handoffs.** How often an issue changes hands before it's done - a property of the process, not of a person.

![Handoffs](docs/images/handoffs.png)

**Lead time.** From the moment a ticket is created to the moment it's done.

![Lead time](docs/images/lead_time.png)

**Where a ticket's calendar time goes.** The median time per status, and every status's own histogram.

![Median hours per status](docs/images/cumulative_queue_time.png)

![Queue time](docs/images/queue_time.png)

**Rework.** How many times tickets came back to review - each return is work done twice.

![Returns to review](docs/images/return_to_testing.png)

**Delivery (DORA).** Point it at the GitLab project behind the work, `--gitlab-project group/app --gitlab-token <token>`, and the report adds DORA's four keys: deploys per week, change lead time from commit to deploy, change fail rate and recovery time. Each release tag is a deploy (`--deploy-tag-pattern`, default `^v?\d+\.\d+\.\d+$`); a deploy failed when the next one is a hotfix (a merge request labelled `hotfix` or from a `hotfix*` branch), a revert, or a rollback to an earlier tag's commit. Name your coding agents with `--agent-authors srv_bot,agent@example.com` to compare their changes with people's.

## What it deliberately does not measure: individuals

The report names no one. Data on individuals works only as self-assessment that management never sees, and "if ever the data is used against even one individual, the entire data collection scheme will come to an abrupt halt" (DeMarco & Lister, *Peopleware*, 2nd ed., с. 61, PDF 74). They list "performance measurement in almost any form" among the things that kill teams (с. 183–184, PDF 196–197). A forecast also needs honest statuses in Jira: once people are measured by them, they stop being honest. So the report shows the system - flow, queues, handoffs - and ends with a reminder: these numbers describe the system; don't turn them into targets.

<details>
<summary>How the forecast is made and checked</summary>

### The forecast

- **What it predicts.** Of the issues open today, how many get done in the next H weeks, at 85% and at 50%. Each simulation draws past weeks' throughput and a share of finishes that went to issues already open, taken from past H-week windows. The headline promise is the 15th percentile of the done count.
- **Why a share.** Work is not served first-in, first-out: urgent and short jobs move to the front (Reinertsen, *The Principles of Product Development Flow*, с. 70, PDF 84), so new arrivals take part of every week. A queue's size is only the balance of arrivals and departures (с. 71–72, PDF 85–86), and with both random it may stay far from zero for long periods (Q15, the Diffusion Principle, с. 76–78, PDF 90–92). The baseline, all throughput to open issues, is the old belief, and the replay shows what it costs: on Hibernate it held 0 of 11 independent 8-week promises (0% of 83 past forecasts), against 7 of 11 with the share.
- **Fixed date, variable scope.** "How much by when" is the question a forecast can answer and check; "when will all of it be done" depends on work not yet asked for (Beck, *Extreme Programming Explained*, 1st ed., PDF 23). The clear date is still shown, from the same simulation, capped at 2 years.

### The replay

- **Only what was known then.** From every past Monday, each issue's status, resolution and assignee are rolled back through its changelog, so the replay sees reopened and not-yet-created work as it stood that day. A prediction system is valid only if it makes accurate predictions of what it claims to predict, established by comparing it with known data in its environment (Fenton & Pfleeger, *Software Metrics: A Rigorous Approach*, с. 104–105, PDF 117–118). So the replay checks the very forecast the headline shows, with the 85% promise as the acceptance range stated in advance.
- **Independent outcomes.** Forecasts made a week apart share most of their outcome. Each horizon also counts the promises whose intervals don't overlap; the verdict judges the longest horizon with at least 10 of them, and with fewer it states the count instead of a verdict; a shorter horizon whose promises already fail is heeded first. "Held 7 of 11" counts those independent promises; the table beside it also gives the share of all past forecasts. A promise of "at least 0" cannot fail, so it is not judged.
- **Pace.** The same replay picks which past weeks the forecast draws from - the last 12, 26 or 52 weeks equally, or every week weighted by recency with a half-life of 4 or 8 weeks - by the lowest CRPS, a score of how far past forecasts landed from what happened. Paces within 5% of the best count as equal and the earlier in that list wins. Weeks, and the past windows the share is measured over, come only from the fetched history, which starts at the earliest Jira resolution date. Hibernate forecasts from the last 26 weeks, Kafka from a half-life of 4 weeks.
- **Bias and drift.** A u-plot per horizon shows whether past forecasts leaned optimistic, pessimistic or too narrow; a y-plot test (after Brocklehurst and Littlewood) shows whether their errors drift over time, tested on independent outcomes only. On Kafka, 4-week forecasts err the same way throughout (u-plot p = 0.045) with no sign of drift; on Hibernate neither horizon leans or drifts (lowest u-plot p = 0.277, lowest y-plot p = 0.502).
- **Recalibration.** When errors keep a steady bias but don't drift, the book's remedy is tried: every past forecast is recalibrated by the u-plot of the forecasts whose outcomes were known by its Monday. It is used only when it also wins on a global score - CRPS standing in for the prequential likelihood Fenton and Pfleeger ask for - and the tile then says so.
- **The naive baseline.** A clever predictor may barely beat a naive one (Fenton & Pfleeger, Example 3.17, с. 105). So the table shows "baseline (all throughput to open issues)" next to the model, at every horizon.
- **Clear dates.** Past "all done by D" promises are judged only once D has passed, and only when their intervals don't overlap. On both trackers: "none of 90 past promises judged; 90 past the 2-year cap and never due."

![Forecast backtest](docs/images/forecast_backtest.png)

### The check on 12 trackers

- **Held rate.** Each tracker was rebuilt from a saved snapshot and its judged, independent promises pooled. A one-sided binomial test asks whether the pool holds fewer than 85%: at 8 weeks all 12 held 96/132 = 72.7% (p = 2e-4), the company-run five 42/55 = 76.4% (p = 0.06), the Apache five 38/55 = 69% (p = 0.002). At 4 weeks all 12 held 220/276 = 79.7%. The baseline held 11% at 8 weeks.
- **Spread.** Each past outcome has a u value: the share of the forecast's simulations that came out below it, ties counted half. For a well-made forecast u is uniform, so 15% of outcomes fall below 0.15 and 15% above 0.85. Pooled over all 12 at 8 weeks, 29% fell below and 28% above, and a Kolmogorov-Smirnov test against uniform gives p = 0.001 (Apache p = 0.011, company-run p = 0.24). In the outer 5% tails, expected 10% together, the Apache trackers have 44% and the company-run 36%. Too many outcomes in both tails means the fan is too narrow, not that it leans one way; the verdict can only say optimistic or cautious, so it does not report this yet.
- **Releases.** The release forecast was replayed from every Monday from 30 weeks before each of 20 releases up to the snapshot: 1,298 Mondays. States are rolled back, membership is today's. Neighbouring Mondays share most of their outcome, so these are shares, not independent tests.
- **Caveats.** The trackers share calendar weeks, so pooled promises are not strictly independent. The verdict rejects when either horizon fails at 0.05, so under a well-made forecast it raises a false alarm up to about 10% of the time; MariaDB's 4-week 16 of 23 (p = 0.046) is borderline.

### Assumptions

- The past share of finishes going to issues already open carries over into the next H weeks.
- Dates beyond the checked horizon are extrapolated, and lean optimistic: the share falls as the horizon grows.
- Discarded issues are not "done": they leave the list but don't count toward the promise.
- Membership in a `--forecast-jql` scope is not rolled back: the replay takes today's scope as if it had been the scope on every past Monday.

</details>

## License

GPL v3 - see [LICENSE](LICENSE).
