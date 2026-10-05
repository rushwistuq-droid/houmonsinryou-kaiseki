"""在宅支援診療所・在宅支援病院の精密集計と居宅患者目標計算."""

from .acquisition import AcquisitionIndicator, compute_acquisition_indicator
from .catchment import CatchmentPoint, aggregate_catchment_supply, compute_regional_supply
from .demand import DemandEstimate, estimate_demand_for_catchment
from .facilities import count_facilities_in_radius, load_facility_points
from .targets import (
    HomePatientTargetResult,
    SupplySnapshot,
    compute_home_patient_targets,
)

__all__ = [
    "AcquisitionIndicator",
    "HomePatientTargetResult",
    "SupplySnapshot",
    "CatchmentPoint",
    "DemandEstimate",
    "compute_acquisition_indicator",
    "compute_home_patient_targets",
    "compute_regional_supply",
    "aggregate_catchment_supply",
    "estimate_demand_for_catchment",
    "count_facilities_in_radius",
    "load_facility_points",
]

__version__ = "0.5.0"
