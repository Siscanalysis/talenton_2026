"""Coastal 2-D transport: domain, seabed source coupling and the FiPy engine.

The chain this package sits at the end of::

    authorised contaminated seabed hotspot
      -> contaminant flux through / near the seabed
      -> reactive mat (1-D reactive layer, per tile)
      -> residual flux into the overlying water     <- seabed_source.py
      -> 2-D coastal advection and diffusion        <- fipy_engine.py

Nothing here intercepts a plume.  There is no frontal area, no swept volume and
no interception efficiency, and no mass is ever subtracted from a water-column
cell.  The mat acts only by reducing the seabed flux that enters the water.

Sub-modules are imported lazily so that ``import reactive_seabed_mat`` stays
cheap and so that a caller who only needs the grid does not pay for FiPy.
"""

from __future__ import annotations

__all__ = ["domain", "fipy_engine", "seabed_source", "geodata"]
