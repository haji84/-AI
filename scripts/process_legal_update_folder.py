"""Run on the department server under its fixed identity and database settings."""
import argparse
import json
from app.db import SessionLocal
from app.settings import settings
from app.legal_update_folder import process_update_folder


def main():
    parser=argparse.ArgumentParser(description='Verify approved-folder legal bundles and create Human review candidates')
    parser.add_argument('--source-id',required=True)
    parser.add_argument('--folder',required=True)
    args=parser.parse_args()
    result=process_update_folder(args.folder,args.source_id,SessionLocal,settings)
    print(json.dumps(result,ensure_ascii=False))
    if result['rejected']:raise SystemExit(1)


if __name__=='__main__':main()
