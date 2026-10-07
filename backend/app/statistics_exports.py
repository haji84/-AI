"""Generic frozen-value exports, with no private lineage or free-text review notes."""
import csv
from io import BytesIO, StringIO
from .statistics_sources import canonical

GENERIC_LABEL = '汎用統計出力（正式様式ではありません）'


def safe(value):
    value = '' if value is None else str(value)
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value


def render_export(report, format):
    snapshot = report['snapshot']
    rows = [[GENERIC_LABEL], ['report_id', report['report_id']], ['lifecycle_version', report['version']],
            ['state', report['state']], ['confirmed_at', report['confirmed_at']],
            ['coverage_status', snapshot['coverage_status']], ['captured_at', snapshot['captured_at']],
            ['query_version', snapshot['query_version']], ['public_checksum', snapshot['public_checksum']]]
    rows.extend([key, value] for key, value in snapshot['period'].items())
    rows.append([])
    rows.append(['metric_key', 'label', 'value', 'unit', 'status', 'coverage_status', 'denominator', 'date_basis', 'definition_version', 'definition', 'exclusions', 'limitations'])
    for metric in snapshot['metrics']:
        rows.append([metric[key] if key not in ('exclusions', 'limitations') else canonical(metric[key])
                     for key in ['key', 'label', 'value', 'unit', 'status', 'coverage_status', 'denominator', 'date_basis', 'definition_version', 'definition', 'exclusions', 'limitations']])
    if format == 'csv':
        stream = StringIO(newline='')
        writer = csv.writer(stream)
        writer.writerows([[safe(value) for value in row] for row in rows])
        return stream.getvalue().encode('utf-8-sig'), 'text/csv; charset=utf-8'
    from openpyxl import Workbook
    workbook = Workbook()
    sheet = workbook.active; sheet.title = '観測統計'
    for row in rows:
        sheet.append([safe(value) for value in row])
        for cell in sheet[sheet.max_row]:
            cell.data_type = 's'
    sheet.freeze_panes = 'A2'
    stream = BytesIO(); workbook.save(stream)
    return stream.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
