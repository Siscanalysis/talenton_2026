# Assumption register

Updated 9 September 2026 from the executable `default_run_config()`. The tables below record all resolved configuration values; scenario-specific overrides are recorded in each run configuration. Numeric material, site, monitoring and cost values are assumptions or synthetic demonstration settings, not measurements or supplier quotations. Numerical resolution is a computational choice, not a physical calibration.

The supplied papers are traced in [PAPER_PARAMETER_TRACEABILITY.md](PAPER_PARAMETER_TRACEABILITY.md). The review was already cited as background, but the extracted experimental numbers did not calibrate the default configuration. Published maxima, measured batch uptake and model operating capacity remain different quantities.

## Geometry and prescribed source

### Domain

| Configuration field | Resolved default |
|---|---|
| `nx` | `60` |
| `ny` | `40` |
| `dx_m` | `10.0` |
| `dy_m` | `10.0` |
| `mixing_depth_m` | `5.0` |
| `crs` | `LOCAL_METRIC` |
| `land_rectangles` | `[[0.0, 0.0, 600.0, 40.0]]` |
| `mode` | `synthetic` |

### Forcing

| Configuration field | Resolved default |
|---|---|
| `kind` | `tidal` |
| `u_mean_m_per_s` | `0.04` |
| `v_mean_m_per_s` | `0.0` |
| `tidal_amplitude_m_per_s` | `0.18` |
| `tidal_period_s` | `44712.0` |
| `tidal_phase_rad` | `0.0` |
| `diffusivity_m2_per_s` | `0.6` |
| `provenance` | `synthetic_demo` |
| `product_ref` | `None` |
| `temporal_averaging` | `instantaneous_synthetic` |

### Hotspot

| Configuration field | Resolved default |
|---|---|
| `hotspot_id` | `authorised_hotspot_1` |
| `x_m` | `260.0` |
| `y_m` | `180.0` |
| `width_m` | `80.0` |
| `length_m` | `80.0` |
| `film_transfer_m_per_s` | `5e-07` |
| `schedule` | `[{"start_s": 0.0, "porewater_kg_per_m3": {"Pb": 0.001, "Hg": 8e-06, "Cu": 0.002}, "seepage_velocity_m_per_s": 3e-08}]` |
| `label` | `synthetic_demo` |

The hotspot coordinates are its lower-left corner. The current tile builder uses the same convention. At full nominal coverage the nine tiles cover the 80 m by 80 m hotspot exactly. Source concentrations are total dissolved Pb, Hg and Cu; the prescribed reservoir does not deplete. No geography, porewater measurement or fitted source is loaded into these defaults.

## Reactive core

| Configuration field | Resolved default |
|---|---|
| `mat_id` | `mat_A` |
| `media_id` | `media_A0` |
| `tiles_x` | `3` |
| `tiles_y` | `3` |
| `coverage_fraction` | `1.0` |
| `thickness_m` | `0.01` |
| `bulk_density_kg_per_m3` | `400.0` |
| `porosity` | `0.5` |
| `overlap_m` | `0.1` |
| `edge_leakage_fraction` | `0.02` |
| `edge_leakage_interval` | `[0.005, 0.08]` |
| `n_layer_nodes` | `40` |
| `preload_kg_per_m2` | `{}` |

### Per-element medium parameters

Every entry below is an assumption. Prior ranges are screening ranges, not measured confidence intervals. Commissioning ranges are hypothetical information for a synthetic operator; they are not completed batch experiments. The Hg `None` records no commissioning information in this scenario, not the absence of keratin-derived Hg literature.

| Configuration field | Pb | Hg | Cu |
|---|---|---|---|
| `kd_m3_per_kg` | `3.0` | `30.0` | `8.0` |
| `kd_interval` | `[0.5, 20.0]` | `[2.0, 300.0]` | `[1.0, 60.0]` |
| `q_max_kg_per_kg` | `0.001` | `0.0025` | `0.003` |
| `q_max_interval` | `[0.0003, 0.008]` | `[0.0002, 0.025]` | `[0.0005, 0.02]` |
| `commissioned_q_max_interval` | `[0.00075, 0.0013]` | `None` | `[0.002, 0.0045]` |
| `k_rate_per_s` | `0.0004` | `0.0002` | `0.0005` |
| `k_rate_interval` | `[0.0001, 0.0012]` | `[3e-05, 0.0008]` | `[0.0001, 0.0015]` |
| `d_eff_m2_per_s` | `2e-10` | `2e-10` | `2.2e-10` |
| `d_eff_interval` | `[8e-11, 5e-10]` | `[8e-11, 5e-10]` | `[9e-11, 5.5e-10]` |
| `available_fraction` | `0.25` | `0.1` | `0.02` |
| `available_fraction_interval` | `[0.05, 0.6]` | `[0.01, 0.4]` | `[0.002, 0.15]` |
| `allocation_fraction` | `0.6` | `0.3` | `0.1` |
| `fouling_rate_capacity` | `0.0` | `0.0` | `0.0` |
| `fouling_rate_kinetics` | `0.8` | `0.8` | `0.8` |
| `fouling_rate_diffusivity` | `0.6` | `0.6` | `0.6` |

The `source_ref` notes point to [MATERIAL_KERATIN.md](MATERIAL_KERATIN.md): older Pb biofibres, the conditional Hg sulphur-site calculation, and older Cu nanofibre studies motivate these assumptions. The new treated-wool, composite and reduced-hair papers broaden the material-screening evidence without replacing the seawater defaults.

The runtime isotherm multiplies `kd_m3_per_kg` by availability and allocation. The column capacity is multiplied by allocation but not availability. This substitutes independent allocated compartments for explicit three-metal competition. Bulk density and porosity are independent effective inputs; their consistency must be measured for the finished composite.

### Derived nominal quantities

| Quantity | Pb | Hg | Cu |
|---|---:|---:|---:|
| Nominal capacity, kg/m^2 | 0.0024 | 0.003 | 0.0012 |
| Nominal capacity over 6400 m^2, kg | 15.36 | 19.2 | 7.68 |
| Apparent partition slope, m^3/kg | 0.75 | 3 | 0.16 |
| Column partition slope, m^3/kg | 0.45 | 0.9 | 0.016 |
| Bare-source flux against clean water, kg/m^2/s | 5.3e-10 | 4.24e-12 | 1.06e-09 |

Core loading is 4 kg/m^2 and total medium mass is 25,600 kg. Dividing nominal capacity by an assumed source flux is a capacity-to-load ratio, not a breakthrough or service-time prediction. Finite affinity can establish equilibrium before nominal capacity is filled. The historical approximately 3.09-year breakthrough belongs to a separate high-affinity numerical benchmark, not these defaults.

### Carrier geotextiles

The tile solver uses two inert carrier layers with standalone defaults: 0.003 m thickness each, porosity 0.55, molecular diffusivity 7e-10 m^2/s and hydraulic conductivity 1.5e-3 m/s. The effective diffusivity is `porosity**1.5 * molecular_diffusivity`; resistance is `thickness / (porosity * effective_diffusivity)`. These are assumed diffusive series resistances without storage nodes or resolved pressure-driven redistribution.

## Degradation

| Configuration field | Resolved default |
|---|---|
| `fouling_growth_per_s` | `5e-09` |
| `burial_growth_m_per_s` | `0.0` |
| `burial_resistance_s_per_m` | `200000000.0` |
| `fouling_bypass_coupling` | `0.35` |
| `events` | `[]` |

The burial-resistance coefficient has dimensional meaning s/m^2 because multiplying by burial depth gives a resistance in s/m. The legacy field name ends in `s_per_m`; values are not converted according to that suffix. Four mechanisms remain distinct: loading, fouling, displacement/burial and local damage. Continuous changes advance after each column step; scheduled events are resolved at their exact times.

## Synthetic observations

| Configuration field | Resolved default |
|---|---|
| `environmental_period_s` | `3600.0` |
| `bottom_water_probe_period_s` | `21600.0` |
| `porewater_sample_period_s` | `7776000.0` |
| `chamber_deployment_period_s` | `15552000.0` |
| `survey_period_s` | `15552000.0` |
| `dgt_deployment_period_s` | `15552000.0` |
| `dgt_exposure_s` | `259200.0` |
| `lab_latency_s` | `1814400.0` |
| `survey_latency_s` | `86400.0` |
| `probe_latency_s` | `0.0` |
| `probe_relative_noise` | `0.2` |
| `probe_lod_ng_per_l` | `12.0` |
| `probe_loq_ng_per_l` | `40.0` |
| `probe_range_top_ng_per_l` | `5000.0` |
| `lab_relative_noise` | `0.08` |
| `lab_lod_ng_per_l` | `1.5` |
| `lab_loq_ng_per_l` | `5.0` |
| `chamber_relative_noise` | `0.35` |
| `chamber_lod_ug_per_m2_per_d` | `0.05` |
| `chamber_loq_ug_per_m2_per_d` | `0.2` |
| `environmental_relative_noise` | `0.02` |
| `missing_probability` | `0.03` |
| `sensor_dropout_window_s` | `None` |
| `sensor_drift_start_s` | `None` |
| `sensor_drift_per_s` | `0.0` |

### Stations

| ID | x, y (m) | Kind | Depth (m) | Datum | Tile |
|---|---|---|---:|---|---|
| ST_MAT_A | 280.0, 200.0 | bottom_water_probe | 0.3 | seabed | tile_0_0 |
| ST_MAT_B | 300.0, 220.0 | porewater | 0.01 | mat_base | tile_1_1 |
| ST_MAT_C | 320.0, 240.0 | chamber | 0.0 | mat_top | tile_2_2 |
| ST_ENV | 300.0, 260.0 | environmental | 1.0 | seabed | None |
| SURVEY_01 | 300.0, 220.0 | survey | 0.0 | mat_top | None |

Campaign schedules use one global run clock. A 30-day decision window does not restart a 90-day porewater or 180-day chamber/survey schedule. Completed observations enter decisions only after their availability times, QC and analytical-fraction checks. Pb and Hg have default chemical observation channels; Cu is simulated physically but remains unmonitored. Environmental records are omitted from the normal coupled maintenance export.

Further channel-specific defaults, such as DGT uptake, chamber area, survey noise and condition vocabularies, live in the observation generator and QC classes and are documented in the manuscript monitoring section. None is an instrument specification.

## Maintenance policy

The interval estimator has additional standalone assumption coefficients:

| Estimation convention | Default |
|---|---|
| Seepage multiplier interval | [0.4, 2.5] |
| Staleness widening per year | 0.35 |
| Extra cross-tile widening | 0.50 |
| Interval-level metadata | 0.90; no calibrated confidence coverage |
| Missing chemical uncertainty | Assumed relative standard deviation 0.50 |
| Numeric condition resolution | Reported uncertainty required; two standard deviations |
| Minimum trend records | 3; reserved, not enforced by the present estimator |
| Indistinguishability margin | 0.15; reserved, not used in present attribution |

Above-range chemical observations retain an unbounded upper endpoint. The
configured media capacity bounds inferred stored loading; it does not convert
an above-range observation into a finite concentration measurement.

| Configuration field | Resolved default |
|---|---|
| `kind` | `evidence_informed` |
| `fixed_interval_s` | `63115200.0` |
| `decision_period_s` | `2592000.0` |
| `saturation_decision_bound` | `mid` |
| `replacement_saturation_threshold` | `0.8` |
| `inspection_saturation_threshold` | `0.55` |
| `minimum_acceptable_attenuation` | `0.7` |
| `max_relative_interval_width` | `1.2` |
| `max_data_age_s` | `17280000.0` |
| `min_evidence_records` | `3` |
| `minimum_coverage_fraction` | `0.9` |
| `allow_partial_replacement` | `True` |

The midpoint/lower/upper saturation choice is a decision posture, not a measured risk probability. All required monitored-element porewater and chamber channels must meet the age test; a fresh physical survey cannot refresh stale chemistry. Physical failure can prompt replacement independently of chemistry when supported by recent condition evidence. The maximum-relative-width and partial-replacement switches remain reserved configuration fields and do not alter the current policy. The estimator reports interval level 0.9 as metadata; these deterministic bounds have no demonstrated statistical coverage.

## Costs

| Configuration field | Resolved default |
|---|---|
| `mat_material_eur_per_m2` | `240.0` |
| `deployment_vessel_day_eur` | `6500.0` |
| `rov_survey_eur` | `4200.0` |
| `benthic_chamber_deployment_eur` | `2800.0` |
| `porewater_sample_eur` | `180.0` |
| `lab_hg_sample_eur` | `210.0` |
| `dgt_deployment_eur` | `260.0` |
| `tile_replacement_eur` | `1900.0` |
| `used_media_handling_eur_per_kg` | `12.0` |
| `sensor_check_eur` | `350.0` |
| `provenance` | `assumption` |

Every euro value is an assumption. Recorded servicing expenditure concerns accepted simulated replacement operations, not complete installation, permitting, monitoring or lifecycle cost. No monetary benefit for recovered metal or avoided contamination is assigned.

## Time, solver and reproducibility

| Configuration field | Resolved default |
|---|---|
| `window_s` | `86400.0` |
| `dt_s` | `600.0` |
| `sample_years` | `[0.0, 3.0]` |

| Configuration field | Resolved default |
|---|---|
| `run_id` | `demo` |
| `scenario` | `fresh_mat` |
| `seed` | `20260908` |
| `start_utc` | `2026-09-08T00:00:00Z` |
| `duration_s` | `189345600.0` |
| `dt_s` | `21600.0` |
| `elements` | `["Pb", "Hg", "Cu"]` |
| `transport_engine` | `fipy` |
| `layer_engine` | `scipy_banded_implicit` |
| `ensemble_size` | `64` |
| `notes` | `` |
| `config_version` | `0.2.0` |

One model year is 365.25 days. The timeline integrates exactly from zero to its configured duration, splits steps at source changes, events and decisions, and evaluates its zero-time output without advancing the initial state. Plume windows use the stored state at an in-horizon age without an extra reaction step; requested ages beyond the run duration are omitted and the actual final age is included.

The long column timeline and short coastal windows have separate control volumes. Whole-hotspot emission mixes column residual flux with uncovered, damaged and bypass contributions. Retained and retrieved inventories belong to the full-footprint column budget. The area-mixed emission diagnostic is not presented as a single globally coupled sediment/mat/water conservation law.

No simulated attenuation or nominal inventory establishes a field service life. The comparison against a non-sorbing barrier uses the same discrete flux equations; high attenuation can arise from physical resistance even when net sorption is small.
