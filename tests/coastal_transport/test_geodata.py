"""Geodata adapters: three explicit modes, offline, and honest about limits."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from reactive_seabed_mat.config import DomainConfig, ForcingConfig, default_run_config
from reactive_seabed_mat.contracts import ProvenanceLabel
from reactive_seabed_mat.coastal_transport.domain import (
    TidalForcingRefused,
    build_grid,
    build_land_mask,
)
from reactive_seabed_mat.coastal_transport.geodata import (
    BathymetryUsage,
    CachedProduct,
    CachedProductMissing,
    GeodataMode,
    GeodataModeRefused,
    ImportedForcingAdapter,
    NetworkAccessRefused,
    ProductMetadata,
    RealMapIllustrativeAdapter,
    SyntheticAdapter,
    adapter_for,
    bathymetry_statement,
    load_cached_product,
    resolve_mode,
    save_cached_product,
)


def hourly_metadata(**overrides) -> ProductMetadata:
    """An hourly instantaneous product.  The name is a placeholder, not a claim
    that any particular vendor product was obtained or tested."""
    base = dict(
        product_name="PLACEHOLDER_HOURLY_CURRENTS",
        product_version="0.0-placeholder",
        variable_names=("uo", "vo"),
        time_coverage_start_utc="2026-09-08T00:00:00Z",
        time_coverage_end_utc="2026-09-09T00:00:00Z",
        depth_m=0.5,
        depth_datum="sea surface",
        native_resolution_deg=0.027,
        native_resolution_m=2800.0,
        temporal_averaging="hourly_instantaneous",
        tide_resolving=True,
        licence="unknown, must be checked per product",
        citation="placeholder; no product has been downloaded for this test",
        provenance=ProvenanceLabel.EXTERNAL_MODEL,
    )
    base.update(overrides)
    return ProductMetadata(**base)


def make_product(metadata: ProductMetadata, u: float = 0.07, v: float = -0.02):
    x = np.array([0.0, 300.0, 600.0])
    y = np.array([0.0, 200.0, 400.0])
    return CachedProduct(
        metadata=metadata,
        x=x,
        y=y,
        u_east_m_per_s=np.full((y.size, x.size), u),
        v_north_m_per_s=np.full((y.size, x.size), v),
    )


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def test_the_default_configuration_selects_the_synthetic_adapter():
    config = default_run_config()
    adapter = adapter_for(config.domain)
    assert isinstance(adapter, SyntheticAdapter)
    assert adapter.mode is GeodataMode.SYNTHETIC


def test_an_unknown_mode_is_refused_and_nothing_is_promoted():
    with pytest.raises(GeodataModeRefused, match="unknown geodata mode"):
        resolve_mode("copernicus")
    with pytest.raises(GeodataModeRefused):
        adapter_for(DomainConfig(mode="whatever_looks_best"))


def test_imported_forcing_without_a_cached_path_is_refused():
    with pytest.raises(CachedProductMissing, match="never inferred"):
        adapter_for(DomainConfig(mode="imported_forcing"))


def test_real_map_mode_keeps_the_physics_illustrative():
    adapter = adapter_for(DomainConfig(mode="real_map_illustrative"),
                          basemap_attribution="placeholder attribution")
    assert isinstance(adapter, RealMapIllustrativeAdapter)
    statement = adapter.resolution_statement()
    assert "Illustrative map mode" in statement
    assert "not a statement about any real location" in statement
    with pytest.raises(CachedProductMissing):
        adapter.basemap()


# ---------------------------------------------------------------------------
# Offline
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "adapter",
    [SyntheticAdapter(), RealMapIllustrativeAdapter(), ImportedForcingAdapter()],
)
def test_no_adapter_ever_fetches_anything(adapter):
    with pytest.raises(NetworkAccessRefused, match="does not fetch"):
        adapter.fetch("https://example.invalid/currents")


def test_a_missing_cached_file_is_reported_not_downloaded(tmp_path):
    adapter = ImportedForcingAdapter(cached_path=str(tmp_path / "absent.json"))
    with pytest.raises(CachedProductMissing, match="Nothing is downloaded"):
        adapter.load()


def test_no_module_in_the_package_imports_a_network_client():
    """A blunt static guard: the coastal package must not import urllib,
    requests, http.client, socket or ftplib anywhere."""
    import pathlib

    import reactive_seabed_mat.coastal_transport as package

    root = pathlib.Path(package.__file__).parent
    forbidden = ("import requests", "import urllib", "from urllib",
                 "import http.client", "import socket", "import ftplib",
                 "urlopen(", "requests.get(")
    offenders = []
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for needle in forbidden:
            if needle in text:
                offenders.append(f"{path.name}: {needle}")
    assert offenders == []


# ---------------------------------------------------------------------------
# Cached products
# ---------------------------------------------------------------------------

def test_a_cached_product_round_trips_with_its_metadata(tmp_path):
    product = make_product(hourly_metadata())
    path = save_cached_product(product, tmp_path / "currents.json")
    loaded = load_cached_product(path)
    assert loaded.metadata.product_name == product.metadata.product_name
    assert loaded.metadata.product_version == product.metadata.product_version
    assert loaded.metadata.temporal_averaging == "hourly_instantaneous"
    assert loaded.metadata.depth_m == 0.5
    assert loaded.metadata.native_resolution_deg == 0.027
    assert loaded.metadata.cached_path == str(path)
    assert np.array_equal(loaded.u_east_m_per_s, product.u_east_m_per_s)


def test_an_unknown_cached_format_is_refused(tmp_path):
    path = tmp_path / "odd.json"
    path.write_text('{"format": "something_else"}', encoding="utf-8")
    with pytest.raises(GeodataModeRefused, match="refuses to guess"):
        load_cached_product(path)


def test_unknown_metadata_fields_are_refused(tmp_path):
    product = make_product(hourly_metadata())
    path = save_cached_product(product, tmp_path / "currents.json")
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["metadata"]["confidence"] = "high"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(GeodataModeRefused, match="unknown field"):
        load_cached_product(path)


def test_a_gap_in_the_product_is_refused_rather_than_filled():
    metadata = hourly_metadata()
    x = np.array([0.0, 300.0])
    y = np.array([0.0, 200.0])
    u = np.array([[0.1, np.nan], [0.1, 0.1]])
    with pytest.raises(GeodataModeRefused, match="non-finite"):
        CachedProduct(metadata=metadata, x=x, y=y, u_east_m_per_s=u,
                      v_north_m_per_s=np.zeros((2, 2)))


# ---------------------------------------------------------------------------
# The refusals that matter
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("averaging", ["daily_mean", "de_tided", "monthly_mean"])
def test_a_de_tided_product_is_refused_for_a_tide_resolving_scenario(tmp_path, averaging):
    product = make_product(hourly_metadata(temporal_averaging=averaging,
                                           tide_resolving=False))
    path = save_cached_product(product, tmp_path / "daily.json")
    adapter = ImportedForcingAdapter(cached_path=str(path))
    config = default_run_config()
    grid = build_grid(config.domain)
    land = build_land_mask(config.domain, grid)
    tidal = ForcingConfig(kind="tidal")
    with pytest.raises(TidalForcingRefused, match="cannot stand in for a tidal"):
        adapter.forcing_at(tidal, grid, land, 0.0, config.start_datetime)
    # the same product is acceptable for a steady scenario, with its limits stated
    steady = adapter.forcing_at(ForcingConfig(kind="steady"), grid, land, 0.0,
                                config.start_datetime)
    assert "not declared tide resolving" in steady.notes


def test_a_product_that_does_not_declare_tide_resolution_is_refused(tmp_path):
    product = make_product(hourly_metadata(tide_resolving=None))
    path = save_cached_product(product, tmp_path / "unknown.json")
    with pytest.raises(TidalForcingRefused):
        load_cached_product(path).metadata.require_tide_resolving()


def test_the_resolution_statement_is_honest_about_interpolation(tmp_path):
    product = make_product(hourly_metadata())
    path = save_cached_product(product, tmp_path / "currents.json")
    config = default_run_config()
    grid = build_grid(config.domain)
    statement = ImportedForcingAdapter(cached_path=str(path)).resolution_statement(grid)
    assert "0.027 deg" in statement
    assert "does not create information" in statement
    assert "10 m by 10 m" in statement
    assert "Surface currents are not automatically near-bed currents" in statement


def test_an_undeclared_depth_is_reported_as_undeclared():
    metadata = hourly_metadata(depth_m=None, depth_datum=None)
    assert "not declared" in metadata.depth_statement()


def test_bathymetry_never_claims_to_feed_the_flow_solver():
    statement = bathymetry_statement()
    assert "visual context only" in statement
    assert "does not itself generate currents" in statement
    assert list(BathymetryUsage) == [BathymetryUsage.VISUAL_CONTEXT_ONLY]
    assert bathymetry_statement() in SyntheticAdapter().bathymetry_statement()


# ---------------------------------------------------------------------------
# Imported forcing on the model grid
# ---------------------------------------------------------------------------

def test_imported_forcing_lands_on_the_model_grid_with_its_metadata(tmp_path):
    product = make_product(hourly_metadata(), u=0.07, v=-0.02)
    path = save_cached_product(product, tmp_path / "currents.json")
    config = default_run_config()
    grid = build_grid(config.domain)
    land = build_land_mask(config.domain, grid)
    adapter = ImportedForcingAdapter(cached_path=str(path))
    forcing = adapter.forcing_at(ForcingConfig(kind="steady"), grid, land, 0.0,
                                 config.start_datetime)
    assert forcing.u_east_m_per_s.shape == (grid.ny, grid.nx)
    assert forcing.provenance is ProvenanceLabel.EXTERNAL_MODEL
    assert forcing.product_ref == "PLACEHOLDER_HOURLY_CURRENTS@0.0-placeholder"
    assert forcing.temporal_averaging == "hourly_instantaneous"
    assert float(forcing.u_east_m_per_s[land].sum()) == 0.0
    assert forcing.u_east_m_per_s[~land][0] == pytest.approx(0.07)
    assert "Nearest-neighbour regridding" in forcing.notes


def test_the_synthetic_adapter_reproduces_the_prescribed_field():
    config = default_run_config()
    grid = build_grid(config.domain)
    land = build_land_mask(config.domain, grid)
    adapter = SyntheticAdapter()
    forcing = adapter.forcing_at(config.forcing, grid, land, 1000.0,
                                 config.start_datetime)
    from reactive_seabed_mat.coastal_transport.domain import forcing_at

    direct = forcing_at(config.forcing, grid, land, 1000.0, config.start_datetime)
    assert np.array_equal(forcing.u_east_m_per_s, direct.u_east_m_per_s)
    assert forcing.provenance is ProvenanceLabel.SYNTHETIC_DEMO


def test_the_illustrative_adapter_labels_every_field_it_produces():
    config = replace(default_run_config().domain, mode="real_map_illustrative")
    grid = build_grid(config)
    land = build_land_mask(config, grid)
    adapter = adapter_for(config)
    forcing = adapter.forcing_at(ForcingConfig(), grid, land, 0.0,
                                 default_run_config().start_datetime)
    assert "Illustrative map mode" in forcing.notes
    assert forcing.provenance is ProvenanceLabel.SYNTHETIC_DEMO
