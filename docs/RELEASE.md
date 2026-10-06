# Repo Explorer 0.1 release gate

The v0.1 feature scope is frozen. Release work is limited to verification,
packaging, documentation corrections, and fixes for failures in those checks.
Follow-up retrieval, cross-file call graphs, and broader language support remain
future work. Live generation experiments are excluded from this release gate.

## Publication order

1. Prepare and review the source snapshot for GitLab. Exclude local configuration,
   credentials, private source, runtime reports, model caches, and old project branding.
2. Push to the selected GitLab project and run its pipeline. Review the exact commit
   and job artifacts. Fix any failures before moving forward.
3. Publish the verified source revision to the selected GitHub account.
4. Adapt and preview the article drafts in the blog CMS, then publish the series
   with links to the public repository.

No job automatically publishes to GitHub or the blog. The GitLab project URL,
GitHub destination, and CMS records are deployment choices supplied by the owner.
Existing local Git history predates the rename; review it before publishing any
history. A source archive contains only the current release files.

## GitLab CI

The root [`.gitlab-ci.yml`](../.gitlab-ci.yml) has two verification jobs:

| Job | Gate |
| --- | --- |
| `backend` | Locked dependencies, package installation, dependency consistency, Ruff, and backend behavior checks |
| `browser-and-docs` | Locked npm installation, production build and type check, offline browser journeys against the real API, and article rendering at desktop/mobile widths |

Jobs run for branch pushes, merge requests, and tags. The
[workflow rules](https://docs.gitlab.com/ci/yaml/workflow/)
avoid duplicate push pipelines for branches with an open merge request. Tests use
authored fixtures, isolated checkpoint storage, and no model credentials. Browser
checks follow [Playwright's CI setup](https://playwright.dev/docs/ci), using its
container version matching the package lock. Each job has a bounded timeout.

JUnit reports and browser/build/article artifacts expire after seven days.
They are release verification evidence; article content does not advertise test
totals. Remote runner access, dependency downloads, and Linux execution must be
confirmed by the actual GitLab pipeline. Local checks cannot establish remote CI
success. A project or group can configure different default runners or variables;
review those when selecting the destination.

## Local verification

Use the commands under [Developer checks](../README.md#developer-checks). Stop the
preview before E2E: those tests own ports 8018 and 5178. Restore the preview after
verification. Rebuild `docs/site` after E2E regenerates article screenshots, then
run `node frontend/scripts/verify-docs.mjs`.

The five articles remain editorial drafts until the author reviews them and the
CMS previews. The source archive and local checks establish readiness to try the
GitLab gate; publication status must be reported separately.
