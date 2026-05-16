# GitHub Launch Checklist

## Repo settings
- Set repository name and short description.
- Set homepage URL if applicable.
- Add a social preview image.
- Enable Issues.
- Enable Discussions if you want design/Q&A traffic separated from Issues.
- Enable Projects if you want roadmap/work tracking.

## Topics
Apply the recommended topics from `repo-metadata/repository_topics.txt`.

## Branch protections
- Protect `main`.
- Require CI checks before merge.
- Prefer pull requests over direct pushes for substantial changes.

## Releases
- Create `v0.3.0-alpha` as the first public release.
- Attach `dist/cognition-core-release-bundle.zip`.
- Paste `repo-metadata/RELEASE_DRAFT_v0.3.0-alpha.md` into the release notes.

## Collaboration surface
- Confirm issue forms render correctly.
- Confirm pull request template appears.
- Confirm CODEOWNERS resolves correctly.
- Confirm Dependabot is enabled.

## SEO/discoverability
- Confirm the README headline and summary match the repository description.
- Add topics.
- Pin the first release.
- Add the repository to the profile pinned repositories if this is a flagship project.

---

## Sponsor Platform Launch Checklist

- [ ] Confirm `.github/FUNDING.yml` includes `github: [GareBear99]`
- [ ] Confirm README sponsor badge links to `https://github.com/sponsors/GareBear99`
- [ ] Confirm `SUPPORT.md` explains sponsor scope and boundaries
- [ ] Confirm `docs/GITHUB_SPONSORS_PLATFORM_SETUP.md` is linked from README
- [ ] Confirm `docs/SPONSOR_ROUTING_INDEX.md` is linked from docs index
- [ ] Confirm release notes include a non-spammy sponsor CTA
- [ ] Confirm GitHub profile and HUB site route to Sponsors
- [ ] Confirm custom software is not promised without separate agreement
