"""
FishMindOS Skills - Built-in Skills
"""

# Navigation skills
from fishmindos.skills.builtin.navigation import (
    StartNavigationSkill,
    StopNavigationSkill,
    GoToWaypointSkill,
    GoToLocationSkill,
    GetNavigationStatusSkill,
    ListMapsSkill,
    ListWaypointsSkill,
)

# Motion skills
from fishmindos.skills.builtin.motion import (
    MotionStandSkill,
    MotionLieDownSkill,
    MotionApplyPresetSkill,
)

# Audio skills
from fishmindos.skills.builtin.audio import (
    PlayAudioSkill,
    TTSSkill,
)

# Light skills
from fishmindos.skills.builtin.lights import (
    SetLightSkill,
    TurnOnLightSkill,
    TurnOffLightSkill,
)

# System skills
from fishmindos.skills.builtin.system import (
    GetBatterySkill,
    GetStatusSkill,
    GetChargingStatusSkill,
    GetPoseSkill,
    WaitEventSkill,
)
from fishmindos.skills.builtin.mission import (
    SubmitMissionSkill,
)

__all__ = [
    "StartNavigationSkill",
    "StopNavigationSkill",
    "GoToWaypointSkill",
    "GoToLocationSkill",
    "GetNavigationStatusSkill",
    "ListMapsSkill",
    "ListWaypointsSkill",
    "MotionStandSkill",
    "MotionLieDownSkill",
    "MotionApplyPresetSkill",
    "PlayAudioSkill",
    "TTSSkill",
    "SetLightSkill",
    "TurnOnLightSkill",
    "TurnOffLightSkill",
    "GetBatterySkill",
    "GetStatusSkill",
    "GetChargingStatusSkill",
    "GetPoseSkill",
    "WaitEventSkill",
    "SubmitMissionSkill",
]
