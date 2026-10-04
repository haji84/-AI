from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Permission, Role, RolePermission

PERMISSIONS: dict[str, str] = {
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
    "emergency.import": "救急データ取込",
    "emergency.report.read": "救急集計参照",
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
}

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
        },
    },
    "emergency_reporter": {
        "name": "救急集計担当",
        "system_role": True,
        "permissions": {
            "system.health.read", "emergency.import", "emergency.report.read",
        },
    },
    "emergency_detail_viewer": {
        "name": "救急個票閲覧",
        "system_role": True,
        "permissions": {
            "system.health.read", "emergency.report.read", "emergency.case.read",
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
    "auditor": {
        "name": "監査閲覧",
        "system_role": True,
        "permissions": {"system.health.read", "audit.read"},
    },
}


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