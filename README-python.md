## ChurchSuite Python Module

The `churchsuite.py` Python module makes it easy to create Python apps and scripts for the ChurchSuite API v2. Not only does it provide a class that supports queries to ChurchSuite, it also automates Churchsuite login, and capture of the user's `client_id`. This is the same module used for the [DocExport app](README.md). It requires Python >= 3.12 for backslashes in f-strings.

## Quick Examples

To print all the people in your database:

```python
import churchsuite
import config

cs = churchsuite.Churchsuite(auth=[config.USER_CLIENT_ID, config.USER_CLIENT_SECRET])
people = cs.get('addressbook/contacts', per_page=100, status='active')
for p in people:
	print(f"{p.first_name} {p.last_name}: {p.email}")
```

To make a web app that does the same in a browser:

```python
import os
import secrets
from flask import Flask
import churchsuite
from churchsuite import ChurchsuiteApp

app = Flask(__name__)
app.config['SESSION_COOKIE_SECURE'] = True  # require secure https (set to False only for localhost debugging below)
app.config['SECRET_KEY'] = secrets.token_hex()  # see config_defaults.py for an explanation

cs = ChurchsuiteApp(app)

@app.route('/')
def home():
    return """Click <a href="/people">here</a> to see everyone."""

@app.route('/people')
@cs.login_required
def people():
    people = cs.get('addressbook/contacts', per_page=100, status='active')
    return '<br>'.join(f"{p.first_name} {p.last_name}: {p.email}" for p in people)

if __name__ == "__main__":
    app.config['SESSION_COOKIE_SECURE'] = False # https not required for localhost debugging
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1' # allow debug using insecure http://localhost
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=True, host="0.0.0.0", port=port)
```

You can test this app on your local computer by simply running `python app.py` and browsing to `localhost:8080`. However, first you will have to set up a new app on ChurchSuite to point the "Redirect URI" to `localhost:8080/login/callback`.

See [`docexport_app.py`](docexport_app.py) for a web app that is more realistic, but still short.

## Installation

Install [Python](https://www.python.org/downloads/) >= 3.12, then:

```bash
# Set up a Python virtual environment
[ ! -d ".venv" ] && python -m venv .venv
export VIRTUAL_ENV="$PWD/.venv"

# Clone this repository and download Python prerequisites
git clone https://github.com/berwynhoyt/churchsuite.git
cd churchsuite
pip install -r requirements-base.txt
```

Now you're ready to create your own Python web app.

If you want to run a **local Python** script to authenticate without a web app, you also need to create a file called `config.py` [your ChurchSuite API keys](https://developer.churchsuite.com/auth):

```python
USER_CLIENT_ID = "your-client-id"
USER_CLIENT_SECRET = "your-client-secret"
```

## OAuth Authorization

In the context of a Flask web app, the Python module also implements all the pages needed to for the app to login to ChurchSuite using OAuth. This can be done by simply applying the decorator `@cs.login_required` to any route handler function (after the @app.route decorator), as shown in the app example above. Any route that requires access to ChurchSuite data may have this decorator and the user will first be required to login if necessary. The login will fetch an `access_token` from ChurchSuite and store it in the web session which the ChurchsuiteApp instance will subsequently use for every access to ChurchSuite data.

The Python module also automates capture of `client_id` from the user. Ordinarily the user would have to supply a `client_id` so that ChurchSuite knows which customer to login for church database access. The `client_id` can then be preserved in a browser cookie for future use. Alternatively, a `client_id` may be supplied in a URL parameter. All this is automated by the Python module. The user is asked for their `client_id` and given instructions on how to obtain it. Their `client_id` is preserved in a browser cookie for 400 days (the maximum allowed), and the user is also given a URL that includes the `client_id` to use in future, if they prefer. This client-specific URL may be given ChurchSuite users by the church administrator so that the user never has to worry about a `client_id`.

## Running your own ChurchSuite app in the cloud using Google Services

You don't have to host your own ChurchSuite web app. You can run it for free on Google Cloud. It can either run your ChurchSuite app as a service or you can make it run your Python script periodically to automate periodic ChurchSuite tasks. Instructions [here](README-python-hosted.md).
