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

    def vis_array_like(
        self,
        filename: str,
        arr: list[float],
        x_label: str = "x_label",
        y_label: str = "y_label",
    ) -> None:
        sns.set_theme()

        sns.histplot(arr, bins="auto", kde=True)

        plt.tight_layout()

        plt.xlabel(x_label)
        plt.ylabel(y_label)

        plt.savefig(filename)
        plt.clf()
