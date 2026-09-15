# Metrics - Jira analytics for engineering teams

[![Build Status](https://github.com/smirnoffmg/metrics/actions/workflows/test.yaml/badge.svg)](https://github.com/smirnoffmg/metrics/actions)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

See how work really flows through your team - straight from Jira, in one command.

**Metrics** pulls your issues and turns them into clear charts plus a single shareable report:

- **How fast are we?** Lead time, cycle time, and a percentile view - "85% of our tickets finish within N days"
- **When will it be done?** A Monte Carlo forecast for your open backlog
- **Where does work get stuck?** Time per status, aging work-in-progress, and a cumulative flow diagram
- **Who carries the load?** Time in flight per person and how often tickets change hands
- **How much do we ship?** Weekly throughput and how often tickets bounce back to testing

Everything lands in `output/` as PNG charts and one self-contained `report.html` you can send to anyone - no servers, no setup, nothing leaves your machine. The report is interactive: headline numbers with trend arrows, hover any dot for the ticket details, click it to open the issue in Jira, and a ready-made list of the longest-waiting tickets.

## Real examples

Every chart below comes from real public projects - the [Hibernate ORM](https://hibernate.atlassian.net) and [Apache Kafka](https://issues.apache.org/jira) issue trackers.

### When will it be done?

**Monte Carlo forecast.** 151 open Hibernate issues at the pace of the last 12 finished weeks: half the simulations clear them by 17 November 2026, 85% by 24 November - real dates, not story points.

![Monte Carlo forecast](docs/images/forecast.png)

**Weekly throughput.** How many issues get finished each week, with the overall trend. The week still in progress is left out, and quiet weeks count as zero.

![Throughput](docs/images/throughput.png)

### How fast do tickets finish?

**Cycle time, ticket by ticket.** Every dot is a Hibernate issue finished in the last three months - the last 4 weeks in blue, the slowest ticket named (HHH-3007, finished after more than twelve years), and the "slow zone" beyond p85 tinted red.

![Cycle time per issue](docs/images/cycle_time_scatter.png)

**Lead time.** From the moment a ticket is created to the moment it's done. The slowest 5% get a grey bar of their own instead of squeezing everything else into the first one.

![Lead time](docs/images/lead_time.png)

**Cycle time distribution.** The same story as the scatterplot, as a histogram with p50 and p85 marked.

![Cycle time](docs/images/cycle_time.png)

### Where does work get stuck?

**Cumulative flow.** Two months of Hibernate: each band is a status, widening bands are bottlenecks - and notable events annotate themselves, like 59 issues leaving "Release pending" in one day.

![Cumulative flow diagram](docs/images/cumulative_flow.png)

**Aging work-in-progress.** Started, unfinished Kafka issues by how long they've sat in their current status - anything above the dashed line has been waiting longer than 85% of past work ever did.

![Aging work-in-progress](docs/images/aging_wip.png)

**Median time per status.** Where a ticket's calendar time actually goes.

![Median hours per status](docs/images/cumulative_queue_time.png)

**Days in each status.** Every status of the workflow at a glance, one histogram each, the longest waits in grey.

![Queue time](docs/images/queue_time.png)

### How does the team work?

**Who carries the work.** Time in flight per assignee (names anonymized here) and how often tickets change hands.

![Assignee load](docs/images/assignee_load.png)

**Rework.** How many times tickets came back to review - each return is work done twice.

![Returns to review](docs/images/return_to_testing.png)

## Try it in one minute - no account needed

Point it at any public Jira, like Hibernate's:

```sh
uv sync
uv run python -m metrics --anonymous \
  --jira-server https://hibernate.atlassian.net \
  --jira-jql 'project = HHH AND (resolved >= -90d OR resolution = Unresolved AND updated >= -90d)' \
  --testing-statuses "In review, Waiting for review"

open output/report.html
```

## Get started with your own Jira

```sh
uv run python -m metrics --jira-server https://your-jira --jira-token <token> --jira-jql 'project=MYPROJ'
```

Then open `output/report.html`.

- **Jira Cloud:** also pass `--jira-email you@company.com` together with an API token.
- **Jira Server / Data Center:** just a personal access token, no email needed.
- **Public instance?** `--anonymous` needs no credentials at all and figures out Cloud vs Server by itself.
- **Your workflow ends differently?** Tell it what "finished" means, e.g. `--done-statuses "Resolved, Shipped"`. By default Jira's own status categories decide: statuses in the Done category finish an issue, statuses in To Do are backlog.
- **Dropped work isn't delivery.** Statuses like `--discarded-statuses "Rejected, Duplicate"` (default: cancelled, canceled, won't do) count neither as throughput nor as open backlog. The same goes for issues closed with a resolution like Won't Fix or Duplicate - set your own with `--discarded-resolutions "Won't Fix, Out of scope"`.
- **Cycle time starts at commitment, not at triage.** It runs from the moment an issue first leaves the backlog; by default, when it first leaves Jira's To Do category; name your pre-work statuses yourself with `--backlog-statuses "Open, Ready"`. Issues closed straight from the backlog have a lead time but no cycle time.
- **QA has its own name?** Same for the rework metric, e.g. `--testing-statuses "In review, QA"` (default: testing).
- **Curious how much time is real work vs waiting?** Tell it where work happens, e.g. `--active-statuses "In Progress, In Development"` (default: in progress) - that powers the flow-efficiency number in the report: the share of cycle time spent in those statuses, so backlog waiting before work starts doesn't count.
- **When will this release or epic be done?** Name its issues with `--forecast-jql 'fixVersion = "9.0"'` and get its own forecast next to the backlog's, at the pace of your main query's issues. If the team spends only part of its time on it, say so: `--forecast-focus 0.5` forecasts at half the throughput.
- **How does delivery look?** Point it at the GitLab project behind the work, `--gitlab-project group/app --gitlab-token <token>`, and the report adds DORA's four keys: deploys per week, change lead time from commit to deploy, change fail rate and recovery time. Each release tag is a deploy (`--deploy-tag-pattern`, default `^v?\d+\.\d+\.\d+$`); a deploy failed when the next one is a hotfix (a merge request labelled `hotfix` or from a `hotfix*` branch), a revert, or a rollback to an earlier tag's commit. Name your coding agents with `--agent-authors srv_bot,agent@example.com` to compare their changes with people's.
- **Iterating on settings?** Fetch once with `--save-raw issues.json`, then rebuild the report as often as you like with `--from-raw issues.json` - no network, seconds instead of minutes, and the same numbers every time, since time-based metrics are computed as of the fetch.
- Prefer environment variables or a config file? `uv run python -m metrics --help` shows every option.

Tip: let your JQL include both finished and still-open issues - the forecast and aging charts need the open ones. Select finished issues by when they were resolved, e.g. `resolved >= -90d OR resolution = Unresolved`: a window on `created` leaves out the old issues your team is finishing now and understates throughput, and one on `updated` pulls in issues closed years ago.

## License

GPL - see [LICENSE](LICENSE).
