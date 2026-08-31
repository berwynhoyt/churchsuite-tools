# Changelog for churchsuite.py

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
