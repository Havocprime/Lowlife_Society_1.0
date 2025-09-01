from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


from .range import Range
from .resolver import Actor, Action, attack


@dataclass(slots=True)
class TurnLog:
actor: str
action: Action
distance: Range
detail: str


@dataclass(slots=True)
class DuelState:
a: Actor
b: Actor
distance: Range = Range.MID
over: bool = False
winner: Optional[str] = None
log: list[TurnLog] | None = None


def __post_init__(self):
if self.log is None:
self.log = []




def apply_action(state: DuelState, actor: Actor, action: Action) -> None:
# very simple placeholder movement rules
if action == "advance":
if state.distance > Range.CLOSE:
state.distance = Range(state.distance - 1)
state.log.append(TurnLog(actor=actor.name, action=action, distance=state.distance, detail="steps in"))
elif action == "retreat":
if state.distance < Range.OUT:
state.distance = Range(state.distance + 1)
state.log.append(TurnLog(actor=actor.name, action=action, distance=state.distance, detail="steps back"))
elif action == "wait":
state.log.append(TurnLog(actor=actor.name, action=action, distance=state.distance, detail="holds"))
elif action == "attack":
opponent = state.b if actor is state.a else state.a
res = attack(actor, opponent, state.distance)
if res.hit:
opponent.hp -= res.dmg
detail = f"hits for {res.dmg} (roll {res.roll} vs DC {res.dc})"
if opponent.hp <= 0:
state.over = True
state.winner = actor.name
else:
detail = f"miss (roll {res.roll} vs DC {res.dc})"
state.log.append(TurnLog(actor=actor.name, action=action, distance=state.distance, detail=detail))




def simulate(a: Actor, b: Actor, a_actions: list[Action], b_actions: list[Action]) -> DuelState:
state = DuelState(a=a, b=b)
for i in range(max(len(a_actions), len(b_actions))):
if state.over:
break
if i < len(a_actions):
apply_action(state, state.a, a_actions[i])
if state.over:
break
if i < len(b_actions):
apply_action(state, state.b, b_actions[i])
if state.a.hp <= 0 or state.b.hp <= 0:
state.over = True
state.winner = state.a.name if state.a.hp > 0 else state.b.name
break
return state