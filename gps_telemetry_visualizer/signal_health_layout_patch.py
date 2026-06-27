from __future__ import annotations

from gps_telemetry_visualizer import core, native_preview

NAME = "signal_health"
_INSTALLED = False
_ORIGINAL_DEFAULT = None
_ORIGINAL_CLONE = None
_ORIGINAL_SCALE = None
_ORIGINAL_SIZE = None
_ORIGINAL_LABEL = None


def install() -> None:
    global _INSTALLED, _ORIGINAL_DEFAULT, _ORIGINAL_CLONE, _ORIGINAL_SCALE, _ORIGINAL_SIZE, _ORIGINAL_LABEL
    if _INSTALLED:
        return
    if NAME not in core.LAYOUT_ELEMENT_NAMES:
        core.LAYOUT_ELEMENT_NAMES = tuple(core.LAYOUT_ELEMENT_NAMES) + (NAME,)
    _ORIGINAL_DEFAULT = core.default_overlay_layout
    _ORIGINAL_CLONE = core.clone_overlay_layout
    _ORIGINAL_SCALE = core.scale_overlay_layout
    _ORIGINAL_SIZE = core._element_size
    _ORIGINAL_LABEL = core._element_label
    core.default_overlay_layout = default_overlay_layout
    core.clone_overlay_layout = clone_overlay_layout
    core.scale_overlay_layout = scale_overlay_layout
    core._element_size = element_size
    core._element_label = element_label
    native_preview.LAYOUT_LABELS[NAME] = "Signal health"
    native_preview.compute_layout_bounds = core.compute_layout_bounds
    native_preview.default_overlay_layout = core.default_overlay_layout
    native_preview.resize_layout_element_from_corner = core.resize_layout_element_from_corner
    _INSTALLED = True


def default_signal_layout(width, height):
    return core.ElementLayout(float(width) * 0.82, float(height) * 0.18, True, 1.0)


def ensure_signal_layout(layout, width, height):
    if not hasattr(layout, NAME):
        setattr(layout, NAME, default_signal_layout(width, height))
    return layout


def default_overlay_layout(width, height, export_mode="both", speedometer_style="half"):
    layout = _ORIGINAL_DEFAULT(width, height, export_mode, speedometer_style)
    return ensure_signal_layout(layout, width, height)


def clone_overlay_layout(layout):
    cloned = _ORIGINAL_CLONE(layout)
    source = getattr(ensure_signal_layout(layout, 1920, 1080), NAME)
    setattr(cloned, NAME, core.ElementLayout(source.x, source.y, source.visible, core._normalized_scale(source.scale)))
    return cloned


def scale_overlay_layout(layout, old_width, old_height, new_width, new_height):
    scaled = _ORIGINAL_SCALE(layout, old_width, old_height, new_width, new_height)
    source = getattr(ensure_signal_layout(layout, old_width, old_height), NAME)
    setattr(scaled, NAME, core.ElementLayout(source.x / max(1, old_width) * new_width, source.y / max(1, old_height) * new_height, source.visible, core._normalized_scale(source.scale)))
    return scaled


def element_size(name, canvas, config=None):
    if name == NAME:
        width = float(canvas.width)
        height = float(canvas.height)
        return min(width * 0.28, 520.0), max(150.0, min(height * 0.18, 220.0))
    return _ORIGINAL_SIZE(name, canvas, config)


def element_label(name):
    if name == NAME:
        return "Signal health overlay"
    return _ORIGINAL_LABEL(name)
