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

    # visualizing the metrics

    vis_service.vis_array_like(
        "lead_time.png",
        lead_time,
        x_label="days",
        y_label="number of issues",
    )

    vis_service.vis_array_like(
        "cycle_time.png",
        cycle_time,
        x_label="days",
        y_label="number of issues",
    )

    vis_service.vis_df(
        "througput.png",
        throughput,
        x_label="weeks",
        y_label="throughput",
    )

    for status_name, values in queue_time.items():
        vis_service.vis_array_like(
            f"queue_time_{status_name}.png",
            values,
            x_label="days",
            y_label="number of issues",
        )


@click.command
@click.option("--jira-server")
@click.option("--jira-token")
@click.option("--jira-jql")
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
