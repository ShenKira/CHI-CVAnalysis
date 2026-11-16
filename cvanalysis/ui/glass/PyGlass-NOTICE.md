# PyGlass adaptation notice

The optical kernel in `material.py` is a PySide6/NumPy adaptation
of the PyGlass design in `neomosh8/pyglass`, Copyright (c) 2026 neomosh8,
available under the MIT License in `PyGlass-LICENSE`.

Adapted ideas and structures include the beveled rounded-rectangle kernel,
precomputed bilinear sample coordinates, channel-dependent refraction,
Fresnel/environment reflection, separable transmission blur, and the separation
of optical material parameters from painter styling. This file changes the Qt
binding, screen-snapshot input, parameter profile, rendering path and menu
integration. It does not include PyGlass's desktop capture providers or widgets.

Source: https://github.com/neomosh8/pyglass
