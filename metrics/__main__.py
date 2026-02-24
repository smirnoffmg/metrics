"""CLI entrypoint for Jira engineering metrics analysis."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import click
from dependency_injector.wiring import Provide, inject

from metrics.containers import Container
from metrics.services import MetricsService, VisService  # noqa: TC001

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


def get_env_config() -> dict[str, str | None]:
    """Read Jira configuration from environment variables."""
    return {
        "server": os.environ.get("JIRA_SERVER"),
        "token": os.environ.get("JIRA_TOKEN"),
        "jql": os.environ.get("JIRA_JQL"),
    }


def validate_config(cfg: dict[str, str | None]) -> list[str]:
    """Validate required Jira configuration fields."""
    errors = []
    if not cfg.get("server"):
        errors.append(
            "Jira server URL is missing."
            " Set --jira-server, JIRA_SERVER, or config file.",
        )
    elif not (
        cfg["server"].startswith("http://") or cfg["server"].startswith("https://")
    ):
        errors.append(
            "Jira server URL must start with http:// or https://.",
        )
    if not cfg.get("token"):
        errors.append(
            "Jira token is missing. Set --jira-token, JIRA_TOKEN, or config file.",
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
def cli(
    config: str | None,
    jira_server: str | None,
    jira_token: str | None,
    jira_jql: str | None,
) -> None:
    """Analyze and visualize Jira issue metrics."""
    logger = logging.getLogger(__name__)
    file_cfg: dict[str, str | None] = {
        "server": None,
        "token": None,
        "jql": None,
    }
    if config:
        try:
            file_data = load_config_file(config)
            jira_section = file_data.get("jira", {})
            file_cfg = {
                "server": jira_section.get("server"),
                "token": jira_section.get("token"),
                "jql": jira_section.get("jql"),
            }
        except (FileNotFoundError, ImportError, ValueError) as e:
            click.echo(f"Error loading config file: {e}", err=True)
            sys.exit(1)
    env_cfg = get_env_config()
    cli_cfg: dict[str, str | None] = {
        "server": jira_server,
        "token": jira_token,
        "jql": jira_jql,
    }
    cfg = merge_config(file_cfg, env_cfg, cli_cfg)
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
) -> None:
    """Calculate all metrics and save visualizations to the output directory."""
    cycle_time = metrics_service.get_cycle_time()
    lead_time = metrics_service.get_lead_time()
    queue_time = metrics_service.get_queue_time()
    throughput = metrics_service.get_throughput()
    cumulative_queue_time = metrics_service.get_cumulative_queue_time()
    return_to_testing = metrics_service.get_return_to_testing()

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    vis_service.vis_array_like(
        f"{output_dir}/lead_time.png",
        lead_time,
        x_label="days",
        y_label="number of issues",
    )
    vis_service.vis_array_like(
        f"{output_dir}/return_to_testing.png",
        return_to_testing,
        x_label="x",
        y_label="y",
    )
    vis_service.vis_array_like(
        f"{output_dir}/cycle_time.png",
        cycle_time,
        x_label="days",
        y_label="number of issues",
    )
    vis_service.vis_df(
        f"{output_dir}/throughput.png",
        throughput,
        x_label="weeks",
        y_label="throughput",
    )
    vis_service.vis_cumulative_queue_time(
        f"{output_dir}/cumulative_queue_time.png",
        cumulative_queue_time,
    )
    for status_name, values in queue_time.items():
        vis_service.vis_array_like(
            f"{output_dir}/queue_time_{status_name}.png",
            values,
            x_label="days",
            y_label="number of issues",
        )


if __name__ == "__main__":
    cli()
