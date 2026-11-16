"""Reader-level tests pending integration of LSV and i-t run types."""
from pathlib import Path

import numpy as np
import pytest

from cvanalysis.domain.errors import ParseError
from cvanalysis.io.chi_sweep import ChiITReader, ChiLSVReader


@pytest.mark.parametrize("reader,title,header,unit", [
    (ChiLSVReader, "Linear Sweep Voltammetry", "Potential/V, Current/A", "V"),
    (ChiITReader, "Amperometric i-t Curve", "Time/sec, Current/A", "s"),
])
def test_reader_retains_arrays_and_metadata(reader, title, header, unit):
    text = f"{title}\nInit E (V) = 1.5\nResults:\n{header}\n0, 1e-6\n1, -2e-6\n"
    data = reader().parse(text, Path("synthetic.txt"))
    assert data.x_unit == unit and data.metadata["Init E (V)"] == "1.5"
    np.testing.assert_allclose(data.x, [0, 1])
    np.testing.assert_allclose(data.current, [1e-6, -2e-6])


def test_reader_rejects_wrong_type_and_nonfinite_values():
    with pytest.raises(ParseError):
        ChiLSVReader().parse("Cyclic Voltammetry", Path("cv.txt"))
    with pytest.raises(ParseError):
        ChiITReader().parse("Amperometric i-t Curve\nTime/sec, Current/A\n0, 1\n1, nan\n", Path("bad.txt"))


def test_standalone_window_and_current_reference():
    from matplotlib.figure import Figure
    from cvanalysis.plotting.sweep_preview import draw_it_preview, draw_lsv_preview

    lsv = ChiLSVReader().parse("Linear Sweep Voltammetry\nPotential/V, Current/A\n0, 1e-6\n2, 2e-6\n", Path("lsv.txt"))
    ax = draw_lsv_preview(Figure(), lsv, voltage_window=(1.5, .5))
    assert len(ax.lines) == 3 and "1 V" in ax.texts[0].get_text()
    run = ChiITReader().parse("Amperometric i-t Curve\nTime/sec, Current/A\n0, 1e-6\n1, 2e-6\n", Path("it.txt"))
    ax = draw_it_preview(Figure(), run, reference_time=.9)
    assert ax.lines[1].get_ydata()[0] == pytest.approx(2e-6)
    assert "t=1 s" in ax.texts[0].get_text()
    with pytest.raises(ValueError):
        draw_it_preview(Figure(), run, reference_time=2)
