from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Permission, Role, RolePermission

PERMISSIONS: dict[str, str] = {
    **{f"learning.{action}": "学習 "+action for action in ("read","record","review","evaluate","promote")},
    "personnel.read": "職員・組織・人事履歴参照",
    "personnel.manage": "職員・組織・人事辞令Human管理",
    "account.manage": "アカウント・永続ロールHuman管理",
    "system.health.read": "ヘルスチェック参照",
    "system.backup": "バックアップ・復元管理",
    "audit.read": "監査ログ参照",
    "facility.read": "対象物参照",
    "facility.create": "対象物新規登録",
    "facility.update": "対象物更新",
    "facility.restore": "対象物復元",
    "facility.import": "旧査察台帳データ取込",
    "document.create": "原本登録",
    "document.read": "原本参照",
    "inspection.read": "査察履歴参照",
    "inspection.create": "査察新規登録",
    "inspection.update": "査察・指摘事項更新",
    "submission.read": "届出参照",
    "submission.create": "届出受付",
    "submission.update": "届出事務処理更新",
    "submission.manage": "届出種別マスタ管理",
    "intake.read": "文書解析結果参照",
    "intake.analyze": "受付文書解析",
    "intake.review": "受付文書解析レビュー",
    "intake.apply": "受付文書から対象物変更反映",
    "emergency.import": "救急データ取込",
    "emergency.report.read": "救急集計参照",
    "emergency.report.export": "救急集計出力",
    "emergency.case.read": "救急事案個票参照",
    "emergency.patient.read": "救急傷病者個票参照",
    "emergency.crew.read": "救急出動隊員個票参照",
    "extension.read": "拡張・取込参照",
    "extension.create": "拡張取込・Change Request作成",
    "extension.review": "拡張案レビュー",
    "extension.apply": "拡張案本番反映",
    "template.read": "正式様式参照",
    "template.manage": "正式様式登録・Version管理",
    "contract.read": "契約案件参照",
    "contract.create": "契約案件作成",
    "contract.update": "契約案件更新",
    "contract.approve": "契約案件正式承認",
    "legal_rule.read": "法令ルール・判定履歴参照",
    "legal_rule.manage": "法令ルール草案・Version管理",
    "legal_rule.approve": "法令ルールVersion正式承認",
    "legal_rule.evaluate": "対象物の必要書類・設備候補判定",
    "legal_source.read": "法令・例規Source/消防本部プロファイル参照",
    "legal_source.manage": "法令・例規Source/消防本部プロファイル管理",
    "legal_source.sync": "法令・例規更新同期実行",
    "equipment.read": "設置消防用設備台帳参照",
    "equipment.manage": "設置消防用設備台帳・設備種別管理",
    "drawing.read": "図面解析・候補参照",
    "drawing.analyze": "図面解析候補作成",
    "drawing.review": "図面解析候補レビュー・設備候補昇格",
    "fire_investigation.read": "火災調査ケース・証拠参照",
    "fire_investigation.create": "火災調査ケース・証拠登録",
    "fire_investigation.update": "火災調査ケース・派生情報更新",
    "fire_investigation.review": "火災調査AI候補・供述・原因候補レビュー",
    "fire_investigation.approve": "火災原因・正式報告承認",
    "search.use": "権限範囲内の横断検索",
}

PERMISSIONS.update({
    "emergency.case.create": "救急事案登録",
    "emergency.case.update": "救急事案訂正",
    "emergency.patient.create": "傷病者登録",
    "emergency.patient.update": "傷病者・処置訂正",
    "emergency.crew.manage": "共通職員から隊員登録",
    "emergency.clinical.generate": "CPA・アレルギー候補作成",
    "emergency.clinical.review": "臨床分類候補Human確認",
    "emergency.report.create": "救急報告・事後検証・救命処置録Draft作成",
    "emergency.report.review": "救急帳票DraftHuman確認",
})

# Additive operational permissions; reporting does not imply sensitive crew access.
for _domain in ('incident','fleet'):
    for _action in ('read','create','update','review','approve','admin','aggregate','export','import'):
        PERMISSIONS[f"{_domain}.{_action}"] = f"{_domain} {_action}"
PERMISSIONS.update({"incident.crew.read":"出動隊員参照", "incident.crew.manage":"出動隊員管理"})

ROLE_POLICY: dict[str, dict] = {
    "system_admin": {
        "name": "システム管理者",
        "system_role": True,
        "permissions": set(PERMISSIONS),
    },
    "prevention_editor": {
        "name": "予防業務担当",
        "system_role": True,
        "permissions": {
            "system.health.read",
            "facility.read", "facility.create", "facility.update", "facility.restore",
            "document.create", "document.read",
            "inspection.read", "inspection.create", "inspection.update",
            "submission.read", "submission.create", "submission.update",
            "intake.read", "intake.analyze", "intake.review", "intake.apply",
            "legal_rule.read", "legal_rule.evaluate", "legal_source.read",
            "equipment.read", "equipment.manage",
            "drawing.read", "drawing.analyze", "drawing.review",
        },
    },
    "emergency_reporter": {
        "name": "救急集計担当",
        "system_role": True,
        "permissions": {
            "system.health.read", "emergency.import", "emergency.report.read", "emergency.report.export",
        },
    },
    "emergency_detail_viewer": {
        "name": "救急個票閲覧",
        "system_role": True,
        "permissions": {
            "system.health.read", "emergency.report.read", "emergency.report.export", "emergency.case.read",
            "emergency.patient.read", "emergency.crew.read",
        },
    },
    "extension_manager": {
        "name": "拡張管理担当",
        "system_role": True,
        "permissions": {
            "system.health.read", "extension.read", "extension.create", "extension.review",
            "template.read", "template.manage",
        },
    },
    "contract_editor": {
        "name": "契約事務担当",
        "system_role": True,
        "permissions": {
            "system.health.read", "contract.read", "contract.create", "contract.update",
            "template.read", "document.create", "document.read",
        },
    },
    "contract_approver": {
        "name": "契約承認者",
        "system_role": True,
        "permissions": {
            "system.health.read", "contract.read", "contract.approve", "template.read",
        },
    },
    "legal_rule_manager": {
        "name": "法令ルール管理担当",
        "system_role": True,
        "permissions": {
            "system.health.read", "legal_rule.read", "legal_rule.manage", "legal_rule.evaluate", "legal_source.read", "legal_source.manage", "legal_source.sync",
            "document.read", "equipment.read", "drawing.read",
        },
    },
    "legal_rule_approver": {
        "name": "法令ルール承認者",
        "system_role": True,
        "permissions": {
            "system.health.read", "legal_rule.read", "legal_rule.approve", "legal_rule.evaluate", "legal_source.read",
            "document.read",
        },
    },
    "fire_investigator": {
        "name": "火災調査担当",
        "system_role": True,
        "permissions": {
            "system.health.read",
            "fire_investigation.read", "fire_investigation.create",
            "fire_investigation.update", "fire_investigation.review",
            "document.create", "document.read", "template.read",
        },
    },
    "fire_investigation_approver": {
        "name": "火災調査承認者",
        "system_role": True,
        "permissions": {
            "system.health.read", "fire_investigation.read",
            "fire_investigation.approve", "document.read", "template.read",
        },
    },
    "auditor": {
        "name": "監査閲覧",
        "system_role": True,
        "permissions": {"system.health.read", "audit.read"},
    },
}


for _action in ("read","create","update","review","approve","admin","import","export","borrower.read","borrower.manage"):
    PERMISSIONS[f"asset.{_action}"] = f"Operational asset {_action}"
ROLE_POLICY["system_admin"]["permissions"].update(code for code in PERMISSIONS if code.startswith("asset."))
ROLE_POLICY["asset_editor"] = {"name":"資機材担当", "system_role":True, "permissions":{"search.use","system.health.read", *[f"asset.{a}" for a in ("read","create","update","import","export","borrower.read","borrower.manage")]}}
ROLE_POLICY["asset_reviewer"] = {"name":"資機材確認者", "system_role":True, "permissions":{"search.use","system.health.read", *[f"asset.{a}" for a in ("read","review","approve")]}}

for _action in ("read","create","update","review","approve","admin","import","export","aggregate"):
    PERMISSIONS[f"workforce.{_action}"] = f"Workforce {_action}"
ROLE_POLICY["system_admin"]["permissions"].update(code for code in PERMISSIONS if code.startswith("workforce."))
ROLE_POLICY["workforce_editor"] = {
    "name":"勤務管理担当", "system_role":True,
    "permissions":{"search.use","system.health.read","document.read",
        *[f"workforce.{a}" for a in ("read","create","update","import","export","aggregate")]}
}
ROLE_POLICY["workforce_reviewer"] = {
    "name":"勤務確認者", "system_role":True,
    "permissions":{"search.use","system.health.read",
        *[f"workforce.{a}" for a in ("read","review","approve","aggregate")]}
}
ROLE_POLICY["workforce_admin"] = {
    "name":"勤務制度管理者", "system_role":True,
    "permissions":{"search.use","system.health.read","personnel.read","document.read",
        *[f"workforce.{a}" for a in ("read","create","update","review","approve","admin","import","export","aggregate")]}
}

ROLE_POLICY["emergency_editor"] = {
    "name": "救急記録担当", "system_role": True,
    "permissions": {"system.health.read", "search.use", "emergency.case.read",
        "emergency.case.create", "emergency.case.update", "emergency.patient.read",
        "emergency.patient.create", "emergency.patient.update", "emergency.crew.read",
        "emergency.crew.manage", "emergency.report.read", "emergency.report.create",
        "emergency.clinical.generate"},
}
ROLE_POLICY["emergency_reviewer"] = {
    "name": "救急記録確認者", "system_role": True,
    "permissions": {"system.health.read", "search.use", "emergency.case.read",
        "emergency.patient.read", "emergency.crew.read", "emergency.report.read",
        "emergency.clinical.review", "emergency.report.review"},
}

for _domain in ('incident','fleet'):
    ROLE_POLICY[f"{_domain}_editor"] = {"name":f"{_domain}業務担当", "system_role":True,
        "permissions": {"search.use", "system.health.read", *[f"{_domain}.{a}" for a in ('read','create','update','import','export','aggregate')]}}
    ROLE_POLICY[f"{_domain}_reviewer"] = {"name":f"{_domain}確認者", "system_role":True,
        "permissions": {"search.use", "system.health.read", *[f"{_domain}.{a}" for a in ('read','review','approve','aggregate')]}}
ROLE_POLICY["incident_editor"]["permissions"].update({"incident.crew.read","incident.crew.manage","fleet.read"})
ROLE_POLICY["incident_reviewer"]["permissions"].add("incident.crew.read")
ROLE_POLICY["operations_reporter"] = {"name":"出動車両集計担当", "system_role":True,
    "permissions": {"system.health.read","incident.aggregate","incident.export","fleet.aggregate","fleet.export"}}

for _action in ('read','create','update','review','approve','admin','import','export'):
    PERMISSIONS[f'finance.{_action}'] = f'Financial {_action}'
ROLE_POLICY['system_admin']['permissions'].update(code for code in PERMISSIONS if code.startswith('finance.'))
ROLE_POLICY['finance_editor'] = {'name':'契約予算担当', 'system_role':True, 'permissions':{'search.use','system.health.read','contract.read','contract.create','contract.update','document.read','document.create','template.read',*[f'finance.{a}' for a in ('read','create','update','import','export')]}}
ROLE_POLICY['finance_reviewer'] = {'name':'財務確認承認者', 'system_role':True, 'permissions':{'search.use','system.health.read','contract.read','contract.approve','document.read','template.read',*[f'finance.{a}' for a in ('read','review','approve')]}}

SEARCH_ENABLED_ROLES = {
    "prevention_editor",
    "emergency_reporter",
    "emergency_detail_viewer",
    "extension_manager",
    "contract_editor",
    "contract_approver",
    "legal_rule_manager",
    "legal_rule_approver",
    "fire_investigator",
    "fire_investigation_approver",
}
for _role_code in SEARCH_ENABLED_ROLES:
    if _role_code in ROLE_POLICY:
        ROLE_POLICY[_role_code]["permissions"].add("search.use")


def seed_rbac(db: Session) -> dict[str, Role]:
    permission_objs: dict[str, Permission] = {}
    for code, description in PERMISSIONS.items():
        perm = db.scalar(select(Permission).where(Permission.code == code))
        if perm is None:
            perm = Permission(code=code, description=description)
            db.add(perm)
            db.flush()
        else:
            perm.description = description
        permission_objs[code] = perm

    roles: dict[str, Role] = {}
    for code, policy in ROLE_POLICY.items():
        role = db.scalar(select(Role).where(Role.code == code))
        if role is None:
            role = Role(code=code, name=policy["name"], system_role=policy["system_role"])
            db.add(role)
            db.flush()
        else:
            role.name = policy["name"]
            role.system_role = policy["system_role"]
        roles[code] = role

        wanted = policy["permissions"]
        current = {
            rp.permission_id: rp
            for rp in db.scalars(select(RolePermission).where(RolePermission.role_id == role.role_id)).all()
        }
        wanted_ids = {permission_objs[p].permission_id for p in wanted}
        for permission_id in wanted_ids - set(current):
            db.add(RolePermission(role_id=role.role_id, permission_id=permission_id))
        for permission_id, rp in current.items():
            if permission_id not in wanted_ids:
                db.delete(rp)
    db.flush()
    return roles

for _action in ('read','create','update','review','approve','export'):
    PERMISSIONS[f'violation.{_action}'] = f'Violation {_action}'
ROLE_POLICY['system_admin']['permissions'].update(code for code in PERMISSIONS if code.startswith('violation.'))

_VIOLATION_SOURCE_RIGHTS={'facility.read','inspection.read','document.read','legal_rule.read','legal_source.read','search.use','system.health.read'}
ROLE_POLICY['violation_editor']={'name':'違反・改善措置担当','system_role':True,'permissions':_VIOLATION_SOURCE_RIGHTS|{'document.create','violation.read','violation.create','violation.update','violation.export'}}
ROLE_POLICY['violation_reviewer']={'name':'違反・改善措置Human確認者','system_role':True,'permissions':_VIOLATION_SOURCE_RIGHTS|{'violation.read','violation.review','violation.approve'}}
