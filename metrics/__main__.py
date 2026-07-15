"""CLI entrypoint for Jira engineering metrics analysis."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click

if TYPE_CHECKING:
    import pandas as pd
from dependency_injector.wiring import Provide, inject

from metrics.consts import ACTIVE_STATUSES, DONE_STATUSES, TESTING_STATUSES
from metrics.containers import Container
from metrics.services import (  # noqa: TC001
    InteractiveVisService,
    MetricsService,
    ReportService,
    VisService,
)
from metrics.services.stats import build_headline_tiles, build_stuck_rows

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]


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


def parse_status_list(value: str | list[str] | None, default: list[str]) -> list[str]:
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
        "testing_statuses": os.environ.get("JIRA_TESTING_STATUSES"),
        "active_statuses": os.environ.get("JIRA_ACTIVE_STATUSES"),
        "anonymous": os.environ.get("JIRA_ANONYMOUS"),
    }


def validate_config(cfg: dict[str, Any]) -> list[str]:
    """Validate required Jira configuration fields."""
    errors = []
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
    f" (default: {','.join(DONE_STATUSES)}).",
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
    testing_statuses: str | None,
    active_statuses: str | None,
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
        "testing_statuses": None,
        "active_statuses": None,
        "anonymous": None,
    }
    if config:
        try:
            file_data = load_config_file(config)
            jira_section = file_data.get("jira", {})
            file_cfg = {
                "server": jira_section.get("server"),
                "token": jira_section.get("token"),
                "jql": jira_section.get("jql"),
                "email": jira_section.get("email"),
                "done_statuses": jira_section.get("done_statuses"),
                "testing_statuses": jira_section.get("testing_statuses"),
                "active_statuses": jira_section.get("active_statuses"),
                "anonymous": jira_section.get("anonymous"),
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
        "testing_statuses": testing_statuses,
        "active_statuses": active_statuses,
        "anonymous": anonymous or None,
    }
    cfg = merge_config(file_cfg, env_cfg, cli_cfg)
    is_anonymous = parse_bool(cfg.get("anonymous"))
    errors = validate_config(cfg)
    if errors:
        for err in errors:
            click.echo(f"Error: {err}", err=True)
        sys.exit(1)
    try:
        container = Container()
        container.config.from_dict(
            {
                "jira": {
                    "server": cfg["server"],
                    "token": cfg["token"],
                    "jql": cfg["jql"],
                    "email": cfg.get("email"),
                    "anonymous": is_anonymous,
                    # None = auto-detect from serverInfo (anonymous mode)
                    "cloud": None if is_anonymous else bool(cfg.get("email")),
                    "done_statuses": parse_status_list(
                        cfg.get("done_statuses"),
                        DONE_STATUSES,
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
            },
        )
        container.init_resources()
        container.wire(modules=[__name__])
        calculate_metrics()
    except Exception:
        logger.exception("Fatal error")
        sys.exit(1)


@inject
def calculate_metrics(
    metrics_service: MetricsService = Provide[Container.metrics_service],
    vis_service: VisService = Provide[Container.vis_service],
    interactive_service: InteractiveVisService = Provide[
        Container.interactive_vis_service
    ],
    report_service: ReportService = Provide[Container.report_service],
    server_url: str = Provide[Container.config.jira.server],
) -> None:
    """Calculate all metrics, save charts, and write the HTML report."""
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    scatter = metrics_service.get_cycle_time_scatter()
    cfd = metrics_service.get_cumulative_flow()
    aging = metrics_service.get_aging_wip()
    forecast = metrics_service.get_forecast()
    throughput = metrics_service.get_throughput()
    load, handoffs = metrics_service.get_assignee_load()

    report_images = _render_static_charts(
        metrics_service,
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
    if forecast:
        fragments.append(interactive_service.forecast_fragment(forecast))

    tiles = build_headline_tiles(
        scatter,
        aging,
        forecast,
        throughput,
        metrics_service.get_flow_efficiency(),
    )
    report_path = output_dir / "report.html"
    report_service.render(
        str(report_path),
        tiles=tiles,
        images=report_images,
        fragments=fragments,
        stuck_rows=build_stuck_rows(aging, server_url),
    )
    click.echo(f"Report: {report_path}")


def _render_static_charts(  # noqa: PLR0913
    metrics_service: MetricsService,
    vis_service: VisService,
    output_dir: Path,
    throughput: dict[str, int],
    load: pd.DataFrame,
    handoffs: list[int],
) -> list[Path]:
    charts = []
    histograms = (
        ("lead_time", metrics_service.get_lead_time(), "days"),
        ("cycle_time", metrics_service.get_cycle_time(), "days"),
        (
            "return_to_testing",
            metrics_service.get_return_to_testing(),
            "returns to testing",
        ),
    )
    for name, values, x_label in histograms:
        path = output_dir / f"{name}.png"
        vis_service.vis_array_like(
            str(path),
            values,
            x_label=x_label,
            y_label="number of issues",
        )
        charts.append(path)

    path = output_dir / "throughput.png"
    vis_service.vis_df(str(path), throughput, x_label="weeks", y_label="throughput")
    charts.append(path)

    path = output_dir / "cumulative_queue_time.png"
    vis_service.vis_cumulative_queue_time(
        str(path),
        metrics_service.get_cumulative_queue_time(),
    )
    charts.append(path)

    path = output_dir / "queue_time.png"
    vis_service.vis_queue_grid(str(path), metrics_service.get_queue_time())
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
        logger.info("Skipping aging WIP chart: no open issues")
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
