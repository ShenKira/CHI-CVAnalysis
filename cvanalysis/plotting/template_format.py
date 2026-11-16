"""Bounded, non-executable formatting for user-provided plot templates."""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from contextvars import ContextVar
import math
import re
from functools import lru_cache

import numpy as np

MAX_TEMPLATE = 4096
MAX_FIELDS = 128
MAX_OUTPUT = 16384
MAX_WIDTH = 128
MAX_PRECISION = 12
MAX_MATH_LENGTH = 512
MAX_MATH_DEPTH = 32
_SPEC = re.compile(r"(?P<sign>[+ -]?)(?P<alternate>\#?)(?P<zero>0?)(?P<width>\d{0,3})(?:\.(?P<precision>\d{1,2}))?(?P<kind>[fFeEgGd%])\Z")
_INTEGERS = (int, np.int8, np.int16, np.int32, np.int64,
             np.uint8, np.uint16, np.uint32, np.uint64)
_NUMERIC = (*_INTEGERS, float, np.float16, np.float32, np.float64)
_WARNINGS = ContextVar("template_warnings", default=None)


class TemplateError(ValueError):
    """A template cannot be safely formatted."""


@contextmanager
def collect_template_warnings():
    warnings = []
    token = _WARNINGS.set(warnings)
    try:
        yield warnings
    finally:
        _WARNINGS.reset(token)


def _warn_invalid():
    warnings = _WARNINGS.get()
    message = "部分文本格式或数学公式无效，已按普通文字显示"
    if warnings is not None and message not in warnings:
        warnings.append(message)


def literal_fallback(template):
    """Keep invalid imported input visible without asking Matplotlib to parse it."""
    _warn_invalid()
    return str(template)[:MAX_TEMPLATE].replace("$", r"\$")


@dataclass(frozen=True)
class DisplayValue:
    value: object
    default: str
    suffix: str = ""


@dataclass(frozen=True)
class DisplayRange:
    start: int
    end: int
    default: str


def _numeric(value):
    if type(value) not in _NUMERIC:
        raise TemplateError("该变量不是可格式化的数值")
    value = int(value) if type(value) in _INTEGERS else float(value)
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise TemplateError("变量数值必须有限")
    return value


def _format_value(value, spec):
    if isinstance(value, DisplayRange):
        if not spec:
            return value.default
        return _format_value(value.start, spec) + "-" + _format_value(value.end, spec)
    if isinstance(value, DisplayValue):
        if not spec:
            return value.default
        if value.value is None:
            return value.default
        suffix, value = value.suffix, value.value
    else:
        suffix = ""
    if not spec:
        if type(value) is str:
            return value
        if value is None:
            return ""
        return str(_numeric(value))
    match = _SPEC.fullmatch(spec)
    if not match:
        raise TemplateError("格式无效；请使用 .2f、.3e 或 .4g 等格式")
    width = int(match.group("width") or 0)
    precision = int(match.group("precision") or 0)
    if width > MAX_WIDTH or precision > MAX_PRECISION:
        raise TemplateError("格式宽度或精度超过上限")
    number = _numeric(value)
    if match.group("kind") == "d" and type(number) is not int:
        raise TemplateError("整数格式 d 只能用于整数")
    # Python's g removes trailing zeros by default; keep requested significant digits.
    if match.group("kind") in "gG" and match.group("precision") is not None and not match.group("alternate"):
        sign = match.group("sign")
        spec = sign + "#" + spec[len(sign):]
    try:
        return format(number, spec) + suffix
    except (ValueError, OverflowError) as exc:
        raise TemplateError("数值格式不适用于该变量") from exc


@lru_cache(maxsize=256)
def _validate_math(expression):
    from matplotlib.mathtext import MathTextParser
    if len(expression) > MAX_MATH_LENGTH:
        raise TemplateError("数学公式过长")
    depth = 0
    for char in expression:
        if char == "{":
            depth += 1
            if depth > MAX_MATH_DEPTH:
                raise TemplateError("数学分组嵌套过深")
        elif char == "}":
            depth -= 1
    try:
        MathTextParser("path").parse(expression)
    except (ValueError, RuntimeError, RecursionError, OverflowError) as exc:
        raise TemplateError("数学公式无效或包含不支持的命令") from exc


def format_template(template, context, *, strict=False, normalize=None):
    """Substitute whitelisted fields, then validate MathText; never evaluate code.

    In math, unrecognised brace groups belong to MathText; a registered field
    wins, so nested groups such as ``$x_{{value:.2f}}$`` remain possible.
    Escapes are read only from the template, never from substituted values.
    """
    if type(template) is not str or len(template) > MAX_TEMPLATE:
        raise TemplateError("模板过长或不是文字")
    output, math_parts = [], []
    in_math = False
    fields = 0
    length = 0
    i = 0

    def append(text):
        nonlocal length
        length += len(text)
        if length > MAX_OUTPUT:
            raise TemplateError("格式化结果过长")
        output.append(text)
        if in_math:
            math_parts.append(text)

    while i < len(template):
        char = template[i]
        if char == "\\" and i + 1 < len(template):
            following = template[i + 1]
            if not in_math and following == "n":
                append("\n")
            elif not in_math and following == "\\":
                append("\\")
            else:
                append(char + following)
            i += 2
            continue
        if char == "$":
            if in_math:
                expression = "$" + "".join(math_parts) + "$"
                try:
                    _validate_math(expression)
                except TemplateError:
                    if strict:
                        raise
                    _warn_invalid()
                    # Keep an invalid imported formula as literal text, rather
                    # than letting Matplotlib abort the entire figure.
                    start = len(output) - len(math_parts) - 1
                    output[start] = r"\$"
                    char = r"\$"
                in_math = False
                math_parts = []
                append(char)
            else:
                append(char)
                in_math = True
            i += 1
            continue
        if char == "{" and not in_math and template.startswith("{{", i):
            append("{")
            i += 2
            continue
        if char == "}" and not in_math and template.startswith("}}", i):
            append("}")
            i += 2
            continue
        if char == "{":
            end = template.find("}", i + 1)
            nested = template.find("{", i + 1, end if end >= 0 else len(template))
            if end < 0:
                if strict:
                    raise TemplateError("花括号不完整")
                append(char)
                i += 1
                continue
            if nested >= 0:
                if not in_math and strict:
                    raise TemplateError("不支持嵌套字段")
                append(char)
                i += 1
                continue
            field = template[i + 1:end]
            name, separator, spec = field.partition(":")
            key = normalize(name) if normalize else name
            if key in context:
                fields += 1
                if fields > MAX_FIELDS:
                    raise TemplateError("模板中的字段过多")
                formatted = _format_value(context[key], spec if separator else "")
                # A math group must survive substitution so subscripts,
                # superscripts and command arguments keep their boundaries.
                append("{" + formatted + "}" if in_math else formatted)
            elif strict and not in_math and (separator or re.match(r"[A-Za-z_]", field)):
                raise TemplateError(f"未知或不允许的变量：{field}")
            else:
                append(template[i:end + 1])
            i = end + 1
            continue
        if char == "}" and not in_math and strict:
            raise TemplateError("花括号不完整")
        append(char)
        i += 1
    if in_math:
        if strict:
            raise TemplateError("数学公式的 $ 未配对")
        _warn_invalid()
        start = len(output) - len(math_parts) - 1
        output[start] = r"\$"
    return "".join(output)
