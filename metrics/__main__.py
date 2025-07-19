import logging
import os
import sys

import click
from dependency_injector.wiring import Provide, inject

from metrics.containers import Container
from metrics.services import MetricsService, VisService

try:
    import yaml
except ImportError:
    yaml = None
import json


def load_config_file(config_path):
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")
    ext = os.path.splitext(config_path)[1].lower()
    with open(config_path) as f:
        if ext in (".yaml", ".yml"):
            if not yaml:
                raise ImportError(
                    "PyYAML is required for YAML config files. Install with 'pip install pyyaml'.",
                )
            return yaml.safe_load(f)
        if ext == ".json":
            return json.load(f)
        raise ValueError(f"Unsupported config file format: {ext}")


def merge_config(file_cfg, env_cfg, cli_cfg):
    # Priority: CLI > ENV > FILE
    result = {}
    for key in set(file_cfg) | set(env_cfg) | set(cli_cfg):
        result[key] = cli_cfg.get(key) or env_cfg.get(key) or file_cfg.get(key)
    return result


def get_env_config():
    return {
        "server": os.environ.get("JIRA_SERVER"),
        "token": os.environ.get("JIRA_TOKEN"),
        "jql": os.environ.get("JIRA_JQL"),
    }


def validate_config(cfg):
    errors = []
    if not cfg.get("server"):
        errors.append(
            "Jira server URL is missing. Set --jira-server, JIRA_SERVER, or config file.",
        )
    elif not (
        cfg["server"].startswith("http://") or cfg["server"].startswith("https://")
    ):
        errors.append("Jira server URL must start with http:// or https://.")
    if not cfg.get("token"):
        errors.append(
            "Jira token is missing. Set --jira-token, JIRA_TOKEN, or config file.",
        )
    if not cfg.get("jql"):
        errors.append("Jira JQL is missing. Set --jira-jql, JIRA_JQL, or config file.")
    return errors


@click.command(
    help="""
    Analyze and visualize Jira issue metrics.

    Examples:
      python -m metrics --jira-server https://your-jira --jira-token <token> --jira-jql 'project=MYPROJ'
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
def cli(config, jira_server, jira_token, jira_jql):
    logger = logging.getLogger(__name__)
    # Load config file if provided
    file_cfg = {"server": None, "token": None, "jql": None}
    if config:
        try:
            file_data = load_config_file(config)
            file_cfg = {
                "server": file_data.get("jira", {}).get("server"),
                "token": file_data.get("jira", {}).get("token"),
                "jql": file_data.get("jira", {}).get("jql"),
            }
        except Exception as e:
            click.echo(f"Error loading config file: {e}", err=True)
            sys.exit(1)
    env_cfg = get_env_config()
    cli_cfg = {"server": jira_server, "token": jira_token, "jql": jira_jql}
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
    except Exception as e:
        logger.exception("Fatal error")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@inject
def calculate_metrics(
    metrics_service: MetricsService = Provide[Container.metrics_service],
    vis_service: VisService = Provide[Container.vis_service],
) -> None:
    # getting the metrics
    cycle_time = metrics_service.get_cycle_time()
    lead_time = metrics_service.get_lead_time()
    queue_time = metrics_service.get_queue_time()
    throughput = metrics_service.get_throughput()
    cumulative_queue_time = metrics_service.get_cumulative_queue_time()
    return_to_testing = metrics_service.get_return_to_testing()
    # visualizing the metrics
    output_dir = "output"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
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
