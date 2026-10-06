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
    def backup():
        run_backup_child([sys.executable,str(Path(__file__).with_name('backup_phase1.py')),
            '--destination',str(destination),'--release-id',args.release_id,'--confirm-writers-stopped'])
    with controlled_termination():
        run_scheduled_backup(slug=args.slug,tenant_id=settings.tenant_id,lock_path=destination/'.scheduled-backup.lock',
            writer_units=writers,control=systemd_control,backup=backup)


if __name__=='__main__':main()
