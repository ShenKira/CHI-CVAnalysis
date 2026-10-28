# -*- coding: utf-8 -*-
import matplotlib
import numpy as np

matplotlib.use("Agg")

from matplotlib.figure import Figure

from cvanalysis.plotting.export import render_plot, render_to_new_figure
from cvanalysis.plotting.presets import BUILTIN_PRESETS
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.analysis.eis import analyze_eis
from cvanalysis.analysis.fitting import fit_eis_model
from cvanalysis.domain.models import ElectrodeParams


def _cv_specs(run_ids):
    return [
        PlotSpec("cv_overlay", run_ids, target_voltage=0.5),
        PlotSpec("cv_cap_scan", run_ids),
        PlotSpec("cv_current_scan", run_ids, target_voltage=0.5),
        PlotSpec("cv_bvalue", run_ids, target_voltage=0.5),
        PlotSpec("cv_contribution", run_ids, selected_scan_rate=0.02),
        PlotSpec("cv_contribution_vs_rate", run_ids),
        PlotSpec("cv_trasatti", run_ids),
    ]


def test_cv_renderers(synthetic_cv_runs):
    dataset = type("D", (), {"cv_runs": synthetic_cv_runs, "eis_runs": []})()
    run_ids = [run.run_id for run in synthetic_cv_runs]
    for style_name in ("daily", "ieee-single"):
        style = BUILTIN_PRESETS[style_name]
        for spec in _cv_specs(run_ids):
            figure = Figure(figsize=style.figure_size, dpi=100)
            warnings = render_plot(figure, dataset, spec, style)
            assert figure.axes, spec.kind
            assert isinstance(warnings, list)


def test_scan_rate_labels_use_consistent_units(synthetic_cv_runs):
    dataset = type("D", (), {"cv_runs": synthetic_cv_runs, "eis_runs": []})()
    run_ids = [run.run_id for run in synthetic_cv_runs]
    for spec in _cv_specs(run_ids):
        if spec.kind not in {"cv_cap_scan", "cv_current_scan", "cv_bvalue", "cv_trasatti", "cv_contribution_vs_rate"}:
            continue
        figure = Figure()
        render_plot(figure, dataset, spec, BUILTIN_PRESETS["daily"])
        assert "V/s" in figure.axes[0].get_xlabel(), spec.kind
        assert "V s" not in figure.axes[0].get_xlabel()


def test_b_value_renderer_uses_selected_current_mode(cv_file_factory):
    from cvanalysis.io.registry import load_files
    from cvanalysis.services.dataset_service import AnalysisSettings, refresh_analysis

    paths = [
        cv_file_factory(
            f"b_{rate:g}.txt",
            scan_rate=rate,
            capacitance=1e-4,
            offset_current=2e-4,
        )
        for rate in (0.01, 0.02, 0.05)
    ]
    dataset, issues = load_files(paths)
    assert not issues
    refresh_analysis(dataset, AnalysisSettings())
    run_ids = [run.run_id for run in dataset.cv_runs]
    style = BUILTIN_PRESETS["daily"]

    def measured(mode=None):
        options = {} if mode is None else {"b_current_mode": mode}
        spec = PlotSpec(
            "cv_bvalue",
            run_ids,
            target_voltage=0.5,
            analysis_options=options,
        )
        figure = Figure(figsize=style.figure_size, dpi=100)
        render_plot(figure, dataset, spec, style)
        return np.asarray(figure.axes[0].lines[0].get_ydata(), dtype=float)

    legacy = measured()
    explicit_legacy = measured("absolute")
    forward = measured("up")
    reverse = measured("down")
    assert np.allclose(legacy, explicit_legacy)
    assert not np.allclose(legacy, forward)
    assert not np.allclose(forward, reverse)


def test_eis_renderers_and_export(synthetic_eis_run):
    dataset = type("D", (), {"cv_runs": [], "eis_runs": [synthetic_eis_run]})()
    fit = fit_eis_model(
        synthetic_eis_run.freq,
        synthetic_eis_run.z_real,
        synthetic_eis_run.z_imag,
        model="rct_c",
    )
    metrics = analyze_eis(synthetic_eis_run)
    specs = [
        PlotSpec("eis_nyquist", [synthetic_eis_run.run_id]),
        PlotSpec("eis_bode", [synthetic_eis_run.run_id]),
        PlotSpec("eis_fit", [synthetic_eis_run.run_id], fit_enabled=True),
    ]
    style = BUILTIN_PRESETS["ieee-double"]
    for spec in specs:
        figure = render_to_new_figure(
            dataset,
            spec,
            style,
            fits={synthetic_eis_run.run_id: fit},
            metrics={synthetic_eis_run.run_id: metrics},
        )
        assert figure.axes
    output = render_to_new_figure(
        dataset,
        PlotSpec("eis_nyquist", [synthetic_eis_run.run_id]),
        style,
    )
    assert output.get_size_inches()[0] == style.figure_size[0]


def test_eis_area_normalization_updates_annotation_units(synthetic_eis_run):
    synthetic_eis_run.params = ElectrodeParams(area_cm2=2.0)
    metrics = analyze_eis(synthetic_eis_run)
    dataset = type("D", (), {"cv_runs": [], "eis_runs": [synthetic_eis_run]})()
    spec = PlotSpec(
        "eis_nyquist",
        [synthetic_eis_run.run_id],
        normalization="area",
    )
    figure = Figure(figsize=(6, 4), dpi=100)
    render_plot(
        figure,
        dataset,
        spec,
        BUILTIN_PRESETS["daily"],
        metrics={synthetic_eis_run.run_id: metrics},
    )
    text = "\n".join(item.get_text() for item in figure.axes[0].texts)
    assert "Ω·cm²" in text
    assert "Rs = 20" in text
    assert "10 Ω" not in text


def test_eis_mass_normalization_warns_and_uses_raw_impedance(synthetic_eis_run):
    dataset = type("D", (), {"cv_runs": [], "eis_runs": [synthetic_eis_run]})()
    spec = PlotSpec(
        "eis_nyquist",
        [synthetic_eis_run.run_id],
        normalization="mass",
    )
    figure = Figure(figsize=(6, 4), dpi=100)
    warnings = render_plot(
        figure,
        dataset,
        spec,
        BUILTIN_PRESETS["daily"],
        metrics={synthetic_eis_run.run_id: analyze_eis(synthetic_eis_run)},
    )
    assert any("质量归一化" in warning for warning in warnings)
    assert "Ω·cm²" not in figure.axes[0].get_xlabel()


def test_svg_render_returns_vector_bytes(synthetic_cv_runs):
    from cvanalysis.plotting.export import render_svg_bytes

    dataset = type("D", (), {"cv_runs": synthetic_cv_runs, "eis_runs": []})()
    spec = PlotSpec("cv_overlay", [run.run_id for run in synthetic_cv_runs])
    svg = render_svg_bytes(dataset, spec, BUILTIN_PRESETS["daily"])
    assert svg.startswith(b"<?xml")
    assert b"<svg" in svg
    assert b"<path" in svg


def test_xkcd_color_generation_is_deterministic():
    from cvanalysis.plotting.xkcd import generate_xkcd_color_sequence

    first = generate_xkcd_color_sequence(42, 20.0, 10)
    second = generate_xkcd_color_sequence(42, 20.0, 10)
    assert first == second
    assert len(first) == 10
    assert len(set(first)) == 10


def test_contribution_vs_rate_bar_axes(synthetic_cv_runs):
    from cvanalysis.plotting.export import render_plot
    from cvanalysis.plotting.presets import BUILTIN_PRESETS
    from cvanalysis.plotting.spec import PlotSpec

    dataset = type("D", (), {"cv_runs": synthetic_cv_runs, "eis_runs": []})()
    spec = PlotSpec("cv_contribution_vs_rate", [run.run_id for run in synthetic_cv_runs])
    figure = Figure(figsize=(8, 6))
    render_plot(figure, dataset, spec, BUILTIN_PRESETS["daily"])
    ax = figure.axes[0]
    assert ax.get_ylim() == (0.0, 100.0)
    assert ax.get_xlabel().startswith("Scan rate")
    assert ax.get_ylabel() == "Contribution (%)"
    assert len(ax.patches) == 6


def test_contribution_current_plot_axes(synthetic_cv_runs):
    from cvanalysis.plotting.export import render_plot
    from cvanalysis.plotting.presets import BUILTIN_PRESETS
    from cvanalysis.plotting.spec import PlotSpec

    dataset = type("D", (), {"cv_runs": synthetic_cv_runs, "eis_runs": []})()
    spec = PlotSpec(
        "cv_contribution",
        [run.run_id for run in synthetic_cv_runs],
        selected_scan_rate=0.02,
    )
    figure = Figure(figsize=(8, 6))
    render_plot(figure, dataset, spec, BUILTIN_PRESETS["daily"])
    ax = figure.axes[0]
    assert ax.get_xlabel() == "Potential (V)"
    assert ax.get_ylabel().startswith("Current")
    assert len(ax.lines) >= 3


def test_multi_run_overlay_legend_is_per_run(synthetic_cv_runs):
    from cvanalysis.plotting.export import render_plot
    from cvanalysis.plotting.presets import BUILTIN_PRESETS
    from cvanalysis.plotting.spec import PlotSpec

    dataset = type("D", (), {"cv_runs": synthetic_cv_runs, "eis_runs": []})()
    spec = PlotSpec("cv_overlay", [run.run_id for run in synthetic_cv_runs])
    figure = Figure(figsize=(8, 6))
    render_plot(figure, dataset, spec, BUILTIN_PRESETS["daily"])
    legend = figure.axes[0].get_legend()
    assert legend is not None
    assert len(legend.get_texts()) == len(synthetic_cv_runs)


def test_cv_legend_template_expands_per_cycle(synthetic_cv_runs):
    from cvanalysis.plotting.export import render_plot
    from cvanalysis.plotting.presets import BUILTIN_PRESETS
    from cvanalysis.plotting.spec import PlotSpec

    run = synthetic_cv_runs[0]
    run.legend_template = "{CV_Voltage}-{Cycle_Number}"
    spec = PlotSpec("cv_overlay", [run.run_id])
    figure = Figure(figsize=(8, 6))
    warnings = render_plot(figure, type("D", (), {"cv_runs": synthetic_cv_runs, "eis_runs": []})(), spec, BUILTIN_PRESETS["daily"])
    texts = [text.get_text() for text in figure.axes[0].get_legend().get_texts()]
    voltage = f"{run.metadata.high_e:g}V"
    assert texts == [f"{voltage}-{cycle.index}" for cycle in run.cycles]
    assert warnings == []


def test_renumbered_cycle_template_restarts_for_each_run(synthetic_cv_runs):
    from cvanalysis.plotting.export import render_plot
    from cvanalysis.plotting.presets import BUILTIN_PRESETS
    from cvanalysis.plotting.spec import PlotSpec

    runs = synthetic_cv_runs[:2]
    spec = PlotSpec(
        "cv_overlay",
        [run.run_id for run in runs],
        renumber_cycles=True,
        legend_templates={run.run_id: "{Cycle_Number}" for run in runs},
    )
    figure = Figure(figsize=(8, 6))
    render_plot(figure, type("D", (), {"cv_runs": synthetic_cv_runs, "eis_runs": []})(), spec, BUILTIN_PRESETS["daily"])
    texts = [text.get_text() for text in figure.axes[0].get_legend().get_texts()]
    expected = [
        str(position)
        for run in runs
        for position, _ in enumerate(run.cycles, 1)
    ]
    assert texts == expected


def test_plot_spec_legend_override_beats_data_template(synthetic_cv_runs):
    from cvanalysis.plotting.export import render_plot
    from cvanalysis.plotting.presets import BUILTIN_PRESETS
    from cvanalysis.plotting.spec import PlotSpec

    run = synthetic_cv_runs[0]
    run.legend_template = "{File_Name}"
    spec = PlotSpec("cv_overlay", [run.run_id], legend_templates={run.run_id: "custom-alias"})
    figure = Figure(figsize=(8, 6))
    render_plot(figure, type("D", (), {"cv_runs": synthetic_cv_runs, "eis_runs": []})(), spec, BUILTIN_PRESETS["daily"])
    assert [text.get_text() for text in figure.axes[0].get_legend().get_texts()] == ["custom-alias"]


def test_unknown_legend_template_field_warns(synthetic_cv_runs):
    from cvanalysis.plotting.export import render_plot
    from cvanalysis.plotting.presets import BUILTIN_PRESETS
    from cvanalysis.plotting.spec import PlotSpec

    run = synthetic_cv_runs[0]
    spec = PlotSpec("cv_overlay", [run.run_id], legend_templates={run.run_id: "{Not_A_Field}"})
    figure = Figure(figsize=(8, 6))
    warnings = render_plot(figure, type("D", (), {"cv_runs": synthetic_cv_runs, "eis_runs": []})(), spec, BUILTIN_PRESETS["daily"])
    assert any("Not_A_Field" in warning for warning in warnings)
    assert [text.get_text() for text in figure.axes[0].get_legend().get_texts()] == ["{Not_A_Field}"]


def test_eis_legend_template(synthetic_eis_run):
    from cvanalysis.plotting.export import render_plot
    from cvanalysis.plotting.presets import BUILTIN_PRESETS
    from cvanalysis.plotting.spec import PlotSpec

    synthetic_eis_run.legend_template = "{Low_Freq}"
    spec = PlotSpec("eis_nyquist", [synthetic_eis_run.run_id])
    figure = Figure(figsize=(8, 6))
    render_plot(
        figure,
        type("D", (), {"cv_runs": [], "eis_runs": [synthetic_eis_run]})(),
        spec,
        BUILTIN_PRESETS["daily"],
    )
    assert [text.get_text() for text in figure.axes[0].get_legend().get_texts()] == [f"{synthetic_eis_run.metadata.low_freq:g}Hz"]


def test_legend_template_token_matching_is_case_insensitive():
    from cvanalysis.plotting.legend import template_uses_cycle

    assert template_uses_cycle("{CyCle_Number}")
    assert template_uses_cycle("{cycle number}")
    assert not template_uses_cycle("{CV_Voltage}")


def test_paper_presets_use_arial_and_font_family_is_not_hardcoded_serif():
    from cvanalysis.plotting.presets import BUILTIN_PRESETS

    for name in ("ieee-single", "ieee-double", "thesis"):
        style = BUILTIN_PRESETS[name]
        assert style.font_family[0] == "Arial"
        assert style.rc()["font.family"] == list(style.font_family)


def test_axes_aspect_and_quick_style_overrides():
    from cvanalysis.plotting.export import render_plot
    from cvanalysis.plotting.presets import BUILTIN_PRESETS
    from cvanalysis.plotting.spec import PlotSpec
    from cvanalysis.plotting.style import PlotStyle

    style = BUILTIN_PRESETS["daily"].with_overrides(
        {"axes_aspect": "4:3", "xlabel_size": 17.0, "ylabel_size": 13.0, "xlabel_bold": True, "ylabel_bold": False}
    )
    assert style.effective_xlabel_size() == 17.0
    assert style.effective_ylabel_size() == 13.0
    assert style.effective_xlabel_bold() is True
    assert style.effective_ylabel_bold() is False
    dataset = type("D", (), {"cv_runs": [], "eis_runs": []})()
    # Directly exercise the figure-level aspect application without needing a plot.
    from matplotlib.figure import Figure
    from cvanalysis.plotting.style import finalize_figure

    fig = Figure(figsize=(8, 6))
    ax = fig.add_subplot(111)
    finalize_figure(fig, style)
    assert ax.get_box_aspect() == 0.75


def test_plot_style_from_dict_coerces_invalid_persisted_values():
    from cvanalysis.plotting.style import PlotStyle

    style = PlotStyle.from_dict(
        {
            "title_size": "large",
            "font_size": None,
            "figure_size": ["x", 6],
            "font_family": [None, "Arial"],
            "color_cycle": ["#zzzzzz", "#ffffff"],
            "legend_columns": 0,
            "tick_direction": "sideways",
            "grid_alpha": 2.0,
            "xlabel_bold": "false",
        }
    )
    assert style.title_size == 20.0
    assert style.font_size == 12.0
    assert style.figure_size == (3.2 * 4.0 / 3.0, 3.2)
    assert style.font_family == ("Arial",)
    assert style.color_cycle == ("#ffffff",)
    assert style.legend_columns == 2
    assert style.tick_direction == "in"
    assert style.grid_alpha == 0.3
    assert style.xlabel_bold is False
