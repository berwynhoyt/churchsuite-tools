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

## Running your own ChurchSuite app using GAE

The [DocExport app](README.md) is run on Google App Engine (GAE). You can run your own web app the same way, or you can use GAE to periodically run your own Python script to automate periodic ChurchSuite tasks. Here is how I set up DocExport on GAE:

1. Follow instructions to [Create a Google Cloud project](https://docs.cloud.google.com/appengine/docs/standard/python3/building-app/creating-gcp-project). Called the project `<yourchurch>-<appname>` (called **[PROJECT_ID]** below). This google cloud interface is complicated, but I'm afraid I can't help you with it. It will make you create a Google billing account and will take your credit card but it won't actually bill you anything unless your app is used several hours a day. Typical usage of DocExport, for example, fits well within the free tier.
2. Note: first test your app on your localhost, e.g. run `python docexport_app.py` and then browse to `localhost:8080`.
3. Create [`app.yaml`](app.yaml) and [`config.py`](config.py) files suitable for your app.
4. Deploy the app to your Google Cloud project by browsing to [Google Cloud Shell](https://shell.cloud.google.com/) and then type your equivalent of:

```sh
git clone https://github.com/berwynhoyt/churchsuite.git
cd churchsuite
gcloud config set project [PROJECT_ID]  # use the project name you selected in point 1 above
# delete artifacts from any previous builds (see below)
gcloud app deploy
```

Now the app will be running on the APP_URL that the command above supplies, typically: `https://[PROJECT_ID].ts.r.appspot.com/`.

**Note:** You are billed for any deployed image bigger than 500MB. Check its size in [Google Cloud Artifact Registry](https://console.cloud.google.com/artifacts). To images small:

* Specify older Pythons in `app.yaml`. The `docexport` app is 461MB with Python 3.12 and 508MB with Python 3.14.
* Before every deployment, delete the old image in [Google Cloud Artifact Registry](https://console.cloud.google.com/artifacts).

### Google Secret Manager

If the app needs access to any secrets, it's better to store them in Google Secret Manager rather than in a file on a public server. You can get a secret using the Python module: `GoogleSecretManager('<project_id>').get('<secret_name>')`. However, first you need to store the secrets in the Google Secret Manager as follows:

1. Go to [Google Cloud Console](https://console.cloud.google.com/welcome).

3. Make sure the name of your Google [PROJECT_ID] is selected in the top-left corner beside Google Cloud.

4. Type "Secret Manager" into the Google Cloud search bar and click it. Enable Secret Manager if necessary.

5. Click "+ Create Secret" for each secret name and value. You only need to enter the name and value of each secret and leave the rest of the settings untouched. Click "Create secret" at the bottom.

6. Add permission for your Google Cloud project to access your secrets by typing the following into your Google Cloud Console, e.g. for secret1 and secret2:

   ```sh
   gcloud secrets add-iam-policy-binding secret1 \
       --member="serviceAccount:[PROJECT_ID]@appspot.gserviceaccount.com" \
       --role="roles/secretmanager.secretAccessor"
   gcloud secrets add-iam-policy-binding secret2 \
       --member="serviceAccount:[PROJECT_ID]@appspot.gserviceaccount.com" \
       --role="roles/secretmanager.secretAccessor"
   ```

If you want to test use of the Google Secrets Manager locally, you need to set up a json key file which you must first get from Google:

1. Go to  [Google Cloud Console](https://console.cloud.google.com/welcome), find `IAM & Admin > Service Accounts`

2. Select the service account for your [Project_ID], go to the **Keys** tab, and add a key of type `json` which will download a json file. Save the json file in a secure location on your computer.

3. Now create two environment variables:

   ```sh
   export GOOGLE_CLOUD_PROJECT=[PROJECT_ID]
   export GOOGLE_APPLICATION_CREDENTIALS=[path_to_your_json_file]
   python docexport_app.py`
   ```

Now you can use `churchsuite.GoogleSecretManager()` to fetch secrets from Google Secret Manager on your local computer.
