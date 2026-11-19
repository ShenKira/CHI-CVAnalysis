"""Choice of charge reference for Dunn plots."""
from PySide6.QtWidgets import QInputDialog, QMessageBox


BASIS_LABELS = {"fitted": "拟合分量之和（默认）", "measured": "实测支路净电荷"}
BASIS_NOTE = (
    "拟合模式以两个分量的带符号净电荷之和为 100%。\n"
    "实测模式以同一扫速、同一支路的实测净电荷为 100%，两项之和可反映拟合偏差。\n"
    "两种模式使用相同的拟合电流。分量异号时可能出现负占比或超过 100%，"
    "分母接近抵消时占比留空。"
)


def choose_dunn_basis(parent) -> str | None:
    labels = list(BASIS_LABELS.values())
    label, accepted = QInputDialog.getItem(
        parent, "Dunn 贡献率基准", BASIS_NOTE + "\n\n本图的 100% 基准", labels, 0, False)
    if not accepted:
        return None
    return next(key for key, value in BASIS_LABELS.items() if value == label)


def show_dunn_basis(parent, basis: str) -> None:
    QMessageBox.information(parent, "Dunn 贡献率基准", f"当前图已选择：{BASIS_LABELS[basis]}。\n\n{BASIS_NOTE}")
