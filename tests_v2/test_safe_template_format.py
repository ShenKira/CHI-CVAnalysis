"""Safe formatting shared by user-editable variable templates."""
import numpy as np
import pytest

from cvanalysis.domain.models import SweepMetadata, SweepRun
from cvanalysis.plotting.legend import render_legend_template, resolve_legend_labels, template_uses_cycle, validate_legend_template
from cvanalysis.plotting.template_format import DisplayRange, DisplayValue, TemplateError, format_template
from cvanalysis.plotting.sweep_renderer import _reference_text
from cvanalysis.domain.units import CURRENT
from cvanalysis.domain.units import IMPEDANCE
from cvanalysis.plotting.cp_renderer import _current_text
from cvanalysis.plotting.eis_renderer import _format_metric_with_unit
from cvanalysis.plotting.texts import safe_format, validate_text_template


@pytest.mark.parametrize('spec,expected', [('.2f', '1.20'), ('.3e', '1.200e+00'),
                                            ('.4g', '1.200'), ('.2F', '1.20')])
def test_numeric_format_retains_zeros(spec, expected):
    assert format_template('{value:' + spec + '}', {'value': 1.2}) == expected


def test_legend_formats_real_numeric_fields_and_preserves_legacy_unit():
    run = SweepRun('it', 'sample', 'it', np.array([0., 1.]), np.array([1., 2.]),
                   SweepMetadata('test', {'Init E': 1.5}))
    assert render_legend_template('{IT_Potential}', run)[0] == '1.5V'
    assert render_legend_template('{IT_Potential:.2f}', run)[0] == '1.50V'
    assert template_uses_cycle('{cycle_n:03d}')
    validate_legend_template('{IT_Potential:.2f}')


def test_it_reference_explicit_format_and_legacy_format():
    run = SweepRun('it', 'sample', 'it', np.array([0., 1.]), np.array([1., 2.]), SweepMetadata('test', {}))
    options = {'it_reference_label_mode': 'custom', 'it_reference_current_unit': 'µA',
               'it_reference_number_format': 'fixed', 'it_reference_digits': 1,
               'it_reference_label_text': '{time} / {current:.3f} {unit}'}
    assert _reference_text(options, 1., 2e-6, CURRENT, run) == '1.0 / 2.000 µA'


def test_preformatted_cp_and_eis_values_support_numeric_precision():
    cp = _current_text(2e-6)
    eis = _format_metric_with_unit(12.0, IMPEDANCE, None)
    assert format_template('{current:.2f}', {'current': cp}) == '2.00 µA'
    assert format_template('{value:.2f}', {'value': eis}) == '12.00 Ω'
    assert validate_text_template('annotation.cp_gcd.current', 'I={current:.2f}')[0]


@pytest.mark.parametrize('template', [
    '{x.__class__}', '{x[0]}', '{__import__("os").system("echo bad")}',
    '{x!r}', '{x:{width}}', '{x:.999999999f}', '{x:999999999f}',
    '{x + 1}',
])
def test_malicious_or_resource_exhausting_templates_are_rejected(template, tmp_path):
    sentinel = tmp_path / 'must_not_exist'
    with pytest.raises(TemplateError):
        format_template(template, {'x': 1.2}, strict=True)
    assert not sentinel.exists()


@pytest.mark.parametrize('template,context', [
    ('{x:129f}', {'x': 1.2}),
    ('{x:.13f}', {'x': 1.2}),
    ('{x}' * 129, {'x': 1}),
    ('{x}' * 128, {'x': 'a' * 129}),
    (r'$\input{secret}$', {}),
    (r'$\write18{command}$', {}),
])
def test_security_boundaries_reject_without_evaluation(template, context):
    with pytest.raises(TemplateError):
        format_template(template, context, strict=True)


def test_safe_resource_boundaries_remain_usable():
    assert len(format_template('{x:128f}', {'x': 1.2}, strict=True)) == 128
    assert format_template('{x:.12f}', {'x': 1.2}, strict=True) == '1.200000000000'
    assert format_template('{x}' * 128, {'x': 'a' * 128}, strict=True) == 'a' * 16384


def test_untrusted_format_method_is_never_called():
    class Evil:
        def __format__(self, spec):
            raise AssertionError('must not run')
        def __str__(self):
            raise AssertionError('must not run')
    with pytest.raises(TemplateError):
        format_template('{x:.2f}', {'x': Evil()}, strict=True)
    with pytest.raises(TemplateError):
        format_template('{x}', {'x': Evil()}, strict=True)


def test_code_like_template_cannot_create_a_file(tmp_path):
    sentinel = tmp_path / 'created_by_template'
    payload = "{__import__('pathlib').Path('" + str(sentinel) + "').touch()}"
    with pytest.raises(TemplateError):
        format_template(payload, {}, strict=True)
    assert format_template(payload, {}, strict=False) == payload
    run = SweepRun('it', 'sample', 'it', np.array([0., 1.]), np.array([1., 2.]), SweepMetadata('test', {}))
    assert render_legend_template(payload, run)[0] == payload
    assert safe_format(payload, {'value': 1.0}) == payload
    assert not sentinel.exists()


def test_limits_and_mathtext_compatibility():
    with pytest.raises(TemplateError):
        format_template('{x}' * 200, {'x': 1}, strict=True)
    with pytest.raises(TemplateError):
        format_template('x' * 4097, {}, strict=True)
    assert format_template(r'$v^{-1/2}$ {value:.2f}', {'value': 2.}, strict=True) == r'$v^{-1/2}$ 2.00'
    assert format_template(r'$I_{ref}$ = {value:.2f}', {'value': 2.}, strict=True) == r'$I_{ref}$ = 2.00'
    assert format_template('{unknown}', {}, strict=False) == '{unknown}'
    assert format_template('{x}', {'x': DisplayValue(2.0, '2V', 'V')}) == '2V'
    assert format_template('{x:03d}', {'x': DisplayRange(1, 12, '1-12')}) == '001-012'


def test_math_groups_variable_first_and_newline_escaping():
    text = r'$\frac{I_{ref}}{\mathrm{A}}={value:.2f}$\n$\nu+\nabla$'
    result = format_template(text, {'value': 2.}, strict=True)
    assert result == '$\\frac{I_{ref}}{\\mathrm{A}}={2.00}$\n$\\nu+\\nabla$'
    assert format_template(r'$I_{value:.2f}$', {'value': 2.}, strict=True) == '$I_{2.00}$'
    assert format_template(r'$I_{{value:.2f}}$', {'value': 2.}, strict=True) == '$I_{{2.00}}$'
    assert format_template(r'first\\nsecond', {}, strict=True) == r'first\nsecond'


def test_math_rejects_invalid_formulas_and_never_reparses_values():
    with pytest.raises(TemplateError):
        format_template(r'$\notacommand{x}$', {}, strict=True)
    with pytest.raises(TemplateError):
        format_template('$x', {}, strict=True)
    with pytest.raises(TemplateError):
        format_template('$' + 'x' * 513 + '$', {}, strict=True)
    with pytest.raises(TemplateError):
        format_template('$' + '{' * 33 + 'x' + '}' * 33 + '$', {}, strict=True)
    assert format_template(r'{name}', {'name': r'literal\n{name}'}, strict=True) == r'literal\n{name}'
    assert format_template(r'$\notacommand{x}$', {}, strict=False).startswith(r'\$')


def test_legend_math_groups_do_not_become_unknown_tokens():
    run = SweepRun('it', 'sample', 'it', np.array([0., 1.]), np.array([1., 2.]),
                   SweepMetadata('test', {'Init E': 1.5}))
    text, unknown = render_legend_template(r'$\frac{1}{2}$\n{IT_Potential:.2f}', run)
    assert text == '$\\frac{1}{2}$\n1.50V'
    assert not unknown
    validate_legend_template(r'$\frac{1}{2}$\n{IT_Potential:.2f}')


def test_legend_alias_supports_math_and_newline():
    run = SweepRun('it', 'sample', 'it', np.array([0., 1.]), np.array([1., 2.]), SweepMetadata('test', {}))
    run.legend_alias = r'$I_{ref}$\nnext'
    assert resolve_legend_labels([run])[run.run_id].label == '$I_{ref}$\nnext'
    assert render_legend_template('{Alias}', run)[0] == '$I_{ref}$\nnext'
