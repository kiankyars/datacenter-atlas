# New Zealand Fast-track official-page lane

`new-zealand-fast-track-2026-07-18-v1` is a deliberately bounded planning
source. It retains two current project candidates—Auckland Surf Park Community
Stage 2 and Datagrid FTA104—and one older Auckland planning observation as
related context. It is not a New Zealand-wide search or a unique-site census.

The Fast-track site blocks faithful scripted retrieval with a managed challenge.
Capture therefore requires two canonical browser-rendered text extracts: the
current Auckland project page and the Fast-track copyright statement. The three
MfE pages are fetched directly, checked against exact evidence markers, and
reduced to canonical text extracts before retention. No full page design,
images, attachments, plans, comments, or third-party documents enter the bundle.

The physical status is `proposed` and review-only for all three observations.
Application milestones never become construction or operation evidence. The
current Auckland page's 54 hectares cover the entire mixed project, not the data
centre. The prior page's 7-hectare solar farm powers the development generally,
so it remains untyped context rather than data-centre power or energy.

The optional advisory-group report is not retained. Its applicant-supplied
project-description content is not clearly within the official page-text reuse
licence, so the lane emits no Datagrid capacity, power, or annual-energy value.

Capture with externally verified browser extracts:

```sh
python3 scripts/fetch_build_new_zealand_fast_track.py \
  --capture-only \
  --browser-extract-directory /path/to/browser-extracts \
  --capture-directory /path/to/new-capture
```

Build from an existing capture and validate offline:

```sh
python3 scripts/fetch_build_new_zealand_fast_track.py \
  --capture-directory /path/to/new-capture
python3 scripts/fetch_build_new_zealand_fast_track.py --validate-only
```
