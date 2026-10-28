from pathlib import Path

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtWidgets import QApplication, QAbstractItemView

from cvanalysis.domain.models import Dataset
from cvanalysis.plotting.export import render_to_new_figure
from cvanalysis.plotting.legend import dataset_file_numbers
from cvanalysis.plotting.presets import BUILTIN_PRESETS
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.services.project_service import load_project, save_project
from cvanalysis.ui.models.dataset_model import DatasetTreeModel


def test_file_and_original_cycle_numbers_use_full_dataset(synthetic_cv_runs):
    runs = synthetic_cv_runs
    dataset = Dataset(cv_runs=runs)
    selected = runs[1]
    spec = PlotSpec(
        "cv_overlay", [selected.run_id], cycle_selection={selected.run_id: [2]},
        renumber_cycles=True,
        legend_templates={selected.run_id: "F{file_n}/C{cycle_n}/display{Cycle_Number}"},
    )
    figure = render_to_new_figure(dataset, spec, BUILTIN_PRESETS["daily"])
    assert figure.axes[0].get_legend().get_texts()[0].get_text() == "F2/C2/display1"
    dataset.cv_runs[:] = [runs[1], runs[0], runs[2]]
    figure = render_to_new_figure(dataset, spec, BUILTIN_PRESETS["daily"])
    assert figure.axes[0].get_legend().get_texts()[0].get_text() == "F1/C2/display1"


def test_source_files_share_numbers_and_eis_uses_dataset_order(synthetic_cv_runs, synthetic_eis_run):
    from copy import deepcopy

    first, second = synthetic_cv_runs[:2]
    extra_run = deepcopy(first)
    extra_run.run_id = "another-run-in-first-file"
    extra_run.run_index = 1
    # Identical names in different directories are distinct source files.
    second.source = Path("other") / first.source.name
    dataset = Dataset(cv_runs=[first, extra_run, second], eis_runs=[synthetic_eis_run])
    assert dataset_file_numbers(dataset) == {
        first.run_id: 1, extra_run.run_id: 1, second.run_id: 2, synthetic_eis_run.run_id: 3,
    }
    synthetic_eis_run.legend_template = "E{file_n}"
    spec = PlotSpec("eis_bode", [synthetic_eis_run.run_id])
    figure = render_to_new_figure(dataset, spec, BUILTIN_PRESETS["daily"])
    assert figure.axes[0].get_legend().get_texts()[0].get_text() == "E3"


def test_model_drag_preserves_cycles_checks_and_indexes(tmp_path, synthetic_cv_runs, synthetic_eis_run):
    from copy import deepcopy

    app = QApplication.instance() or QApplication([])
    second_eis = deepcopy(synthetic_eis_run)
    second_eis.run_id = "second-eis"
    second_eis.name = "second-eis"
    dataset = Dataset(cv_runs=list(synthetic_cv_runs), eis_runs=[synthetic_eis_run, second_eis])
    a, b, c = dataset.cv_runs
    model = DatasetTreeModel()
    model.set_dataset(dataset, {b.run_id: False}, {a.run_id: [2]})
    group = model.index(0, 0)
    eis_group = model.index(1, 0)
    tracked = QPersistentModelIndex(model.index_for_run(a.run_id))
    cycle = QPersistentModelIndex(model.index(1, 0, model.index_for_run(a.run_id)))
    mime = model.mimeData([model.index_for_run(a.run_id), model.index_for_run(c.run_id)])
    assert not model.canDropMimeData(mime, Qt.MoveAction, -1, 0, eis_group)
    assert not model.canDropMimeData(mime, Qt.MoveAction, -1, 0, QModelIndex())
    assert not model.mimeData([QModelIndex(cycle)]).hasFormat(model.RUN_MIME_TYPE)
    assert model.dropMimeData(mime, Qt.MoveAction, -1, 0, group)
    assert [run.run_id for run in dataset.cv_runs] == [b.run_id, a.run_id, c.run_id]
    assert tracked.row() == 1 and tracked.data() == a.display_name
    assert cycle.parent().row() == 1 and cycle.data() == "Cycle 2"
    assert model.visible_runs[b.run_id] is False
    assert model.cycle_selection[a.run_id] == [2]
    # Drops from another model must not rearrange the target dataset.
    other = DatasetTreeModel()
    other.set_dataset(dataset)
    assert not other.canDropMimeData(mime, Qt.MoveAction, 0, 0, other.index(0, 0))
    eis_mime = model.mimeData([model.index_for_run(second_eis.run_id)])
    assert model.dropMimeData(eis_mime, Qt.MoveAction, 0, 0, eis_group)
    assert dataset.eis_runs == [second_eis, synthetic_eis_run]
    path = tmp_path / "reordered.cvproj"
    save_project(path, dataset, visible_runs=model.visible_runs, cycle_selection=model.cycle_selection)
    restored = load_project(path)
    assert [run.name for run in restored.dataset.cv_runs] == [b.name, a.name, c.name]
    assert [run.name for run in restored.dataset.eis_runs] == [second_eis.name, synthetic_eis_run.name]
    restored_b, restored_a = restored.dataset.cv_runs[:2]
    assert restored.visible_runs[restored_b.run_id] is False
    assert restored.cycle_selection[restored_a.run_id] == [2]
    app.processEvents()


def test_drag_updates_existing_plots_selection_and_previews(tmp_path, synthetic_cv_runs):
    from cvanalysis.ui.main_window import MainWindow
    from cvanalysis.ui.dialogs.legend_dialog import LegendTemplateDialog
    from cvanalysis.ui.dialogs.plot_data_dialog import PlotDataDialog

    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "settings.json")
    runs = list(synthetic_cv_runs)
    for run in runs:
        run.legend_template = "F{file_n}-C{cycle_n}"
    window._on_import_complete(Dataset(cv_runs=runs), [])
    tab = next(window.tabs.widget(i) for i in range(window.tabs.count())
               if window.tabs.widget(i).spec.kind == "cv_overlay")
    selected = runs[1]
    tab.spec.follow_dataset = False
    tab.spec.run_ids = [selected.run_id]
    tab.spec.cycle_selection = {selected.run_id: [2]}
    window._select_run_ids([selected.run_id])
    window._mark_clean()
    model = window.dataset_model
    mime = model.mimeData([model.index_for_run(selected.run_id)])
    assert window.tree.dragDropMode() == QAbstractItemView.InternalMove
    assert window.tree.dragEnabled() and window.tree.acceptDrops()
    assert model.dropMimeData(mime, Qt.MoveAction, 0, 0, model.index(0, 0))
    assert window._selected_run_ids() == [selected.run_id]
    assert window._dirty
    assert tab.spec.run_ids == [selected.run_id]
    assert tab.spec.cycle_selection == {selected.run_id: [2]}
    assert tab.figure.axes[0].get_legend().get_texts()[0].get_text() == "F1-C2"
    numbers = dataset_file_numbers(window.dataset)
    # A subset preview must retain dataset-wide numbers, rather than restarting at 1.
    dialog = LegendTemplateDialog([runs[0]], file_numbers=numbers)
    assert "F2-C1" in dialog.preview.toPlainText()
    data_dialog = PlotDataDialog(window.dataset, tab.spec, tab.spec.kind)
    assert data_dialog._run_items[selected.run_id].child(1).text(2) == "F1-C2"
    dialog.close()
    data_dialog.close()
    window.close()
    app.processEvents()
