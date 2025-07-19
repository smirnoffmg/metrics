import os

import click
from dependency_injector.wiring import Provide, inject

from metrics.containers import Container
from metrics.services import MetricsService, VisService


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


@click.command
@click.option("--jira-server", envvar="JIRA_SERVER")
@click.option("--jira-token", envvar="JIRA_TOKEN")
@click.option("--jira-jql",envvar="JIRA_JQL")
def cli(jira_server: str, jira_token: str, jira_jql: str) -> None:
    container = Container()
    container.config.from_dict(
        {
            "jira": {
                "server": jira_server,
                "token": jira_token,
                "jql": jira_jql,
            },
        },
    )

    container.init_resources()
    container.wire(modules=[__name__])

    calculate_metrics()


if __name__ == "__main__":
    cli()
