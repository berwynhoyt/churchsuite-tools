#!/usr/bin/env python3
# Example minimal web app to display all the people in your database

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
