## Hosting your own ChurchSuite app in the cloud using Google Services

You don't have to host your own ChurchSuite web app. You can run it for free on Google Cloud Run or GAE. It can either run your ChurchSuite app as a service or you can make it run your Python script periodically to automate periodic ChurchSuite tasks. 

### Google Cloud Setup

1. Follow instructions to [Create a Google Cloud project](https://docs.cloud.google.com/appengine/docs/standard/python3/building-app/creating-gcp-project). Call the project `<yourchurch>-<appname>` (called **[PROJECT_ID]** below). This google cloud interface is complicated, but I'm afraid I can't help you with it. It will make you create a Google billing account and will take your credit card but it won't actually bill you anything unless your app is used several hours a day. Typical usage of DocExport, for example, fits well within the free tier.
2. Note: first test your app on your localhost, e.g. run `python docexport_app.py` and then browse to `localhost:8080`.
3. Create a [`config.py`](config.py) file suitable for your app if necessary to override items in `config_defaults.py`.
4. Deploy the app to your Google Cloud project by browsing to [Google Cloud Shell](https://shell.cloud.google.com/) and then type your equivalent of:

```sh
git clone https://github.com/berwynhoyt/churchsuite-tools.git
cd churchsuite-tools
gcloud config set project [PROJECT_ID]  # use the project name you selected in point 1 above
```

### Option 1: Using Cloud Run (recommended)

Now deploy it with cloud run:

```sh
gcloud run deploy [APP_NAME] --source . --region [REGION] --allow-unauthenticated
```

Replace `[APP_NAME]` with a name for your service and `[REGION]` with a Google Cloud region near you, e.g. `australia-southeast1`. Cloud Run will build a container image and prompt you to enable any APIs it needs the first time you deploy.

By default, Cloud Run starts the app with `gunicorn -b :8080 main:app`. The repository's [`main.py`](main.py) simply runs `docexport_app`. To deploy a different app, create a `Procfile` containing one line: `web: gunicorn -b :$PORT contacts_app:app`

Now the app will be running on the URL that the command above supplies, typically: `https://[APP_NAME]-[HASH]-[REGION].a.run.app/`.

**Custom domain:** To change Cloud Run's ugly URL, you have to have a domain of your own and map it as follows:

1. Verify domain ownership in [Google Search Console](https://search.google.com/search-console), using the same Google account as your Cloud Run project.
2. Run `gcloud run domain-mappings create --service [APP_NAME] --domain [yourdomain] --region [REGION]`. This tells you exactly which DNS record to add at your registrar -- typically a `CNAME` to `ghs.googlehosted.com` for a subdomain, or `A`/`AAAA` records for an apex domain.

### Option 2: Using GAE (older method)

Instead of Cloud Run, you can deploy on Google App Engine (GAE). This is an older mechanism, and slightly more difficult. The [DocExport app](README.md) is run on Google App Engine (GAE).

First perform the "Google Cloud Setup" instructions above. Then modify `app.yaml` in this repository to suit yourself. (Cloud Run above doesn't require this file.)

**Note:** Before you deploy, delete artifacts from any previous builds. This is because you are billed for any deployed image bigger than 500MB. Note that Google Cloud Run (above) doesn't have this limitation. Check its size in [Google Cloud Artifact Registry](https://console.cloud.google.com/artifacts). To make images small:

* Specify older Pythons in `app.yaml`. The `docexport` app is 461MB with Python 3.12 and 508MB with Python 3.14.
* Before every deployment, delete the old image in [Google Cloud Artifact Registry](https://console.cloud.google.com/artifacts).

Then deploy:

```sh
gcloud app deploy
```

Now the app will be running on the APP_URL that the command above supplies, typically: `https://[PROJECT_ID].[REGION_ID].r.appspot.com/` where for Australia, for example, REGION_ID = `ts`

**Custom domain:** To change GAE's ugly URL, you have to have a domain of your own and map the same as for Google Cloud Run above, except use this command in step 2: `gcloud app domain-mappings create --domain [yourdomain]`.

### Google Secret Manager

If the app needs access to any secrets, it's better to store them in Google Secret Manager rather than in a file on a public server. You can get a secret using the Python module: `GoogleSecretManager('<project_id>').get('<secret_name>')`. However, first you need to store the secrets in the Google Secret Manager as follows:

1. Go to [Google Cloud Console](https://console.cloud.google.com/welcome).

2. Make sure the name of your Google [PROJECT_ID] is selected in the top-left corner beside Google Cloud.

3. Type "Secret Manager" into the Google Cloud search bar and click it. Enable Secret Manager if necessary.

4. Click "+ Create Secret" for each secret name and value. You only need to enter the name and value of each secret and leave the rest of the settings untouched. Click "Create secret" at the bottom.

5. Add permission for your Google Cloud project to access your secrets by typing the following into your Google Cloud Console, e.g. for secret1 and secret2:

   ```sh
   gcloud secrets add-iam-policy-binding secret1 \
       --member="serviceAccount:[SERVICE_ACCOUNT]" \
       --role="roles/secretmanager.secretAccessor"
   gcloud secrets add-iam-policy-binding secret2 \
       --member="serviceAccount:[SERVICE_ACCOUNT]" \
       --role="roles/secretmanager.secretAccessor"
   ```

   Replace `[SERVICE_ACCOUNT]` with the service account your app runs as:

   * Cloud Run: `[PROJECT_NUMBER]-compute@developer.gserviceaccount.com` (the Compute Engine default service account).
     Find your `[PROJECT_NUMBER]` with `gcloud projects describe [PROJECT_ID] --format="value(projectNumber)"`.
   * GAE: `[PROJECT_ID]@appspot.gserviceaccount.com`.

If you want to test use of the Google Secrets Manager locally, you need to set up a json key file which you must first get from Google:

1. Go to  [Google Cloud Console](https://console.cloud.google.com/welcome), find `IAM & Admin > Service Accounts`

2. Select the service account for your [PROJECT_ID], go to the **Keys** tab, and add a key of type `json` which will download a json file. Save the json file in a secure location on your computer.

3. Now create two environment variables:

   ```sh
   export GOOGLE_CLOUD_PROJECT=[PROJECT_ID]
   export GOOGLE_APPLICATION_CREDENTIALS=[path_to_your_json_file]
   python docexport_app.py
   ```

Now you can use `churchsuite.GoogleSecretManager()` to fetch secrets from Google Secret Manager on your local computer (you may need to `pip install google-cloud-secret-manager`).
