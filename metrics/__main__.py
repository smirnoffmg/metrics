"""CLI entrypoint for Jira engineering metrics analysis."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import timedelta
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click
from dependency_injector import providers

if TYPE_CHECKING:
    from datetime import datetime

    import pandas as pd

    from metrics.entity import Issue
from dependency_injector.wiring import Provide, inject

from metrics.consts import (
    ACTIVE_STATUSES,
    BACKLOG_STATUSES,
    DISCARDED_RESOLUTIONS,
    DISCARDED_STATUSES,
    DONE_STATUSES,
    TESTING_STATUSES,
)
from metrics.containers import Container
from metrics.repository.gitlab import (
    DEFAULT_DELIVERY_DAYS,
    DEFAULT_GITLAB_URL,
    DEFAULT_HOTFIX_LABELS,
    DEFAULT_TAG_PATTERN,
)
from metrics.repository.jira import JiraIssuesRepository  # noqa: TC001
from metrics.repository.snapshot import StaticSnapshotSource, load_snapshot
from metrics.services import (  # noqa: TC001
    InteractiveVisService,
    ReportService,
    VisService,
)
from metrics.services.backtest import (
    SHORT_HORIZONS_WEEKS,
    BacktestSummary,
    backtest_forecast,
    summarize_backtests,
)
from metrics.services.calculator import (
    aging_wip,
    assignee_load,
    cumulative_flow,
    cycle_time_points,
    cycle_times,
    flow_efficiency,
    lead_times,
    median_queue_hours,
    monte_carlo_forecast,
    queue_times,
    returns_to_testing,
    weekly_throughput,
)
from metrics.services.delivery import (
    agent_comparison,
    change_failure_rate,
    change_lead_times,
    deployment_frequency,
    deploys_from_raw,
    recovery_times,
)
from metrics.services.stats import (
    Tile,
    backtest_tile,
    build_delivery_tiles,
    build_headline_tiles,
    build_stuck_rows,
    scope_forecast_tile,
)

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]


GITLAB_CONFIG_KEYS = (
    "gitlab_url",
    "gitlab_token",
    "gitlab_project",
    "deploy_tag_pattern",
    "hotfix_labels",
    "agent_authors",
    "delivery_days",
)


def load_config_file(config_path: str) -> dict[str, Any]:
    """Load configuration from a YAML or JSON file."""
    path = Path(config_path)
    if not path.exists():
        msg = f"Config file not found: {config_path}"
        raise FileNotFoundError(msg)
    ext = path.suffix.lower()
    with path.open() as f:
        if ext in (".yaml", ".yml"):
            if not yaml:
                msg = (
                    "PyYAML is required for YAML config files."
                    " Install with 'pip install pyyaml'."
                )
                raise ImportError(msg)
            return yaml.safe_load(f)
        if ext == ".json":
            return json.load(f)
        msg = f"Unsupported config file format: {ext}"
        raise ValueError(msg)


def merge_config(
    file_cfg: dict[str, str | None],
    env_cfg: dict[str, str | None],
    cli_cfg: dict[str, str | None],
) -> dict[str, str | None]:
    """Merge config sources with priority: CLI > ENV > FILE."""
    return {
        key: cli_cfg.get(key) or env_cfg.get(key) or file_cfg.get(key)
        for key in set(file_cfg) | set(env_cfg) | set(cli_cfg)
    }


def parse_bool(value: object) -> bool:
    """Normalize a flag value from CLI bool, env string, or config file."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def parse_status_list(
    value: str | list[str] | None,
    default: list[str] | None,
) -> list[str] | None:
    """Normalize a status list from a comma string or list; default otherwise."""
    if value is None:
        return default
    if isinstance(value, str):
        value = value.split(",")
    return [status.strip().lower() for status in value if status.strip()]


def get_env_config() -> dict[str, str | None]:
    """Read Jira configuration from environment variables."""
    return {
        "server": os.environ.get("JIRA_SERVER"),
        "token": os.environ.get("JIRA_TOKEN"),
        "jql": os.environ.get("JIRA_JQL"),
        "email": os.environ.get("JIRA_EMAIL"),
        "done_statuses": os.environ.get("JIRA_DONE_STATUSES"),
        "discarded_statuses": os.environ.get("JIRA_DISCARDED_STATUSES"),
        "discarded_resolutions": os.environ.get("JIRA_DISCARDED_RESOLUTIONS"),
        "backlog_statuses": os.environ.get("JIRA_BACKLOG_STATUSES"),
        "testing_statuses": os.environ.get("JIRA_TESTING_STATUSES"),
        "active_statuses": os.environ.get("JIRA_ACTIVE_STATUSES"),
        "anonymous": os.environ.get("JIRA_ANONYMOUS"),
        "forecast_jql": os.environ.get("JIRA_FORECAST_JQL"),
        "forecast_focus": os.environ.get("JIRA_FORECAST_FOCUS"),
        "gitlab_url": os.environ.get("GITLAB_URL"),
        "gitlab_token": os.environ.get("GITLAB_TOKEN"),
        "gitlab_project": os.environ.get("GITLAB_PROJECT"),
        "deploy_tag_pattern": os.environ.get("GITLAB_DEPLOY_TAG_PATTERN"),
        "hotfix_labels": os.environ.get("GITLAB_HOTFIX_LABELS"),
        "agent_authors": os.environ.get("GITLAB_AGENT_AUTHORS"),
        "delivery_days": os.environ.get("GITLAB_DELIVERY_DAYS"),
    }


def _focus_errors(focus: object) -> list[str]:
    if focus is None:
        return []
    try:
        in_range = 0 < float(str(focus)) <= 1
    except ValueError:
        in_range = False
    return [] if in_range else ["Forecast focus must be a number above 0 and up to 1."]


def _gitlab_errors(cfg: dict[str, Any]) -> list[str]:
    errors = []
    pattern = cfg.get("deploy_tag_pattern")
    if pattern:
        try:
            re.compile(pattern)
        except re.error as err:
            errors.append(
                f"Deploy tag pattern is not a valid regular expression: {err}"
            )
    days = cfg.get("delivery_days")
    if days is not None and not (str(days).isdigit() and int(days) > 0):
        errors.append("Delivery days must be a whole number above 0.")
    return errors


def validate_config(cfg: dict[str, Any]) -> list[str]:
    """Validate required Jira configuration fields."""
    errors = _focus_errors(cfg.get("forecast_focus")) + _gitlab_errors(cfg)
    if cfg.get("from_raw"):
        return errors
    server = cfg.get("server")
    anonymous = parse_bool(cfg.get("anonymous"))
    if not server:
        errors.append(
            "Jira server URL is missing."
            " Set --jira-server, JIRA_SERVER, or config file.",
        )
    elif not server.startswith(("http://", "https://")):
        errors.append(
            "Jira server URL must start with http:// or https://.",
        )
    if anonymous:
        if cfg.get("token"):
            errors.append(
                "--anonymous cannot be combined with a Jira token; drop one of them.",
            )
        if cfg.get("email"):
            errors.append(
                "--anonymous cannot be combined with --jira-email; drop one of them.",
            )
    elif not cfg.get("token"):
        errors.append(
            "Jira token is missing. Set --jira-token, JIRA_TOKEN, or config file"
            " (or use --anonymous for public instances).",
        )
    if not cfg.get("jql"):
        errors.append(
            "Jira JQL is missing. Set --jira-jql, JIRA_JQL, or config file.",
        )
    return errors


@click.command(
    help="""
    Analyze and visualize Jira issue metrics.

    Examples:\n
      python -m metrics --jira-server https://your-jira \\
        --jira-token <token> --jira-jql 'project=MYPROJ'
      python -m metrics --config config.yaml
    """,
)
@click.option(
    "--config",
    type=click.Path(exists=True),
    help="Path to YAML or JSON config file (see README for format).",
)
@click.option(
    "--jira-server",
    envvar="JIRA_SERVER",
    help="Jira server URL (e.g., https://your-jira).",
)
@click.option(
    "--jira-token",
    envvar="JIRA_TOKEN",
    help="Jira API token (see your Jira profile/API settings).",
)
@click.option(
    "--jira-jql",
    envvar="JIRA_JQL",
    help="Jira JQL query for issues (e.g., 'project=MYPROJ').",
)
@click.option(
    "--jira-email",
    envvar="JIRA_EMAIL",
    help="Account email; enables Jira Cloud mode (basic auth with API token)."
    " Omit for Server/Data Center with a personal access token.",
)
@click.option(
    "--done-statuses",
    envvar="JIRA_DONE_STATUSES",
    help="Comma-separated statuses that mean an issue is finished"
    " (default: statuses in Jira's Done category; for statuses of unknown"
    f" category, {','.join(DONE_STATUSES)}).",
)
@click.option(
    "--discarded-statuses",
    envvar="JIRA_DISCARDED_STATUSES",
    help="Comma-separated statuses that mean an issue was dropped, not delivered:"
    " excluded from throughput, cycle time, and the open backlog"
    f" (default: {','.join(DISCARDED_STATUSES)}).",
)
@click.option(
    "--discarded-resolutions",
    envvar="JIRA_DISCARDED_RESOLUTIONS",
    help="Comma-separated resolutions that mean an issue in a done status was"
    " dropped, not delivered"
    f" (default: {','.join(DISCARDED_RESOLUTIONS)}).",
)
@click.option(
    "--backlog-statuses",
    envvar="JIRA_BACKLOG_STATUSES",
    help="Comma-separated statuses before work is committed to; cycle time starts"
    " when an issue first leaves them (default: statuses in Jira's To Do"
    f" category; for statuses of unknown category, {','.join(BACKLOG_STATUSES)}).",
)
@click.option(
    "--testing-statuses",
    envvar="JIRA_TESTING_STATUSES",
    help="Comma-separated statuses that count as testing/QA for the"
    f" return-to-testing metric (default: {','.join(TESTING_STATUSES)}).",
)
@click.option(
    "--active-statuses",
    envvar="JIRA_ACTIVE_STATUSES",
    help="Comma-separated statuses where work is actively done, for the"
    f" flow-efficiency metric (default: {','.join(ACTIVE_STATUSES)}).",
)
@click.option(
    "--forecast-jql",
    envvar="JIRA_FORECAST_JQL",
    help="JQL naming the issues to forecast, such as an epic or a release"
    " (e.g. 'fixVersion = 7.2'); forecast at the pace of the main query's issues.",
)
@click.option(
    "--forecast-focus",
    envvar="JIRA_FORECAST_FOCUS",
    help="Share of the team's throughput spent on the forecast issues, above 0"
    " and up to 1 (default: 1, the team works on nothing else).",
)
@click.option(
    "--gitlab-project",
    envvar="GITLAB_PROJECT",
    help="GitLab project path (e.g. group/app) whose release tags are its deploys;"
    " adds DORA delivery metrics to the report.",
)
@click.option(
    "--gitlab-url",
    envvar="GITLAB_URL",
    help=f"GitLab instance URL (default: {DEFAULT_GITLAB_URL}).",
)
@click.option(
    "--gitlab-token",
    envvar="GITLAB_TOKEN",
    help="GitLab access token with read_api scope.",
)
@click.option(
    "--deploy-tag-pattern",
    envvar="GITLAB_DEPLOY_TAG_PATTERN",
    help="Regular expression for tags that are deploys"
    f" (default: {DEFAULT_TAG_PATTERN}).",
)
@click.option(
    "--hotfix-labels",
    envvar="GITLAB_HOTFIX_LABELS",
    help="Comma-separated merge request labels marking a hotfix; branches named"
    f" hotfix* count too (default: {','.join(DEFAULT_HOTFIX_LABELS)}).",
)
@click.option(
    "--agent-authors",
    envvar="GITLAB_AGENT_AUTHORS",
    help="Comma-separated usernames, commit author names or emails of agents,"
    " to compare their changes with people's.",
)
@click.option(
    "--delivery-days",
    envvar="GITLAB_DELIVERY_DAYS",
    help=f"Days of deploys to measure (default: {DEFAULT_DELIVERY_DAYS}).",
)
@click.option(
    "--save-raw",
    type=click.Path(dir_okay=False),
    help="Also save the issues fetched from Jira to this JSON file.",
)
@click.option(
    "--from-raw",
    type=click.Path(exists=True, dir_okay=False),
    help="Build the report from a file written by --save-raw, without Jira;"
    " time-based metrics are computed as of when it was fetched.",
)
@click.option(
    "--anonymous",
    is_flag=True,
    default=False,
    help="Connect without credentials - for public Jira instances"
    " (e.g. open-source project trackers). No token needed.",
)
def cli(  # noqa: PLR0913
    config: str | None,
    jira_server: str | None,
    jira_token: str | None,
    jira_jql: str | None,
    jira_email: str | None,
    done_statuses: str | None,
    discarded_statuses: str | None,
    discarded_resolutions: str | None,
    backlog_statuses: str | None,
    testing_statuses: str | None,
    active_statuses: str | None,
    forecast_jql: str | None,
    forecast_focus: str | None,
    gitlab_project: str | None,
    gitlab_url: str | None,
    gitlab_token: str | None,
    deploy_tag_pattern: str | None,
    hotfix_labels: str | None,
    agent_authors: str | None,
    delivery_days: str | None,
    save_raw: str | None,
    from_raw: str | None,
    anonymous: bool,  # noqa: FBT001 - click flag
) -> None:
    """Analyze and visualize Jira issue metrics."""
    logger = logging.getLogger(__name__)
    file_cfg: dict[str, str | None] = {
        "server": None,
        "token": None,
        "jql": None,
        "email": None,
        "done_statuses": None,
        "discarded_statuses": None,
        "discarded_resolutions": None,
        "backlog_statuses": None,
        "testing_statuses": None,
        "active_statuses": None,
        "anonymous": None,
        "forecast_jql": None,
        "forecast_focus": None,
        **dict.fromkeys(GITLAB_CONFIG_KEYS),
    }
    if config:
        try:
            file_data = load_config_file(config)
            jira_section = file_data.get("jira", {})
            gitlab_section = file_data.get("gitlab", {})
            file_cfg = {
                "server": jira_section.get("server"),
                "token": jira_section.get("token"),
                "jql": jira_section.get("jql"),
                "email": jira_section.get("email"),
                "done_statuses": jira_section.get("done_statuses"),
                "discarded_statuses": jira_section.get("discarded_statuses"),
                "discarded_resolutions": jira_section.get("discarded_resolutions"),
                "backlog_statuses": jira_section.get("backlog_statuses"),
                "testing_statuses": jira_section.get("testing_statuses"),
                "active_statuses": jira_section.get("active_statuses"),
                "anonymous": jira_section.get("anonymous"),
                "forecast_jql": jira_section.get("forecast_jql"),
                "forecast_focus": jira_section.get("forecast_focus"),
                **{
                    key: gitlab_section.get(key.removeprefix("gitlab_"))
                    for key in GITLAB_CONFIG_KEYS
                },
            }
        except (FileNotFoundError, ImportError, ValueError) as e:
            click.echo(f"Error loading config file: {e}", err=True)
            sys.exit(1)
    env_cfg = get_env_config()
    cli_cfg: dict[str, Any] = {
        "server": jira_server,
        "token": jira_token,
        "jql": jira_jql,
        "email": jira_email,
        "done_statuses": done_statuses,
        "discarded_statuses": discarded_statuses,
        "discarded_resolutions": discarded_resolutions,
        "backlog_statuses": backlog_statuses,
        "testing_statuses": testing_statuses,
        "active_statuses": active_statuses,
        "anonymous": anonymous or None,
        "from_raw": from_raw,
        "forecast_jql": forecast_jql,
        "forecast_focus": forecast_focus,
        "gitlab_url": gitlab_url,
        "gitlab_token": gitlab_token,
        "gitlab_project": gitlab_project,
        "deploy_tag_pattern": deploy_tag_pattern,
        "hotfix_labels": hotfix_labels,
        "agent_authors": agent_authors,
        "delivery_days": delivery_days,
    }
    cfg = merge_config(file_cfg, env_cfg, cli_cfg)
    is_anonymous = parse_bool(cfg.get("anonymous"))
    errors = validate_config(cfg)
    if errors:
        for err in errors:
            click.echo(f"Error: {err}", err=True)
        sys.exit(1)
    try:
        snapshot = load_snapshot(from_raw) if from_raw else None
        wanted_scope = cfg.get("forecast_jql")
        if snapshot and wanted_scope and wanted_scope != snapshot.forecast_jql:
            saved = snapshot.forecast_jql or "no forecast query"
            click.echo(
                f"Error: {from_raw} was saved with {saved}, not '{wanted_scope}';"
                " fetch again with --forecast-jql and --save-raw.",
                err=True,
            )
            sys.exit(1)
        container = Container()
        container.config.from_dict(
            {
                "jira": {
                    "server": snapshot.server if snapshot else cfg["server"],
                    "token": cfg["token"],
                    "jql": snapshot.jql if snapshot else cfg["jql"],
                    "save_raw": save_raw,
                    "forecast_jql": snapshot.forecast_jql
                    if snapshot
                    else cfg.get("forecast_jql") or "",
                    "forecast_focus": float(cfg.get("forecast_focus") or 1),
                    "email": cfg.get("email"),
                    "anonymous": is_anonymous,
                    # None = auto-detect from serverInfo (anonymous mode)
                    "cloud": None if is_anonymous else bool(cfg.get("email")),
                    # unset done and backlog lists leave it to status categories
                    "done_statuses": parse_status_list(
                        cfg.get("done_statuses"),
                        None,
                    ),
                    "discarded_statuses": parse_status_list(
                        cfg.get("discarded_statuses"),
                        DISCARDED_STATUSES,
                    ),
                    "discarded_resolutions": parse_status_list(
                        cfg.get("discarded_resolutions"),
                        DISCARDED_RESOLUTIONS,
                    ),
                    "backlog_statuses": parse_status_list(
                        cfg.get("backlog_statuses"),
                        None,
                    ),
                    "testing_statuses": parse_status_list(
                        cfg.get("testing_statuses"),
                        TESTING_STATUSES,
                    ),
                    "active_statuses": parse_status_list(
                        cfg.get("active_statuses"),
                        ACTIVE_STATUSES,
                    ),
                },
                "gitlab": {
                    "url": cfg.get("gitlab_url") or DEFAULT_GITLAB_URL,
                    "token": cfg.get("gitlab_token"),
                    "project": cfg.get("gitlab_project") or "",
                    "deploy_tag_pattern": cfg.get("deploy_tag_pattern")
                    or DEFAULT_TAG_PATTERN,
                    "hotfix_labels": parse_status_list(
                        cfg.get("hotfix_labels"),
                        DEFAULT_HOTFIX_LABELS,
                    ),
                    "agent_authors": parse_status_list(cfg.get("agent_authors"), []),
                    "delivery_days": int(
                        cfg.get("delivery_days") or DEFAULT_DELIVERY_DAYS,
                    ),
                },
            },
        )
        if snapshot:
            container.snapshot_source.override(
                providers.Object(StaticSnapshotSource(snapshot)),
            )
        container.init_resources()
        container.wire(modules=[__name__])
        calculate_metrics()
    except Exception:
        logger.exception("Fatal error")
        sys.exit(1)


@inject
def calculate_metrics(  # noqa: PLR0913
    repo: JiraIssuesRepository = Provide[Container.repo],
    vis_service: VisService = Provide[Container.vis_service],
    interactive_service: InteractiveVisService = Provide[
        Container.interactive_vis_service
    ],
    report_service: ReportService = Provide[Container.report_service],
    server_url: str = Provide[Container.config.jira.server],
    active_statuses: list[str] = Provide[Container.config.jira.active_statuses],
    testing_statuses: list[str] = Provide[Container.config.jira.testing_statuses],
    forecast_focus: float = Provide[Container.config.jira.forecast_focus],
    agent_authors: list[str] = Provide[Container.config.gitlab.agent_authors],
    hotfix_labels: list[str] = Provide[Container.config.gitlab.hotfix_labels],
) -> None:
    """Calculate all metrics, save charts, and write the HTML report."""
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    issues = repo.all()
    now = repo.snapshot.fetched_at
    scatter = cycle_time_points(issues)
    cfd = cumulative_flow(issues, now=now)
    aging = aging_wip(issues, now=now)
    throughput = weekly_throughput(issues, now=now)
    forecast = monte_carlo_forecast(issues, throughput, now=now)
    load, handoffs = assignee_load(issues)

    report_images = _render_static_charts(
        issues,
        testing_statuses,
        vis_service,
        output_dir,
        throughput,
        load,
        handoffs,
    )
    _render_flow_pngs(vis_service, output_dir, scatter, cfd, aging, forecast)

    fragments = [
        interactive_service.scatter_fragment(scatter, include_js=True),
        interactive_service.cfd_fragment(cfd),
    ]
    if not aging.empty:
        fragments.append(interactive_service.aging_fragment(aging))
    backtest = None
    backtests: list[BacktestSummary] = []
    if forecast:
        fragments.append(interactive_service.forecast_fragment(forecast))
        backtest, backtests, chart = _report_backtest(
            repo,
            throughput,
            forecast,
            vis_service,
            output_dir,
        )
        if chart:
            report_images.insert(0, chart)

    scope_tile = None
    if repo.snapshot.forecast_jql:
        scope = repo.forecast_issues()
        scope_forecast, title = _forecast_scope(
            repo.snapshot.forecast_jql,
            scope,
            throughput,
            now,
            forecast_focus,
        )
        scope_tile = scope_forecast_tile(
            scope_forecast,
            sum(1 for issue in scope if issue.is_open),
        )
        click.echo(title.replace("\n", ": "))
        if scope_forecast:
            vis_service.vis_forecast(
                str(output_dir / "forecast_scope.png"),
                scope_forecast,
                title=title,
            )
            fragments.insert(
                0,
                interactive_service.forecast_fragment(scope_forecast, title=title),
            )

    tiles = build_headline_tiles(
        scatter,
        aging,
        forecast,
        throughput,
        flow_efficiency(issues, active_statuses),
        scope_tile,
        backtest,
    )
    comparison = None
    if repo.snapshot.delivery:
        delivery_tiles, comparison, charts = _report_delivery(
            repo.snapshot.delivery,
            now,
            agent_authors,
            hotfix_labels,
            vis_service,
            output_dir,
        )
        tiles.extend(delivery_tiles)
        report_images.extend(charts)

    report_path = output_dir / "report.html"
    report_service.render(
        str(report_path),
        tiles=tiles,
        images=report_images,
        fragments=fragments,
        stuck_rows=build_stuck_rows(aging, server_url),
        agent_comparison=comparison,
        backtests=backtests,
    )
    click.echo(f"Report: {report_path}")


def _report_backtest(
    repo: JiraIssuesRepository,
    throughput: dict[str, int],
    forecast: dict[str, Any],
    vis_service: VisService,
    output_dir: Path,
) -> tuple[Tile, list[BacktestSummary], Path | None]:
    """Replay past forecasts over short horizons and the one the forecast promises."""
    horizon = max(1, round(forecast["p85"]))
    # the horizons rebuild the same Mondays, so each moment is converted once
    throughput_at = cache(lambda at: weekly_throughput(repo.issues_at(at), now=at))
    runs = {
        h: backtest_forecast(throughput_at, list(throughput), horizon=h)
        for h in sorted({*SHORT_HORIZONS_WEEKS, horizon})
    }
    summaries = {
        h: summary
        for h, results in runs.items()
        if (summary := summarize_backtests(results)) is not None
    }
    for h, summary in summaries.items():
        click.echo(
            f"Backtest: {summary.held_85:.0%} of {summary.count} past 85% forecasts"
            f" over {h} weeks held ({summary.independent} independent);"
            f" Kolmogorov distance {summary.kolmogorov:.2f}",
        )
    tile = backtest_tile(summaries.get(horizon))
    if horizon not in summaries:
        click.echo(f"Backtest: too little history for {horizon}-week forecasts")
        return tile, list(summaries.values()), None
    chart = output_dir / "forecast_backtest.png"
    vis_service.vis_backtest(str(chart), runs, summaries, horizon)
    return tile, list(summaries.values()), chart


def _report_delivery(  # noqa: PLR0913
    delivery: dict[str, Any],
    now: datetime,
    agent_authors: list[str],
    hotfix_labels: list[str],
    vis_service: VisService,
    output_dir: Path,
) -> tuple[list[Tile], pd.DataFrame | None, list[Path]]:
    """DORA tiles, the agent comparison and charts for the snapshot's deploys."""
    deploys = deploys_from_raw(
        delivery,
        agent_authors=agent_authors,
        hotfix_labels=hotfix_labels,
    )
    # the tag before the window is only there to diff the first deploy against
    since = now - timedelta(days=delivery["days"])
    deploys = [deploy for deploy in deploys if deploy.at >= since]
    weekly = deployment_frequency(deploys, now)
    lead_times = change_lead_times(deploys)
    failure_rate = change_failure_rate(deploys)
    tiles = build_delivery_tiles(
        weekly,
        lead_times,
        failure_rate,
        recovery_times(deploys),
    )
    rate = f"{failure_rate:.0%}" if failure_rate is not None else "n/a"
    click.echo(
        f"{delivery['project']}: {len(deploys)} deploys in {delivery['days']} days;"
        f" change fail rate {rate}",
    )
    charts = [
        output_dir / "deployment_frequency.png",
        output_dir / "change_lead_time.png",
    ]
    vis_service.vis_df(
        str(charts[0]),
        weekly,
        x_label="weeks",
        y_label="deploys",
        peak_label="deploys",
    )
    vis_service.vis_duration_histogram(
        str(charts[1]),
        list(lead_times["lead_time_days"]),
        y_label="changes",
    )
    comparison = agent_comparison(deploys) if agent_authors else None
    return tiles, comparison, charts


def _forecast_scope(
    jql: str,
    scope: list[Issue],
    throughput: dict[str, int],
    now: datetime,
    focus: float,
) -> tuple[dict[str, Any], str]:
    """Forecast the issues a forecast query named, with a one-line summary."""
    result = monte_carlo_forecast(scope, throughput, now=now, focus=focus)
    open_count = sum(1 for issue in scope if issue.is_open)
    # the query on its own line: a chart title cannot fit a long one beside the rest
    summary = f"{jql}\n{open_count} of {len(scope)} issues open"
    if result:
        summary += (
            f"; 85% chance done by {result['p85_date']:%d %b %Y}"
            f" at {focus:.0%} of throughput"
        )
    elif open_count:
        summary += "; not enough throughput history to forecast"
    return result, summary


def _render_static_charts(  # noqa: PLR0913
    issues: list[Issue],
    testing_statuses: list[str],
    vis_service: VisService,
    output_dir: Path,
    throughput: dict[str, int],
    load: pd.DataFrame,
    handoffs: list[int],
) -> list[Path]:
    charts = []
    durations = (
        ("lead_time", lead_times(issues)),
        ("cycle_time", cycle_times(issues)),
    )
    for name, days in durations:
        path = output_dir / f"{name}.png"
        vis_service.vis_duration_histogram(str(path), days)
        charts.append(path)

    path = output_dir / "return_to_testing.png"
    vis_service.vis_array_like(
        str(path),
        returns_to_testing(issues, testing_statuses),
        x_label="returns to testing",
        y_label="number of issues",
    )
    charts.append(path)

    path = output_dir / "throughput.png"
    vis_service.vis_df(str(path), throughput, x_label="weeks", y_label="throughput")
    charts.append(path)

    path = output_dir / "cumulative_queue_time.png"
    vis_service.vis_cumulative_queue_time(
        str(path),
        median_queue_hours(issues),
    )
    charts.append(path)

    path = output_dir / "queue_time.png"
    vis_service.vis_queue_grid(str(path), queue_times(issues))
    charts.append(path)

    path = output_dir / "assignee_load.png"
    vis_service.vis_assignee_load(str(path), load, handoffs)
    charts.append(path)
    return charts


def _render_flow_pngs(  # noqa: PLR0913
    vis_service: VisService,
    output_dir: Path,
    scatter: pd.DataFrame,
    cfd: pd.DataFrame,
    aging: pd.DataFrame,
    forecast: dict[str, Any],
) -> None:
    """Write the flow charts as PNGs (the report embeds them interactively)."""
    logger = logging.getLogger(__name__)
    vis_service.vis_scatter_percentiles(
        str(output_dir / "cycle_time_scatter.png"),
        scatter,
    )
    vis_service.vis_cfd(str(output_dir / "cumulative_flow.png"), cfd)
    if aging.empty:
        logger.info("Skipping aging WIP chart: no started, unfinished issues")
    else:
        vis_service.vis_aging_wip(str(output_dir / "aging_wip.png"), aging)
    if forecast:
        vis_service.vis_forecast(str(output_dir / "forecast.png"), forecast)
    else:
        logger.info(
            "Skipping forecast chart: no open issues"
            " or fewer than 6 weeks of throughput history",
        )


if __name__ == "__main__":
    cli()
