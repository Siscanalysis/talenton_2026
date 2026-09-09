"""One monitoring experiment must not depend on the controller's call cadence."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from reactive_seabed_mat.config import ObservationConfig
from reactive_seabed_mat.contracts import AcquisitionKind, Matrix, Parameter, Qualifier
from reactive_seabed_mat.observations.generator import ObservationGenerator, constant_mat_scene

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
DAY = 86400.0


def _config():
    return ObservationConfig(porewater_sample_period_s=9 * DAY,
        bottom_water_probe_period_s=5 * DAY, chamber_deployment_period_s=11 * DAY,
        dgt_deployment_period_s=13 * DAY, dgt_exposure_s=4 * DAY,
        survey_period_s=15 * DAY, lab_latency_s=7 * DAY,
        sensor_dropout_window_s=(18 * DAY, 29 * DAY), missing_probability=0.0)


def test_window_partition_preserves_every_reading_and_deployment():
    config = _config()
    scene = constant_mat_scene(START, 40 * DAY)
    full = ObservationGenerator(config, seed=123, start_utc=START).generate_window(
        scene, 0, 40 * DAY, include_environmental=False)
    generator = ObservationGenerator(config, seed=123, start_utc=START)
    partitioned = []
    for begin, end in ((0, 10), (10, 28), (28, 40)):
        partitioned.extend(generator.generate_window(scene, begin * DAY, end * DAY, include_environmental=False))
    assert len({record.record_id for record in partitioned}) == len(partitioned)
    assert {record.record_id: record for record in partitioned} == {record.record_id: record for record in full}
    assert any(record.sampling_start_utc is not None
               and record.sampling_start_utc < START + timedelta(days=28) < record.observed_at_utc
               for record in full)


def test_dropout_changes_only_the_sensor_readings_in_its_global_time_window():
    config = _config()
    scene = constant_mat_scene(START, 40 * DAY)
    generators = [ObservationGenerator(choice, seed=77, start_utc=START)
                  for choice in (config, replace(config, sensor_dropout_window_s=None))]
    streams = [generator.generate_window(scene, 15 * DAY, 40 * DAY, include_environmental=False)
               for generator in generators]
    laboratory = [{record.record_id: record for record in stream
                   if record.acquisition_kind in (AcquisitionKind.GRAB_SAMPLE, AcquisitionKind.BENTHIC_CHAMBER)}
                  for stream in streams]
    assert laboratory[0] == laboratory[1]
    affected = [record for record in streams[0] if record.matrix is Matrix.BOTTOM_WATER
                and record.acquisition_kind is AcquisitionKind.IN_SITU_SENSOR
                and START + timedelta(days=18) <= record.observed_at_utc <= START + timedelta(days=29)]
    assert affected and all(record.qualifier is Qualifier.MISSING for record in affected)


def test_record_completion_and_availability_are_separate_clocks():
    from reactive_seabed_mat.observations.records import observations_available
    scene = constant_mat_scene(START, 10 * DAY)
    records = ObservationGenerator(_config(), seed=1, start_utc=START).generate_window(
        scene, 0, 10 * DAY, include_environmental=False)
    sampled = [record for record in records if record.observed_at_utc == START + timedelta(days=9)
               and record.parameter is Parameter.PB and record.matrix is Matrix.POREWATER]
    assert sampled
    assert not list(observations_available(sampled, START + timedelta(days=10)))
    assert list(observations_available(sampled, START + timedelta(days=16))) == sampled
