"""Offline geodata adapters for the coastal model.

Three explicit modes, never silently promoted between:
``synthetic``, ``real_map_illustrative`` and ``imported_forcing``.
The default run is fully offline: no account, no token, no tile server and no
network call in any default code path.

See :mod:`reactive_seabed_mat.coastal_transport.geodata.adapters`.
"""

from __future__ import annotations

from .adapters import (  # noqa: F401
    BathymetryUsage,
    CachedProduct,
    CachedProductMissing,
    GeodataMode,
    GeodataModeRefused,
    NetworkAccessRefused,
    ProductMetadata,
    ImportedForcingAdapter,
    RealMapIllustrativeAdapter,
    SyntheticAdapter,
    adapter_for,
    bathymetry_statement,
    forcing_from_product,
    load_cached_product,
    resolve_mode,
    save_cached_product,
)

__all__ = [
    "BathymetryUsage",
    "CachedProduct",
    "CachedProductMissing",
    "GeodataMode",
    "GeodataModeRefused",
    "NetworkAccessRefused",
    "ProductMetadata",
    "ImportedForcingAdapter",
    "RealMapIllustrativeAdapter",
    "SyntheticAdapter",
    "adapter_for",
    "bathymetry_statement",
    "forcing_from_product",
    "load_cached_product",
    "resolve_mode",
    "save_cached_product",
]
