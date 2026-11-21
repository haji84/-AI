'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const base = '/emergency/audit';
  const readPermissions = ['emergency.case.read', 'emergency.patient.read', 'emergency.report.read'];
  const readStates = {confirmed: '原本で確認済み', unconfirmed: 'まだ確認していない', unreadable: '読み取れない', not_printed: '印刷されない欄', unmapped: '対応が未設定'};
  const findingStates = {REVIEW_REQUIRED: '確認が必要', NO_ISSUE_DETECTED: 'この検査では指摘なし', NOT_TESTED: '未検査', NOT_APPLICABLE: '適用対象外'};
  const decisions = {correction_needed: '訂正が必要', false_alarm: '誤警告だった', exception: '例外に該当', unresolved: 'まだ判断できない'};
  const reasonLabels = {unknown: '理由は未確認', missing: '記載漏れ', inconsistent: '不整合', code_selection: '区分選択', format: '表記', reading_error: '読取誤り', local_rule: '本部運用'};
  const eventLabels = {study: '比較区分を記録', submitted: '実際の提出を記録', followup: '提出後の追跡を記録', work_interval: '作業時間を記録', truth_review: '独立確認を記録', upload: '原本を登録', revision: '新しい原本を登録', fields: '読み取りを確認', check: 'チェックを実施', retry: '読み取りを再試行', reviewer: '確認担当者を指定'};
  const pendingJobs = new Set(['queued', 'pending', 'running', 'processing', 'retrying']);
  const MAX_FILE_BYTES = 25 * 1024 * 1024;
  const MAX_CONFIG_BYTES = 2 * 1024 * 1024;
  const state = {
    generation: 0, intent: 0, previewIntent: 0, configPreviewIntent: 0, listIntent: 0, configIntent: 0, truthIntent: 0,
    catalogIntent: 0, uploadIntent: 0, permissions: new Set(), userId: null, capabilities: null,
    report: null, reports: [], offset: 0, profiles: [], ruleSets: [], reviewers: [], sources: [],
    busy: false, uploadBusy: false, configBusy: false, configPreflight: null, stale: false, activeTab: 'reports',
    page: 1, previewUrl: null, configPreviewUrl: null, transientUrls: new Set(), pollTimer: null,
    queue: [], revisionUpload: null, fieldDrafts: new Map(), fieldDirty: false,
    profileRecord: null, profileDirty: false, mappingFields: [], editingField: null,
    sourceId: null, sourceMetadata: null, sourceUpload: null, mappingStart: null, mappingPreview: null,
    configRequest: null, ruleRequest: null, ruleSetRecord: null, ruleDrafts: [],
    catalogOffset: 0, catalogTotal: 0, catalogItems: [], eventRetries: new Map(),
    workCapture: null, truthRun: null, truthDrafts: new Map(), missedErrors: [], decisionControls: [],
    sourceShownRevision: null, editingWorkEvent: null, editingSubmissionEvent: null,
    patternIntent: 0, patternBusy: false,
  };
  const ticket = () => ({generation: state.generation, intent: state.intent});
  const current = t => t.generation === state.generation && t.intent === state.intent;
  const canRead = () => readPermissions.every(code => state.permissions.has(code));
  const canWrite = () => canRead() && state.permissions.has('emergency.report.create');
  const canConfigure = () => canRead() && state.permissions.has('emergency.audit.configure');
  const canApprove = () => canRead() && state.permissions.has('emergency.audit.approve');
  const headSelected = () => state.report && state.report.revision?.revision_id === state.report.current_revision_id;
  const writable = () => canWrite() && headSelected() && !state.busy && !state.uploadBusy && !state.stale;
  const originalVisibleFor = revisionId => !!revisionId && state.sourceShownRevision === revisionId && !!state.previewUrl && !$('sourceImage').hidden && $('sourceImage').src === state.previewUrl;
  const isOwner = report => report?.owner === true || report?.owner === state.userId || report?.owner?.user_id === state.userId;
  const canTruthReview = () => canRead() && state.permissions.has('emergency.report.review') && state.report && !isOwner(state.report) && (state.report.reviewer_id === state.userId || state.permissions.has('emergency.audit.read_all'));
  const canRecordWork = () => canWrite() || canTruthReview();
  const canRecordDecision = () => (canWrite() || canTruthReview()) && headSelected() && !state.busy && !state.uploadBusy && !state.stale;
  const aiConfigured = () => state.capabilities?.ai?.configured === true || state.capabilities?.ai?.available === true;
  const scalarText = value => ['string', 'number', 'boolean'].includes(typeof value) ? String(value) : '';
  const list = value => Array.isArray(value) ? value : [];
  const fieldEvidence = field => Array.isArray(field?.evidence) ? field.evidence : field?.evidence ? [field.evidence] : [];
  const today = () => { const d = new Date(); return [d.getFullYear(), String(d.getMonth() + 1).padStart(2, '0'), String(d.getDate()).padStart(2, '0')].join('-'); };
  const formatDate = value => { const d = new Date(value); return value && !Number.isNaN(d.getTime()) ? d.toLocaleString('ja-JP', {month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'}) : '日時未記録'; };
  const safeError = (message, status) => Object.assign(new Error(message), {safe: true, status});
  const cancelled = () => Object.assign(new Error('operation cancelled'), {cancelled: true});

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function message(id, text, error = false) { $(id).textContent = text; $(id).classList.toggle('error', error); }
  function button(text, handler, className = 'button quiet') { const node = element('button', text, className); node.type = 'button'; node.onclick = handler; return node; }
  function option(value, label) { const node = element('option', label); node.value = value; return node; }
  function badge(text, className = '') { return element('span', text, 'badge ' + className); }
  function setOptions(id, entries, placeholder = null) {
    const control = $(id), selected = control.value;
    control.replaceChildren();
    if (placeholder !== null) control.append(option('', placeholder));
    for (const [value, label] of entries) control.append(option(value, label));
    if (entries.some(([value]) => value === selected)) control.value = selected;
    else if (placeholder !== null) control.value = '';
  }
  function reportLabel(report) { return formatDate(report.created_at) + ' / 版 ' + (report.revision_number ?? report.revision?.number ?? 1); }
  function configLabel(config) { return config.label + ' / ' + ({draft: '下書き', approved: '承認済み', retired: '利用停止'}[config.status] ?? '確認待ち'); }
  function selectedConfiguration() { return [...state.profiles, ...state.ruleSets].find(item => item.config_id === $('reviewConfiguration').value) ?? null; }
  function reportPending() { return pendingJobs.has(state.report?.job_status) || pendingJobs.has(state.report?.revision?.processing_status); }

  function controls() {
    const ready = canRead(), idle = ready && !state.busy && !state.uploadBusy;
    for (const id of ['reportsTab', 'configurationTab', 'catalogTab', 'measurementTab', 'refreshReports', 'catalogSearch', 'catalogFilter', 'searchCatalog']) $(id).disabled = !ready;
    const upload = canWrite() && !state.uploadBusy && state.capabilities?.enabled === true && state.capabilities?.storage_ready === true;
    for (const id of ['uploadFiles', 'datasetKind', 'profileSelect']) $(id).disabled = !upload;
    $('startUpload').disabled = !upload || !state.queue.some(item => item.status === 'pending');
    $('retryFailedUploads').disabled = !upload || !state.queue.some(item => item.status === 'failed' && item.file);
    $('retryFailedUploads').hidden = !state.queue.some(item => item.status === 'failed' && item.file);
    $('previousReports').disabled = !ready || state.offset === 0;
    $('nextReports').disabled = !ready || state.reports.length < 30;
    $('previousCandidates').disabled = !ready || state.catalogOffset === 0;
    $('nextCandidates').disabled = !ready || state.catalogOffset + 50 >= state.catalogTotal;
    for (const id of ['clearReport', 'refreshReport']) $(id).disabled = !state.report || !idle || !!state.workCapture;
    const revision = state.report?.revision, pages = revision?.page_count ?? 0;
    $('previousPage').disabled = !state.report || state.page <= 1;
    $('nextPage').disabled = !state.report || state.page >= pages;
    $('previewZoom').disabled = !state.previewUrl;
    $('downloadOriginal').disabled = !state.report || !ready;
    const edit = writable(), fieldsEditable = edit && !reportPending() && originalVisibleFor(revision?.revision_id);
    for (const id of ['revisionFile', 'revisionProfile', 'applyMapping', 'retryJob', 'checkRules', 'checkMode', 'checkDate']) $(id).disabled = !edit;
    $('uploadRevision').disabled = !edit || !$('revisionFile').files?.length;
    $('applyMapping').disabled = !edit || !$('revisionProfile').value;
    $('retryJob').hidden = !['failed', 'error', 'exhausted'].includes(state.report?.job_status) && !['failed', 'error', 'partial'].includes(revision?.processing_status);
    $('confirmOriginal').disabled = !fieldsEditable || !state.fieldDirty;
    $('saveFields').disabled = !fieldsEditable || !state.fieldDirty || !$('confirmOriginal').checked;
    for (const draft of state.fieldDrafts.values()) {
      draft.stateControl.disabled = !fieldsEditable;
      draft.blankControl.disabled = !fieldsEditable || draft.stateControl.value !== 'confirmed';
      draft.valueControl.disabled = !fieldsEditable || draft.stateControl.value !== 'confirmed' || draft.blankControl.checked;
    }
    $('runCheck').disabled = !edit || reportPending() || state.fieldDirty || state.report?.measurement?.cohort === 'baseline';
    $('runAI').disabled = !edit || reportPending() || state.fieldDirty || !aiConfigured() || state.report?.measurement?.cohort === 'baseline';
    $('runVision').disabled = !edit || reportPending() || !aiConfigured() || !state.previewUrl || state.report?.measurement?.cohort === 'baseline';
    for (const item of state.decisionControls) { item.choice.disabled = !canRecordDecision() || state.report?.last_run?.stale; item.reason.disabled = item.choice.disabled; item.save.disabled = item.choice.disabled; }
    const configEdit = canConfigure() && !state.configBusy;
    $('configurationView').setAttribute('aria-busy', String(state.configBusy));
    for (const id of ['profileList', 'ruleList']) for (const control of $(id).querySelectorAll('button')) control.disabled = !ready || state.configBusy;
    for (const control of $('mappedFieldList').querySelectorAll('button')) control.disabled = !configEdit;
    for (const id of ['newProfile', 'profileName', 'profileCode', 'profileValidFrom', 'profileValidTo', 'profilePageCount', 'profileImport', 'configurationImportKind', 'configSourceFile', 'newRule', 'ruleCode', 'ruleSetLabel', 'ruleTitle', 'ruleField', 'ruleOperator', 'ruleValue', 'ruleOtherField', 'ruleMinimum', 'ruleMaximum', 'ruleSourceTitle', 'ruleSourceVersion', 'ruleSourcePage', 'ruleEvidence', 'saveRule', 'addMappedField', 'mappedFieldId', 'mappedFieldLabel', 'mappedFieldType', 'mappedFieldPage', 'regionX0', 'regionY0', 'regionX1', 'regionY1', 'saveMappedField', 'cancelMappedField']) $(id).disabled = !configEdit;
    const regionEntered = ['regionX0', 'regionY0', 'regionX1', 'regionY1'].some(id => $(id).value.trim() !== '');
    $('saveMappedField').disabled = !configEdit || (regionEntered && !mappingPageVisible());
    $('saveProfile').disabled = !configEdit || !state.profileDirty;
    $('uploadConfigSource').disabled = !configEdit || !$('configSourceFile').files?.length;
    $('sourceSelect').disabled = !(canConfigure() || canApprove()) || state.configBusy;
    $('reviewConfiguration').disabled = !ready || state.configBusy;
    $('impactReports').disabled = !configEdit;
    $('validateConfiguration').disabled = !configEdit || !selectedConfiguration();
    const selected = selectedConfiguration();
    const approval = canApprove() && !state.configBusy && selected?.source_id && selected?.impact?.can_approve === true && selected.created_by !== state.userId && selected.status === 'draft';
    $('sourceVerified').disabled = !approval; $('mappingVerified').disabled = !approval;
    $('approveConfiguration').disabled = !approval || !$('sourceVerified').checked || !$('mappingVerified').checked;
    $('retireConfiguration').disabled = !canApprove() || state.configBusy || selected?.status !== 'approved';
    const measurement = canWrite() && state.report && !state.busy && !state.stale;
    const workMeasurement = canRecordWork() && state.report && !state.busy && !state.stale;
    for (const id of ['measurementCohort', 'activityKind', 'recordStudy', 'submittedAt', 'submissionConfirmed', 'afterSubmission', 'followupComplete', 'workComplete']) $(id).disabled = !measurement;
    for (const id of ['workStage', 'workStartedAt', 'workEndedAt', 'recordWork']) $(id).disabled = !workMeasurement;
    $('recordStudy').disabled = !measurement || !!state.report?.initial_run;
    $('startWork').disabled = !workMeasurement || !!state.workCapture;
    $('pauseWork').disabled = !workMeasurement || !state.workCapture;
    $('workStage').disabled = !workMeasurement || !!state.workCapture;
    $('recordSubmission').disabled = !measurement || !$('submissionConfirmed').checked || (!!state.report?.submitted_at && !state.editingSubmissionEvent);
    $('cancelWorkCorrection').disabled = !workMeasurement; $('cancelSubmissionCorrection').disabled = !measurement;
    $('cancelWorkCorrection').hidden = !state.editingWorkEvent; $('cancelSubmissionCorrection').hidden = !state.editingSubmissionEvent;
    $('recordFollowup').disabled = !measurement || !state.report?.submitted_at;
    const assign = measurement && (isOwner(state.report) || state.permissions.has('emergency.audit.read_all'));
    $('reviewerSelect').disabled = !assign; $('assignReviewer').disabled = !assign || !$('reviewerSelect').value;
    $('loadTruthReview').disabled = !canTruthReview() || state.busy || !state.report?.initial_run;
    $('truthRunSelect').disabled = !canTruthReview() || state.busy || !state.report?.initial_run;
    $('openTruthSource').disabled = !canTruthReview() || state.busy || !state.truthRun;
    for (const id of ['addMissedError', 'wholeReportChecked', 'truthReviewComplete', 'saveTruthReview']) $(id).disabled = !canTruthReview() || !state.truthRun || state.busy;
    $('wholeReportChecked').disabled = $('wholeReportChecked').disabled || !originalVisibleFor(state.truthRun?.revision_id);
    $('truthReviewComplete').disabled = $('truthReviewComplete').disabled || !originalVisibleFor(state.truthRun?.revision_id);
    for (const item of state.truthDrafts.values()) { item.truth.disabled = !canTruthReview() || state.busy; item.verified.disabled = item.truth.disabled; item.errorChoice.disabled = item.truth.disabled || item.truth.value !== 'error'; item.later.disabled = item.errorChoice.disabled; }
    $('measurementExportReports').disabled = !ready;
    $('exportMeasurements').disabled = !ready || state.busy || !state.reports.length;
    $('patternScope').disabled = !ready || state.patternBusy;
    $('loadPatterns').disabled = !ready || state.patternBusy || ($('patternScope').value === 'selected' ? !state.report : !state.reports.length);
    $('patternScopeNote').textContent = $('patternScope').value === 'selected' ? state.report ? '現在選択している報告書1件が対象です。' : '報告書を選択してください。' : state.reports.length ? '現在の一覧に表示している ' + (state.offset + 1) + '〜' + (state.offset + state.reports.length) + '件目が対象です。全報告書の集計ではありません。' : '一覧に報告書はありません。';
  }

  function revoke(url) { if (url) URL.revokeObjectURL(url); }
  function clearPreview() {
    state.previewIntent++; revoke(state.previewUrl); state.previewUrl = null;
    state.sourceShownRevision = null; state.page = 1;
    $('confirmOriginal').checked = false; $('wholeReportChecked').checked = false; $('truthReviewComplete').checked = false;
    $('pageLabel').textContent = 'ページ未選択';
    $('sourceImage').removeAttribute('src'); $('sourceImage').hidden = true;
    $('sourceRegions').replaceChildren(); $('sourceMessage').hidden = false;
    message('sourceMessage', '原本ページを選択してください。');
    $('sourceFrame').style.width = '100%'; $('previewZoom').value = '100';
    if (!state.sourceId) clearMappingPreview();
  }
  function clearReport() {
    state.intent++; state.previewIntent++; clearTimeout(state.pollTimer); state.pollTimer = null;
    state.report = null; state.stale = false; state.busy = false; state.fieldDirty = false; state.fieldDrafts.clear();
    state.revisionUpload = null; state.truthRun = null; state.truthDrafts.clear(); state.missedErrors = []; state.eventRetries.clear(); state.workCapture = null; state.decisionControls = [];
    state.truthIntent++; state.editingWorkEvent = null; state.editingSubmissionEvent = null;
    clearPatterns();
    clearPreview(); $('reportWorkspace').hidden = true; $('workspaceEmpty').hidden = false;
    for (const id of ['fieldList', 'findingList', 'findingSummary', 'revisionHistory', 'eventHistory', 'revisionDifference', 'measurementHistory', 'truthReviewList', 'missedErrorList', 'aiCandidates', 'truthRunSelect']) $(id).replaceChildren();
    for (const id of ['revisionFile', 'submittedAt', 'workStartedAt', 'workEndedAt']) $(id).value = '';
    for (const id of ['confirmOriginal', 'submissionConfirmed', 'wholeReportChecked', 'truthReviewComplete', 'followupComplete', 'workComplete']) $(id).checked = false;
    for (const id of ['fieldMessage', 'findingMessage', 'revisionMessage', 'measurementMessage', 'reviewerMessage', 'truthMessage', 'truthRunContext', 'reportMeta', 'reportMode', 'aiStatus']) message(id, '');
    $('reportHeading').textContent = '報告書'; $('measurementReport').textContent = '報告書を選択してください。';
    $('workTimerStatus').textContent = '計測していません。'; $('afterSubmission').value = '';
    $('recordWork').textContent = 'この時間を記録'; $('recordSubmission').textContent = '提出を記録';
    $('fieldProgress').textContent = '未確認'; $('checkStatus').textContent = '未検査'; $('jobStatus').textContent = ''; $('reportBanner').textContent = '';
    controls();
  }
  function reset() {
    state.generation++; state.listIntent++; state.configIntent++; state.catalogIntent++; state.uploadIntent++;
    state.permissions = new Set(); state.userId = null; state.capabilities = null;
    state.uploadBusy = false; state.configBusy = false; state.configPreflight = null; state.queue = []; state.reports = []; state.profiles = []; state.ruleSets = []; state.reviewers = []; state.sources = [];
    state.offset = 0; state.profileRecord = null; state.mappingFields = []; state.ruleSetRecord = null; state.ruleDrafts = [];
    state.profileDirty = false; state.configRequest = null; state.ruleRequest = null; state.sourceId = null; state.sourceMetadata = null; state.sourceUpload = null; state.mappingStart = null; state.mappingPreview = null;
    state.configPreviewIntent++; revoke(state.configPreviewUrl); state.configPreviewUrl = null;
    for (const url of state.transientUrls) revoke(url); state.transientUrls.clear(); clearReport();
    for (const id of ['reportList', 'uploadQueue', 'profileList', 'mappedFieldList', 'ruleList', 'catalogList', 'configurationHuman']) $(id).replaceChildren();
    for (const id of ['profileSelect', 'revisionProfile', 'checkRules', 'ruleField', 'ruleOtherField', 'reviewConfiguration', 'impactReports', 'measurementExportReports', 'reviewerSelect', 'sourceSelect']) $(id).replaceChildren();
    for (const id of ['uploadFiles', 'profileName', 'profileCode', 'profileValidFrom', 'profileValidTo', 'profileImport', 'configSourceFile', 'mappedFieldId', 'mappedFieldLabel', 'regionX0', 'regionY0', 'regionX1', 'regionY1', 'ruleCode', 'ruleSetLabel', 'ruleTitle', 'ruleValue', 'ruleMinimum', 'ruleMaximum', 'ruleSourceTitle', 'ruleSourceVersion', 'ruleSourcePage', 'ruleEvidence', 'catalogSearch']) $(id).value = '';
    for (const id of ['sourceVerified', 'mappingVerified']) $(id).checked = false;
    for (const id of ['uploadMessage', 'uploadSummary', 'profileMessage', 'profileStatus', 'mappingMessage', 'configSourceMessage', 'ruleMessage', 'impactSummary', 'configurationDefinition', 'configurationReviewMessage', 'catalogMessage', 'exportMessage']) message(id, '');
    $('mappingImage').removeAttribute('src'); $('mappingImage').hidden = true; $('mappingSelection').hidden = true;
    $('mappingHint').hidden = false; $('catalogCount').textContent = ''; state.catalogItems = []; state.catalogTotal = 0;
    message('reportListMessage', 'ログインと権限を確認してから再読込してください。');
    message('auditMessage', 'セッションまたは権限が変わりました。ホームから再ログインしてください。', true); controls();
  }
  // Lock before the shared session check, then unlock immediately before its
  // authorized click replay. Otherwise a delayed reset can erase fresh input.
  window.emergencyAuditSessionPreflight = (target, eventType) => {
    if (eventType !== 'click' || !canRead() || state.configBusy || (!['newProfile', 'newRule', 'addMappedField', 'cancelMappedField'].includes(target.id) && target.dataset.auditConfigReset !== 'true')) return;
    const operation = {generation: state.generation}; state.configPreflight = operation;
    state.configBusy = true; state.mappingStart = null; controls();
    return () => {
      if (state.configPreflight !== operation || operation.generation !== state.generation) return;
      state.configPreflight = null; state.configBusy = false; controls();
    };
  };
  window.FireAISession.install({reset});

  async function responseFor(path, options = {}) {
    let response;
    try { response = await fetch(base + path, {...options, cache: 'no-store'}); }
    catch (error) { if (error.cancelled) throw error; throw safeError('通信を完了できませんでした。接続を確認して再試行してください。'); }
    if (!response.ok) {
      if (response.status === 401 || response.status === 403) { window.FireAISession.invalidate(); throw cancelled(); }
      const messages = {400: '入力形式を確認してください。', 404: '記録が見つかりません。再読込して確認してください。', 409: '記録の版や操作の条件が変わっています。再読込して確認してください。', 413: 'ファイルまたは記録が上限を超えています。容量と件数を確認してください。', 415: 'この形式は取り込めません。対応するPDF・画像を選んでください。', 422: '入力内容と操作の条件を確認してください。原本や設定は変更していません。', 429: '処理が混み合っています。時間を置いて再試行してください。', 503: '現在この処理を利用できません。稼働状態を確認して再試行してください。'};
      throw safeError(messages[response.status] ?? '処理を完了できませんでした。再読込して利用環境を確認してください。', response.status);
    }
    return response;
  }
  async function request(path, method = 'GET', body) {
    const response = await responseFor(path, {method, ...(body === undefined ? {} : {headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})});
    try { return await response.json(); } catch (error) { if (error.cancelled) throw error; throw safeError('応答を確認できませんでした。再読込してください。'); }
  }
  async function upload(path, data) { const response = await responseFor(path, {method: 'POST', body: data}); return response.json(); }
  function fail(id, error, t = null) {
    if (error.cancelled || (t && !current(t))) return;
    message(id, error.safe ? error.message : '操作を完了できませんでした。内容を確認してやり直してください。', true);
    if (error.status === 409 && t && state.report) { state.stale = true; $('reportBanner').hidden = false; $('reportBanner').textContent = '保存されている記録を再読込してください。古い版への変更は保存しません。'; controls(); }
  }

  function renderReportList() {
    clearPatterns();
    $('reportList').replaceChildren();
    for (const report of state.reports) {
      const item = button('', () => selectReport(report.report_id), 'report-item' + (state.report?.report_id === report.report_id ? ' selected' : ''));
      item.dataset.reportId = report.report_id;
      item.append(element('strong', reportLabel(report)), element('span', (report.dataset_kind === 'synthetic' ? '合成データ' : '本部内の報告書') + ' · ' + (pendingJobs.has(report.job_status) ? '読み取り中' : report.job_status === 'failed' ? '読み取りを要確認' : '確認できます')));
      item.disabled = !!state.workCapture; $('reportList').append(item);
    }
    message('reportListMessage', state.reports.length ? '新しい報告書から表示しています。' : '閲覧できる報告書はありません。');
    const entries = state.reports.map(report => [report.report_id, reportLabel(report)]);
    setOptions('impactReports', entries); setOptions('measurementExportReports', entries);
    controls();
  }
  async function loadReports() {
    if (!canRead()) return;
    const generation = state.generation, intent = ++state.listIntent;
    try {
      const rows = await request('/reports?limit=30&offset=' + state.offset);
      if (generation !== state.generation || intent !== state.listIntent) return;
      state.reports = list(rows); renderReportList();
    } catch (error) { if (generation === state.generation && intent === state.listIntent) fail('reportListMessage', error); }
  }
  function stopPolling() { clearTimeout(state.pollTimer); state.pollTimer = null; }
  function schedulePoll() {
    stopPolling(); if (!state.report || !headSelected() || !reportPending()) return;
    const t = ticket(), identity = state.report.report_id;
    state.pollTimer = setTimeout(async () => {
      if (!current(t)) return;
      try {
        const report = await request('/reports/' + encodeURIComponent(identity));
        if (!current(t)) return;
        if (state.busy || report.version < state.report.version) { schedulePoll(); return; }
        if (state.fieldDirty) {
          if (report.version !== state.report.version) { state.stale = true; message('fieldMessage', '別の変更が保存されています。再読込して確認してください。', true); controls(); }
          else schedulePoll();
          return;
        }
        await renderReport(report); if (current(t)) schedulePoll();
      } catch (error) { if (current(t)) { fail('auditMessage', error, t); if (!error.cancelled) schedulePoll(); } }
    }, document.visibilityState === 'visible' ? 1500 : 6000);
  }
  async function selectReport(id, revisionId = null) {
    if (!canRead() || state.workCapture) return;
    clearReport(); const t = ticket(); state.busy = true; controls(); message('auditMessage', '報告書を読み込んでいます。');
    try {
      const report = await request(revisionId ? '/revisions/' + encodeURIComponent(revisionId) : '/reports/' + encodeURIComponent(id));
      if (!current(t)) return;
      await renderReport(report); if (!current(t)) return;
      message('auditMessage', '原本と読み取りを照合してください。確認候補は提出許可を示すものではありません。');
      schedulePoll(); renderReportList();
    } catch (error) { fail('auditMessage', error, t); }
    finally { if (current(t)) { state.busy = false; controls(); } }
  }
  async function renderReport(report) {
    const previous = state.report?.revision;
    const reloadOriginal = previous?.revision_id !== report.revision?.revision_id || (!previous?.page_count && report.revision?.page_count);
    if (reloadOriginal) clearPreview();
    state.report = report; state.stale = false;
    $('reportWorkspace').hidden = false; $('workspaceEmpty').hidden = true;
    $('reportHeading').textContent = '報告書 · 版 ' + (report.revision?.number ?? report.revision_number ?? 1);
    $('reportMode').textContent = report.dataset_kind === 'synthetic' ? '合成データ・操作確認' : '本部内の報告書';
    $('reportMeta').textContent = formatDate(report.created_at) + '登録 / ' + (report.revision?.page_count ?? '未確認') + 'ページ';
    $('reportBanner').hidden = report.dataset_kind !== 'synthetic' && headSelected();
    $('reportBanner').textContent = !headSelected() ? '過去の原本と、その版の確認結果を表示しています。変更するには最新の報告書を開いてください。' : '合成データの操作確認です。実帳票の精度や訂正削減の実測ではありません。';
    const job = report.job_status ?? report.revision?.processing_status;
    const partial = report.revision?.processing_status === 'partial';
    $('jobPanel').hidden = !pendingJobs.has(job) && !['failed', 'error', 'exhausted'].includes(job) && !partial;
    $('jobStatus').textContent = pendingJobs.has(job) ? '読み取り処理を進めています。原本は保存されています。' : partial ? '読み取りが終わっていないページがあります。原本を確認し、必要に応じて再試行してください。' : '読み取りを完了できませんでした。原本と設定を確認して再試行してください。';
    $('revisionProfile').value = report.revision?.profile_id ?? '';
    renderFields(); renderFindings(); renderHistory(); renderMeasurement(); renderAI();
    controls();
    if (reloadOriginal) await loadPage(1);
    else if (originalVisibleFor(report.revision?.revision_id)) renderRegions();
  }
  async function loadPage(page) {
    if (!state.report || !canRead()) return;
    const revision = state.report.revision, t = ticket(), intent = ++state.previewIntent;
    state.page = page; revoke(state.previewUrl); state.previewUrl = null; state.sourceShownRevision = null;
    $('confirmOriginal').checked = false; $('wholeReportChecked').checked = false; $('truthReviewComplete').checked = false;
    $('sourceImage').removeAttribute('src'); $('sourceImage').hidden = true; $('sourceRegions').replaceChildren();
    if (!state.sourceId) clearMappingPreview();
    $('sourceMessage').hidden = false; message('sourceMessage', '原本ページを読み込んでいます。');
    $('pageLabel').textContent = page + ' / ' + (revision.page_count ?? '未確認') + 'ページ'; controls();
    if (!revision.page_count) { message('sourceMessage', '読み取りが終わると原本ページを表示できます。'); return; }
    try {
      const response = await responseFor('/revisions/' + encodeURIComponent(revision.revision_id) + '/pages/' + page + '.png');
      const blob = await response.blob();
      if (!current(t) || intent !== state.previewIntent || state.report?.revision?.revision_id !== revision.revision_id) return;
      if (blob.type.split(';')[0] !== 'image/png') throw safeError('原本ページの応答形式を確認できませんでした。');
      const url = URL.createObjectURL(blob); state.previewUrl = url;
      $('sourceImage').src = url; await $('sourceImage').decode();
      if (!current(t) || intent !== state.previewIntent || state.report?.revision?.revision_id !== revision.revision_id || state.previewUrl !== url) { revoke(url); return; }
      state.sourceShownRevision = revision.revision_id; $('sourceImage').hidden = false; $('sourceMessage').hidden = true;
      if (!state.sourceId) showReportMappingPreview();
      renderRegions(); controls();
    } catch (error) {
      if (current(t) && intent === state.previewIntent) {
        revoke(state.previewUrl); state.previewUrl = null; state.sourceShownRevision = null;
        $('sourceImage').removeAttribute('src'); $('sourceImage').hidden = true;
        fail('sourceMessage', error, t); controls();
      }
    }
  }
  function validBox(box) { return Array.isArray(box) && box.length === 4 && box.every(x => typeof x === 'number' && Number.isFinite(x) && x >= 0 && x <= 1) && box[2] > box[0] && box[3] > box[1]; }
  function positionBox(node, box) { node.style.left = box[0] * 100 + '%'; node.style.top = box[1] * 100 + '%'; node.style.width = (box[2] - box[0]) * 100 + '%'; node.style.height = (box[3] - box[1]) * 100 + '%'; }
  function renderRegions() {
    $('sourceRegions').replaceChildren();
    for (const [id, field] of Object.entries(state.report?.revision?.fields ?? {})) {
      for (const evidence of fieldEvidence(field)) {
        if (evidence?.page !== state.page || !validBox(evidence?.bbox)) continue;
        const region = button('', () => focusField(id), 'source-region');
        region.setAttribute('aria-label', field.label + 'の確認欄へ移動'); region.dataset.fieldId = id; positionBox(region, evidence.bbox); $('sourceRegions').append(region);
      }
    }
    for (const [index, candidate] of list(state.report?.revision?.ai_result?.candidates).entries()) {
      if (candidate.page !== state.page || !validBox(candidate.bbox)) continue;
      const region = button('', () => { const card = $('ai-candidate-' + index); if (card) { card.scrollIntoView({block: 'center', behavior: 'smooth'}); card.focus(); } }, 'source-region ai-region');
      region.setAttribute('aria-label', '未確認の画像候補 ' + (index + 1)); positionBox(region, candidate.bbox); $('sourceRegions').append(region);
    }
  }
  function focusField(id) {
    for (const [key, field] of state.fieldDrafts) field.container.classList.toggle('active', key === id);
    const selected = state.fieldDrafts.get(id);
    if (selected) { selected.container.scrollIntoView({block: 'center', behavior: 'smooth'}); selected.stateControl.focus(); }
  }
  function fieldChanged() { state.fieldDirty = true; $('confirmOriginal').checked = false; message('fieldMessage', '変更はまだ保存されていません。原本との照合後に保存してください。'); controls(); }
  function renderFields() {
    state.fieldDrafts.clear(); state.fieldDirty = false; $('confirmOriginal').checked = false; $('fieldList').replaceChildren();
    const fields = Object.entries(state.report?.revision?.fields ?? {});
    let confirmed = 0;
    for (const [id, field] of fields) {
      if (field.state === 'confirmed') confirmed++;
      const container = element('article', undefined, 'review-field'); container.dataset.fieldId = id;
      const heading = element('div', undefined, 'review-field-heading');
      heading.append(element('strong', field.label || id), badge(readStates[field.state] ?? '対応が未設定', field.state === 'confirmed' ? 'confirmed' : ''));
      const evidence = element('p', undefined, 'evidence');
      const firstEvidence = fieldEvidence(field)[0];
      evidence.textContent = firstEvidence?.page ? '原本 ' + firstEvidence.page + 'ページ / ' + ({pdf_text: 'PDFの文字', ocr: '画像の読み取り', tesseract: '画像の読み取り', manual: '手動確認'}[firstEvidence.method] ?? '読み取り候補') + (typeof firstEvidence.confidence === 'number' ? ' / 読取確度 ' + Math.round(firstEvidence.confidence * 100) + '%' : ' / 読取確度は未評価') : '原本の対応位置は未確認です。';
      const candidate = element('p', '読取候補：' + (scalarText(field.candidate) || '取得できていません'), 'small muted');
      const stateLabel = element('label', '読取状態', 'field'), stateControl = element('select'); stateControl.id = 'field-state-' + id;
      for (const [value, label] of Object.entries(readStates)) stateControl.append(option(value, label)); stateControl.value = Object.hasOwn(readStates, field.state) ? field.state : 'unmapped'; stateLabel.append(stateControl);
      const valueLabel = element('label', '原本で確認した値', 'field');
      const valueControl = element(field.value_type === 'boolean' ? 'select' : 'input'); valueControl.id = 'field-value-' + id;
      if (field.value_type === 'boolean') { valueControl.append(option('', '選択してください'), option('true', 'はい'), option('false', 'いいえ')); }
      else {
        valueControl.type = field.value_type === 'number' ? 'number' : ['date', 'time'].includes(field.value_type) ? field.value_type : 'text';
        valueControl.maxLength = 2000;
        if (field.value_type === 'number') valueControl.step = 'any';
        if (field.value_type === 'time') valueControl.step = '1';
        if (field.value_type === 'datetime') valueControl.placeholder = '例：2026-01-01T09:00:00+09:00';
      }
      valueControl.value = scalarText(field.state === 'confirmed' ? field.value : field.candidate); valueLabel.append(valueControl);
      const blankLabel = element('label', undefined, 'check-label'), blankControl = element('input'); blankControl.type = 'checkbox'; blankControl.id = 'field-blank-' + id; blankControl.checked = field.state === 'confirmed' && field.value === null; blankLabel.append(blankControl, document.createTextNode('原本の空欄を確認した'));
      const inputs = element('div', undefined, 'field-controls'); inputs.append(stateLabel, valueLabel);
      container.append(heading, evidence, candidate, inputs, blankLabel); $('fieldList').append(container);
      stateControl.addEventListener('change', fieldChanged); valueControl.addEventListener('input', fieldChanged); valueControl.addEventListener('change', fieldChanged); blankControl.addEventListener('change', fieldChanged);
      state.fieldDrafts.set(id, {field, container, stateControl, valueControl, blankControl});
    }
    $('fieldProgress').textContent = confirmed + ' / ' + fields.length + '欄を確認';
    if (!fields.length) $('fieldList').append(element('p', reportPending() ? '読み取りが終わるまでお待ちください。' : '対応する入力欄がありません。帳票の対応表を選ぶか設定してください。', 'small muted'));
  }
  function typedValue(raw, type) {
    if (type === 'number') { if (!raw.trim() || !Number.isFinite(Number(raw))) throw safeError('数値欄に有効な数値を入力してください。空欄は「原本の空欄」で指定します。'); return Number(raw); }
    if (type === 'boolean') { if (!['true', 'false'].includes(raw)) throw safeError('はい・いいえを選択してください。'); return raw === 'true'; }
    if (!raw.trim()) throw safeError('値がない欄は「原本の空欄を確認した」を選択してください。');
    return raw;
  }
  async function mutate(path, body, messageId, success) {
    if (!state.report || state.busy) return;
    const t = ticket(); state.busy = true; controls();
    try {
      const detail = await request(path, 'POST', body);
      if (!current(t)) return;
      await renderReport(detail); if (!current(t)) return;
      message(messageId, success); await loadReports(); schedulePoll();
      return detail;
    } catch (error) { fail(messageId, error, t); }
    finally { if (current(t)) { state.busy = false; controls(); } }
  }
  async function saveFields() {
    if (!writable() || !state.fieldDirty || !$('confirmOriginal').checked) return;
    if (!originalVisibleFor(state.report.revision.revision_id)) { message('fieldMessage', 'この版の原本ページを表示し、照合してから確認内容を保存してください。', true); return; }
    try {
      const fields = [...state.fieldDrafts].map(([id, item]) => ({field_id: id, state: item.stateControl.value, value: item.stateControl.value === 'confirmed' && !item.blankControl.checked ? typedValue(item.valueControl.value, item.field.value_type) : null}));
      await mutate('/revisions/' + state.report.revision.revision_id + '/fields', {expected_version: state.report.version, confirmed_from_original: true, fields}, 'fieldMessage', '原本と照合した内容を保存しました。変更前のチェックは再実行してください。');
    } catch (error) { fail('fieldMessage', error, ticket()); }
  }
  function sourceReference(value) {
    if (typeof value === 'string') return value;
    if (!value || typeof value !== 'object') return '根拠の参照情報は未登録です。';
    return [value.document_title, value.version, value.page ? value.page + 'ページ' : null, value.section].filter(x => ['string', 'number'].includes(typeof x)).join(' / ') || '根拠の参照情報は未登録です。';
  }
  function renderFindings() {
    $('findingList').replaceChildren(); $('findingSummary').replaceChildren(); $('revisionDifference').replaceChildren(); state.decisionControls = [];
    const run = state.report?.last_run;
    $('checkStatus').textContent = run ? run.stale ? '古い結果' : '検査結果あり' : '未検査';
    $('checkMeta').textContent = !run ? '保存した読み取りの状態でチェックできます。未確認の欄は未検査として残ります。' : run.stale ? '読み取りや原本の変更前の結果です。最新の内容で再チェックしてください。' : 'この結果は、表示された条件で検査した範囲だけの確認候補です。提出の許可や報告書全体の適正を示しません。';
    if (!run) return;
    for (const [status, label] of Object.entries(findingStates)) $('findingSummary').append(badge(label + ' ' + (run.counts?.[status] ?? list(run.findings).filter(x => x.status === status).length), status === 'REVIEW_REQUIRED' ? 'warning' : ''));
    for (const finding of list(run.findings)) {
      const card = element('article', undefined, 'finding-card ' + (finding.status === 'REVIEW_REQUIRED' ? 'warning' : finding.status === 'NO_ISSUE_DETECTED' ? 'clear' : ''));
      card.dataset.ruleId = finding.rule_id;
      card.append(badge(findingStates[finding.status] ?? '未検査', finding.status === 'REVIEW_REQUIRED' ? 'warning' : ''), element('h4', finding.message || finding.rule_id), element('p', sourceReference(finding.source_reference), 'muted'));
      card.append(element('p', finding.rule_approval === 'APPROVED' || finding.rule_approval === 'approved' ? '承認済みの条件を使用' : '暫定の確認候補・正式な運用承認は未確認', 'small muted'));
      const related = element('div', undefined, 'toolbar');
      for (const id of list(finding.fields)) { const field = state.report.revision?.fields?.[id]; related.append(button(field?.label || id, async () => { const evidence = fieldEvidence(field)[0]; if (evidence?.page) await loadPage(evidence.page); focusField(id); }, 'text-button')); }
      card.append(related);
      const review = element('div', undefined, 'decision-controls'), choice = element('select'); choice.setAttribute('aria-label', 'この候補の確認結果'); choice.id = 'decision-choice-' + finding.rule_id; choice.className = 'decision-choice';
      choice.append(option('', '確認結果を選択')); for (const [value, label] of Object.entries(decisions)) choice.append(option(value, label));
      const previous = Array.isArray(run.decisions) ? run.decisions.find(x => x.rule_id === finding.rule_id)?.decision : run.decisions?.[finding.rule_id];
      choice.value = previous ?? '';
      const reason = selectControl('decision-reason-' + finding.rule_id, Object.entries(reasonLabels), 'unknown'); reason.setAttribute('aria-label', '判断した理由');
      const previousReason = Array.isArray(run.decisions) ? run.decisions.find(x => x.rule_id === finding.rule_id)?.reason_code : run.decision_reasons?.[finding.rule_id];
      if (Object.hasOwn(reasonLabels, previousReason)) reason.value = previousReason;
      const save = button('記録', () => saveDecision(finding.rule_id, choice.value, reason.value)); save.id = 'decision-save-' + finding.rule_id;
      choice.disabled = !canRecordDecision() || run.stale; save.disabled = !canRecordDecision() || run.stale;
      review.append(choice, reason, save); card.append(review); $('findingList').append(card); state.decisionControls.push({choice, reason, save});
    }
    const changeLabels = {resolved: 'この検査で指摘がなくなった項目', persistent: '引き続き確認が必要', new: '新しく確認が必要', untested: '未検査の項目'};
    for (const [kind, label] of Object.entries(changeLabels)) {
      const ids = list(run.changes?.[kind]); if (!ids.length) continue;
      const row = element('div', undefined, 'difference-item'); row.append(element('span', label), element('strong', ids.length + '件')); $('revisionDifference').append(row);
      $('revisionDifference').append(element('p', ids.join('、'), 'small muted'));
    }
  }
  async function runCheck() {
    if (!writable() || state.fieldDirty || reportPending() || state.report?.measurement?.cohort === 'baseline') return;
    const mode = $('checkMode').value, ruleSet = $('checkRules').value || null;
    if (mode === 'approved' && !ruleSet) { message('findingMessage', '承認済みのルールセットを選択してください。初期候補は候補モードで確認します。', true); return; }
    if (!$('checkDate').value) { message('findingMessage', '適用を確認する日を入力してください。', true); return; }
    await mutate('/revisions/' + state.report.revision.revision_id + '/checks', {expected_version: state.report.version, rule_set_id: ruleSet, mode, as_of: $('checkDate').value}, 'findingMessage', 'チェック結果を保存しました。未検査・適用対象外の項目も確認してください。');
  }
  async function saveDecision(ruleId, decision, reasonCode) {
    if (!canRecordDecision() || !state.report.last_run || state.report.last_run.stale || !Object.hasOwn(decisions, decision)) return;
    if (!Object.hasOwn(reasonLabels, reasonCode)) return;
    const updated = [{rule_id: ruleId, decision, reason_code: reasonCode}];
    await mutate('/runs/' + state.report.last_run.run_id + '/decisions', {expected_version: state.report.version, decisions: updated}, 'findingMessage', '候補の確認結果を記録しました。独立した正誤の評価は別担当者が行います。');
  }
  function renderAI() {
    const result = state.report?.revision?.ai_result;
    $('aiCandidates').replaceChildren();
    const statuses = {NOT_CONFIGURED: 'この環境に候補読取用のモデルは設定されていません。通常の確認とチェックは継続できます。', UNAVAILABLE: '候補の読み取りを完了できませんでした。原本を確認してください。', NO_CANDIDATE: '今回の処理では候補はありませんでした。記載の正しさや見落としがないことを示す結果ではありません。', REVIEW_REQUIRED: '未確認の候補です。原本と照合するまで入力欄の確認値には使いません。'};
    $('aiStatus').textContent = result ? statuses[result.status] ?? '候補の処理状態を確認してください。' : !aiConfigured() ? statuses.NOT_CONFIGURED : '必要な場合だけ、保存した内容や画像から未確認の候補を作成します。';
    for (const [index, candidate] of list(result?.candidates).entries()) {
      const card = element('article', undefined, 'finding-card warning'); card.id = 'ai-candidate-' + index; card.tabIndex = -1;
      const kind = {printed: '活字', handwritten: '手書き', strikeout: '取消線'}[candidate.kind] ?? '記載の整合性';
      card.append(badge('未確認', 'warning'), element('h4', kind + 'の候補 / ' + candidate.page + 'ページ'));
      if (candidate.text !== null && candidate.text !== undefined) card.append(element('p', candidate.text));
      if (candidate.quote) card.append(element('p', candidate.quote));
      if (candidate.reason) card.append(element('p', candidate.reason, 'muted'));
      if (candidate.suggested_text) card.append(element('p', '修正案（未確認）：' + candidate.suggested_text, 'muted'));
      card.append(button('原本の該当ページを見る', async () => { await loadPage(candidate.page); $('sourceViewport').scrollIntoView({block: 'center', behavior: 'smooth'}); }, 'text-button'));
      $('aiCandidates').append(card);
    }
  }
  function renderHistory() {
    $('revisionHistory').replaceChildren(); $('eventHistory').replaceChildren();
    for (const revision of list(state.report?.revisions)) {
      const row = element('div', undefined, 'history-entry');
      row.append(button('版 ' + (revision.number ?? revision.revision_number ?? '?') + (revision.revision_id === state.report.current_revision_id ? '（最新）' : ''), () => selectReport(state.report.report_id, revision.revision_id), 'text-button'), element('span', ' ' + formatDate(revision.created_at)));
      $('revisionHistory').append(row);
    }
    for (const event of list(state.report?.events).slice(-30).reverse()) {
      const row = element('div', undefined, 'history-entry'); row.append(element('strong', eventLabels[event.kind] ?? '確認作業の記録'), element('span', formatDate(event.occurred_at ?? event.created_at))); $('eventHistory').append(row);
    }
  }

  function validateFile(file) {
    if (!file || !Number.isFinite(file.size) || file.size < 1 || file.size > Math.min(MAX_FILE_BYTES, state.capabilities?.limits?.max_file_bytes ?? MAX_FILE_BYTES)) throw safeError('空のファイル、または25 MiBを超えるファイルは選択できません。');
    if (!/\.(pdf|png|jpe?g)$/i.test(file.name ?? '') || (file.type && !['application/pdf', 'image/png', 'image/jpeg'].includes(file.type))) throw safeError('PDF・PNG・JPEGのファイルを選択してください。');
  }
  function renderQueue() {
    $('uploadQueue').replaceChildren();
    const done = state.queue.filter(item => item.status === 'done').length, failed = state.queue.filter(item => item.status === 'failed').length;
    const currentIndex = state.queue.findIndex(item => item.status === 'uploading' || item.status === 'pending');
    const visible = new Set(state.queue.map((item, index) => ({item, index})).filter(({item}) => item.status === 'failed').slice(0, 30).map(({index}) => index));
    const start = Math.max(0, (currentIndex < 0 ? state.queue.length : currentIndex) - 10);
    for (let index = start; index < Math.min(state.queue.length, start + 30); index++) visible.add(index);
    $('uploadSummary').textContent = state.queue.length ? '選択 ' + state.queue.length + '件 / 保存 ' + done + '件 / 要再試行 ' + failed + '件' : '';
    for (const index of [...visible].sort((a, b) => a - b)) {
      const item = state.queue[index];
      const row = element('div', undefined, 'queue-item ' + item.status);
      row.append(element('strong', 'ファイル ' + (index + 1)), element('span', {pending: '取込待ち', uploading: '安全性を確認して取り込み中', done: '原本を保存・読み取り待ち', failed: '取り込みを完了できませんでした'}[item.status], 'queue-state'));
      if (item.status === 'failed' && item.file) {
        const retry = button('再試行', () => retryUpload(index), 'text-button'); retry.id = 'retry-upload-' + index; retry.disabled = state.uploadBusy; row.append(retry);
      }
      $('uploadQueue').append(row);
    }
    controls();
  }
  function chooseFiles() {
    if (!canWrite() || state.uploadBusy) return;
    state.uploadIntent++; state.queue = [];
    const files = Array.from($('uploadFiles').files ?? []);
    try {
      if (files.length > 1000) throw safeError('一度に選択できるファイルは1,000件までです。');
      for (const file of files) validateFile(file);
      state.queue = files.map(file => ({file, requestId: crypto.randomUUID(), status: 'pending', attempted: false, dataset: $('datasetKind').value, profileId: $('profileSelect').value || null}));
      message('uploadMessage', files.length ? files.length + '件を選択しました。内容を確認して取り込みを始めてください。' : '');
    } catch (error) { fail('uploadMessage', error); }
    $('uploadFiles').value = ''; renderQueue();
  }
  function updateQueuedOptions() {
    if (state.uploadBusy) return;
    for (const item of state.queue) if (!item.attempted) { item.dataset = $('datasetKind').value; item.profileId = $('profileSelect').value || null; }
    if (state.queue.some(item => item.attempted && item.status === 'failed')) message('uploadMessage', '再試行するファイルは、最初に取り込んだデータ区分・対応表を保ちます。');
  }
  async function processQueue() {
    if (!canWrite() || state.uploadBusy || !state.capabilities?.enabled || !state.capabilities?.storage_ready) return;
    const generation = state.generation, intent = state.uploadIntent;
    state.uploadBusy = true; controls(); let lastReport = null;
    try {
      for (const item of state.queue) {
        if (generation !== state.generation || intent !== state.uploadIntent) return;
        if (item.status !== 'pending') continue;
        item.status = 'uploading'; item.attempted = true; renderQueue();
        try {
          if (item.dataset === 'internal_trial' && !state.capabilities.internal_enabled) throw safeError('本部内の報告書は、この環境では取り込めません。');
          const data = new FormData(); data.append('file', item.file, item.file.name); data.append('request_id', item.requestId); data.append('dataset_kind', item.dataset);
          if (item.profileId) data.append('profile_id', item.profileId);
          const report = await upload('/reports', data);
          if (generation !== state.generation || intent !== state.uploadIntent) return;
          item.status = 'done'; item.file = null; lastReport = report.report_id;
        } catch (error) {
          if (generation !== state.generation || intent !== state.uploadIntent || error.cancelled) return;
          item.status = 'failed'; fail('uploadMessage', error);
        }
        renderQueue();
      }
      if (generation === state.generation && intent === state.uploadIntent) {
        const failed = state.queue.filter(item => item.status === 'failed').length;
        message('uploadMessage', failed ? '取り込みできなかったファイルが' + failed + '件あります。接続と原本を確認して再試行できます。' : '原本を保存しました。読み取りの進み具合は報告書で確認できます。', failed > 0);
        await loadReports();
      }
    } finally {
      if (generation === state.generation && intent === state.uploadIntent) { state.uploadBusy = false; renderQueue(); if (lastReport) await selectReport(lastReport); }
    }
  }
  function retryUpload(index) { const item = state.queue[index]; if (!canWrite() || state.uploadBusy || !item?.file || item.status !== 'failed') return; item.status = 'pending'; return processQueue(); }
  function retryFailedUploads() { if (!canWrite() || state.uploadBusy) return; for (const item of state.queue) if (item.status === 'failed' && item.file) item.status = 'pending'; return processQueue(); }
  async function uploadRevision() {
    if (!writable() || !$('revisionFile').files?.length) return;
    const t = ticket(), file = $('revisionFile').files[0];
    try {
      validateFile(file);
      if (!state.revisionUpload || state.revisionUpload.file !== file) state.revisionUpload = {file, requestId: crypto.randomUUID(), expectedVersion: state.report.version};
      const pending = state.revisionUpload, data = new FormData();
      data.append('file', file, file.name); data.append('request_id', pending.requestId); data.append('expected_version', String(pending.expectedVersion));
      if (state.report.revision.profile_id) data.append('profile_id', state.report.revision.profile_id);
      state.busy = true; controls(); message('revisionMessage', '修正後の原本を取り込んでいます。');
      const updated = await upload('/reports/' + state.report.report_id + '/revisions', data);
      if (!current(t)) return;
      state.revisionUpload = null; $('revisionFile').value = ''; await renderReport(updated); if (!current(t)) return;
      await loadReports(); schedulePoll();
      message('revisionMessage', '新しい版を保存しました。読み取りの確認後に再チェックしてください。');
    } catch (error) { fail('revisionMessage', error, t); }
    finally { if (current(t)) { state.busy = false; controls(); } }
  }
  async function downloadBlob(blob, filename, generation) {
    if (generation !== state.generation) return;
    const url = URL.createObjectURL(blob); state.transientUrls.add(url);
    const link = element('a'); link.href = url; link.download = filename; document.body.append(link); link.click(); link.remove();
    setTimeout(() => { revoke(url); state.transientUrls.delete(url); }, 1000);
  }
  async function downloadOriginal() {
    if (!state.report || !canRead()) return;
    const t = ticket(), revision = state.report.revision;
    try {
      const response = await responseFor('/revisions/' + revision.revision_id + '/original'); const blob = await response.blob(); if (!current(t)) return;
      const ext = {'application/pdf': 'pdf', 'image/png': 'png', 'image/jpeg': 'jpg'}[revision.media_type] ?? 'bin';
      await downloadBlob(blob, 'report-original-' + revision.number + '.' + ext, t.generation);
    } catch (error) { fail('sourceMessage', error, t); }
  }
  function switchTab(name) {
    if (!canRead()) return;
    if (state.fieldDirty && name !== 'reports') { message('auditMessage', '読み取りの変更を保存してから画面を切り替えてください。', true); return; }
    state.activeTab = name;
    for (const view of ['reports', 'configuration', 'catalog', 'measurement']) {
      $(view + 'View').hidden = view !== name; $(view + 'Tab').classList.toggle('active', view === name);
      if (view === name) $(view + 'Tab').setAttribute('aria-current', 'page'); else $(view + 'Tab').removeAttribute('aria-current');
    }
    if (name === 'catalog') return loadCatalog();
    if (name === 'measurement') renderMeasurement();
  }

  function configChanged() { state.profileDirty = true; state.configRequest = null; state.ruleRequest = null; controls(); }
  function clearMappingPreview() {
    state.mappingPreview = null; state.mappingStart = null;
    $('mappingImage').removeAttribute('src'); $('mappingImage').hidden = true;
    $('mappingHint').hidden = false; $('mappingSelection').hidden = true;
  }
  function mappingPageVisible() {
    const preview = state.mappingPreview;
    if (!preview || $('mappingImage').hidden || $('mappingImage').src !== preview.url || Number($('mappedFieldPage').value) !== preview.page) return false;
    return state.sourceId ? preview.kind === 'source' && preview.id === state.sourceId
      : preview.kind === 'revision' && preview.id === state.report?.revision?.revision_id && preview.page === state.page && preview.url === state.previewUrl && originalVisibleFor(preview.id);
  }
  function showReportMappingPreview() {
    if (state.sourceId || !originalVisibleFor(state.report?.revision?.revision_id)) return;
    state.mappingPreview = {kind: 'revision', id: state.report.revision.revision_id, page: state.page, url: state.previewUrl};
    $('mappingImage').src = state.previewUrl; $('mappingImage').hidden = false; $('mappingHint').hidden = true;
    showMappingSelection();
  }
  function invalidateMappingPage() {
    state.configPreviewIntent++; revoke(state.configPreviewUrl); state.configPreviewUrl = null; clearMappingPreview();
    if (!state.sourceId) clearPreview();
    controls();
  }
  async function loadMappingPage(page) {
    invalidateMappingPage();
    const maximum = state.sourceId ? state.sourceMetadata?.page_count ?? 50 : state.report?.revision?.page_count ?? 0;
    if (!Number.isInteger(page) || page < 1 || page > maximum) { message('mappingMessage', '登録する範囲に対応する原本と、有効なページを選択してください。', true); return; }
    if (state.sourceId) await loadConfigPage(page);
    else if (state.report) await loadPage(page);
    showMappingSelection(); controls();
  }
  function clearFieldEditor() {
    state.editingField = null; state.mappingStart = null;
    for (const id of ['mappedFieldId', 'mappedFieldLabel', 'regionX0', 'regionY0', 'regionX1', 'regionY1']) $(id).value = '';
    $('mappedFieldType').value = 'text'; $('mappedFieldPage').value = String(state.mappingPreview?.page ?? 1); $('mappingSelection').hidden = true;
    $('saveMappedField').textContent = 'この欄を追加';
    controls();
  }
  function renderMappedFields() {
    $('mappedFieldList').replaceChildren();
    for (const field of state.mappingFields) {
      const row = element('div', undefined, 'mapped-field-item'), text = element('div');
      text.append(element('strong', field.label), element('div', field.field_id + ' / ' + field.page + 'ページ / ' + ({region: '範囲を指定', manual: '手動確認', not_printed: '印刷されない欄'}[field.extraction] ?? '未設定'), 'small muted'));
      const tools = element('div', undefined, 'toolbar');
      const edit = button('編集', () => editMappedField(field.field_id), 'text-button'); edit.dataset.auditConfigReset = 'true';
      tools.append(edit, button('削除', () => { if (!canConfigure() || state.configBusy) return; state.mappingFields = state.mappingFields.filter(x => x.field_id !== field.field_id); configChanged(); renderMappedFields(); }, 'text-button'));
      for (const control of tools.children) control.disabled = !canConfigure();
      row.append(text, tools); $('mappedFieldList').append(row);
    }
    const entries = state.mappingFields.map(field => [field.field_id, field.label]); setOptions('ruleField', entries, '選択してください'); setOptions('ruleOtherField', entries, '選択してください');
    $('profilePageCount').value = String(Math.max(1, ...state.mappingFields.map(field => field.page)));
  }
  async function editMappedField(id) {
    if (!canConfigure() || state.configBusy) return;
    const field = state.mappingFields.find(x => x.field_id === id); if (!field) return;
    state.editingField = id; $('mappedFieldId').value = field.field_id; $('mappedFieldLabel').value = field.label; $('mappedFieldType').value = field.value_type; $('mappedFieldPage').value = String(field.page);
    for (const [index, key] of ['regionX0', 'regionY0', 'regionX1', 'regionY1'].entries()) $(key).value = field.bbox ? String(field.bbox[index]) : '';
    $('saveMappedField').textContent = 'この欄を更新'; await loadMappingPage(field.page);
  }
  function showMappingSelection() {
    const box = ['regionX0', 'regionY0', 'regionX1', 'regionY1'].map(id => $(id).value.trim() === '' ? NaN : Number($(id).value));
    $('mappingSelection').hidden = !mappingPageVisible() || !validBox(box); if (!$('mappingSelection').hidden) positionBox($('mappingSelection'), box);
    controls();
  }
  function saveMappedField() {
    if (!canConfigure() || state.configBusy) return;
    try {
      const fieldId = $('mappedFieldId').value.trim(), label = $('mappedFieldLabel').value.trim(), page = Number($('mappedFieldPage').value);
      if (!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/.test(fieldId) || !label || label.length > 100 || !Number.isInteger(page) || page < 1 || page > 50) throw safeError('項目ID・表示名・ページ番号を確認してください。項目IDは英数字で始まる64文字以内の英数字・_・.・-です。');
      if (state.mappingFields.some(field => field.field_id === fieldId && field.field_id !== state.editingField)) throw safeError('同じ項目IDが既にあります。');
      const coordinates = ['regionX0', 'regionY0', 'regionX1', 'regionY1'].map(id => $(id).value.trim());
      if (coordinates.some(value => value === '') && coordinates.some(value => value !== '')) throw safeError('範囲を指定する場合は、左・上・右・下をすべて入力してください。手動確認にする場合は4欄とも空欄にします。');
      const bbox = coordinates.every(value => value === '') ? null : coordinates.map(Number);
      if (bbox && !validBox(bbox)) throw safeError('原本上の範囲は0〜1で、右と下が左と上より大きくなるように指定してください。');
      if (bbox && !mappingPageVisible()) throw safeError('この範囲の原本・ページを表示し、照合してから欄を保存してください。');
      const existing = state.mappingFields.find(field => field.field_id === state.editingField);
      const valueType = $('mappedFieldType').value;
      const sameType = existing?.value_type === valueType, codeMap = sameType ? existing.code_map ?? {} : {}, choices = sameType ? existing.options ?? [] : [];
      if (valueType === 'enum' && !choices.length) throw safeError('選択肢の項目は、所定のJSONで選択肢と印字の対応を登録してください。');
      if (['boolean', 'enum'].includes(valueType) && bbox && !Object.keys(codeMap).length) throw safeError('選択肢・はい・いいえの画像読取には、所定のJSONで印字と値の対応を登録してください。');
      const field = {field_id: fieldId, label, value_type: valueType, page, bbox, extraction: bbox ? 'region' : existing?.extraction === 'not_printed' ? 'not_printed' : 'manual', unit: existing?.unit ?? null, phase: existing?.phase ?? null, code_map: codeMap, options: choices};
      if (state.editingField) state.mappingFields = state.mappingFields.map(item => item.field_id === state.editingField ? field : item); else state.mappingFields.push(field);
      configChanged(); renderMappedFields(); clearFieldEditor(); message('mappingMessage', '欄を下書きに追加しました。対応表を保存すると登録されます。');
    } catch (error) { fail('mappingMessage', error); }
  }
  function profileDefinition() {
    const label = $('profileName').value.trim(), formKey = $('profileCode').value.trim(), start = $('profileValidFrom').value, end = $('profileValidTo').value || null;
    if (!label || label.length > 100 || !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/.test(formKey) || !start || (end && end < start)) throw safeError('対応表の名前・様式コード・適用期間を確認してください。');
    return {label, form_key: formKey, valid_from: start, valid_to: end, fields: structuredClone(state.mappingFields)};
  }
  function selectProfile(config, fromSave = false) {
    if (state.configBusy && !fromSave) return;
    if (state.ruleSetRecord && state.ruleSetRecord.form_key !== config.definition.form_key) {
      state.ruleSetRecord = null; state.ruleDrafts = []; state.ruleRequest = null;
      for (const id of ['ruleSetLabel', 'ruleCode', 'ruleTitle', 'ruleValue', 'ruleMinimum', 'ruleMaximum']) $(id).value = '';
      message('ruleMessage', '別の様式を開いたため、前のルールセットの編集を閉じました。');
    }
    state.profileRecord = config; state.mappingFields = structuredClone(list(config.definition?.fields)); state.profileDirty = false; state.configRequest = null;
    $('profileName').value = config.definition.label; $('profileCode').value = config.definition.form_key; $('profileValidFrom').value = config.definition.valid_from; $('profileValidTo').value = config.definition.valid_to ?? '';
    $('profilePageCount').value = String(Math.max(1, ...state.mappingFields.map(field => field.page)));
    state.sourceId = config.source_id; state.sourceMetadata = state.sources.find(item => item.source_id === state.sourceId) ?? null; state.sourceUpload = null; renderSourcePicker();
    revoke(state.configPreviewUrl); state.configPreviewUrl = null; state.configPreviewIntent++;
    clearMappingPreview(); if (!state.sourceId) showReportMappingPreview();
    $('reviewConfiguration').value = config.config_id;
    message('profileStatus', configLabel(config) + ' / 設定版 ' + config.version + '。編集して保存すると新しい下書き版になります。');
    clearFieldEditor(); renderMappedFields(); renderConfigReview(); controls();
    if (state.sourceId) loadConfigPage(1);
  }
  function newProfile() {
    if (!canConfigure() || state.configBusy) return;
    state.profileRecord = null; state.mappingFields = []; state.profileDirty = true; state.configRequest = null; state.sourceId = null; state.sourceMetadata = null; state.sourceUpload = null; state.ruleSetRecord = null; state.ruleDrafts = []; renderSourcePicker();
    for (const id of ['profileName', 'profileCode', 'profileValidTo']) $(id).value = '';
    $('profileValidFrom').value = today(); $('profilePageCount').value = '1';
    revoke(state.configPreviewUrl); state.configPreviewUrl = null; state.configPreviewIntent++;
    clearMappingPreview(); showReportMappingPreview();
    clearFieldEditor(); renderMappedFields(); message('profileStatus', '新しい対応表の下書きです。'); controls();
  }
  async function saveProfile() {
    if (!canConfigure() || state.configBusy || !state.profileDirty) return;
    const generation = state.generation;
    try {
      const definition = profileDefinition(); if (!definition.fields.length) throw safeError('対応する欄を1件以上追加してください。');
      state.configRequest ??= {request_id: crypto.randomUUID(), definition, source_id: state.sourceId, supersedes_id: state.profileRecord?.config_id ?? null};
      state.configBusy = true; controls();
      const saved = await request('/profiles', 'POST', state.configRequest); if (generation !== state.generation) return;
      state.configRequest = null; await loadConfigurations(); if (generation !== state.generation) return; selectProfile(saved, true);
      message('profileMessage', '対応表を下書きとして保存しました。承認前は候補の確認に使用します。');
    } catch (error) { if (generation === state.generation) fail('profileMessage', error); }
    finally { if (generation === state.generation) { state.configBusy = false; controls(); } }
  }
  async function loadConfigPage(page) {
    if (!state.sourceId || !(canConfigure() || canApprove())) return;
    const generation = state.generation, intent = ++state.configPreviewIntent, sourceId = state.sourceId;
    revoke(state.configPreviewUrl); state.configPreviewUrl = null; clearMappingPreview(); controls();
    try {
      const response = await responseFor('/sources/' + sourceId + '/pages/' + page + '.png'); const blob = await response.blob();
      if (generation !== state.generation || intent !== state.configPreviewIntent || sourceId !== state.sourceId || page !== Number($('mappedFieldPage').value)) return;
      if (blob.type.split(';')[0] !== 'image/png') throw safeError('根拠のページを確認できませんでした。');
      const url = URL.createObjectURL(blob); state.configPreviewUrl = url; $('mappingImage').src = url; await $('mappingImage').decode();
      if (generation !== state.generation || intent !== state.configPreviewIntent || sourceId !== state.sourceId || page !== Number($('mappedFieldPage').value) || state.configPreviewUrl !== url) { revoke(url); return; }
      state.mappingPreview = {kind: 'source', id: sourceId, page, url}; $('mappingImage').hidden = false; $('mappingHint').hidden = true;
      showMappingSelection(); controls();
    } catch (error) {
      if (generation === state.generation && intent === state.configPreviewIntent) {
        revoke(state.configPreviewUrl); state.configPreviewUrl = null; clearMappingPreview(); fail('mappingMessage', error); controls();
      }
    }
  }
  async function uploadConfigSource() {
    if (!canConfigure() || state.configBusy || !$('configSourceFile').files?.length) return;
    const generation = state.generation, file = $('configSourceFile').files[0];
    try {
      validateFile(file); if (!state.sourceUpload || state.sourceUpload.file !== file) state.sourceUpload = {file, requestId: crypto.randomUUID()};
      state.configBusy = true; controls(); const data = new FormData(); data.append('file', file, file.name); data.append('request_id', state.sourceUpload.requestId);
      const source = await upload('/sources', data); if (generation !== state.generation) return;
      state.sourceId = source.source_id; state.sourceMetadata = source; state.sourceUpload = null; $('configSourceFile').value = '';
      $('mappedFieldPage').value = '1';
      await loadConfigurations(); if (generation !== state.generation) return;
      configChanged(); await loadConfigPage(1); message('configSourceMessage', '根拠を保存しました。設定と内容を照合してから承認してください。');
    } catch (error) { if (generation === state.generation) fail('configSourceMessage', error); }
    finally { if (generation === state.generation) { state.configBusy = false; controls(); } }
  }
  function renderSourcePicker() {
    setOptions('sourceSelect', state.sources.map((source, index) => {
      const titles = [...new Set(state.ruleSets.flatMap(config => list(config.definition?.rules)).filter(rule => rule.source?.sha256 === source.sha256).map(rule => rule.source.document_title))];
      const title = titles.length ? titles.slice(0, 2).join(' / ') : '資料 ' + (index + 1);
      return [source.source_id, title + ' / ' + source.page_count + 'ページ / ' + formatDate(source.created_at)];
    }), '保存した根拠資料を選択');
    $('sourceSelect').value = state.sourceId ?? '';
  }
  async function selectSource() {
    if (!(canConfigure() || canApprove()) || state.configBusy) return;
    const source = state.sources.find(item => item.source_id === $('sourceSelect').value) ?? null;
    state.sourceId = source?.source_id ?? null; state.sourceMetadata = source; state.sourceUpload = null;
    state.configPreviewIntent++; revoke(state.configPreviewUrl); state.configPreviewUrl = null;
    clearMappingPreview(); $('mappedFieldPage').value = '1';
    if (canConfigure()) configChanged();
    if (source) { await loadConfigPage(1); message('configSourceMessage', '保存済みの根拠資料を開きました。文書名・版・該当ページを照合してください。'); }
    else { showReportMappingPreview(); $('mappedFieldPage').value = String(state.mappingPreview?.page ?? 1); showMappingSelection(); }
  }
  function renderConfigLists() {
    $('profileList').replaceChildren();
    for (const config of state.profiles) { const item = button('', () => selectProfile(config), 'profile-item'); item.dataset.auditConfigReset = 'true'; item.append(element('strong', config.label), element('span', configLabel(config))); $('profileList').append(item); }
    $('ruleList').replaceChildren();
    for (const config of state.ruleSets) {
      const card = element('article', undefined, 'rule-card'); card.append(badge(config.status === 'approved' ? '承認済み' : config.status === 'retired' ? '利用停止' : '下書き'), element('h4', config.label), element('p', list(config.definition?.rules).length + '件のルール / ' + config.form_key, 'muted'));
      const open = button('この設定を開く', () => openRuleSet(config), 'text-button'); open.dataset.auditConfigReset = 'true'; card.append(open);
      $('ruleList').append(card);
    }
  }
  function openRuleSet(config) {
    if (state.configBusy) return;
    $('reviewConfiguration').value = config.config_id; renderConfigReview();
    if ($('profileCode').value.trim() !== config.form_key) { message('ruleMessage', 'このルールを編集するには、先に様式「' + config.form_key + '」の対応表を開いてください。', true); return; }
    state.ruleSetRecord = config; state.ruleDrafts = structuredClone(list(config.definition.rules)); state.ruleRequest = null;
    state.sourceId = config.source_id ?? null; state.sourceMetadata = state.sources.find(item => item.source_id === state.sourceId) ?? null;
    state.configPreviewIntent++; revoke(state.configPreviewUrl); state.configPreviewUrl = null;
    clearMappingPreview(); if (!state.sourceId) showReportMappingPreview(); clearFieldEditor();
    state.configRequest = null; renderSourcePicker(); if (state.sourceId) loadConfigPage(1);
    $('ruleSetLabel').value = config.label; message('ruleMessage', 'このセットにルールを追加して保存すると、新しい下書き版になります。'); controls();
  }
  function ruleInputs() {
    const operator = $('ruleOperator').value;
    $('ruleValueLabel').hidden = operator !== 'eq'; $('ruleOtherFieldLabel').hidden = operator !== 'field_eq';
    $('ruleMinimumLabel').hidden = operator !== 'range'; $('ruleMaximumLabel').hidden = operator !== 'range'; state.ruleRequest = null;
  }
  function ruleExpression() {
    const id = $('ruleField').value, field = state.mappingFields.find(item => item.field_id === id);
    if (!field) throw safeError('確認対象の項目を選択してください。');
    const operator = $('ruleOperator').value, expression = {kind: 'field', field: id};
    if (operator === 'required' || operator === 'blank') return {...expression, operator: operator === 'required' ? 'not_blank' : 'blank'};
    const unit = field.unit ? {unit: field.unit} : {};
    if (operator === 'field_eq') {
      const right = state.mappingFields.find(item => item.field_id === $('ruleOtherField').value);
      if (!right || right.value_type !== field.value_type || (right.unit ?? null) !== (field.unit ?? null)) throw safeError('比較する欄は同じ値の種類・単位から選択してください。');
      return {...expression, operator: 'compare_field', right_field: right.field_id, ...unit};
    }
    if (operator === 'eq') {
      let value = typedValue($('ruleValue').value, field.value_type);
      if (['date', 'time', 'datetime'].includes(field.value_type)) value = {type: field.value_type, value};
      return {...expression, operator: 'eq', value, ...unit};
    }
    if (operator === 'range' && field.value_type === 'number') {
      const minimum = typedValue($('ruleMinimum').value, 'number'), maximum = typedValue($('ruleMaximum').value, 'number');
      if (minimum > maximum) throw safeError('下限は上限以下にしてください。');
      return {kind: 'all', expressions: [{...expression, operator: 'ge', value: minimum, ...unit}, {...expression, operator: 'le', value: maximum, ...unit}]};
    }
    throw safeError('この条件は数値の項目を選択して設定してください。');
  }
  async function saveRule() {
    if (!canConfigure() || state.configBusy) return;
    const generation = state.generation;
    try {
      const profile = profileDefinition(), ruleId = $('ruleCode').value.trim(), label = $('ruleTitle').value.trim();
      if (state.ruleSetRecord && state.ruleSetRecord.form_key !== profile.form_key) throw safeError('開いているルールセットと対応表の様式が一致しません。対応する帳票を選び直してください。');
      if (!/^[A-Za-z0-9_][A-Za-z0-9_.:-]{0,63}$/.test(ruleId) || !label || label.length > 150 || !$('ruleSetLabel').value.trim()) throw safeError('ルールID・確認内容・ルールセット名を入力してください。');
      const source = {document_title: $('ruleSourceTitle').value.trim(), version: $('ruleSourceVersion').value.trim(), page: $('ruleSourcePage').value.trim(), section: $('ruleEvidence').value.trim(), sha256: state.sourceMetadata?.sha256 ?? null};
      if (!source.document_title || !source.version || !source.page) throw safeError('根拠の文書名・版・ページを入力してください。');
      const rule = {rule_id: ruleId, label, message: label, severity: 'review', source, candidate_ids: [], applies_when: null, exceptions: [], assertion: ruleExpression()};
      const rules = state.ruleDrafts.filter(item => item.rule_id !== ruleId); rules.push(rule);
      const definition = {label: $('ruleSetLabel').value.trim(), form_key: profile.form_key, valid_from: profile.valid_from, valid_to: profile.valid_to, rules};
      state.ruleRequest ??= {request_id: crypto.randomUUID(), definition, source_id: state.sourceId, supersedes_id: state.ruleSetRecord?.config_id ?? null};
      state.configBusy = true; controls(); const saved = await request('/rule-sets', 'POST', state.ruleRequest);
      if (generation !== state.generation) return;
      state.ruleSetRecord = saved; state.ruleDrafts = structuredClone(list(saved.definition.rules)); state.ruleRequest = null;
      await loadConfigurations(); if (generation !== state.generation) return; $('reviewConfiguration').value = saved.config_id; renderConfigReview();
      message('ruleMessage', 'ルールセットを下書きとして保存しました。根拠・適用範囲・影響を確認してから別担当者が承認します。');
    } catch (error) { if (generation === state.generation) fail('ruleMessage', error); }
    finally { if (generation === state.generation) { state.configBusy = false; controls(); } }
  }
  async function importConfiguration() {
    if (!canConfigure() || state.configBusy) return;
    const file = $('profileImport').files?.[0], generation = state.generation; if (!file) return;
    try {
      if (file.size > MAX_CONFIG_BYTES) throw safeError('構造化ファイルは2 MiB以下にしてください。');
      const parsed = JSON.parse(await file.text()); if (generation !== state.generation) return;
      const definition = parsed.definition ?? parsed, kind = $('configurationImportKind').value;
      if (!definition || typeof definition !== 'object' || Array.isArray(definition)) throw safeError('所定の対応表またはルールセットを選択してください。');
      if (kind === 'profile' && (!Array.isArray(definition.fields) || definition.fields.length > 200)) throw safeError('対応表の項目数・構造を確認してください。');
      if (kind === 'rules' && (!Array.isArray(definition.rules) || definition.rules.length > 500)) throw safeError('ルールセットの項目数・構造を確認してください。');
      state.configBusy = true; controls();
      const saved = await request(kind === 'profile' ? '/profiles' : '/rule-sets', 'POST', {request_id: crypto.randomUUID(), definition, source_id: state.sourceId, supersedes_id: null});
      if (generation !== state.generation) return;
      await loadConfigurations(); if (generation !== state.generation) return;
      if (kind === 'profile') selectProfile(saved, true); else { state.ruleSetRecord = saved; state.ruleDrafts = structuredClone(list(saved.definition.rules)); $('ruleSetLabel').value = saved.label; }
      message('profileMessage', '構造化された設定を新しい下書きとして保存しました。承認は行っていません。');
    } catch (error) { if (generation === state.generation) fail('profileMessage', error.safe || error.cancelled ? error : safeError('所定のJSONを読み込めませんでした。内容と形式を確認してください。')); }
    finally { if (generation === state.generation) { $('profileImport').value = ''; state.configBusy = false; controls(); } }
  }
  function configurationFieldLabels(config) {
    const profiles = config.kind === 'profile' ? [config] : state.profileRecord?.form_key === config.form_key ? [state.profileRecord] : state.profiles.filter(profile => profile.form_key === config.form_key);
    const labels = new Map();
    for (const profile of profiles) for (const field of list(profile.definition?.fields)) {
      if (!labels.has(field.field_id)) labels.set(field.field_id, new Set());
      labels.get(field.field_id).add(field.label);
    }
    return id => { const candidates = labels.get(id); return candidates?.size === 1 ? '「' + [...candidates][0] + '」（' + id + '）' : '項目「' + id + '」'; };
  }
  function expressionValue(value) {
    if (value === null) return '空欄';
    if (typeof value === 'boolean') return value ? 'はい' : 'いいえ';
    if (value && typeof value === 'object') {
      const label = {date: '日付', datetime: '日時', time: '時刻'}[value.type];
      return label && typeof value.value === 'string' ? label + '「' + value.value + '」' : '値の表示を確認してください';
    }
    return typeof value === 'string' ? '「' + value + '」' : scalarText(value);
  }
  function expressionView(expression, fieldLabel, depth = 0) {
    if (!expression || typeof expression !== 'object' || depth > 8) return element('p', '条件の内容を詳細表示で確認してください。', 'small muted');
    if (['all', 'any', 'not'].includes(expression.kind)) {
      const group = element('div', undefined, 'expression-group');
      group.append(element('strong', {all: '次のすべてを満たす', any: '次のいずれかを満たす', not: '次の条件に該当しない'}[expression.kind]));
      const entries = element('ul');
      for (const child of expression.kind === 'not' ? [expression.expression] : list(expression.expressions)) {
        const item = element('li'); item.append(expressionView(child, fieldLabel, depth + 1)); entries.append(item);
      }
      group.append(entries); return group;
    }
    if (expression.kind !== 'field') return element('p', '条件の内容を詳細表示で確認してください。', 'small muted');
    const field = fieldLabel(expression.field), value = expressionValue(expression.value), unit = expression.unit ? ' ' + expression.unit : '';
    const temporal = expression.value && typeof expression.value === 'object' && ['date', 'datetime', 'time'].includes(expression.value.type);
    let text;
    switch (expression.operator) {
      case 'blank': text = field + 'が空欄である'; break;
      case 'not_blank': text = field + 'に記入あり'; break;
      case 'compare_field': text = field + 'と' + fieldLabel(expression.right_field) + 'の値が一致する' + (unit ? '（単位：' + expression.unit + '）' : ''); break;
      case 'eq': text = field + 'が' + value + unit + 'と一致する'; break;
      case 'ne': text = field + 'が' + value + unit + 'と一致しない'; break;
      case 'lt': text = field + 'が' + value + unit + (temporal ? 'より前である' : '未満である'); break;
      case 'le': text = field + 'が' + value + unit + (temporal ? '以前である' : '以下である'); break;
      case 'gt': text = field + 'が' + value + unit + (temporal ? 'より後である' : 'を超える'); break;
      case 'ge': text = field + 'が' + value + unit + (temporal ? '以降である' : '以上である'); break;
      case 'in': text = field + 'が次のいずれかと一致する：' + list(expression.value).map(expressionValue).join('、') + unit; break;
      default: text = 'この条件は詳細表示で確認してください。';
    }
    return element('p', text, 'expression-leaf');
  }
  function renderConfigurationHuman(config) {
    const target = $('configurationHuman'); target.replaceChildren(); if (!config) return;
    const definition = config.definition, fieldLabel = configurationFieldLabels(config);
    target.append(element('h4', config.label), element('p', '様式：' + config.form_key + ' / 適用期間：' + definition.valid_from + ' 〜 ' + (definition.valid_to ?? '終了日の指定なし'), 'small muted'));
    target.append(element('p', config.source_id ? '根拠資料は保存されています。上の「根拠資料」で原文を確認してください。' : '根拠資料は未登録です。承認に進む前に根拠を登録してください。', 'small muted'));
    if (config.kind === 'profile') {
      for (const field of list(definition.fields)) {
        const row = element('article', undefined, 'configuration-review-item');
        const kind = {text: '文字', number: '数値', boolean: 'はい・いいえ', date: '日付', time: '時刻', datetime: '日時', enum: '選択肢'}[field.value_type] ?? '詳細で確認';
        row.append(element('strong', fieldLabel(field.field_id)), element('p', kind + (field.unit ? ' / 単位：' + field.unit : '') + ' / ' + field.page + 'ページ / ' + ({region: '原本の指定範囲から読み取る', manual: '原本を見て手動確認する', not_printed: '印刷されない欄として扱う'}[field.extraction] ?? '対応を確認してください'), 'small'));
        if (field.options?.length) row.append(element('p', '選択肢：' + field.options.join('、'), 'small muted'));
        if (Object.keys(field.code_map ?? {}).length) row.append(element('p', '印字の対応：' + Object.entries(field.code_map).map(([printed, value]) => '「' + printed + '」 → ' + expressionValue(value)).join(' / '), 'small muted'));
        target.append(row);
      }
      return;
    }
    target.append(element('p', '未確認・読取不能の値が残る場合は、条件を満たしたとは扱いません。', 'small muted'));
    for (const rule of list(definition.rules)) {
      const row = element('article', undefined, 'configuration-review-item'); row.append(element('h5', rule.label + '（' + rule.rule_id + '）'));
      const source = rule.source;
      row.append(element('p', '根拠：' + source.document_title + ' / 版 ' + source.version + ' / ' + source.page + 'ページ' + (source.section ? ' / ' + source.section : ''), 'small muted'));
      row.append(element('strong', '適用条件'));
      row.append(rule.applies_when ? expressionView(rule.applies_when, fieldLabel) : element('p', '個別の条件指定なし。様式と適用期間に従って確認します。', 'small'));
      row.append(element('strong', '例外条件'));
      if (list(rule.exceptions).length) row.append(expressionView({kind: 'any', expressions: rule.exceptions}, fieldLabel), element('p', 'いずれかの例外に該当することを確認した場合は、このルールの適用対象外です。', 'small muted'));
      else row.append(element('p', '例外の指定なし。', 'small'));
      row.append(element('strong', '確認する条件'), expressionView(rule.assertion, fieldLabel));
      row.append(element('p', '条件を満たさなかった場合：' + rule.message + ' / 表示区分：' + ({error: 'エラー', warning: '注意', review: '要確認'}[rule.severity] ?? '要確認'), 'small muted'));
      target.append(row);
    }
  }
  function renderConfigReview() {
    const selected = selectedConfiguration(); $('sourceVerified').checked = false; $('mappingVerified').checked = false;
    $('configurationDefinition').textContent = selected ? JSON.stringify(selected.definition, null, 2) : '確認する設定を選択してください。';
    renderConfigurationHuman(selected);
    const impact = selected?.impact;
    message('impactSummary', !selected ? '確認する設定を選択してください。' : !impact ? 'この設定の影響確認はまだありません。' : '対象 ' + (impact.report_count ?? 0) + '件 / 検査項目 ' + (impact.tested_opportunities ?? 0) + '件 / 未完了 ' + (impact.incomplete_count ?? 0) + '件 / 変更 ' + (impact.changed_count ?? 0) + '件。' + (impact.can_approve ? '別担当者が根拠と適用条件を確認してください。' : '承認条件はまだ満たしていません。'));
    controls();
  }
  async function configurationAction(action) {
    const config = selectedConfiguration(); if (!config || state.configBusy || (action === 'impact' ? !canConfigure() : !canApprove())) return;
    const generation = state.generation;
    try {
      let body;
      if (action === 'impact') { const ids = Array.from($('impactReports').selectedOptions).map(item => item.value); if (!ids.length) throw safeError('影響を確認する報告書を1件以上選択してください。'); body = {report_ids: ids}; }
      else if (action === 'approve') { if (!$('sourceVerified').checked || !$('mappingVerified').checked) return; body = {expected_version: config.version, source_verified: true, mapping_verified: true}; }
      else body = {expected_version: config.version};
      state.configBusy = true; controls(); const result = await request('/configurations/' + config.config_id + '/' + action, 'POST', body);
      if (generation !== state.generation) return;
      await loadConfigurations(); if (generation !== state.generation) return;
      $('reviewConfiguration').value = config.config_id;
      if (action === 'impact') { const updated = selectedConfiguration(); if (updated && !updated.impact) updated.impact = result.impact ?? result; }
      renderConfigReview(); message('configurationReviewMessage', action === 'impact' ? '影響確認を保存しました。結果と根拠を確認してください。' : action === 'approve' ? '担当者による設定の承認を記録しました。実運用全体の受入完了ではありません。' : 'この設定を今後の承認済みチェックに使わない状態にしました。履歴は残ります。');
    } catch (error) { if (generation === state.generation) fail('configurationReviewMessage', error); }
    finally { if (generation === state.generation) { state.configBusy = false; controls(); } }
  }
  async function loadCatalog() {
    if (!canRead()) return;
    const generation = state.generation, intent = ++state.catalogIntent;
    const query = new URLSearchParams({group: $('catalogFilter').value, query: $('catalogSearch').value.trim(), limit: '50', offset: String(state.catalogOffset)});
    try {
      const catalog = await request('/rule-candidates?' + query);
      if (generation !== state.generation || intent !== state.catalogIntent) return;
      state.catalogTotal = catalog.total; state.catalogItems = list(catalog.items); $('catalogList').replaceChildren(); $('catalogCount').textContent = catalog.total + '件の候補';
      const flagLabels = {HOLD_SOURCE: '根拠の確認待ち', HOLD_FIELD: '項目対応の確認待ち', EXAMPLE_ONLY: '例示のみ', DESIGN_GUARD: '設計上の制約', USER_OPERATION: '操作上の確認'};
      for (const item of state.catalogItems) {
        const card = element('article', undefined, 'catalog-card'); card.append(badge(item.candidate_id), badge('未承認', 'warning'), element('h3', item.summary), element('p', item.source_reference, 'muted'));
        for (const flag of list(item.flags)) card.append(badge(flagLabels[flag] ?? '確認待ち', 'warning'));
        $('catalogList').append(card);
      }
      message('catalogMessage', state.catalogItems.length ? '候補を表示しています。登録済みの実行ルールの件数ではありません。' : '条件に一致する候補はありません。'); controls();
    } catch (error) { if (generation === state.generation && intent === state.catalogIntent) fail('catalogMessage', error); }
  }

  for (const name of ['reports', 'configuration', 'catalog', 'measurement']) $(name + 'Tab').onclick = () => switchTab(name);
  $('uploadFiles').addEventListener('change', chooseFiles); $('startUpload').onclick = processQueue; $('retryFailedUploads').onclick = retryFailedUploads;
  $('datasetKind').addEventListener('change', () => { if ($('datasetKind').value === 'internal_trial' && !state.capabilities?.internal_enabled) { $('datasetKind').value = 'synthetic'; message('datasetNotice', '本部内の報告書は、この環境では有効になっていません。', true); } else message('datasetNotice', $('datasetKind').value === 'synthetic' ? '合成データは実運用の成果として集計しません。' : '承認された内部環境の原本だけを扱ってください。'); updateQueuedOptions(); });
  $('profileSelect').addEventListener('change', updateQueuedOptions);
  $('revisionFile').addEventListener('change', () => { state.revisionUpload = null; controls(); }); $('uploadRevision').onclick = uploadRevision;
  $('revisionProfile').addEventListener('change', controls);
  $('applyMapping').onclick = () => writable() && $('revisionProfile').value && mutate('/revisions/' + state.report.revision.revision_id + '/mapping', {expected_version: state.report.version, profile_id: $('revisionProfile').value}, 'fieldMessage', '対応表を適用しました。原本と照合して読み取りを確認してください。');
  $('retryJob').onclick = () => writable() && mutate('/revisions/' + state.report.revision.revision_id + '/retry', {expected_version: state.report.version}, 'fieldMessage', '読み取りを再試行するよう登録しました。');
  $('runAI').onclick = () => writable() && aiConfigured() && mutate('/revisions/' + state.report.revision.revision_id + '/ai', {expected_version: state.report.version}, 'findingMessage', '記載の整合性候補の確認を開始しました。');
  $('runVision').onclick = () => writable() && aiConfigured() && mutate('/revisions/' + state.report.revision.revision_id + '/vision', {expected_version: state.report.version, page: state.page}, 'findingMessage', '表示ページの画像・手書きの候補読取を開始しました。候補は未確認として扱います。');
  $('downloadOriginal').onclick = downloadOriginal;
  $('newProfile').onclick = newProfile; $('saveProfile').onclick = saveProfile;
  $('addMappedField').onclick = $('cancelMappedField').onclick = () => { clearFieldEditor(); if (!state.mappingPreview) return loadMappingPage(Number($('mappedFieldPage').value)); }; $('saveMappedField').onclick = saveMappedField;
  for (const id of ['profileName', 'profileCode', 'profileValidFrom', 'profileValidTo']) $(id).addEventListener('input', configChanged);
  for (const id of ['regionX0', 'regionY0', 'regionX1', 'regionY1']) $(id).addEventListener('input', showMappingSelection);
  $('mappedFieldPage').addEventListener('input', invalidateMappingPage);
  $('mappedFieldPage').addEventListener('change', () => loadMappingPage(Number($('mappedFieldPage').value)));
  $('configSourceFile').addEventListener('change', () => { state.sourceUpload = null; controls(); }); $('uploadConfigSource').onclick = uploadConfigSource;
  $('sourceSelect').addEventListener('change', selectSource);
  $('profileImport').addEventListener('change', importConfiguration); $('ruleOperator').addEventListener('change', ruleInputs); $('saveRule').onclick = saveRule;
  for (const id of ['ruleCode', 'ruleSetLabel', 'ruleTitle', 'ruleField', 'ruleValue', 'ruleOtherField', 'ruleMinimum', 'ruleMaximum', 'ruleSourceTitle', 'ruleSourceVersion', 'ruleSourcePage', 'ruleEvidence']) $(id).addEventListener('input', () => { state.ruleRequest = null; });
  $('newRule').onclick = () => { if (!canConfigure()) return; for (const id of ['ruleCode', 'ruleTitle', 'ruleValue', 'ruleMinimum', 'ruleMaximum']) $(id).value = ''; state.ruleRequest = null; $('ruleOperator').value = 'required'; ruleInputs(); };
  $('reviewConfiguration').addEventListener('change', renderConfigReview);
  $('sourceVerified').addEventListener('change', controls); $('mappingVerified').addEventListener('change', controls);
  $('validateConfiguration').onclick = () => configurationAction('impact'); $('approveConfiguration').onclick = () => configurationAction('approve'); $('retireConfiguration').onclick = () => configurationAction('retire');
  $('searchCatalog').onclick = () => { state.catalogOffset = 0; return loadCatalog(); };
  $('previousCandidates').onclick = () => { state.catalogOffset = Math.max(0, state.catalogOffset - 50); return loadCatalog(); };
  $('nextCandidates').onclick = () => { state.catalogOffset += 50; return loadCatalog(); };
  $('mappingImage').addEventListener('pointerdown', event => {
    if (!canConfigure() || state.configBusy || !mappingPageVisible()) return; event.preventDefault();
    const rect = $('mappingImage').getBoundingClientRect();
    state.mappingStart = {generation: state.generation, source: $('mappingImage').src, x: Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)), y: Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)), check: window.FireAISession.check()};
    state.mappingStart.check.catch(() => {}); $('mappingImage').setPointerCapture(event.pointerId);
  });
  $('mappingImage').addEventListener('pointerup', async event => {
    const start = state.mappingStart; state.mappingStart = null; if (!start) return;
    try {
      await start.check; if (start.generation !== state.generation || !canConfigure() || !mappingPageVisible() || start.source !== $('mappingImage').src) return;
      const rect = $('mappingImage').getBoundingClientRect(), x = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)), y = Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height));
      const box = [Math.min(start.x, x), Math.min(start.y, y), Math.max(start.x, x), Math.max(start.y, y)]; if (!validBox(box)) return;
      for (const [index, id] of ['regionX0', 'regionY0', 'regionX1', 'regionY1'].entries()) $(id).value = String(Math.round(box[index] * 10000) / 10000);
      showMappingSelection(); message('mappingMessage', '選択した範囲を入力しました。項目IDと表示名を付けて欄を追加してください。');
    } catch (error) { if (!error.cancelled && start.generation === state.generation) fail('mappingMessage', error); }
  });

  $('confirmOriginal').addEventListener('change', controls);
  $('saveFields').onclick = saveFields; $('runCheck').onclick = runCheck;
  $('refreshReports').onclick = loadReports;
  $('previousReports').onclick = () => { state.offset = Math.max(0, state.offset - 30); return loadReports(); };
  $('nextReports').onclick = () => { state.offset += 30; return loadReports(); };
  $('clearReport').onclick = () => { if (!state.workCapture) { clearReport(); renderReportList(); } };
  $('refreshReport').onclick = () => state.report && selectReport(state.report.report_id);
  $('previousPage').onclick = () => loadPage(Math.max(1, state.page - 1));
  $('nextPage').onclick = () => loadPage(Math.min(state.report?.revision?.page_count ?? 1, state.page + 1));
  $('previewZoom').addEventListener('change', () => { $('sourceFrame').style.width = (['100', '150', '200'].includes($('previewZoom').value) ? $('previewZoom').value : '100') + '%'; });

  function renderMeasurement() {
    $('measurementReport').textContent = state.report ? reportLabel(state.report) + ' / ' + (state.report.dataset_kind === 'synthetic' ? '合成データ' : '本部内の報告書') : '報告書を選択してください。';
    if (!state.report) return;
    const events = list(state.report.events), superseded = new Set(events.map(item => item.supersedes_event_id).filter(Boolean));
    const activeEvents = events.filter(item => !superseded.has(item.event_id));
    const study = [...activeEvents].reverse().find(item => item.kind === 'study')?.payload;
    if (study) { $('measurementCohort').value = study.cohort; $('activityKind').value = study.activity_kind; }
    const followup = [...activeEvents].reverse().find(item => item.kind === 'followup')?.payload;
    if (followup) { $('afterSubmission').value = typeof followup.corrected_after_submission === 'boolean' ? String(followup.corrected_after_submission) : ''; $('followupComplete').checked = followup.complete === true; $('workComplete').checked = followup.work_complete === true; }
    $('reviewerSelect').value = state.report.reviewer_id ?? '';
    const runs = list(state.report.runs).length ? state.report.runs : state.report.initial_run ? [state.report.initial_run] : [];
    const selectedRun = $('truthRunSelect').value;
    setOptions('truthRunSelect', runs.map((run, index) => [run.run_id, (run.run_id === state.report.initial_run?.run_id ? '初回' : '検査 ' + (index + 1)) + ' / ' + formatDate(run.created_at) + ' / ' + ({vision: '画像候補', text: '記載候補', ai: '記載候補', candidate: '候補チェック', approved: '承認条件'}[run.mode] ?? '確認結果')]));
    if (!runs.some(run => run.run_id === selectedRun) && state.report.initial_run) $('truthRunSelect').value = state.report.initial_run.run_id;
    $('measurementHistory').replaceChildren();
    for (const event of events.filter(item => ['study', 'submitted', 'followup', 'work_interval', 'truth_review'].includes(item.kind)).slice(-40).reverse()) {
      const row = element('div', undefined, 'history-entry');
      let note = '';
      if (event.kind === 'work_interval') {
        const minutes = (new Date(event.payload?.ended_at) - new Date(event.payload?.started_at)) / 60000;
        if (Number.isFinite(minutes) && minutes >= 0) note = ' / ' + minutes.toLocaleString('ja-JP', {maximumFractionDigits: 1}) + '分';
      }
      row.append(element('strong', eventLabels[event.kind] + note + (superseded.has(event.event_id) ? '（訂正前）' : event.supersedes_event_id ? '（訂正後）' : '')), element('span', formatDate(event.created_at)));
      if (!superseded.has(event.event_id) && event.can_correct === true && ['work_interval', 'submitted'].includes(event.kind)) {
        const edit = button('この記録を訂正', () => editEvent(event), 'text-button'); edit.id = 'edit-event-' + event.event_id; row.append(edit);
      }
      $('measurementHistory').append(row);
    }
    if (state.report.measurement_pending?.includes('SUBMISSION_NOT_RECORDED')) message('exportMessage', '検査と提出の前後関係は未確認です。実際に提出した日時を記録すると測定記録へ出力できます。');
    controls();
  }
  function eventAllowed(kind) { return state.report && !state.busy && !state.stale && (kind === 'truth_review' ? canTruthReview() : kind === 'work_interval' ? canRecordWork() : canWrite()); }
  async function recordEvent(kind, payload, success, messageId = 'measurementMessage', supersedesId = null) {
    if (!eventAllowed(kind)) return;
    const key = state.report.report_id + ':' + kind + ':' + (supersedesId ?? '') + ':' + JSON.stringify(payload);
    let pending = state.eventRetries.get(key);
    if (!pending) { pending = {event_id: crypto.randomUUID(), expected_version: state.report.version, kind, payload, ...(supersedesId ? {supersedes_event_id: supersedesId} : {})}; state.eventRetries.set(key, pending); }
    const result = await mutate('/reports/' + state.report.report_id + '/events', pending, messageId, success);
    if (result) state.eventRetries.delete(key); return result;
  }
  function inputInstant(id) {
    const value = $(id).value, instant = new Date(value);
    if (!value || Number.isNaN(instant.getTime()) || instant.getTime() > Date.now()) throw safeError('実際に作業した、現在以前の日時を入力してください。');
    return instant.toISOString();
  }
  async function recordManualWork() {
    if (!eventAllowed('work_interval')) return;
    try {
      const start = inputInstant('workStartedAt'), end = inputInstant('workEndedAt');
      if (new Date(end) < new Date(start)) throw safeError('終了日時は開始日時以降にしてください。');
      const result = await recordEvent('work_interval', {stage: $('workStage').value, started_at: start, ended_at: end}, state.editingWorkEvent ? '前の記録を残して作業区間を訂正しました。' : '実際の作業区間を保存しました。', 'measurementMessage', state.editingWorkEvent);
      if (result) cancelWorkCorrection();
    } catch (error) { fail('measurementMessage', error, ticket()); }
  }
  function startWork() {
    if (!eventAllowed('work_interval') || state.workCapture) return;
    state.workCapture = {reportId: state.report.report_id, stage: $('workStage').value, started_at: new Date().toISOString(), ended_at: null};
    $('workTimerStatus').textContent = '作業を計測中です。休憩・離席の前に止めてください。'; renderReportList(); controls();
  }
  async function pauseWork() {
    if (!eventAllowed('work_interval') || !state.workCapture || state.workCapture.reportId !== state.report.report_id) return;
    const capture = state.workCapture; capture.ended_at ??= new Date().toISOString();
    const result = await recordEvent('work_interval', {stage: capture.stage, started_at: capture.started_at, ended_at: capture.ended_at}, 'ここまでの作業時間を記録しました。');
    if (result && state.workCapture === capture) { state.workCapture = null; $('workTimerStatus').textContent = '計測していません。'; renderReportList(); controls(); }
    else if (state.workCapture === capture) $('workTimerStatus').textContent = '計測は止まっています。接続を確認し、同じボタンで記録を再試行してください。';
  }
  async function recordSubmission() {
    if (!eventAllowed('submitted') || !$('submissionConfirmed').checked || (state.report.submitted_at && !state.editingSubmissionEvent)) return;
    try {
      const result = await recordEvent('submitted', {occurred_at: inputInstant('submittedAt')}, state.editingSubmissionEvent ? '前の記録を残して提出日時を訂正しました。' : '元のシステムで提出した日時を記録しました。', 'measurementMessage', state.editingSubmissionEvent);
      if (result) cancelSubmissionCorrection();
    } catch (error) { fail('measurementMessage', error, ticket()); }
  }
  async function recordFollowup() {
    if (!eventAllowed('followup') || !state.report.submitted_at) return;
    const value = $('afterSubmission').value;
    if ($('followupComplete').checked && !['true', 'false'].includes(value)) { message('measurementMessage', '追跡完了にするには、提出後の訂正の有無を確認してください。', true); return; }
    await recordEvent('followup', {complete: $('followupComplete').checked, corrected_after_submission: value === '' ? null : value === 'true', work_complete: $('workComplete').checked}, '追跡結果を記録しました。未確認の結果は未測定のまま残します。');
  }
  function selectControl(id, choices, value = '') {
    const control = element('select'); control.id = id;
    for (const [key, label] of choices) control.append(option(key, label)); control.value = value; return control;
  }
  function truthChoices() { return [['unknown', 'まだ正誤を判断できない'], ['error', '原本に誤りがある'], ['correct', 'この点の記載は正しい'], ['not_applicable', 'この条件の対象外']]; }
  function stateChoices() { return [['', '読取状態を選択'], ...Object.entries(readStates)]; }
  function knownErrors() {
    const result = new Map();
    for (const event of list(state.report?.events)) {
      if (event.kind !== 'truth_review') continue;
      for (const item of list(event.payload?.items)) if (item.truth === 'error' && item.error_id) result.set(item.error_id, item.rule_id + ' / ' + formatDate(event.created_at));
      for (const item of list(event.payload?.missed_errors)) if (item.error_id) result.set(item.error_id, '指摘外の誤り / ' + formatDate(event.created_at));
    }
    return [...result];
  }
  async function loadTruthReview() {
    if (!canTruthReview() || !state.report.initial_run) return;
    const t = ticket(), intent = ++state.truthIntent, selected = $('truthRunSelect').value || state.report.initial_run.run_id;
    try {
      const run = selected === state.report.initial_run.run_id ? state.report.initial_run : await request('/runs/' + encodeURIComponent(selected));
      if (!current(t) || intent !== state.truthIntent) return;
      state.truthRun = structuredClone(run);
    } catch (error) { if (intent === state.truthIntent) fail('truthMessage', error, t); return; }
    state.truthDrafts.clear(); state.missedErrors = [];
    $('truthReviewList').replaceChildren(); $('missedErrorList').replaceChildren(); $('wholeReportChecked').checked = false; $('truthReviewComplete').checked = false;
    const previous = [...list(state.report.events)].reverse().find(item => item.kind === 'truth_review' && item.payload?.run_id === selected)?.payload;
    const errors = knownErrors();
    for (const finding of list(state.truthRun.findings)) {
      const prior = list(previous?.items).find(item => item.rule_id === finding.rule_id);
      const row = element('article', undefined, 'review-field'); row.append(element('strong', finding.message || finding.rule_id), element('p', 'この検査：' + (findingStates[finding.status] ?? '未検査') + ' / 読取状態：' + (readStates[state.truthRun.rule_read_states?.[finding.rule_id]] ?? '未確認'), 'small muted'));
      const truth = selectControl('truth-' + finding.rule_id, truthChoices(), prior?.truth ?? 'unknown');
      const verified = selectControl('truth-read-' + finding.rule_id, stateChoices(), prior?.verified_read_state ?? '');
      const truthLabel = element('label', '独立して確認した正誤', 'field'); truthLabel.append(truth);
      const stateLabel = element('label', '原本と照合した読取状態', 'field'); stateLabel.append(verified); row.append(truthLabel, stateLabel);
      const errorChoice = selectControl('truth-error-' + finding.rule_id, [['new', '新しい誤りとして記録'], ...errors.map(([identity, label]) => [identity, '以前に確認した同じ誤り：' + label])], prior?.error_id ?? 'new');
      const errorLabel = element('label', '実際の誤りの紐付け', 'field'); errorLabel.append(errorChoice); row.append(errorLabel); truth.addEventListener('change', controls);
      const later = element('input'); later.type = 'checkbox'; later.id = 'truth-later-' + finding.rule_id;
      const laterRun = state.report.last_run;
      const canLink = laterRun && laterRun.run_id !== state.truthRun.run_id && list(laterRun.findings).some(item => item.rule_id === finding.rule_id && item.status === 'REVIEW_REQUIRED');
      later.checked = !!canLink && list(prior?.detected_in_run_ids).includes(laterRun.run_id);
      if (canLink) { const label = element('label', undefined, 'check-label'); label.append(later, document.createTextNode('現在の再チェックでも、同じ誤りが指摘されたことを原本で確認した')); row.append(label); }
      $('truthReviewList').append(row);
      state.truthDrafts.set(finding.rule_id, {truth, verified, errorChoice, later, laterRunId: canLink ? laterRun.run_id : null, previousLinks: list(prior?.detected_in_run_ids), errorId: prior?.error_id ?? crypto.randomUUID()});
    }
    for (const missed of list(previous?.missed_errors)) addMissedError(missed);
    const revision = list(state.report.revisions).find(item => item.revision_id === state.truthRun.revision_id);
    message('truthRunContext', '確認対象：原本の版 ' + (revision?.number ?? '未確認') + ' / ' + formatDate(state.truthRun.created_at));
    message('truthMessage', 'この検査の原本全体を確認します。再チェックで同じ誤りが続いている場合だけ、以前の誤りへ明示的に紐付けてください。'); controls();
  }
  function addMissedError(previous = null) {
    if (!canTruthReview() || !state.truthRun || state.missedErrors.length >= 200) return;
    const index = state.missedErrors.length + 1, identity = previous?.opportunity_id ?? crypto.randomUUID();
    const row = element('article', undefined, 'review-field'); row.append(element('strong', '指摘されていなかった誤り ' + index));
    const observed = selectControl('missed-observed-' + identity, stateChoices(), previous?.read_state ?? '');
    const verified = selectControl('missed-verified-' + identity, stateChoices(), previous?.verified_read_state ?? '');
    const observedLabel = element('label', '最初のチェックでの読取状態', 'field'); observedLabel.append(observed);
    const verifiedLabel = element('label', '独立して確認した読取状態', 'field'); verifiedLabel.append(verified); row.append(observedLabel, verifiedLabel);
    const errorChoice = selectControl('missed-error-' + identity, [['new', '新しい誤りとして記録'], ...knownErrors().map(([key, label]) => [key, '以前に確認した同じ誤り：' + label])], previous?.error_id ?? 'new');
    const errorLabel = element('label', '実際の誤りの紐付け', 'field'); errorLabel.append(errorChoice); row.append(errorLabel);
    const item = {identity, errorId: previous?.error_id ?? crypto.randomUUID(), observed, verified, errorChoice};
    row.append(button('この項目を取り消す', () => { if (!canTruthReview()) return; state.missedErrors = state.missedErrors.filter(value => value !== item); row.remove(); }, 'text-button'));
    state.missedErrors.push(item); $('missedErrorList').append(row);
  }
  async function saveTruthReview() {
    if (!canTruthReview() || !state.truthRun || state.busy) return;
    try {
      const complete = $('truthReviewComplete').checked, whole = $('wholeReportChecked').checked;
      if ((whole || complete) && !originalVisibleFor(state.truthRun.revision_id)) throw safeError('この検査に対応する原本を開いて確認してから、原本全体の確認を記録してください。');
      if (complete && !whole) throw safeError('確認完了にするには、指摘のない欄も含めて報告書全体を確認してください。');
      const items = [...state.truthDrafts].map(([ruleId, item]) => {
        const truth = item.truth.value, verified = item.verified.value;
        if (complete && (truth === 'unknown' || !Object.hasOwn(readStates, verified))) throw safeError('全項目の正誤と読取状態を確認するまで完了にはできません。');
        const links = item.previousLinks.filter(id => id !== item.laterRunId);
        if (item.laterRunId && item.later.checked) links.push(item.laterRunId);
        return {rule_id: ruleId, truth, error_id: truth === 'error' ? item.errorChoice.value === 'new' ? item.errorId : item.errorChoice.value : null, verified_read_state: Object.hasOwn(readStates, verified) ? verified : null, detected_in_run_ids: truth === 'error' ? links : []};
      });
      const missed = state.missedErrors.map(item => {
        if (!Object.hasOwn(readStates, item.observed.value) || !Object.hasOwn(readStates, item.verified.value)) throw safeError('指摘されていなかった誤りの読取状態を選択してください。');
        return {opportunity_id: item.identity, error_id: item.errorChoice.value === 'new' ? item.errorId : item.errorChoice.value, read_state: item.observed.value, verified_read_state: item.verified.value};
      });
      await recordEvent('truth_review', {run_id: state.truthRun.run_id, complete, whole_report_checked: whole, items, missed_errors: missed}, complete ? '別担当者による原本全体の確認を記録しました。' : '独立確認の途中経過を保存しました。未確認は未確定として残ります。', 'truthMessage');
    } catch (error) { fail('truthMessage', error, ticket()); }
  }
  async function exportMeasurements() {
    if (!canRead() || state.busy) return;
    const generation = state.generation;
    try {
      const ids = Array.from($('measurementExportReports').selectedOptions).map(item => item.value);
      if (!ids.length) throw safeError('出力する報告書を1件以上選択してください。');
      state.busy = true; controls(); const result = await request('/measurement-export', 'POST', {report_ids: ids});
      if (generation !== state.generation) return;
      await downloadBlob(new Blob([JSON.stringify(result, null, 2)], {type: 'application/json'}), 'emergency-measurement.json', generation);
      message('exportMessage', '測定記録を保存しました。「5つの評価指標」で取り込めます。未測定の値や承認は補っていません。');
    } catch (error) { if (generation === state.generation) fail('exportMessage', error); }
    finally { if (generation === state.generation) { state.busy = false; controls(); } }
  }
  function clearPatterns() {
    state.patternIntent++; state.patternBusy = false;
    $('patternTable').replaceChildren(); message('patternSummary', ''); message('patternMessage', '');
  }
  function patternReports() { return $('patternScope').value === 'selected' ? state.report ? [state.report.report_id] : [] : state.reports.map(report => report.report_id); }
  async function loadPatterns() {
    if (!canRead() || state.patternBusy) return;
    const ids = patternReports(); if (!ids.length) return;
    const generation = state.generation, intent = ++state.patternIntent;
    state.patternBusy = true; controls();
    try {
      const result = await request('/correction-patterns', 'POST', {report_ids: ids});
      if (generation !== state.generation || intent !== state.patternIntent) return;
      $('patternTable').replaceChildren();
      message('patternSummary', '報告書 ' + result.report_count + '件 / 検査 ' + result.run_count + '件 / 独立確認が未確認の検査 ' + result.unreviewed_run_count + '件');
      const table = element('table'), head = element('thead'), headings = element('tr');
      for (const label of ['確認条件', '指摘数', '担当者の判断', '別担当者が確認した誤り', '正誤が未確認', '判断した理由', '設定']) { const cell = element('th', label); cell.scope = 'col'; headings.append(cell); }
      head.append(headings); table.append(head); const body = element('tbody');
      for (const item of list(result.items)) {
        const row = element('tr'), label = element('td'); label.append(element('strong', item.label || item.rule_id), element('div', item.rule_id, 'small muted'));
        const counts = (values, labels) => Object.entries(labels).filter(([key]) => Number.isFinite(values?.[key]) && values[key] > 0).map(([key, text]) => text + ' ' + values[key] + '件').join(' / ') || '記録なし';
        row.append(label, element('td', item.warning_count + '件 / 報告書 ' + item.report_count + '件'), element('td', counts(item.decision_counts, decisions)), element('td', item.verified_error_count + '件'), element('td', item.unresolved_truth_count + '件'), element('td', counts(item.reason_counts, reasonLabels)));
        const configCell = element('td'), config = state.ruleSets.find(ruleSet => ruleSet.config_id === item.rule_set_id);
        if (config) configCell.append(button('設定を開く', () => { switchTab('configuration'); if (state.activeTab === 'configuration') { openRuleSet(config); $('rulesHeading').scrollIntoView({block: 'start'}); } }, 'text-button'));
        else configCell.textContent = '初期候補・AI等';
        row.append(configCell); body.append(row);
      }
      table.append(body); $('patternTable').append(table);
      message('patternMessage', list(result.items).length ? '集計を表示しました。過去の訂正判断だけでは正解と確定しません。ルールとモデルは自動変更していません。' : 'この範囲には集計できる検査記録がありません。');
    } catch (error) { if (generation === state.generation && intent === state.patternIntent) fail('patternMessage', error); }
    finally { if (generation === state.generation && intent === state.patternIntent) { state.patternBusy = false; controls(); } }
  }
  $('recordStudy').onclick = () => recordEvent('study', {cohort: $('measurementCohort').value, activity_kind: $('activityKind').value}, '比較区分を保存しました。導入前の区分では自動チェックを行いません。');
  $('recordWork').onclick = recordManualWork; $('startWork').onclick = startWork; $('pauseWork').onclick = pauseWork;
  $('submissionConfirmed').addEventListener('change', controls); $('recordSubmission').onclick = recordSubmission; $('recordFollowup').onclick = recordFollowup;
  $('reviewerSelect').addEventListener('change', controls);
  $('assignReviewer').onclick = () => state.report && $('reviewerSelect').value && mutate('/reports/' + state.report.report_id + '/reviewer', {expected_version: state.report.version, reviewer_id: $('reviewerSelect').value}, 'reviewerMessage', '確認担当者を指定しました。原本全体の独立確認を依頼できます。');
  $('loadTruthReview').onclick = loadTruthReview; $('addMissedError').onclick = () => addMissedError(); $('saveTruthReview').onclick = saveTruthReview; $('exportMeasurements').onclick = exportMeasurements;
  $('truthRunSelect').addEventListener('change', () => { state.truthIntent++; state.truthRun = null; state.truthDrafts.clear(); state.missedErrors = []; $('truthReviewList').replaceChildren(); $('missedErrorList').replaceChildren(); $('wholeReportChecked').checked = false; $('truthReviewComplete').checked = false; message('truthRunContext', '選んだ検査結果を読み込んでください。'); controls(); });
  $('openTruthSource').onclick = async () => {
    if (!state.truthRun || !state.report || state.busy) return;
    const reportId = state.report.report_id, runId = state.truthRun.run_id, revisionId = state.truthRun.revision_id, generation = state.generation;
    await selectReport(reportId, revisionId); if (generation !== state.generation || state.report?.report_id !== reportId) return;
    $('truthRunSelect').value = runId; await loadTruthReview(); switchTab('reports');
  };
  function localInput(value) {
    const d = new Date(value); if (Number.isNaN(d.getTime())) return '';
    const pad = number => String(number).padStart(2, '0');
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + 'T' + pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
  }
  function editEvent(event) {
    if (!(event.kind === 'work_interval' ? canRecordWork() : canWrite()) || state.busy || event.can_correct !== true || state.workCapture) return;
    if (event.kind === 'work_interval') {
      state.editingWorkEvent = event.event_id; $('workStartedAt').value = localInput(event.payload.started_at); $('workEndedAt').value = localInput(event.payload.ended_at); $('workStage').value = event.payload.stage;
      $('workStartedAt').closest('details').open = true; $('recordWork').textContent = '作業時間を訂正して保存'; $('workStartedAt').focus();
    } else if (event.kind === 'submitted') {
      state.editingSubmissionEvent = event.event_id; $('submittedAt').value = localInput(event.payload.occurred_at); $('submissionConfirmed').checked = false; $('recordSubmission').textContent = '提出日時を訂正して保存'; $('submittedAt').focus();
    }
    message('measurementMessage', '以前の記録を履歴に残し、訂正した内容を新しい記録として保存します。'); controls();
  }
  function cancelWorkCorrection() { state.editingWorkEvent = null; $('workStartedAt').value = ''; $('workEndedAt').value = ''; $('recordWork').textContent = 'この時間を記録'; controls(); }
  function cancelSubmissionCorrection() { state.editingSubmissionEvent = null; $('submittedAt').value = ''; $('submissionConfirmed').checked = false; $('recordSubmission').textContent = '提出を記録'; controls(); }
  $('cancelWorkCorrection').onclick = cancelWorkCorrection; $('cancelSubmissionCorrection').onclick = cancelSubmissionCorrection;
  $('loadPatterns').onclick = loadPatterns; $('patternScope').addEventListener('change', () => { clearPatterns(); controls(); });
  async function loadConfigurations() {
    const generation = state.generation, intent = ++state.configIntent;
    const [profiles, rules, reviewers, sources] = await Promise.all([request('/profiles'), request('/rule-sets'), request('/reviewers'), canConfigure() || canApprove() ? request('/sources') : Promise.resolve([])]);
    if (generation !== state.generation || intent !== state.configIntent) return;
    state.profiles = list(profiles); state.ruleSets = list(rules); state.reviewers = list(reviewers); state.sources = list(sources);
    state.sourceMetadata = state.sources.find(item => item.source_id === state.sourceId) ?? null; renderSourcePicker();
    setOptions('profileSelect', state.profiles.map(item => [item.config_id, configLabel(item)]), '対応表なし・手動で設定');
    setOptions('revisionProfile', state.profiles.map(item => [item.config_id, configLabel(item)]), '選択してください');
    setOptions('checkRules', state.ruleSets.map(item => [item.config_id, configLabel(item)]), '初期の暫定候補');
    setOptions('reviewerSelect', state.reviewers.map(item => [item.user_id, item.display_name]), '選択してください');
    setOptions('reviewConfiguration', [...state.profiles, ...state.ruleSets].map(item => [item.config_id, configLabel(item)]), '選択してください');
    renderConfigLists(); controls();
  }
  (async () => {
    const generation = state.generation;
    try {
      const response = await fetch('/auth/context', {cache: 'no-store'});
      if (!response.ok) throw safeError('ログインと権限を確認できません。');
      const context = await response.json(); if (generation !== state.generation) return;
      state.permissions = new Set(list(context.permissions)); state.userId = context.user_id;
      if (!canRead()) { reset(); message('auditMessage', 'この報告書画面を表示する権限がありません。管理者に確認してください。', true); return; }
      const capabilities = await request('/capabilities'); if (generation !== state.generation) return;
      state.capabilities = capabilities; $('checkDate').value = today(); $('profileValidFrom').value = today();
      message('auditMessage', capabilities.enabled && capabilities.storage_ready ? '原本と照合して確認します。未承認のルール・未検査の欄を区別して表示します。' : 'この環境では新しい原本の取込を利用できません。管理者に稼働状態を確認してください。');
      controls(); await Promise.all([loadReports(), loadConfigurations()]);
    } catch (error) { if (generation === state.generation && !error.cancelled) { reset(); message('auditMessage', 'ログインと利用環境を確認できません。ホームからログインして再読込してください。', true); } }
  })();
})();
