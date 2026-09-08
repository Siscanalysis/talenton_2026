"""Observation ingestion, validation, synthesis, quality control and replay.

Import order matters here and is deliberate: ``records`` is coordinator-owned
and depends on nothing in this package; ``generator`` supplies the record
primitives; ``condition`` builds the mat-condition channels on top of them;
``qc`` needs the controlled damage vocabulary; ``operator`` needs both.
``generator`` imports ``condition`` lazily, inside
:meth:`ObservationGenerator.generate`, so the composition does not become a
circular import.
"""

from __future__ import annotations

from .records import (  # noqa: F401
    ObservationValidationError,
    observations_available,
    read_jsonl,
    record_from_dict,
    record_to_dict,
    validate_record_dict,
    write_jsonl,
)
from .generator import (  # noqa: F401
    GeneratorAssumptions,
    MatHistorySpec,
    MatStateSample,
    MediaBatch,
    MediaReplacement,
    ObservationGenerator,
    ScriptedScene,
    constant_mat_scene,
    scene_from_layer_history,
    synthetic_mat_history,
)
from .condition import (  # noqa: F401
    DAMAGE_CLASS_INTEGRITY_BAND,
    MAT_DAMAGE_CLASSES,
    ConditionAssumptions,
    MatConditionGenerator,
)
from .qc import (  # noqa: F401
    DEMO_THRESHOLDS,
    AssetHealth,
    QCOutcome,
    QCReport,
    QCThresholds,
    apply_qc_flags,
    run_qc,
)
from .operator import (  # noqa: F401
    AssimilationDecision,
    AssimilationSet,
    ModelQuantity,
    ObservationUse,
    OperatorConfig,
    build_assimilation_set,
    classify_record,
)
