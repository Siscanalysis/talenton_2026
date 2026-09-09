"""Release cases must remain visible in plots as well as in numeric exports."""
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np

from reactive_seabed_mat.contracts import FieldState, GridSpec
from reactive_seabed_mat.visualization.maps import attenuation_timeline, risk_ratio_map


def test_attenuation_axis_includes_negative_release_values():
    timeline = [SimpleNamespace(elapsed_years=year, attenuation={"Pb": value})
                for year, value in enumerate((0.9, -0.4, 0.2))]
    figure = attenuation_timeline(timeline, ("Pb",))
    assert figure.layout.yaxis.range[0] < -0.4
    assert figure.layout.yaxis.range[1] > 0.9
    assert tuple(figure.data[0].y) == (0.9, -0.4, 0.2)


def test_plume_ratio_colours_include_concentration_above_untreated_case():
    grid = GridSpec(nx=2, ny=1, dx_m=1.0, dy_m=1.0, mixing_depth_m=1.0)
    when = datetime(2026, 1, 1, tzinfo=timezone.utc)
    untreated = FieldState(grid=grid, time_utc=when,
                          concentration_kg_per_m3={"Pb": np.array([[1.0, 1.0]])},
                          land_mask=np.zeros((1, 2), dtype=bool))
    treated = untreated.with_concentration({"Pb": np.array([[0.5, 2.4]])})
    figure = risk_ratio_map(grid, treated, untreated, "Pb")
    assert figure.data[0].zmax >= 2.4
    assert figure.data[0].zmin <= 0.5
    np.testing.assert_allclose(figure.data[0].z, [[0.5, 2.4]])
