from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import EquipmentType

SEED_VERSION = "equipment-master-v1"

DEFAULT_EQUIPMENT_TYPES = {
    "extinguisher": ("消火器", "extinguishing"),
    "indoor_fire_hydrant": ("屋内消火栓設備", "extinguishing"),
    "sprinkler": ("スプリンクラー設備", "extinguishing"),
    "water_spray_extinguishing": ("水噴霧消火設備", "extinguishing"),
    "foam_extinguishing": ("泡消火設備", "extinguishing"),
    "inert_gas_extinguishing": ("不活性ガス消火設備", "extinguishing"),
    "halogenated_extinguishing": ("ハロゲン化物消火設備", "extinguishing"),
    "powder_extinguishing": ("粉末消火設備", "extinguishing"),
    "outdoor_fire_hydrant": ("屋外消火栓設備", "extinguishing"),
    "leakage_fire_alarm": ("漏電火災警報器", "alarm"),
    "automatic_fire_alarm": ("自動火災報知設備", "alarm"),
    "fire_service_notification_alarm": ("消防機関へ通報する火災報知設備", "alarm"),
    "gas_leak_fire_alarm": ("ガス漏れ火災警報設備", "alarm"),
    "emergency_alarm": ("非常警報設備", "alarm"),
    "evacuation_equipment": ("避難器具", "evacuation"),
    "exit_light": ("誘導灯", "evacuation"),
    "exit_sign": ("誘導標識", "evacuation"),
    "connected_sprinkler": ("連結散水設備", "firefighting_support"),
    "connected_water_pipe": ("連結送水管", "firefighting_support"),
    "smoke_control": ("排煙設備", "firefighting_support"),
    "emergency_power_outlet": ("非常コンセント設備", "firefighting_support"),
    "radio_communication_support": ("無線通信補助設備", "firefighting_support"),
}


def seed_equipment_types(db: Session) -> dict[str, EquipmentType]:
    out: dict[str, EquipmentType] = {}
    for code, (name, category) in DEFAULT_EQUIPMENT_TYPES.items():
        row = db.scalar(select(EquipmentType).where(EquipmentType.code == code))
        metadata = {
            "seed_version": SEED_VERSION,
            "legal_completeness": False,
            "editable_master": True,
        }
        if row is None:
            row = EquipmentType(
                code=code,
                name=name,
                category=category,
                equipment_metadata=metadata,
            )
            db.add(row)
            db.flush()
        else:
            row.name = name
            row.category = category
            current = dict(row.equipment_metadata or {})
            current.update(metadata)
            row.equipment_metadata = current
            row.active = True
        out[code] = row
    db.flush()
    return out
