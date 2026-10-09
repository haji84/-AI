# Workforce checkout and cancellation browser continuation

Canonical main e617b7be/treeaaa0517 has accepted exact/main CI (D17). Source PR86 initial CI37881248722 failed in browser navigation; repaired exact-head CI37882703445 is pending. Protected-search delta is reviewed local work. This checkout delta is isolated and must wait for dependency exact/main acceptance before publication. No migration or new privileges.

User-authorized bounded design: connect existing draft-only Attendance PATCH and draft/reviewed cancellation APIs to the browser. Preserve version checks, current session/rights, Human reason and pending-operation lock. Existing server computes minutes only through approved working rules. Approved entries stay immutable; no new payroll/leave policy. Stored timestamps are displayed/edited explicitly in Asia/Tokyo, independent of the browser timezone. Reuse shared workforce clearing and view-generation guards.

RED tests must cover actually rendered draft edit controls, approved immutability, explicit timezone checkout, one PATCH with expected_version, duplicate clicks and obsolete form handlers. Existing Human-control tests must survive adding explicit cancellation alongside review/approval. Real Chromium must complete draft checkout→Human review→approval and separate draft cancellation using actual endpoints; no fabricated responses.

Chapters25/45/48/54 remain Partial. Team/work-result and roster→dispatch→work result→overtime/allowance linkage, balances/crew UI and policy reconciliation remain internal. Only actual institutional rule values/production acceptance are Human External. No ten-flow/release credit.
