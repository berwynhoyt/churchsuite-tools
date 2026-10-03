# Changelog for docexport.py and docexport_app.py

v1.2.1: Bugfixes:
- `--pagesize letter` and `--starts-from YYYY-MM-DD` no longer crash.
- The web app no longer gives a server error for `?max_age_days=30`.
- Plan names with times like `10:30am` no longer crash sorting.
- "Afternoon" and "evening" plans now sort after morning plans on the same day.
- `12pm` plans now sort at noon, and `12am` plans at midnight.
- The web app heading now has correctly nested HTML.

v1.2.0: Sort 'draft' and 'published' plans properly, and sort by the hour within the day.

v1.1.0: Release that supports churchsuite.py v1.1.0 updates, which allows it to work when there are more than 50 service plans.

v1.0.0: First public release

