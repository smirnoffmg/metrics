import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from .base import BaseService


class VisService(BaseService):
    def vis_df(
        self,
        filename: str,
        data: dict,
        x_label: str = "x_label",
        y_label: str = "y_label",
    ) -> None:
        df = pd.DataFrame(
            {
                "x": range(1, len(data) + 1),
                "y": list(data.values()),
            },
        )

        sns.set_theme()

        sns.regplot(
            data=df,
            x="x",
            y="y",
        )

        plt.tight_layout()

        plt.xlabel(x_label.replace("_", " "))
        plt.ylabel(y_label.replace("_", " "))

        plt.savefig(filename)
        plt.clf()

    def vis_cumulative_queue_time(
        self,
        filename: str,
        df: pd.DataFrame,
    ) -> None:
        _, ax = plt.subplots()

        # sort the DataFrame by 'median_hours' in descending order
        df = df.sort_values(by="median_hours", ascending=False)

        hbars = ax.barh(
            y=df["status"],
            width=df["median_hours"],
        )
        ax.set_yticks(
            df["status"],
            labels=df["status"] + " (" + df["count"].astype(str) + ")",
        )

        ax.invert_yaxis()
        # Set labels - add number to the end of each bar

        ax.bar_label(hbars, fmt="%.2f", labels=df["median_hours"].astype(str) + "h")
        ax.set_xlim(right=max(df["median_hours"]) * 1.3)

        plt.xlabel("Median hours")
        plt.ylabel("Status")

        plt.title("Median Hours in Each Status")
        plt.xticks(rotation=45)
        plt.grid(axis="x", linestyle="--", alpha=0.7)

        plt.tight_layout()

        plt.savefig(filename)
        plt.clf()

    def vis_array_like(
        self,
        filename: str,
        arr: list[int] | list[float],
        x_label: str = "x_label",
        y_label: str = "y_label",
    ) -> None:

        plt.grid(True)

        counts, _, bars = plt.hist(
            arr,
            bins=5,
            rwidth=0.9,
            align="mid",
            label="Count",
        )

        plt.bar_label(bars, labels=counts, label_type="edge")

        plt.xlabel(x_label)
        plt.ylabel(y_label)

        plt.tight_layout()

        plt.savefig(filename)
        plt.clf()
