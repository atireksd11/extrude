"""Small, explicit pilot mappings. Repository files never configure tool commands."""

import json
import os
import re
import uuid
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from extrude import github_history as git
from extrude.runtime import data_dir


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


def repository_path(value: str) -> str:
    git._validate_path(value)
    if ":" in value or "\\" in value or PurePosixPath(value).is_absolute() or len(value) > 1024:
        raise ValueError("Use a relative repository path.")
    return value


class CadPair(StrictModel):
    board_file: str
    mesh_file: str
    units: Literal["mm", "cm", "m", "in"]
    mesh_kind: Literal["exterior", "cavity"] = "exterior"
    board_axes: tuple[Literal["x", "y", "z"], Literal["x", "y", "z"]]
    cavity_mm: tuple[float, float, float] | None = None

    _paths = field_validator("board_file", "mesh_file")(repository_path)

    @model_validator(mode="after")
    def valid(self):
        if len(set(self.board_axes)) != 2:
            raise ValueError("Board X and Y must map to different enclosure axes.")
        if self.cavity_mm is not None and any(n <= 0 or n > 1e6 for n in self.cavity_mm):
            raise ValueError("Cavity dimensions must be positive millimetres.")
        if not self.board_file.lower().endswith(".kicad_pcb") or Path(self.mesh_file).suffix.lower() not in {".stl", ".obj", ".step", ".stp"}:
            raise ValueError("Choose a KiCad PCB and an STL/OBJ/STEP export.")
        if Path(self.mesh_file).suffix.lower() in {".step", ".stp"} and self.units != "mm":
            raise ValueError("STEP geometry is normalized to millimetres; select mm.")
        return self


class PinMapping(StrictModel):
    firmware_file: str
    firmware_symbol: str = Field(pattern=r"^[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*$", max_length=160)
    netlist_file: str  # committed .net, or native root .kicad_sch exported safely
    schematic_net: str = Field(min_length=1, max_length=200)
    mcu_ref: str = Field(pattern=r"^[A-Za-z]+[0-9]+$")
    numbering: Literal["package", "gpio"]
    gpio_to_pad: dict[str, str] = Field(default_factory=dict, max_length=256)

    _paths = field_validator("firmware_file", "netlist_file")(repository_path)

    @model_validator(mode="after")
    def valid(self):
        if any(not re.fullmatch(r"\d{1,6}", key) or not re.fullmatch(r"[A-Za-z0-9_.+-]{1,32}", val)
               for key, val in self.gpio_to_pad.items()):
            raise ValueError("GPIO mappings must map literal GPIO numbers to package pad identifiers.")
        if self.numbering == "package" and self.gpio_to_pad:
            raise ValueError("GPIO mapping is only applicable to GPIO numbering.")
        if Path(self.netlist_file).suffix.lower() not in {".net", ".kicad_sch"}:
            raise ValueError("Choose a KiCad .net or root .kicad_sch file.")
        return self


class BomMapping(StrictModel):
    bom_file: str
    schematic_file: str
    reference_column: str = Field(default="Reference", min_length=1, max_length=100)
    part_column: str = Field(default="MPN", min_length=1, max_length=100)
    quantity_column: str = Field(default="Quantity", min_length=1, max_length=100)
    dnp_column: str | None = Field(default=None, max_length=100)
    delimiter: Literal[",", ";", "\t"] = ","

    _paths = field_validator("bom_file", "schematic_file")(repository_path)

    @model_validator(mode="after")
    def valid(self):
        cols = [self.reference_column, self.part_column, self.quantity_column]
        if self.dnp_column:
            cols.append(self.dnp_column)
        if len(set(cols)) != len(cols):
            raise ValueError("BOM columns must be distinct.")
        if Path(self.bom_file).suffix.lower() not in {".csv", ".tsv"} or not self.schematic_file.lower().endswith(".kicad_sch"):
            raise ValueError("Choose a CSV/TSV BOM and its root KiCad schematic.")
        return self


class Settings(StrictModel):
    version: Literal[1] = 1
    cad_pairs: list[CadPair] = Field(default_factory=list, max_length=12)
    pin_assignments: list[PinMapping] = Field(default_factory=list, max_length=32)
    boms: list[BomMapping] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def unique(self):
        for rows, keys in ((self.cad_pairs, ("board_file", "mesh_file")),
                           (self.pin_assignments, ("firmware_file", "firmware_symbol")),
                           (self.boms, ("bom_file",))):
            identities = [tuple(getattr(row, key) for key in keys) for row in rows]
            if len(identities) != len(set(identities)):
                raise ValueError("Remove duplicate project mappings.")
        return self


def _path(repo_id: str) -> Path:
    git._repository(repo_id)  # validate identity and ownership before constructing a path
    return data_dir() / "workspace-settings" / f"{repo_id}.json"


def get(repo_id: str) -> Settings:
    path = _path(repo_id)
    try:
        return Settings.model_validate_json(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Settings()


def save(repo_id: str, settings: Settings) -> Settings:
    path = _path(repo_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(uuid.uuid4().hex + ".tmp")
    try:
        pending.write_text(settings.model_dump_json(), encoding="utf-8")
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)
    return settings
