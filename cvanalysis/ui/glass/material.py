"""PySide6 adaptation of PyGlass's cached bevel/refraction architecture.

See PyGlass-NOTICE.md and PyGlass-LICENSE for attribution and license.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap


@dataclass(frozen=True)
class GlassMaterial:
    """Coupled slab/frost controls; values are tuned for legible menus."""
    thickness: float = .46
    frost: float = .28
    strength: float = 14.0
    bevel: float = 12.0
    pad: float = 24.0
    ior_edge: float = 2.05
    ior_inner: float = 1.34
    chroma: float = .025
    disp_glow: float = 30.0
    disp_saturation: float = .28
    disp_width: float = 1.5
    reflect: float = .48
    f0: float = .035
    max_frost_sigma: float = 8.0

    def pad_px(self, dpr: float) -> int:
        scale = 1.0 if self.thickness <= .5 else 1.0 + 1.2 * (self.thickness - .5)
        return max(2, round(self.pad * scale * dpr))


@dataclass(frozen=True)
class GlassStyle:
    """Non-optical presentation, kept separate from the refraction kernel."""
    tint_top: int = 7
    tint_bottom: int = 2
    sheen_alpha: int = 9
    sheen_extent: float = .46
    rim_top: int = 125
    rim_mid: int = 28
    rim_bottom: int = 70
    rim_width: float = 1.0


class GlassKernel:
    """Precompute a rounded-bevel Snell response for one size and material."""
    def __init__(self, width, height, radius, dpr, material: GlassMaterial):
        self.width, self.height = int(width), int(height)
        self.pad = material.pad_px(dpr)
        pad, w, h = self.pad, self.width, self.height
        xs, ys = np.meshgrid(np.arange(w, dtype=np.float32) + pad,
                             np.arange(h, dtype=np.float32) + pad)
        cx, cy = pad + w / 2.0, pad + h / 2.0
        half_w, half_h = w / 2.0, h / 2.0
        radius = min(float(radius), half_w, half_h)
        qx = np.abs(xs - cx) - (half_w - radius)
        qy = np.abs(ys - cy) - (half_h - radius)
        distance = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - radius
        inside_depth = np.maximum(-distance, 0)
        inside = distance < 0
        gy, gx = np.gradient(distance)
        norm = np.hypot(gx, gy) + 1e-6
        nx, ny = gx / norm, gy / norm

        t = np.clip(inside_depth / max(1e-3, material.bevel * dpr), 0, 1)
        slope_x = np.where(inside, np.clip(1 - t, 0, .96), 0)
        slope = slope_x / np.sqrt(np.maximum(1e-5, 1 - slope_x * slope_x))
        cos_t, sin_t = 1 / np.sqrt(1 + slope * slope), slope / np.sqrt(1 + slope * slope)
        ior = material.ior_edge + (material.ior_inner - material.ior_edge) * t
        thickness_scale = material.strength * dpr * (.88 + .48 * material.thickness)
        max_disp = .92 * pad

        self.samples = []
        for channel_factor in (-1.0, 0.0, 1.0):
            eta = 1 / np.maximum(1.01, ior * (1 + material.chroma * channel_factor))
            cos_r = np.sqrt(np.clip(1 - eta * eta * sin_t * sin_t, 0, 1))
            coeff = eta * cos_t - cos_r
            z_down = np.maximum(1e-3, eta - coeff * cos_t)
            scale = thickness_scale / z_down
            sx = np.clip(xs + np.clip(coeff * nx * sin_t * scale, -max_disp, max_disp), 0, w + 2 * pad - 1)
            sy = np.clip(ys + np.clip(coeff * ny * sin_t * scale, -max_disp, max_disp), 0, h + 2 * pad - 1)
            self.samples.append(self._bilinear_map(sx, sy))

        fresnel = material.f0 + (1 - material.f0) * (1 - np.clip(cos_t, 0, 1)) ** 5
        fresnel = np.where(inside, fresnel * material.reflect, 0).astype(np.float32)[..., None]
        rx, ry = 2 * cos_t * nx * sin_t, 2 * cos_t * ny * sin_t
        rz = 2 * cos_t * cos_t - 1
        key = np.clip(-.15 * rx - .75 * ry + .65 * rz, 0, 1) ** 46
        fill = np.clip(-.62 * rx + .55 * ry + .56 * rz, 0, 1) ** 22
        horizon = 1 - np.clip(rz, 0, 1)
        env = np.stack((horizon * 98 + key * 235 + fill * 130,
                        horizon * 114 + key * 239 + fill * 164,
                        horizon * 143 + key * 245 + fill * 214), axis=-1)
        self.one_minus_fresnel = 1 - fresnel
        self.reflection = env.astype(np.float32) * fresnel

        angle = np.arctan2(ny, nx)
        hue = (angle / (2 * math.pi) + .5) % 1
        h6 = hue * 6
        sector = np.floor(h6).astype(np.int8) % 6
        f = h6 - np.floor(h6)
        q = 1 - f
        rgb = np.stack((np.select([sector == i for i in range(6)], [1, q, 0, 0, f, 1]),
                        np.select([sector == i for i in range(6)], [f, 1, 1, q, 0, 0]),
                        np.select([sector == i for i in range(6)], [0, 0, f, 1, 1, q])), axis=-1)
        rgb = rgb * material.disp_saturation + (1 - material.disp_saturation)
        line = np.where(inside, np.clip(1 - inside_depth / (material.disp_width * dpr), 0, 1), 0)
        frost = max(0.0, material.frost) ** 1.5 * material.max_frost_sigma * dpr
        self.blur_radius = max(0, round((-1 + math.sqrt(1 + 4 * frost * frost)) / 2))
        self.haze = min(1.0, max(0.0, material.frost)) * .18
        self.dispersion = (rgb * (line * material.disp_glow * (1 - .4 * material.frost))[..., None]).astype(np.float32)

    def _bilinear_map(self, sx, sy):
        x0, y0 = np.floor(sx).astype(np.int32), np.floor(sy).astype(np.int32)
        fx, fy = (sx - x0).astype(np.float32), (sy - y0).astype(np.float32)
        max_x, max_y = self.width + 2 * self.pad - 1, self.height + 2 * self.pad - 1
        return (np.clip(x0, 0, max_x), np.clip(x0 + 1, 0, max_x),
                np.clip(y0, 0, max_y), np.clip(y0 + 1, 0, max_y), fx, fy)

    @staticmethod
    def _box_blur(channel, radius):
        if radius < 1:
            return channel
        kernel, inv = radius * 2 + 1, np.float32(1 / (radius * 2 + 1))
        for _ in range(3):
            padded = np.pad(channel, ((0, 0), (radius + 1, radius)), mode="edge")
            summed = np.cumsum(padded, axis=1, dtype=np.float32)
            channel = (summed[:, kernel:] - summed[:, :-kernel]) * inv
            padded = np.pad(channel, ((radius + 1, radius), (0, 0)), mode="edge")
            summed = np.cumsum(padded, axis=0, dtype=np.float32)
            channel = (summed[kernel:, :] - summed[:-kernel, :]) * inv
        return channel

    def apply(self, padded):
        out = np.empty((self.height, self.width, 3), np.float32)
        for channel, (x0, x1, y0, y1, fx, fy) in enumerate(self.samples):
            plane = padded[..., channel].astype(np.float32, copy=False)
            top = plane[y0, x0] * (1 - fx) + plane[y0, x1] * fx
            bottom = plane[y1, x0] * (1 - fx) + plane[y1, x1] * fx
            out[..., channel] = top * (1 - fy) + bottom * fy
        if self.blur_radius:
            for channel in range(3):
                out[..., channel] = self._box_blur(out[..., channel], self.blur_radius)
        if self.haze:
            milky = .5 * out.mean(axis=2, keepdims=True) + 127.5
            out = out * (1 - self.haze) + milky * self.haze
        out = out * self.one_minus_fresnel + self.reflection + self.dispersion
        return np.clip(out, 0, 255).astype(np.uint8)


MAX_GLASS_PIXELS = 200_000


@lru_cache(maxsize=4)
def _cached_kernel(width, height, radius, dpr, material):
    return GlassKernel(width, height, radius, dpr, material)


class GlassRenderer:
    """Slice a padded app snapshot and render with one cached optical kernel."""
    def __init__(self, width, height, radius, dpr, material):
        self.width, self.height = round(width * dpr), round(height * dpr)
        self.dpr = dpr
        if self.width < 2 or self.height < 2 or self.width * self.height > MAX_GLASS_PIXELS:
            raise ValueError("glass surface exceeds the bounded optical buffer")
        self.kernel = _cached_kernel(self.width, self.height, round(radius * dpr), dpr, material)

    def render(self, backdrop, origin, backdrop_dpr, base_color):
        from PIL import Image
        from PySide6.QtGui import QImage

        pad = self.kernel.pad
        source_pad = round(pad * backdrop_dpr / self.dpr)
        x, y = round(origin.x() * backdrop_dpr), round(origin.y() * backdrop_dpr)
        logical_width = self.width / self.dpr
        logical_height = self.height / self.dpr
        bounds = (x - source_pad, y - source_pad,
                  x + round(logical_width * backdrop_dpr) + source_pad,
                  y + round(logical_height * backdrop_dpr) + source_pad)
        sample = np.empty((self.height + 2 * pad, self.width + 2 * pad, 4), np.uint8)
        sample[:] = (*base_color, 255)
        left, top = max(0, bounds[0]), max(0, bounds[1])
        right, bottom = min(backdrop.shape[1], bounds[2]), min(backdrop.shape[0], bounds[3])
        if right > left and bottom > top:
            crop = backdrop[top:bottom, left:right]
            dx = round((left - bounds[0]) * self.dpr / backdrop_dpr)
            dy = round((top - bounds[1]) * self.dpr / backdrop_dpr)
            target_w = min(sample.shape[1] - dx, round(crop.shape[1] * self.dpr / backdrop_dpr))
            target_h = min(sample.shape[0] - dy, round(crop.shape[0] * self.dpr / backdrop_dpr))
            if target_w > 0 and target_h > 0:
                rgba = Image.fromarray(crop, "RGBA").resize((target_w, target_h), Image.Resampling.LANCZOS)
                sample[dy:dy + target_h, dx:dx + target_w] = np.asarray(rgba)
        rgb = self.kernel.apply(sample[..., :3])
        image = QImage(rgb.data, self.width, self.height, self.width * 3, QImage.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(self.dpr)
        return pixmap


def paint_glass(painter: QPainter, rect: QRectF, radius: float,
                refracted: QPixmap | None, style: GlassStyle):
    """Composite a refracted layer with the restrained PyGlass style tokens."""
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    painter.save()
    painter.setClipPath(path)
    if refracted is not None:
        painter.drawPixmap(rect, refracted, QRectF(refracted.rect()))
    tint = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    tint.setColorAt(0, QColor(255, 255, 255, style.tint_top))
    tint.setColorAt(1, QColor(255, 255, 255, style.tint_bottom))
    painter.fillRect(rect, QBrush(tint))
    if style.sheen_alpha:
        sheen = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.top() + rect.height() * style.sheen_extent))
        sheen.setColorAt(0, QColor(255, 255, 255, style.sheen_alpha))
        sheen.setColorAt(1, QColor(255, 255, 255, 0))
        painter.fillRect(rect, QBrush(sheen))
    painter.restore()
    rim = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    rim.setColorAt(0, QColor(255, 255, 255, style.rim_top))
    rim.setColorAt(.5, QColor(255, 255, 255, style.rim_mid))
    rim.setColorAt(1, QColor(255, 255, 255, style.rim_bottom))
    painter.setPen(QPen(QBrush(rim), style.rim_width))
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(rect.adjusted(.6, .6, -.6, -.6), radius, radius)
