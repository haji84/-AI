"""Actual Chromium team grouping and dated canonical history; synthetic only."""
import os
import pytest
from test_statistics_browser import statistics_browser

pytestmark=pytest.mark.skipif(os.environ.get('FIRE_AI_TEST_BROWSER')!='1',reason='actual Chromium acceptance runs in authorized CI')


def test_actual_team_membership_human_versions_and_history_staleness(statistics_browser):
    from playwright.sync_api import expect
    ui=statistics_browser;page=ui['page']
    ui['database']('''
from datetime import date
from app.db import SessionLocal
from app.models import Employee
from app.personnel import OrganizationUnit,EmployeeAssignment
with SessionLocal() as db:
 employee=Employee(employee_code='SYN-TEAM-UI',display_name='Synthetic team browser member')
 organization=OrganizationUnit(code='SYN-TEAM-UI',name='Synthetic team browser station')
 db.add_all([employee,organization]);db.flush()
 db.add(EmployeeAssignment(employee_id=employee.employee_id,organization_id=organization.organization_id,title='Synthetic duty',kind='primary',valid_from=date(2026,1,1)))
 db.commit()
''')
    ui['login']('statistics-writer')
    employees=page.request.get(ui['base']+'/workforce/employees').json()
    employee=next(row for row in employees if row['employee_code']=='SYN-TEAM-UI')
    organization=next(row for row in page.request.get(ui['base']+'/workforce/organizations').json() if row['code']=='SYN-TEAM-UI')
    assignment=page.request.get(ui['base']+'/administration/staff/'+employee['employee_id']+'/assignments').json()[0]
    page.locator('#workforceBtn').click();page.locator('#workforceTeams').click()
    page.locator('#workforceTeamNew').click()
    page.locator('#workforceField_organization_id').select_option(organization['organization_id'])
    page.locator('#workforceField_code').fill('SYN-TEAM-UI')
    page.locator('#workforceField_name').fill('Synthetic team browser group')
    page.locator('#workforceField_reason').fill('Synthetic Human team setup')
    with page.expect_response(lambda response:response.url.endswith('/workforce/teams') and response.request.method=='POST') as saved:
        page.locator('#workforceTeamSave').click()
    assert saved.value.status==201,saved.value.text()
    team=saved.value.json()
    expect(page.locator('#workforceTeamMembers_'+team['team_id'])).to_be_visible()
    expect(page.locator('#workforceHumanStatus')).to_have_text('')
    page.locator('#workforceTeamMembers_'+team['team_id']).click()
    page.locator('#workforceTeamMemberNew').click()
    page.locator('#workforceField_employee_id').select_option(employee['employee_id'])
    expect(page.locator('#workforceField_assignment_id option[value="'+assignment['assignment_id']+'"]')).to_have_count(1)
    page.locator('#workforceField_assignment_id').select_option(assignment['assignment_id'])
    page.locator('#workforceField_valid_from').fill('2026-01-01')
    page.locator('#workforceField_reason').fill('Synthetic Human member setup')
    with page.expect_response(lambda response:response.url.endswith('/workforce/teams/'+team['team_id']+'/members') and response.request.method=='POST') as member:
        page.locator('#workforceTeamMemberSave').click()
    assert member.value.status==201,member.value.text()
    assert member.value.request.post_data_json['expected_team_version']==1
    assert member.value.request.post_data_json['expected_assignment_version']==assignment['version']
    assert member.value.json()['team_version']==2
    assert member.value.json()['formal_crew_assignment'] is False
    member_id=member.value.json()['membership']['membership_id']
    expect(page.locator('#workforceTeamMemberToggle_'+member_id)).to_be_visible()
    expect(page.locator('#workforceContent')).to_contain_text('Synthetic team browser member')
    expect(page.locator('#workforceHumanStatus')).to_have_text('')
    stale=page.request.post(ui['base']+'/workforce/teams/'+team['team_id']+'/members',data=member.value.request.post_data_json)
    assert stale.status==409,stale.text()
    changed=page.request.patch(ui['base']+'/administration/assignments/'+assignment['assignment_id'],data={
        'expected_version':assignment['version'],'expected_employee_version':employee['version'],
        'title':'Synthetic revised duty','reason':'Synthetic Human assignment update'})
    assert changed.status==200,changed.text()
    page.locator('#workforceTeamBack').click();page.locator('#workforceTeamMembers_'+team['team_id']).click()
    expect(page.locator('#workforceContent')).to_contain_text('利用不可（無効または根拠変更）')
    page.screenshot(path=str(ui['artifacts']/'workforce-team-history-stale.png'),full_page=True)
    page.locator('#workforceTeamBack').click();page.locator('#workforceTeamHistory_'+team['team_id']).click()
    expect(page.locator('#workforceContent')).to_contain_text('Synthetic Human member setup')
    expect(page.locator('#workforceContent')).to_contain_text('Synthetic duty')
    expect(page.locator('[data-workforce-human]')).to_have_count(0)
    expect(page.locator('[data-workforce-team-edit]')).to_have_count(0)
    page.screenshot(path=str(ui['artifacts']/'workforce-team-protected-history.png'),full_page=True)
