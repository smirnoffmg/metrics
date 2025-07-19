import os

import pandas as pd

from metrics.services.vis import VisService


def test_visservice_vis_df_creates_file(temp_png_file):
    vis = VisService()
    data = {"a": 1, "b": 2, "c": 3}
    vis.vis_df(temp_png_file, data, x_label="x", y_label="y")
    assert os.path.exists(temp_png_file)


def test_visservice_vis_array_like_creates_file(temp_png_file):
    vis = VisService()
    arr = [1, 2, 2, 3, 3, 3]
    vis.vis_array_like(temp_png_file, arr, x_label="x", y_label="y")
    assert os.path.exists(temp_png_file)


def test_visservice_vis_cumulative_queue_time_creates_file(temp_png_file):
    vis = VisService()
    df = pd.DataFrame(
        {
            "status": ["A", "B"],
            "median_hours": [1.5, 2.5],
            "count": [10, 20],
        },
    )
    vis.vis_cumulative_queue_time(temp_png_file, df)
    assert os.path.exists(temp_png_file)
