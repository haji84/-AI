from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import ModuleDefinition, FeatureFlag

MODULES = {
    "hazardous_materials": {"name":"危険物台帳", "version":"1.0.0"},
    "work_queue": {"name":"今日の作業", "version":"1.0.0"},
    "inquiries": {"name":"議会・照会", "version":"1.0.0"},
    "violations": {"name":"正式違反・改善措置", "version":"1.0.0"},
    "procurement": {"name":"契約・調達", "version":"1.0.0"},
    "budget": {"name":"予算・財務", "version":"1.0.0"},
    "learning": {"name":"学習・評価・Human昇格", "version":"1.0.0"},
    "operational_assets": {"name": "資機材・在庫", "version": "1.0.0"},
    "workforce": {"name": "勤務・人員配置", "version": "1.0.0"},
    "operations": {"name": "事案・出動", "version": "1.0.0"},
    "fleet": {"name": "車両運用", "version": "1.0.0"},
    "prevention": {"name": "予防業務", "version": "1.0.0"},
    "emergency_reporting": {"name": "救急報告・集計", "version": "1.1.0"},
    "fire_investigation": {"name": "火災調査", "version": "0.1.0"},
    "contracts": {"name": "契約管理", "version": "0.1.0"},
    "extensions": {"name": "拡張・取込", "version": "1.0.0"},
}


def seed_modules(db: Session) -> dict[str, ModuleDefinition]:
    out = {}
    for code, cfg in MODULES.items():
        row = db.scalar(select(ModuleDefinition).where(ModuleDefinition.code == code))
        if row is None:
            row = ModuleDefinition(code=code, name=cfg["name"], version=cfg["version"], manifest={"code": code, "name": cfg["name"]})
            db.add(row); db.flush()
        else:
            row.name = cfg["name"]
        if code == "work_queue":
            row.version=cfg["version"]
            row.manifest={**(row.manifest or {}),"operational_api":"/work-queue","surface":"/ui/","read_only":True}
        if code == "hazardous_materials":
            row.version=cfg["version"]
            row.manifest={**(row.manifest or {}),"operational_api":"/hazardous","surface":"/ui/","human_evidence_review":True,"legal_evaluation":False}
        if code == "emergency_reporting":
            row.version = cfg["version"]
            row.manifest = {**(row.manifest or {}), "operational_api": "/emergency", "surface": "/ui/", "aggregate_api": "/emergency/reports/summary"}
        if code in {"operations", "fleet"}:
            row.version = cfg["version"]
            row.manifest = {**(row.manifest or {}), "operational_api": "/operations", "surface": "/ui/"}
        if code in {"procurement", "budget"}:
            row.version=cfg["version"]
            row.manifest={**(row.manifest or {}), "operational_api":"/finance", "surface":"/ui/", "common_contract_module":"contracts"}
        if code == "operational_assets":
            row.version = cfg["version"]
            row.manifest = {**(row.manifest or {}), "operational_api": "/assets", "surface": "/ui/"}
        if code == "workforce":
            row.version = cfg["version"]
            row.manifest = {**(row.manifest or {}), "operational_api": "/workforce", "surface": "/ui/"}
        if code == 'violations':
            row.manifest={**(row.manifest or {}),'operational_api':'/violations','surface':'/ui/','formal_human_gate':True}
        if code == "inquiries":
            row.manifest={**(row.manifest or {}), "operational_api":"/inquiries", "surface":"/ui/", "human_review_required":True}
        if code == 'learning':
            row.manifest = {**(row.manifest or {}), 'operational_api':'/learning', 'surface':'/ui/learning.html', 'engine':'literal-correction-v1', 'human_promotion_required':True}
        out[code] = row
        key = f"module.{code}.enabled"
        flag = db.scalar(select(FeatureFlag).where(FeatureFlag.key == key))
        if flag is None:
            db.add(FeatureFlag(key=key, module_code=code, enabled=True, config={}))
    db.flush()
    return out
