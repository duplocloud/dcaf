# Project Change Log

A running narrative of significant non-code changes made to this repository: what was done, why, and the expected impact.

| Date | Change | Files Affected | Reasoning | Benefit |
|------|--------|----------------|-----------|---------|
| 2025-07-28 | Created **Gap Analysis Checklist** | `docs/gaps.md` | Provide a single place to capture engineering gaps and track progress. | Improves visibility and accountability for remediation work. |
| 2025-07-28 | Added **Ruff** as recommended linter and CI step | `docs/best-practices.md`, `docs/gaps.md` | Establish clear linting standards and automated enforcement. | Higher code quality, consistent style, faster feedback from CI. |
| 2025-07-28 | Documented **“src” layout** guidance | `docs/best-practices.md` | Educate contributors on preferred project structure and alternatives. | Reduces onboarding friction; avoids import path pitfalls. |
| 2025-07-28 | Removed **Butler-specific** wording to generalise best-practice guide | `docs/best-practices.md` | Make guidelines reusable across multiple projects. | Broader applicability; easier adoption elsewhere. | 