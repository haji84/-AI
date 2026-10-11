#!/usr/bin/env python3
"""Protected systemd entry point; never operates any other department's units."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from app.backup_contract import binding
from app.scheduled_backup import run_scheduled_backup,systemd_control,controlled_termination,run_backup_child
from app.settings import settings
from app.tenant_deployment import render_department


def backup_command(destination: Path, release_id: str) -> list[str]:
    required_value = os.environ.get('FIRE_AI_BACKUP_ENCRYPTION_REQUIRED', 'false').lower()
    if required_value not in {'true', 'false'}:
        raise SystemExit('backup encryption requirement must be true or false')
    recipient = os.environ.get('FIRE_AI_BACKUP_RECIPIENT_PUBLIC_KEY')
    if required_value == 'true' and not recipient:
        raise SystemExit('required encrypted backup recipient is unavailable')
    if recipient:
        recipient_path = Path(recipient)
        if recipient_path.is_symlink() or not recipient_path.is_file():
            raise SystemExit('encrypted backup recipient must be an available regular file')
    command = [sys.executable, str(Path(__file__).with_name('backup_phase1.py')),
        '--destination', str(destination), '--release-id', release_id, '--confirm-writers-stopped']
    if recipient:
        command += ['--recipient-public-key-env', 'FIRE_AI_BACKUP_RECIPIENT_PUBLIC_KEY']
    return command


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--slug',required=True)
    p.add_argument('--release-id',required=True)
    args=p.parse_args()
    if not settings.production_mode or not settings.database_url.startswith('postgresql') or not settings.tenant_id:
        raise SystemExit('scheduled backup requires a bound production PostgreSQL department')
    # Reuse the strict deployment identifier validation before constructing paths/units.
    render_department(slug=args.slug,tenant_id=settings.tenant_id,host='validation.internal',port=8101,release_id=args.release_id)
    storage=Path('/var/lib/fire-ai')/args.slug/'storage'
    destination=Path('/var/backups/fire-ai')/args.slug
    if Path(settings.storage_root)!=storage or storage.is_symlink():raise SystemExit('storage does not match the selected department')
    if destination.is_symlink() or not destination.is_dir():raise SystemExit('protected department backup directory required')
    st=destination.stat()
    if st.st_uid!=os.geteuid() or st.st_mode&0o077:raise SystemExit('backup directory must be owner-only')
    binding(settings.database_url,storage,settings.tenant_id)
    writers=json.loads(os.environ.get('FIRE_AI_BACKUP_WRITER_UNITS','[]'))
    if not isinstance(writers,list) or any(not isinstance(unit,str) for unit in writers):raise SystemExit('writer units must be a JSON string list')
    command = backup_command(destination, args.release_id)
    def backup():
        run_backup_child(command)
    with controlled_termination():
        run_scheduled_backup(slug=args.slug,tenant_id=settings.tenant_id,lock_path=destination/'.scheduled-backup.lock',
            writer_units=writers,control=systemd_control,backup=backup)


if __name__=='__main__':main()
