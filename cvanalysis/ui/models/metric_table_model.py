# -*- coding: utf-8 -*-
"""Backward-compatible import for the result table model.

The result views now use a tree model so a run row can expose per-cycle
children.  ``MetricTableModel`` keeps its flat ``set_data`` API and is an
alias of :class:`MetricTreeModel`.
"""

from cvanalysis.ui.models.metric_tree_model import MetricTableModel, MetricTreeModel

__all__ = ["MetricTableModel", "MetricTreeModel"]
