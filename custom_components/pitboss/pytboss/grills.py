"""Routines for accessing grill metadata."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from typing import Any, TypedDict

from dukpy import evaljs

from .exceptions import InvalidGrill

_LOGGER = logging.getLogger(__name__)


@cache
def _get_grills() -> dict[str, Any]:
    return json.loads(resources.files(__package__).joinpath("grills.json").read_text())


UNSUPPORTED_MODELS = (
    "PBX - test 1",
    "LG0800BL",
    "LG1000BL",
    "LG1200BL",
    "LG1200FL",
    "LG1200FP",
    "LG300BL",
    "LG800FL",
    "LG800FP",
    "LGV4BL",
    "PBV30DS",
    "PBV30DX",
)

_COMMAND_JS_TMPL = """\
function command() {
    var formatHex = function(n) {
        var t = '0' + parseInt(n).toString(16);
        return t.substring(t.length - 2)
    };
    var formatDecimal = function(n) {
        var t = '000' + parseInt(n).toString(10);
        return t.substring(t.length - 3);
    };
    %s
}
command.apply(null, dukpy['args']);
"""

_CONTROLLER_JS_TMPL = """\
function parse(message) {
    var convertTemperature = function(parts, startIndex) {
        var temp = (
            parts[startIndex] * 100 +
            parts[startIndex + 1] * 10 +
            parts[startIndex + 2]
        );
        return temp === 960 ? null : temp;
    };
    var parseHexMessage = function(data) {
        var parsed = [];
        for (var i = 0; i < data.length; i+=2) {
            parsed.push(parseInt(data.substring(i, i+2), 16));
        }
        return parsed;
    };
    %s
}
parse(dukpy['message']);
"""

_FN_RE = re.compile(r"(.+ ?= ?)(\(.[^\)]+\))( ?=>)?(.+)")


def _scrub_js(s: str | None) -> str | None:
    if s is None:
        return s
    s = _FN_RE.sub(r"\1 function \2\4", s)
    s = s.replace("let ", "var ")
    s = s.replace("const ", "var ")
    return s


class StateDict(TypedDict, total=False):
    """State of the grill."""

    p1Target: int
    p2Target: int | None
    p1Temp: int | None
    p2Temp: int | None
    p3Temp: int
    p4Temp: int
    smokerActTemp: int
    grillSetTemp: int
    grillTemp: int
    moduleIsOn: bool
    err1: bool
    err2: bool
    err3: bool
    highTempErr: bool
    fanErr: bool
    hotErr: bool
    motorErr: bool
    noPellets: bool
    erL: bool
    fanState: bool
    hotState: bool
    motorState: bool
    lightState: bool
    primeState: bool
    isFahrenheit: bool
    recipeStep: bool
    recipeTime: int


@dataclass
class Command:
    """A control board command."""

    name: str
    slug: str
    _hex: str | None
    _js_func: str | None

    @classmethod
    def from_dict(cls, cmd_dict) -> Command:
        js_func = _scrub_js(cmd_dict["function"])
        return cls(
            name=cmd_dict["name"],
            slug=cmd_dict["slug"],
            _hex=cmd_dict["hexadecimal"],
            _js_func=js_func,
        )

    def __call__(self, *args) -> str:
        if self._hex:
            return self._hex
        if self._js_func is None:
            raise NotImplementedError
        return evaljs(_COMMAND_JS_TMPL % self._js_func, args=args)


@dataclass(frozen=True)
class ControlBoard:
    """Specifications for a control board connected via UART."""

    name: str
    commands: dict[str, Command]
    _status_js_func: str | None
    _temperatures_js_func: str | None

    @classmethod
    def from_dict(cls, ctrl_dict) -> ControlBoard:
        return cls(
            name=ctrl_dict["name"],
            commands={
                c["slug"]: Command.from_dict(c)
                for c in ctrl_dict["control_board_commands"]
            },
            _status_js_func=_scrub_js(ctrl_dict["status_function"]),
            _temperatures_js_func=_scrub_js(ctrl_dict["temperature_function"]),
        )

    def _evaljs(self, js_func: str, message: str) -> StateDict | None:
        try:
            js = _CONTROLLER_JS_TMPL % js_func
            return evaljs(js, message=message)
        except Exception as ex:
            _LOGGER.warning("JS evaluation failed for message %r: %s", message[:20], ex)
            return None

    def parse_status(self, message: str) -> StateDict | None:
        if not self._status_js_func:
            raise NotImplementedError
        return self._evaljs(self._status_js_func, message)

    def parse_temperatures(self, message: str) -> StateDict | None:
        if not self._temperatures_js_func:
            raise NotImplementedError
        return self._evaljs(self._temperatures_js_func, message)


@dataclass(frozen=True)
class Grill:
    """Specifications for a particular grill model."""

    name: str
    control_board: ControlBoard
    has_lights: bool = False
    min_temp: int | None = None
    max_temp: int | None = None
    meat_probes: int = 0
    temp_increments: list[int] | None = field(default_factory=list)
    json: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, grill_dict) -> Grill:
        min_temp = None
        try:
            min_temp = int(grill_dict["min_temp"])
        except (ValueError, TypeError):
            pass

        max_temp = None
        try:
            max_temp = int(grill_dict["max_temp"])
        except (ValueError, TypeError):
            pass

        return cls(
            name=grill_dict["name"],
            has_lights=grill_dict["lights"] > 0,
            min_temp=min_temp,
            max_temp=max_temp,
            meat_probes=grill_dict["meat_probes"],
            temp_increments=list(
                int(t) for t in grill_dict["temp_increment"].split("/")
            ),
            json=grill_dict,
            control_board=ControlBoard.from_dict(grill_dict["control_board"]),
        )


def get_grills(control_board: str | None = None) -> Iterable[Grill]:
    """Retrieves all supported grill specifications."""
    for grill in _get_grills().values():
        if not grill["control_board"].get("status_function"):
            continue
        if grill["name"] in UNSUPPORTED_MODELS:
            continue
        if control_board is None or grill["control_board"]["name"] == control_board:
            yield Grill.from_dict(grill)


def get_grill(grill_name: str) -> Grill:
    """Retrieves a grill specification by model name."""
    if (grill := _get_grills().get(grill_name)) is None:
        raise InvalidGrill(f"Unknown grill name: {grill_name}")
    return Grill.from_dict(grill)
