#!/usr/bin/env python3
""" Library to access ChurchSuite data conveniently """

import sys
import os.path
import json
import logging
import pprint
import time

from datetime import datetime
from types import SimpleNamespace
from functools import wraps
from urllib.parse import urljoin, urlencode

import requests
import jinja2
from flask import Flask, session, request, redirect, render_template_string
from requests_oauthlib import OAuth2Session


__version__ = '1.1.0'

class ChurchError(Exception): pass

api = 'https://api.churchsuite.com/v2'

def dump_request(req):
    """ Debugging function to dump a PreparedRequest from request.Request().prepare() or response.request """
    output = f"{req.method} {req.path_url} HTTP/1.1\n"
    output += '\n'.join(f'{k}: {v}' for k, v in req.headers.items())
    output += "\n\n"
    if req.body is not None:
        # Decode body if it is in bytes, handling potential encoding issues
        output += req.body.decode('utf-8') if isinstance(req.body, bytes) else req.body
    return output

def joiner(*args):
    """ Join multiple args to the end of a url, separating them with '/' """
    return '/'.join(str(arg) for arg in args if arg is not None)

def trace_logging():
    """ Detect whether trace-level logging is enabled with a log_level even more verbose than DEBUG (-vvv) """
    return logging.getLogger(__name__).getEffectiveLevel() < logging.DEBUG

class GoogleSecretManager:
    def __init__(self, project_id):
        self.project_id = project_id

    def get(self, secret_id, version_id="latest"):
        """ Access the value of given secret_id from Google Secret Manager; version_id can be "latest" or a specific number """
        # Additional requirement if this function is used: pip install google-cloud-secret-manager
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{self.project_id}/secrets/{secret_id}/versions/{version_id}"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")


class Churchsuite:
    """ Class used to access ChurchSuite data """

    token_url = "https://login.churchsuite.com/oauth2/token"
    auth_url = "https://login.churchsuite.com/oauth2/authorize"
    scope = 'full_access'

    def __init__(self, auth=None, *, raw=None, scope=('full_access',), lazy_auth=False):
        """ Create ChurchSuite instance for access to ChurchSuite data.
            Attempt to authorize using user auth (client_id, client_secret).
            If the authorization expires later, re-authorize using the same auth.
            If filename raw is supplied, store all json text received from the server into that file.
            scope: is a list of scopes (default 'full_access') selected from: https://developer.churchsuite.com/auth#scopes
            lazy_auth: if True, delays authorization until it is first required
        """
        if not auth:
            raise ChurchError("You need to supply (client_id, client_secret) to Churchsuite class")
        self.auth = auth
        self.raw = raw
        if raw is not None:
            # truncate file
            open(raw, 'w').close()
        if not isinstance(scope, (list, tuple)):
            raise Exception("Scope specified to Churchsuite must be a list or tuple")
        self.scope = scope
        self._access_token = None
        if not lazy_auth:
            self.authorize()

    @property
    def access_token(self):
        if not self._access_token or time.time() >= self._token_expiry:
            self.authorize()
        return self._access_token

    def append_raw(self, text):
        if self.raw is not None:
            with open(self.raw, 'a') as f:
                f.write(text)

    def authorize(self):
        """ Return access_token using api_enbaled_user authorization with the authorization credentials self.auth """
        data = {'grant_type': 'client_credentials', 'scope': ' '.join(self.scope)}
        r = requests.post(self.token_url, auth=self.auth, json=data, headers={'Content-Type': 'application/json'})
        r.raise_for_status()
        self._token_expiry = time.time() + float(r.json().get('expires_in')) - 60
        self._access_token = r.json().get('access_token')

    def _update_params(self, params=None, **kwargs):
        """ Update params dict (default={}) with kwargs, appending '[]' to the names of keys whose values are lists/tuple """
        if params is None:
            params = {}
        for k, v in kwargs.items():
            if isinstance(v, (list, tuple)):
                k = k + '[]'
                v = list(v)
            params[k] = v
        return params

    def get1(self, url, id=None, item=None, *, params=None, **kwargs):
        """ Same as get() but fetch at most one page of a list result, not all pages
            and instead of return data, returns an object that contains data and may contain a pagination field
        """
        url = joiner(url, id, item)
        if not url.startswith(api):
            url = joiner(api, url)
        params = self._update_params(params, **kwargs)
        r = requests.get(url, headers={'Authorization': f'Bearer {self.access_token}'}, params=params)
        if trace_logging():
            logging.debug(f"request: {dump_request(r.request).replace('\n', '\n|  ')}")
        r.raise_for_status()
        self.append_raw(json.dumps(r.json(), indent=4) + '\n')
        # Convert json dict to SimpleNamespace (recursively for sub-objects)
        object = json.loads(r.text, object_hook=lambda d: SimpleNamespace(**d))
        formatted_response = f"GET {url} =>\n| {pprint.pformat(object).replace('\n', '\n| ')}"
        if trace_logging():
            logging.debug(formatted_response)
        if not hasattr(object, 'data'):
            raise Exception("No 'data' field found in response to {formatted_response}")
        return object

    def get(self, url, id=None, item=None, *, params=None, **kwargs):
        """ Return 'data' field from ChurchSuite GET response as a SimpleNamespace, or list of SimpleNamespaces if the request returns a list.
            If the result is a list and 'page' is not specified in params or kwargs, then repeatedly fetch all pages and return as a single list.
            If id or item are supplied, they are prefixed with '/' and appended as strings to the url.
            If params dict is supplied, it is updated with kwargs and then sent as json params to the url.
        """
        params = self._update_params(params, **kwargs)
        params['per_page'] = params.get('per_page', 250)  # if per_page not specified, set it to ChurchSuite maximum
        r = self.get1(url, id, item, params=params)
        if not isinstance(r.data, list) or 'page' in params:
            return r.data
        page = 2
        data = r.data
        while r.pagination.next_page:
            r = self.get1(url, id, item, params=params, page=page)
            data += r.data
            page += 1
        return data

    def post(self, url, *, params=None, **kwargs):
        """ Return 'data' field from ChurchSuite POST request as a SimpleNamespace, or list of SimpleNamespaces if the request returns a list.
            If params dict is supplied, it is updated with kwargs and then sent as json params to the url.
        """
        if not url.startswith(api):
            url = joiner(api, url)
        params = self._update_params(params, **kwargs)
        r = requests.post(url, headers={'Authorization': f'Bearer {self.access_token}'}, json=params)
        if trace_logging():
            logging.debug(f"request: {dump_request(r.request).replace('\n', '\n|  ')}")
        r.raise_for_status()
        self.append_raw(json.dumps(r.json(), indent=4) + '\n')
        # Convert json dict to SimpleNamespace (recursively for sub-objects)
        object = json.loads(r.text, object_hook=lambda d: SimpleNamespace(**d))
        formatted_response = f"GET {url} =>\n| {pprint.pformat(object).replace('\n', '\n| ')}"
        if trace_logging():
            logging.debug(formatted_response)
        if not hasattr(object, 'data'):
            raise Exception("No 'data' field found in response to {formatted_response}")
        return object.data

    def get_by_name(self, url, name):
        """ Search for ChurchSuite list item by name at url and return its id or None if it doesn't exist.
            Used, for example, by get_tag_id() to find tags by name:
                `get_by_name('addressbook/tags', tag_name)`
            Only returns exact matches, avoiding near matches from ChurchSuite's fuzzy search.
        """
        data = self.get(url, q=name)
        if not data:
            return None
        for item in data:
            if item.name == name:
                return item.id
        return None

    def get_tag_id(self, tag_name):
        """ Return tag_id or None if the tag does not exit """
        return self.get_by_name('addressbook/tags', tag_name)


# Test function to help a developer see the OAuth PKCE process flow in linear fashion
def test_manual_oauth(client_id, redirect_url=None):
    """ Fetch access access_token using oauth_app authorization with the supplied authorization credentials.
        This is a test function to simulate what occurs with authorize_app_stage{1,2}()
    """
    from requests_oauthlib import OAuth2Session
    oauth = OAuth2Session(client_id, redirect_uri=redirect_url, scope=('full_access',), pkce='S256')
    authorization_url, state = oauth.authorization_url(Churchsuite.auth_url)
    code_verifier = oauth._code_verifier  # fetch from private field as requests-oauthlib does not yet support a public access method
    # In a web app, you would save state for later: session['oauth_state'] = state
    # Simulate callback into Python here by making the user paste in the URL that came back to the browser from to the redirect_url
    print(f"Please authorize at:")
    print(f"    {authorization_url}")
    print()
    print(f"Note: after login, the browser may say the site can't be reached (because you're not running a web server).")
    print(f"But the URL shown in the address bar will still be suitable for pasting here.")
    authorization_response_url = input('Enter the full callback URL (shown in the browser address bar): ')
    # Check that request.args.get('state') != session.pop('oauth_state'); otherwise bomb out with error 400
    # code_verifier = session.pop('code_verifier')
    oauth = OAuth2Session(client_id, redirect_uri=redirect_url)
    oauth._code_verifier = code_verifier  # store into a private field as requests-oauthlib does not yet support a public access method
    json = oauth.fetch_token(Churchsuite.token_url, authorization_response=authorization_response_url, code_verifier=code_verifier)
    return json.get('access_token')


class ChurchsuiteApp(Churchsuite):
    def __init__(self, app, client_id=None, client_secret=None, *, use_pkce=True, login_url='/login', redirect_url='/login/callback', identify_url='/login/identify', css=None, scope=('full_access',)):
        """ ChurchSuite subclass that sets up web server route functions to make the user log in.
            app: the flask app being authorized
            client_id: defaults to app.config['OAUTH_CLIENT_ID'] or, failing that, to the query parameter 'client_id' sent to the a url that triggers login
            client_secret: defaults to app.config['OAUTH_CLIENT_SECRET']
            use_pkce: if True, no client_secret is required (better): select 'public' app on ChurchSuite to use this
            login_url: path of url that routes will redirect to for login if they are decorated with @login_required
            redirect_url: path of url that ChurchSuite will call back after login (must match the redirect_url set in ChurchSuite app config)
            identify_url: path of url used to internally to request client_id from user
            css: if not None, a css template for the identify page, to override the css in this file
            scope: is a list of scopes (default 'full_access') selected from: https://developer.churchsuite.com/auth#scopes
            Note: You can skip sending the user to the identify_url page by supplying client_id=xxx in the request URL.
                Before redirecting to any URL decorated by @login_required, any client_id parameter will always be stripped
                from the URL by the @login_required wrapper, regardless of whether a login was actually necessary.
        """
        self.app = app
        self.raw = None  # it's unlikely the web server wants to retain all the json data
        self.client_id = client_id or app.config.get('OAUTH_CLIENT_ID')
        self.client_secret = client_secret or app.config.get('OAUTH_CLIENT_SECRET')
        self.use_pkce = use_pkce
        self.login_url = login_url
        self.redirect_url = redirect_url
        self.identify_url = identify_url
        self.login_urls = (login_url, redirect_url)
        templates.docx_css = css or templates.docx_css
        self.scope = scope

        app.before_request(self._log_request)
        app.after_request(self._log_response)

        app.add_url_rule(login_url, view_func=self._login)
        app.add_url_rule(redirect_url, view_func=self._callback)
        app.add_url_rule(identify_url, view_func=self._identify)

        # Allow jinja to load the string templates defined in this file
        string_loader = jinja2.DictLoader(vars(templates))
        app.jinja_env.loader = jinja2.ChoiceLoader([string_loader, app.jinja_env.loader])

    @property
    def access_token(self):
        token = session.get('access_token', None)
        if not token or time.time() >= float(session.get('token_expiry', time.time()-60)):
            return None
        return token

    # Debugging logging of full incoming requests during login
    def _log_request(self):
        if request.path in self.login_urls:
            self.app.logger.debug(f"Auth Req {request.url}:\n|  " + (str(request.headers)+request.get_data(as_text=True)).replace('\n', '\n|  '))
    def _log_response(self, response):
        if request.path in self.login_urls:
            self.app.logger.debug(f"Response status [{response.status} by URL {request.url}:\n|  " + response.get_data(as_text=True).replace('\n', '\n|  '))
        return response

    def _login(self):
        """ Get ChurchSuite authorization access_token and store it in the flask session """
        self.move_param_to_session('client_id')
        client_id = self.client_id or session.get('client_id')
        if not client_id:
            return redirect(self.identify_url)
        callback_url = urljoin(request.url_root, self.redirect_url)
        pkce = 'S256' if self.use_pkce else None
        oauth = OAuth2Session(client_id, redirect_uri=callback_url, scope=self.scope, pkce=pkce)
        authorization_url, state = oauth.authorization_url(Churchsuite.auth_url)
        # Store items for the callback when redirected back there
        session['oauth_state'] = state
        session['code_verifier'] = oauth._code_verifier
        return redirect(authorization_url)

    def _identify(self):
        """ Ask user for ChurchSuite client_id and store it in the flask session """
        return render_template_string(templates.docx_identify, login_url=self.login_url, next_url=session.get('next_url', ''))

    def _callback(self):
        """ OAuth callback route that receives the authorization access_token from ChurchSuite """
        if request.args.get('state') != session.pop('oauth_state'):
            return "Invalid state parameter", 400

        callback_url = urljoin(request.url_root, self.redirect_url)
        client_id = self.client_id or session.get('client_id')
        oauth = OAuth2Session(client_id, redirect_uri=callback_url)
        json = oauth.fetch_token(Churchsuite.token_url, authorization_response=request.url, code_verifier=session.pop('code_verifier'))
        session['access_token'] = json.get('access_token')
        session['token_expiry'] = time.time() + float(json.get('expires_in')) - 60
        return redirect(session.pop('next_url', '/'))

    # Define a decorator that requires login for a route and brings them back to the same place.
    # Saves 'next_page' so that it automatically comes back to the page that triggered the login.
    @property
    def login_required(self):
        """ This is a decorator for a view function (route). If the user is not logged in when this route is called,
            save the current page url, redirect the user to login, and bring them back to the same url after login.
        """
        def wrapper(func):
            @wraps(func)
            def check_authorization(*args, **kwargs):
                request_url = self.move_param_to_session('client_id')
                token = session.get('access_token', None)
                expiry = float(session.get('token_expiry', 0))
                self.app.logger.debug(f"Session access_token ({f'length {len(token)}' if token else None}) expires at {datetime.fromtimestamp(expiry) if expiry else None}")
                if not token or not expiry or expiry <= time.time():
                    session['next_url'] = request_url
                    # directly call _login rather than redirecting to it for the sake of speed
                    return self._login()
                return func(*args, **kwargs)
            return check_authorization
        return wrapper

    def move_param_to_session(self, param):
        """ Move the given parameter out of request.url and into the session. Return the modified request url as a string. """
        request_url = request.url
        value = request.args.get(param)
        if value is not None:
            session[param] = value
            # Move client_id from query parameters to session so it doesn't doesn't confuse the app by being in the url query parameters.
            query_params = request.args.to_dict()
            query_params.pop(param)
            request_url = f"{request.base_url}?{urlencode(query_params)}" if query_params else request.base_url
        return request_url


# HTML pages

templates = SimpleNamespace(
    docx_header = """<!DOCTYPE html><html> <head>
            <title>Churchsuite Login</title>
            <style> {% include 'docx_css' %} </style><link rel="icon" href="data:,">
        </head><body>
            <h1 style="margin: 30px 0px 10px;"><a href="javascript:history.back()" style="text-decoration: none;">
                <svg id="logo" fill="#3c4791" width="35" height="35" viewBox="0 0 512 512" style="margin:0px 5px;" transform="translate(0,5)" xmlns="http://www.w3.org/2000/svg">
                <path d="M256 512C397.385 512 512 397.385 512 256C512 114.615 397.385 0 256 0C114.615 0 0 114.615 0 256C0 397.385 114.615 512 256 512Z"/>
                <path fill-rule="evenodd" clip-rule="evenodd" d="M297.773 282.397C320.904 283.664 343.906 286.644 366.582 291.311C383.291 295.131 399.754 299.982 416.278 304.712C424.293 307.016 432.124 310.169 440.077 312.837C442.297 313.565 442.79 314.535 442.05 316.779C430.789 351.267 409.635 381.821 381.133 404.764C362.348 420.086 340.836 431.846 317.688 439.449C315.407 440.238 314.544 439.449 313.804 437.63C306.879 420.805 301.313 403.47 297.156 385.785C293.272 367.108 289.449 348.371 286.428 329.513C284.455 317.021 283.9 304.227 282.79 291.614C282.79 289.371 282.79 287.066 282.359 284.823C281.927 282.579 282.975 282.519 284.702 282.579L297.773 282.397Z" fill="#FDFEFF"/>
                <path fill-rule="evenodd" clip-rule="evenodd" d="M300.732 230.127C295.43 230.127 290.127 230.127 284.825 230.127C282.913 230.127 282.297 229.582 282.358 227.702C283.523 201.063 286.864 174.56 292.347 148.448C295.375 131.891 299.494 115.545 304.678 99.5134C307.515 91.3273 310.844 83.2625 313.557 75.2583C314.297 73.1966 315.53 72.7721 317.565 73.4998C342.722 81.5913 365.938 94.6423 385.794 111.855C405.65 129.069 421.729 150.082 433.048 173.613C436.624 180.829 439.214 188.651 442.112 196.17C442.852 198.05 442.112 198.96 440.385 199.687C419.473 207.412 398.1 213.872 376.385 219.031C351.462 224.779 326.303 228.937 300.732 230.127Z" fill="#FDFEFF"/>
                <path fill-rule="evenodd" clip-rule="evenodd" d="M229.21 292.888C227.734 316.762 224.582 340.508 219.777 363.955C215.164 386.439 208.984 408.583 201.28 430.232C200.416 432.84 199.306 435.326 198.32 437.873C197.333 440.42 196.902 440.056 195.114 439.449C148.944 424.533 110.053 393.286 85.9809 351.767C79.4544 340.62 74.1824 328.807 70.2583 316.536C69.5801 314.475 70.2583 313.626 72.0464 312.898C95.0833 304.306 118.692 297.276 142.705 291.857C165.043 287.253 187.726 284.454 210.528 283.489L227.114 282.7C229.148 282.7 229.827 283.246 229.642 285.247C229.457 287.248 229.333 290.22 229.21 292.888Z" fill="#FDFEFF"/>
                <path fill-rule="evenodd" clip-rule="evenodd" d="M228.908 214.968C228.908 219.213 229.34 223.518 229.648 227.823C229.648 229.582 229.155 230.188 227.367 230.127C199.059 229.573 170.865 226.447 143.143 220.789C118.879 215.374 95.0393 208.261 71.8058 199.505C69.8945 198.838 69.8944 197.868 70.4494 196.231C80.4929 165.162 98.649 137.228 123.104 115.219C143.8 96.3195 168.379 82.0099 195.182 73.2572C197.093 72.5902 197.956 73.2572 198.573 74.8338C202.642 86.9614 207.266 99.0889 210.904 111.702C217.631 135.433 222.617 159.609 225.825 184.043C227.243 194.29 228.045 204.659 229.093 214.968H228.908Z" fill="#FDFEFF"/>
                </svg>
                Identification
            </h1></a>
    """,

    docx_footer = """</body></html>""",

    docx_css = """
        body { margin: 0 30px; }
        html { font-family: "Trebuchet MS", sans-serif; }
        h1, h2, h3, h4, h5, h6 { color: #3c4791; margin-bottom: -10px; }
        a { color: #3c4791; }
        input { color: #3c4791; accent-color: #3c4791; font-family: "Trebuchet MS", sans-serif; }
        input[type="submit"] { font-weight: bold; cursor: pointer; }
        .note-box {
            border: 2px solid #333; /* Thick solid border */
            background-color: #f9f9f9; /* Light grey background */
            padding: 0px 15px; /* top and  bottom inside box */
            border-radius: 5px;
        }
    """,

    docx_identify = """
        {% include 'docx_header' %}
        <p>To use this app you need a Client Identifier from ChurchSuite.</p>
        <form action="{{ login_url }}">
            <label for="client_id">Client Identifier<sup>(<b>Note 1</b>)</sup>:</label>
                <input type="text" id="client_id" name="client_id" autocomplete="off">
                    <span id="error" style="color: red;" {{ '' if request.url == request.referrer else 'hidden' }}>
                        Enter a valid Client Identifier.</span><br>
                <div id="linksection" style="display:none; margin-left: 20px;">Direct link: <a id="autolink"></a><br>
                    (Bookmark this link to skip this page next time.
                    You can also send this link to your ChurchSuite users so they don't need to enter it.)</div><br>
          <input type="submit" value="Login this ChurchSuite client" autofocus>
        </form>

        <br><br>
        <p><b>Note 1:</b> Obtain this by setting up this app in ChurchSuite at:</p>
          <pre>    User Menu -> Settings -> OAuth Apps -> Add OAuth App</pre>
        <p>When adding an app, select "Public" for Application Type, and enter the following into the "Redirect URI" field:</p>
          <pre>    {{ request.url_root }}login/callback</pre>
        <p>ChurchSuite will then display your "Client Identifier" in your newly created app. Enter that number here.</p>

        <script>
            const form = document.querySelector('form')
            const autolink = document.querySelector('#autolink')
            function getCookie(name) {
                let value = `; ${document.cookie}`
                let parts = value.split(`; ${name}=`)
                if (parts.length === 2) return parts.pop().split(';').shift()
            }

            // Store client_id back into cookie on submit
            form.onsubmit = function(f) {
                if (!form.client_id.value) {
                    document.querySelector('#error').hidden = false
                    return false
                }
                const date = new Date();
                date.setTime(date.getTime() + ( 400 * 24 * 60 * 60 * 1000)); // 400 days is max that browsers allow
                document.cookie = "churchsuite_client_id=" + encodeURIComponent(form.client_id.value) + ";expires=" + date.toUTCString() + ";path=/"
                return true  // true allows form submission
            }

            // Auto-fill from cookie on load
            form.client_id.value = getCookie('churchsuite_client_id') ?? ''

            // Update automatic client_id link as user types
            const input = document.querySelector('#client_id')
            input.onchange = input.onkeyup = function(input) {
                if ('{{ next_url }}') {
                    const next_url = new URL('{{ next_url }}')
                    next_url.searchParams.set('client_id', encodeURIComponent(form.client_id.value))
                    autolink.href = autolink.textContent = next_url
                }
                document.querySelector('#linksection').style.display = (form.client_id.value && '{{ next_url }}')? 'block': 'none'
            };
            input.onchange()
        </script>
        {% include 'docx_footer' %}
    """,
)


if __name__ == "__main__":
    if '--app' not in sys.argv:
        import config
        cs = Churchsuite(auth=(config.USER_CLIENT_ID, config.USER_CLIENT_SECRET))
        print(f"Here is your churchsuite access token to use with curl for testing:\n{cs.access_token}\n")
        print("Run with --app to run as a localhost server and test login")
    else:
        logging.basicConfig(level=logging.DEBUG, format=f'%(levelname)s: %(message)s')

        app = Flask(__name__)
        app.config.from_pyfile('config_defaults.py', silent=True)  # update app config from version-tracked config defaults
        app.config.from_pyfile('config.py', silent=True)  # update app config from non-version-tracked config file
        app.config['SESSION_COOKIE_SECURE'] = False  # https not required for localhost debugging
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1' # allow debug using insecure http://localhost
        cs = ChurchsuiteApp(app)

        @app.route('/')
        @cs.login_required
        def index():
            return f"""<h1>Logged in!</h1><p style="overflow-wrap: break-word;">Access token is: {cs.access_token}."""

        port = int(os.environ.get("PORT", 8080))
        app.run(debug=True, host="0.0.0.0", port=port)
