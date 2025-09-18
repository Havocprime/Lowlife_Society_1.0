# GAME/src/tags/curves.py
from __future__ import annotations
from typing import Dict


# Global severity curves. Edit here to rebalance.
# Convention: severity 1..10 mapped to multipliers or flat values.


BLEED_DOT_PER_TICK = { # hp per tick @ sev
1: 0.0, 2: 0.5, 3: 0.5, 4: 1.0, 5: 1.0,
6: 1.5, 7: 1.5, 8: 2.0, 9: 2.5, 10: 3.0,
}


BRUISE_MOVE_ACCURACY = { # negative mod per severity (sum)
1: -0.005, 2: -0.010, 3: -0.015, 4: -0.020, 5: -0.030,
6: -0.040, 7: -0.050, 8: -0.060, 9: -0.075, 10: -0.100,
}


FRACTURE_AGI_MULT = { # multiplier at given severity
4: 0.95, 5: 0.90, 6: 0.88, 7: 0.85, 8: 0.82, 9: 0.80, 10: 0.75,
}


DEFAULT_TIMESCALE_CLAMP = (0.7, 1.3)