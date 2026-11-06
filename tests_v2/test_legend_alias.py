# -*- coding: utf-8 -*-
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import QApplication

from cvanalysis.domain.models import Dataset
from cvanalysis.io.registry import load_files
from cvanalysis.plotting.export import render_plot, render_to_new_figure
from cvanalysis.plotting.legend import dataset_file_numbers, resolve_legend_labels
from cvanalysis.plotting.presets import BUILTIN_PRESETS
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.services.dataset_service import AnalysisSettings, refresh_analysis
from cvanalysis.services.project_service import load_project, save_project
from cvanalysis.ui.models.dataset_model import ALIAS_COLUMN, COLUMNS, DatasetTreeModel


LONG_NAMES = [
    "LFPN-DC55W-0dot8Pa44h_CV_1dot5V_0dot01Vps",
    "LFPN-DC55W-0dot8Pa44h_CV_1dot5V_0dot05Vps",
    "LFPN-DC55W-0dot8Pa44h_CV_2dot5V_0dot01Vps",
    "LFPN-DC55W-0dot8Pa44h_CV_2dot5V_0dot05Vps",
]


def _long_dataset(cv_file_factory) -> Dataset:
    paths = []
    for index, name in enumerate(LONG_NAMES):
        paths.append(
            cv_file_factory(
                name + ".txt",
                scan_rate=(0.01, 0.05)[index % 2],
                capacitance=1e-4,
                high=1.5 if "1dot5" in name else 2.5,
            )
        )
    dataset, issues = load_files(paths)
    assert not issues
    refresh_analysis(dataset, AnalysisSettings())
    return dataset


def _model(dataset: Dataset, text_values=None) -> DatasetTreeModel:
    app = QApplication.instance() or QApplication([])
    model = DatasetTreeModel()
    model.set_dataset(dataset, text_values=text_values)
    app.processEvents()
    return model


def test_long_similar_names_compact_all_family_members(cv_file_factory):
    dataset = _long_dataset(cv_file_factory)
    labels = resolve_legend_labels(
        dataset.all_runs(),
        file_numbers=dataset_file_numbers(dataset),
    )
    decisions = [labels[run.run_id] for run in dataset.cv_runs]
    assert all(decision.auto and decision.compact for decision in decisions)
    texts = [decision.label for decision in decisions]
    assert len(set(texts)) == len(texts)
    assert texts[0].startswith("#1 ")
    assert all("1.5V" in text or "2.5V" in text for text in texts)


def test_dataset_tree_alias_column_shows_auto_only_when_triggered(cv_file_factory):
    dataset = _long_dataset(cv_file_factory)
    model = _model(dataset)
    assert COLUMNS[:2] == ["名称", "图例/别名"]
    assert "平均电容 / Rs / 放电容量" not in COLUMNS
    assert "单位面积 / Rct / 比容量" not in COLUMNS
    assert "质量比 / Cdl / 保持段" not in COLUMNS

    group = model.index(0, 0)
    for row in range(model.rowCount(group)):
        index = model.index(row, ALIAS_COLUMN, group)
        assert model.data(index)


def test_short_unique_names_leave_alias_column_empty(synthetic_cv_runs):
    model = _model(Dataset(cv_runs=list(synthetic_cv_runs)))
    group = model.index(0, 0)
    for row in range(model.rowCount(group)):
        index = model.index(row, ALIAS_COLUMN, group)
        assert model.data(index) == ""


def test_manual_alias_overrides_auto_and_can_be_used_in_template(
    cv_file_factory,
):
    dataset = _long_dataset(cv_file_factory)
    run = dataset.cv_runs[0]
    run.legend_alias = "Sample A"
    labels = resolve_legend_labels(
        dataset.all_runs(),
        file_numbers=dataset_file_numbers(dataset),
    )
    assert labels[run.run_id].manual
    assert labels[run.run_id].label == "Sample A"

    spec = PlotSpec("cv_overlay", [item.run_id for item in dataset.cv_runs])
    figure = render_to_new_figure(dataset, spec, BUILTIN_PRESETS["daily"])
    assert figure.axes[0].get_legend().get_texts()[0].get_text() == "Sample A"

    spec.legend_templates = {run.run_id: "{Alias}-{CV_Voltage}"}
    figure = render_to_new_figure(dataset, spec, BUILTIN_PRESETS["daily"])
    assert figure.axes[0].get_legend().get_texts()[0].get_text() == "Sample A-1.5V"


def test_alias_column_updates_after_manual_alias_and_clear(cv_file_factory):
    dataset = _long_dataset(cv_file_factory)
    model = _model(dataset)
    run = dataset.cv_runs[0]
    group = model.index(0, 0)
    index = model.index(0, ALIAS_COLUMN, group)
    assert model.data(index).startswith("#1 ")

    run.legend_alias = "Custom label"
    model.refresh_auto_labels()
    assert model.data(index) == "Custom label"

    run.legend_alias = ""
    model.refresh_auto_labels()
    assert model.data(index).startswith("#1 ")


def test_single_run_cv_alias_is_used_for_each_cycle(synthetic_cv_runs):
    run = synthetic_cv_runs[0]
    run.legend_alias = "Sample A"
    dataset = Dataset(cv_runs=[run])
    figure = Figure(figsize=BUILTIN_PRESETS["daily"].figure_size, dpi=100)
    FigureCanvasAgg(figure)
    render_plot(
        figure,
        dataset,
        PlotSpec("cv_overlay", [run.run_id]),
        BUILTIN_PRESETS["daily"],
    )
    labels = [text.get_text() for text in figure.axes[0].get_legend().get_texts()]
    assert labels
    assert all(label.startswith("Sample A C") for label in labels)


def test_cp_efficiency_legend_survives_standard_and_paper_fit(synthetic_cp_run):
    dataset = Dataset(cp_runs=[synthetic_cp_run])
    spec = PlotSpec("cp_capacity", [synthetic_cp_run.run_id])
    figure = Figure(figsize=BUILTIN_PRESETS["daily"].figure_size, dpi=100)
    FigureCanvasAgg(figure)
    render_plot(figure, dataset, spec, BUILTIN_PRESETS["daily"])
    labels = [text.get_text() for text in figure.axes[0].get_legend().get_texts()]
    assert any("CE" in label for label in labels)

    spec.paper_layout = {
        "enabled": True,
        "fraction": 0.5,
        "text_width_mm": 160,
        "body_pt": 10,
        "legend_placement": "inside",
        "legend_columns": "auto",
    }
    figure = render_to_new_figure(dataset, spec, BUILTIN_PRESETS["daily"])
    FigureCanvasAgg(figure)
    labels = [text.get_text() for text in figure.axes[0].get_legend().get_texts()]
    assert any("CE" in label for label in labels)


def test_cp_alias_with_template_keeps_current_suffix(synthetic_cp_run):
    run = synthetic_cp_run
    run.legend_alias = "Sample A"
    run.legend_template = "{Sample_Name}"
    dataset = Dataset(cp_runs=[run])
    figure = Figure(figsize=BUILTIN_PRESETS["daily"].figure_size, dpi=100)
    FigureCanvasAgg(figure)
    render_plot(
        figure,
        dataset,
        PlotSpec("cp_gcd", [run.run_id], annotations=False),
        BUILTIN_PRESETS["daily"],
    )
    labels = [text.get_text() for text in figure.axes[0].get_legend().get_texts()]
    assert labels
    assert any("(" in label for label in labels)


def test_auto_label_avoids_manual_alias_regardless_of_order(synthetic_cv_runs):
    first, second = synthetic_cv_runs[:2]
    first.name = "same"
    second.name = "same"
    first.legend_alias = "same"
    second.legend_alias = ""
    forward = resolve_legend_labels([first, second], file_numbers={first.run_id: 1, second.run_id: 2})
    reverse = resolve_legend_labels([second, first], file_numbers={first.run_id: 1, second.run_id: 2})
    assert forward[first.run_id].label == "same"
    assert forward[second.run_id].label != "same"
    assert reverse[first.run_id].label == "same"
    assert reverse[second.run_id].label != "same"


def test_project_roundtrip_keeps_legend_alias(tmp_path, synthetic_cv_runs):
    dataset = Dataset(cv_runs=list(synthetic_cv_runs))
    dataset.cv_runs[0].legend_alias = "sample alias"
    path = tmp_path / "alias.cvproj"
    save_project(path, dataset)
    restored = load_project(path)
    assert restored.dataset.cv_runs[0].legend_alias == "sample alias"
