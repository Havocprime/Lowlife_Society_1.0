from __future__ import annotations
from enum import IntEnum


class Range(IntEnum):
CLOSE = 0
NEAR = 1
MID = 2
FAR = 3
OUT = 4 # out-of-range


# movement cost to move one step between ranges
MOVE_COST = {
(Range.CLOSE, Range.NEAR): 1,
(Range.NEAR, Range.MID): 1,
(Range.MID, Range.FAR): 1,
}


# basic hit modifiers by current distance bucket (placeholder numbers)
HIT_MOD = {
Range.CLOSE: +15,
Range.NEAR: +10,
Range.MID: 0,
Range.FAR: -10,
Range.OUT: -99, # cannot hit
}