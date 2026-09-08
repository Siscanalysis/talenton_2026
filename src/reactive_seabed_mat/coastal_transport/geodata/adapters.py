"""Cached-file geodata adapters, offline by default.

``docs/REUSE_AND_DATA.md`` fixes three modes and forbids silent promotion
between them:

``synthetic``
    A small channel-like domain with a prescribed current field.  The default.
    Nothing about it is geographic.
``real_map_illustrative``
    A cached geographic basemap for **context only**.  The physics stay
    illustrative and are labelled as such on every chart.  A real map must never
    imply that this project located a real hotspot.
``imported_forcing``
    Currents read from a cached external product, with the product name,
    version, time, depth, native resolution and temporal averaging preserved,
    and the resolution limits printed next to every chart.

Rules this module enforces rather than merely documents:

* **No network access in any code path.**  ``fetch`` exists only to raise
  :class:`NetworkAccessRefused` with instructions for a human to place the file.
* A **de-tided or daily-mean** product is refused for a tide-resolving scenario
  [S10]: it cannot stand in for a tidal reversal.
* **Surface currents are not near-bed currents.**  A near-bed release driven by
  a surface product must say so, and :meth:`ProductMetadata.depth_statement`
  says it.
* **Interpolation creates no information.**  Regridding a coarse product onto a
  10 m grid is stated as such in :meth:`ProductMetadata.resolution_statement`,
  which is attached to every :class:`~reactive_seabed_mat.contracts.Forcing`
  built from it.
* **Bathymetry does not generate currents.**  Depth is visual context only in
  this demonstrator; :class:`BathymetryUsage` has exactly one member and
  :func:`bathymetry_statement` says so in words.

Nothing here invents a product, a licence or a resolution.  A cached product
file carries its own metadata; if a field is unknown it stays ``None`` and is
reported as unknown.
"""

from __future__ import annotations

import enum
import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from ...config import DomainConfig, ForcingConfig
from ...contracts import Forcing, GridSpec, ProvenanceLabel
from ..domain import (
    NON_TIDE_RESOLVING_AVERAGING,
    SYNTHETIC_FORCING_NOTE,
    TidalForcingRefused,
    forcing_at,
)

__all__ = [
    "GeodataMode",
    "BathymetryUsage",
    "NetworkAccessRefused",
    "CachedProductMissing",
    "GeodataModeRefused",
    "ProductMetadata",
    "CachedProduct",
    "SyntheticAdapter",
    "RealMapIllustrativeAdapter",
    "ImportedForcingAdapter",
    "resolve_mode",
    "adapter_for",
    "bathymetry_statement",
    "save_cached_product",
    "load_cached_product",
    "forcing_from_product",
    "OFFLINE_NOTE",
    "ILLUSTRATIVE_MAP_NOTE",
]

OFFLINE_NOTE = (
    "Offline by default: this adapter reads a cached file that a human placed "
    "on disc. It never opens a network connection, and it holds no account, "
    "token or tile-server address."
)

ILLUSTRATIVE_MAP_NOTE = (
    "Illustrative map mode. The basemap is geographic context only. The flow "
    "and the contaminant source remain synthetic and are not a statement about "
    "any real location. Nothing in this project has located a real hotspot."
)


class GeodataMode(str, enum.Enum):
    """The three modes.  Promotion between them is always explicit."""

    SYNTHETIC = "synthetic"
    REAL_MAP_ILLUSTRATIVE = "real_map_illustrative"
    IMPORTED_FORCING = "imported_forcing"


class BathymetryUsage(str, enum.Enum):
    """How depth enters this demonstrator.

    One member on purpose.  A bathymetric map does not itself generate currents,
    and no depth raster feeds the flow solver here: the mixing depth in
    :class:`~reactive_seabed_mat.contracts.GridSpec` is a prescribed effective
    depth, not a bathymetry.
    """

    VISUAL_CONTEXT_ONLY = "visual_context_only"


class NetworkAccessRefused(RuntimeError):
    """Raised whenever anything asks an adapter to reach the network."""


class CachedProductMissing(FileNotFoundError):
    """The cached product file is not on disc.  Nothing is downloaded."""


class GeodataModeRefused(ValueError):
    """An unknown mode, or an implicit promotion between modes."""


# ---------------------------------------------------------------------------
# Product metadata
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ProductMetadata:
    """Everything a cached external product must carry to be usable.

    Unknown stays unknown: a ``None`` field is reported as unknown rather than
    filled with a plausible value.
    """

    product_name: str
    #: Vendor or catalogue version string, exactly as distributed.
    product_version: str | None = None
    #: Variable names as they appear in the source product.
    variable_names: Sequence[str] = ()
    time_coverage_start_utc: str | None = None
    time_coverage_end_utc: str | None = None
    #: Depth of the extracted layer, metres below the sea surface.
    depth_m: float | None = None
    depth_datum: str | None = None
    #: Native horizontal resolution as distributed, in degrees and / or metres.
    native_resolution_deg: float | None = None
    native_resolution_m: float | None = None
    #: 'hourly_instantaneous', 'daily_mean', 'de_tided', ... exactly as declared.
    temporal_averaging: str = "unknown"
    #: Whether the distributor states the product resolves the tide.
    tide_resolving: bool | None = None
    licence: str | None = None
    citation: str | None = None
    cached_path: str | None = None
    retrieved_at_utc: str | None = None
    crs: str = "EPSG:4326"
    provenance: ProvenanceLabel = ProvenanceLabel.EXTERNAL_MODEL
    notes: str = ""

    # -- honest statements --------------------------------------------------

    @property
    def resolves_tide(self) -> bool:
        """Whether this product may be used for a tide-resolving scenario."""
        if str(self.temporal_averaging).strip().lower() in NON_TIDE_RESOLVING_AVERAGING:
            return False
        if self.tide_resolving is None:
            return False
        return bool(self.tide_resolving)

    def resolution_statement(self, grid: GridSpec | None = None) -> str:
        """One honest sentence about what this product can and cannot resolve."""
        parts = [f"Product {self.product_name}"]
        if self.product_version:
            parts[0] += f" version {self.product_version}"
        if self.native_resolution_deg is not None:
            native = f"{self.native_resolution_deg} deg"
            if self.native_resolution_m is not None:
                native += f" (about {self.native_resolution_m:.0f} m)"
        elif self.native_resolution_m is not None:
            native = f"{self.native_resolution_m:.0f} m"
        else:
            native = "an undeclared native resolution"
        parts.append(f"native horizontal resolution {native}")
        parts.append(f"temporal averaging {self.temporal_averaging}")
        if grid is not None:
            parts.append(
                f"regridded onto a {grid.dx_m:.0f} m by {grid.dy_m:.0f} m "
                f"{grid.nx}x{grid.ny} model grid"
            )
        statement = "; ".join(parts) + ". "
        statement += (
            "Interpolating a coarse product onto a fine grid does not create "
            "information at the fine scale: every feature below the native "
            "resolution is interpolation, not measurement."
        )
        if not self.resolves_tide:
            statement += (
                " This product is not declared tide resolving, so it must not "
                "be used for a tidal-reversal scenario."
            )
        return statement

    def depth_statement(self) -> str:
        """Whether the extracted layer is near-bed, and what that costs."""
        if self.depth_m is None:
            return (
                "The depth of the extracted current layer is not declared in "
                "the cached product, so it cannot be treated as a near-bed "
                "field. Surface currents are not automatically near-bed "
                "currents."
            )
        datum = self.depth_datum or "an undeclared datum"
        return (
            f"Current layer extracted at {self.depth_m} m below {datum}. "
            "Surface currents are not automatically near-bed currents: a "
            "near-bed source driven by a shallower layer overstates the "
            "transport that reaches the seabed."
        )

    def require_tide_resolving(self) -> None:
        """Refuse a de-tided or daily product for a tide-resolving scenario."""
        if not self.resolves_tide:
            raise TidalForcingRefused(
                f"product {self.product_name!r} declares temporal averaging "
                f"{self.temporal_averaging!r} and tide_resolving="
                f"{self.tide_resolving!r}, so it cannot drive a tide-resolving "
                "scenario. Copernicus Marine distributes both hourly and "
                "daily / de-tided products [S09, S10]; a de-tided or daily-mean "
                "current field cannot stand in for a tidal reversal."
            )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["variable_names"] = list(self.variable_names)
        payload["provenance"] = self.provenance.value
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProductMetadata":
        data = dict(payload)
        data["variable_names"] = tuple(data.get("variable_names", ()))
        label = data.get("provenance", ProvenanceLabel.EXTERNAL_MODEL.value)
        try:
            data["provenance"] = ProvenanceLabel(label)
        except ValueError:
            raise GeodataModeRefused(
                f"cached product provenance {label!r} is not a ProvenanceLabel; "
                "every number needs a valid label"
            ) from None
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        unknown = set(data) - known
        if unknown:
            raise GeodataModeRefused(
                f"cached product metadata carries unknown field(s) "
                f"{sorted(unknown)}; the adapter refuses to guess what they mean"
            )
        return cls(**data)


@dataclass(frozen=True, slots=True)
class CachedProduct:
    """A cached current product: metadata plus the arrays it distributes."""

    metadata: ProductMetadata
    #: Longitude / easting coordinates of the product grid, ascending.
    x: np.ndarray
    #: Latitude / northing coordinates of the product grid, ascending.
    y: np.ndarray
    #: Eastward velocity, ``(ny_product, nx_product)`` in m s^-1.
    u_east_m_per_s: np.ndarray
    #: Northward velocity, same shape.
    v_north_m_per_s: np.ndarray

    def __post_init__(self) -> None:
        shape = (self.y.size, self.x.size)
        for label, array in (
            ("u_east_m_per_s", self.u_east_m_per_s),
            ("v_north_m_per_s", self.v_north_m_per_s),
        ):
            if array.shape != shape:
                raise GeodataModeRefused(
                    f"cached product {label} has shape {array.shape}, expected "
                    f"{shape} from its own coordinate arrays"
                )
            if not np.all(np.isfinite(array)):
                raise GeodataModeRefused(
                    f"cached product {label} contains non-finite values; a gap "
                    "is not a zero current and is refused rather than filled"
                )


def save_cached_product(product: CachedProduct, path: str | Path) -> Path:
    """Write a cached product to a self-contained JSON file.

    Deliberately plain JSON: it needs no optional dependency, it is diffable,
    and the metadata travels in the same file as the arrays so the two cannot
    drift apart.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "format": "reactive_seabed_mat.cached_current_product.v1",
        "metadata": product.metadata.to_dict(),
        "x": [float(v) for v in np.asarray(product.x).ravel()],
        "y": [float(v) for v in np.asarray(product.y).ravel()],
        "u_east_m_per_s": np.asarray(product.u_east_m_per_s, dtype=float).tolist(),
        "v_north_m_per_s": np.asarray(product.v_north_m_per_s, dtype=float).tolist(),
    }
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return target


def load_cached_product(path: str | Path) -> CachedProduct:
    """Read a cached product.  Never downloads, never guesses a missing field."""
    source = Path(path)
    if not source.is_file():
        raise CachedProductMissing(
            f"no cached product at {source}. Nothing is downloaded: place the "
            "file there by hand, with its metadata, or stay in 'synthetic' "
            "mode. " + OFFLINE_NOTE
        )
    payload = json.loads(source.read_text(encoding="utf-8"))
    fmt = payload.get("format")
    if fmt != "reactive_seabed_mat.cached_current_product.v1":
        raise GeodataModeRefused(
            f"cached product at {source} declares format {fmt!r}, which this "
            "adapter does not read. It refuses to guess the layout."
        )
    metadata = replace(
        ProductMetadata.from_dict(payload["metadata"]), cached_path=str(source)
    )
    return CachedProduct(
        metadata=metadata,
        x=np.asarray(payload["x"], dtype=float),
        y=np.asarray(payload["y"], dtype=float),
        u_east_m_per_s=np.asarray(payload["u_east_m_per_s"], dtype=float),
        v_north_m_per_s=np.asarray(payload["v_north_m_per_s"], dtype=float),
    )


def bathymetry_statement(usage: BathymetryUsage = BathymetryUsage.VISUAL_CONTEXT_ONLY) -> str:
    """State explicitly whether depth enters the numerical model."""
    if usage is not BathymetryUsage.VISUAL_CONTEXT_ONLY:  # pragma: no cover
        raise GeodataModeRefused(
            "this demonstrator has no depth-resolving flow solver, so no other "
            "bathymetry usage can be claimed"
        )
    return (
        "Bathymetry is visual context only. No depth raster feeds the flow "
        "solver: the model uses a prescribed effective mixing depth, and a "
        "bathymetric map does not itself generate currents. EMODnet Bathymetry "
        "[S11, S12] gives terrain context at its own supported resolution, and "
        "a rendered map service is not a numerical depth raster."
    )


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class _BaseAdapter:
    """Shared behaviour.  Every adapter is offline and says so."""

    mode: GeodataMode
    bathymetry_usage: BathymetryUsage = BathymetryUsage.VISUAL_CONTEXT_ONLY

    def fetch(self, *args: Any, **kwargs: Any) -> Any:
        """Always refuses.  No adapter in this repository opens a connection."""
        raise NetworkAccessRefused(
            f"the {self.mode.value!r} adapter does not fetch anything. "
            + OFFLINE_NOTE
        )

    def bathymetry_statement(self) -> str:
        return bathymetry_statement(self.bathymetry_usage)

    def resolution_statement(self, grid: GridSpec | None = None) -> str:  # pragma: no cover
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class SyntheticAdapter(_BaseAdapter):
    """The default: a prescribed synthetic current field, no geography at all."""

    mode: GeodataMode = GeodataMode.SYNTHETIC

    def resolution_statement(self, grid: GridSpec | None = None) -> str:
        text = SYNTHETIC_FORCING_NOTE
        if grid is not None:
            text += (
                f" Model grid: {grid.nx} by {grid.ny} cells of "
                f"{grid.dx_m:.0f} m by {grid.dy_m:.0f} m, effective mixing "
                f"depth {grid.mixing_depth_m:.1f} m, CRS {grid.crs}."
            )
        return text

    def forcing_at(
        self,
        cfg: ForcingConfig,
        grid: GridSpec,
        land_mask: np.ndarray,
        elapsed_s: float,
        start_utc: datetime,
    ) -> Forcing:
        """The prescribed synthetic field, unchanged."""
        return forcing_at(cfg, grid, land_mask, elapsed_s, start_utc)


@dataclass(frozen=True, slots=True)
class RealMapIllustrativeAdapter(_BaseAdapter):
    """A cached basemap for context.  The physics stay synthetic and labelled.

    ``basemap_path`` is checked for existence when the adapter is used, and
    nothing is downloaded if it is missing.  The adapter deliberately offers no
    way to turn a basemap into a current field.
    """

    mode: GeodataMode = GeodataMode.REAL_MAP_ILLUSTRATIVE
    basemap_path: str | None = None
    basemap_attribution: str | None = None

    def resolution_statement(self, grid: GridSpec | None = None) -> str:
        text = ILLUSTRATIVE_MAP_NOTE + " " + SYNTHETIC_FORCING_NOTE
        if self.basemap_attribution:
            text += f" Basemap attribution: {self.basemap_attribution}."
        if grid is not None:
            text += (
                f" Model grid: {grid.nx} by {grid.ny} cells of "
                f"{grid.dx_m:.0f} m by {grid.dy_m:.0f} m."
            )
        return text

    def basemap(self) -> Path:
        if not self.basemap_path:
            raise CachedProductMissing(
                "real_map_illustrative mode needs a cached basemap path. "
                + OFFLINE_NOTE
            )
        path = Path(self.basemap_path)
        if not path.is_file():
            raise CachedProductMissing(
                f"no cached basemap at {path}. " + OFFLINE_NOTE
            )
        return path

    def forcing_at(
        self,
        cfg: ForcingConfig,
        grid: GridSpec,
        land_mask: np.ndarray,
        elapsed_s: float,
        start_utc: datetime,
    ) -> Forcing:
        """The prescribed synthetic field, labelled as illustrative."""
        return forcing_at(
            cfg, grid, land_mask, elapsed_s, start_utc,
            extra_note=ILLUSTRATIVE_MAP_NOTE,
        )


@dataclass(frozen=True, slots=True)
class ImportedForcingAdapter(_BaseAdapter):
    """Currents from a cached external product, with its limits preserved."""

    mode: GeodataMode = GeodataMode.IMPORTED_FORCING
    cached_path: str | None = None

    def load(self) -> CachedProduct:
        if not self.cached_path:
            raise CachedProductMissing(
                "imported_forcing mode needs a cached product path. "
                + OFFLINE_NOTE
            )
        return load_cached_product(self.cached_path)

    def resolution_statement(self, grid: GridSpec | None = None) -> str:
        product = self.load()
        return (
            product.metadata.resolution_statement(grid)
            + " "
            + product.metadata.depth_statement()
            + " "
            + bathymetry_statement(self.bathymetry_usage)
        )

    def forcing_at(
        self,
        cfg: ForcingConfig,
        grid: GridSpec,
        land_mask: np.ndarray,
        elapsed_s: float,
        start_utc: datetime,
    ) -> Forcing:
        """Regrid the cached product onto the model grid.

        Refuses a non-tide-resolving product when ``cfg.kind == 'tidal'``.
        """
        product = self.load()
        if str(cfg.kind).lower() == "tidal":
            product.metadata.require_tide_resolving()
        return forcing_from_product(
            product, grid, land_mask, elapsed_s, start_utc,
            diffusivity_m2_per_s=float(cfg.diffusivity_m2_per_s),
        )


def forcing_from_product(
    product: CachedProduct,
    grid: GridSpec,
    land_mask: np.ndarray,
    elapsed_s: float,
    start_utc: datetime,
    *,
    diffusivity_m2_per_s: float,
) -> Forcing:
    """Build a :class:`Forcing` from a cached product, keeping its metadata.

    Regridding is nearest neighbour on purpose: a smoother interpolation would
    make the field *look* like it carries information at the model scale, and it
    does not.  The honest resolution statement travels in ``Forcing.notes``.

    ASSUMPTION: the product coordinates are already in the metric computation
    CRS of ``grid``.  A geographic product must be projected by the caller;
    this function does not silently reproject, because a wrong projection would
    be invisible in the output.
    """
    land_mask = np.asarray(land_mask, dtype=bool)
    if land_mask.shape != (grid.ny, grid.nx):
        raise ValueError(
            f"land_mask has shape {land_mask.shape}, expected {(grid.ny, grid.nx)}"
        )
    ix = np.arange(grid.nx)
    iy = np.arange(grid.ny)
    xc = grid.origin_x_m + (ix + 0.5) * grid.dx_m
    yc = grid.origin_y_m + (iy + 0.5) * grid.dy_m
    jx = np.abs(np.asarray(product.x)[None, :] - xc[:, None]).argmin(axis=1)
    jy = np.abs(np.asarray(product.y)[None, :] - yc[:, None]).argmin(axis=1)
    u = product.u_east_m_per_s[np.ix_(jy, jx)].astype(float).copy()
    v = product.v_north_m_per_s[np.ix_(jy, jx)].astype(float).copy()
    u[land_mask] = 0.0
    v[land_mask] = 0.0
    notes = (
        product.metadata.resolution_statement(grid)
        + " "
        + product.metadata.depth_statement()
        + " Nearest-neighbour regridding onto the model grid; no smoothing is "
        "applied, so nothing implies information below the native resolution."
    )
    return Forcing(
        time_utc=start_utc + timedelta(seconds=float(elapsed_s)),
        u_east_m_per_s=u,
        v_north_m_per_s=v,
        diffusivity_m2_per_s=float(diffusivity_m2_per_s),
        provenance=product.metadata.provenance,
        product_ref=(
            f"{product.metadata.product_name}"
            + (f"@{product.metadata.product_version}"
               if product.metadata.product_version else "")
        ),
        temporal_averaging=product.metadata.temporal_averaging,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Mode selection
# ---------------------------------------------------------------------------

def resolve_mode(mode: str | GeodataMode) -> GeodataMode:
    """Turn a configuration string into a mode.  Unknown modes are refused."""
    if isinstance(mode, GeodataMode):
        return mode
    try:
        return GeodataMode(str(mode))
    except ValueError:
        raise GeodataModeRefused(
            f"unknown geodata mode {mode!r}; the three explicit modes are "
            f"{[m.value for m in GeodataMode]}. There is no default promotion "
            "between them."
        ) from None


def adapter_for(
    domain: DomainConfig,
    *,
    cached_path: str | None = None,
    basemap_path: str | None = None,
    basemap_attribution: str | None = None,
) -> _BaseAdapter:
    """The adapter named by ``DomainConfig.mode``.  Never promoted silently."""
    mode = resolve_mode(domain.mode)
    if mode is GeodataMode.SYNTHETIC:
        return SyntheticAdapter()
    if mode is GeodataMode.REAL_MAP_ILLUSTRATIVE:
        return RealMapIllustrativeAdapter(
            basemap_path=basemap_path,
            basemap_attribution=basemap_attribution,
        )
    if cached_path is None:
        raise CachedProductMissing(
            "imported_forcing mode needs an explicit cached product path; it "
            "is never inferred, and nothing is downloaded. " + OFFLINE_NOTE
        )
    return ImportedForcingAdapter(cached_path=cached_path)
