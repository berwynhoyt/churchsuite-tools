# Changelog for churchsuite.py

v1.2.0:

- New Churchsuite.put() and delete() methods.
- New get_by_name(), get_tag_id(), get_flow_id(), get_stages() and get_stage_id() methods look up ids by name.
- Name lookups are case-insensitive unless case_sensitive=True is given.
- Tag, flow and stage lookups take a module parameter (default 'addressbook').
- Churchsuite.get1() is renamed request(), and can now make any type of request.
- Running churchsuite.py directly prints an access token for testing. Use --app to test the login server.

Bugfixes:
- Logging in no longer gives a server error when the login session has expired.
- Requests no longer hang forever if ChurchSuite stops responding.
- API errors now include ChurchSuite's own explanation of what went wrong.
- Trace logs now show the correct HTTP method, not always GET.
- Login bookmark links now work when the page URL has several query parameters.
- The client ID in bookmark links is no longer encoded twice.
- Custom login CSS given to one app no longer affects other apps.
- The login page heading now has correctly nested HTML.

v1.1.0:

- Churchsuite.post() method is now supported
- Churchsuite.get() method now automatically captures all pages of returned results using repeated requests unless page=n is explicity specified.
- Churchsuite.get() and post() methods now allow just the endpoint to be specified and will automatically prepend the churchsuite API url 'https://api.churchsuite.com/v2' with joining slash if necessary.
- Lists and tuples passed as parameters to get() are now automatically and transparently encoded as multiple-url parameters with the parameter name correctly suffixed with '[]'.
- Updated tools to specify the specific scopes they require (now that ChurchSuite supports this) rather than 'full_access'.

Bugfixes:
- Now correctly handles multiple scopes being specified (previously failed because it joined them with commas instead of spaces).
- Updated contacts.py to work with the new standard of client secrets being stored in config.py

v1.0.0: First public release
