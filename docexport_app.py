#!/usr/bin/env python3
""" Run a web app on port $PORT (default 8080) to fetch the upcoming service plans from ChurchSuite and export into docx format """

import os
import sys
import io
import bisect
import secrets
from datetime import date, timedelta
from types import SimpleNamespace
from collections import defaultdict
from operator import attrgetter

import jinja2
import flask
from flask import Flask, session, request, url_for, redirect, render_template_string
from requests_oauthlib import OAuth2Session

from churchsuite import ChurchsuiteApp
import docexport

__version__ = docexport.__version__

app = Flask(__name__)
app.config['SESSION_COOKIE_SECURE'] = True  # require secure https (set to False only for localhost debugging below)
app.config.from_pyfile('config_defaults.py', silent=True)  # update from version-tracked config defaults
app.config.from_pyfile('config.py', silent=True)  # update from non-version-tracked config file

cs = ChurchsuiteApp(app, scope=['planning.read'])

@app.route('/docx')
def home():
    """ Display home page """
    return render_template_string(templates.home, __version__=__version__)

@app.route('/docx/version')
def version():
    return __version__

@app.route('/docx/plans')
@cs.login_required
def plans():
    """ List download link for each service plan up to query parameter 'max_age_days' (default 400), sorted by date """
    max_age_days = request.args.get('max_age_days', 400)
    today = date.today()
    plans = docexport.get_serviceplans(cs, starts_from=date.today()-timedelta(days=max_age_days))
    # separate plans by date
    past = defaultdict(list)
    upcoming = defaultdict(list)
    for plan in reversed(plans):
        old = date.fromisoformat(plan.date) < today
        plan.title = f"{plan.name}{' (draft)' if (plan.status=='draft' and not old) else ''}"
        plan.filename = f"{plan.date} {plan.title}"
        # add plans to each date and keep in sorted order using bisect and the plan.hour attribute
        if date.fromisoformat(plan.date) >= today:
            bisect.insort(upcoming[plan.date], plan, key=attrgetter('hour'))
        else:
            bisect.insort(past[plan.date], plan, key=attrgetter('hour'))
    return render_template_string(templates.plans, past=past, upcoming=upcoming, today=today)

@app.route('/docx/plan/<int:plan_id>')
@cs.login_required
def plan(plan_id):
    """ Download the specific plan by plan_id """
    stream = io.BytesIO()
    title = request.args.get('title', f'plan_{plan_id}')
    filename = docexport.plan2docx(cs, plan_id, title, stream=stream)
    return flask.send_file(stream, as_attachment=True, download_name=filename)

# If there is more than one app run by this server, override this in the parent app that imports this module """
@app.errorhandler(404)
def notfound(e):
    if request.path == '/':
        return redirect(url_for('home', **request.args))
    return "<h1>Not found</h1>The requested URL was not found on this server.", 404


# HTML pages

templates = SimpleNamespace(
    header = """<!DOCTYPE html><html> <head><style> {% include 'css' %} </style><link rel="icon" href="data:,"></head>
        <!-- Google tag (gtag.js) -->
        <script async src="https://www.googletagmanager.com/gtag/js?id=G-MF5P9QH2LL"></script>
        <script>
          window.dataLayer = window.dataLayer || [];
          function gtag(){dataLayer.push(arguments);}
          gtag('js', new Date());

          gtag('config', 'G-MF5P9QH2LL');
        </script>
        <body>
        <h1 style="margin: 30px 0px 10px;"><a href="/docx" style="text-decoration: none;">
            <svg id="logo" fill="#3c4791" height="35" width="35" viewBox="0 0 493.525 493.525" style="margin: 0px 5px;" transform="translate(0,5) scale(1,-1)">
                <path d="M430.557,79.556H218.44c21.622,12.688,40.255,29.729,54.859,49.906h157.258
                    c7.196,0,13.063,5.863,13.063,13.06v238.662c0,7.199-5.866,13.064-13.063,13.064H191.894c-7.198,0-13.062-5.865-13.062-13.064
                    V222.173c-6.027-3.1-12.33-5.715-18.845-7.732c-3.818,11.764-12.105,21.787-23.508,27.781c-2.39,1.252-4.987,2.014-7.554,2.844
                    v136.119c0,34.717,28.25,62.971,62.968,62.971h238.663c34.718,0,62.969-28.254,62.969-62.971V142.522
                    C493.525,107.806,465.275,79.556,430.557,79.556z"/>
                <path d="M129.037,175.989c51.419,1.234,96.388,28.283,122.25,68.865c2.371,3.705,6.434,5.848,10.657,5.848
                    c1.152,0,2.322-0.162,3.46-0.486c5.377-1.545,9.114-6.418,9.179-12.006c0-0.504,0-1.01,0-1.51
                    c0-81.148-64.853-147.023-145.527-148.957V64.155c0-5.492-3.038-10.512-7.879-13.078c-2.16-1.139-4.533-1.707-6.889-1.707
                    c-2.94,0-5.848,0.88-8.35,2.584L5.751,120.526C2.162,122.98,0.018,127.041,0,131.394c-0.017,4.338,2.113,8.418,5.687,10.902
                    l100.17,69.451c2.518,1.753,5.459,2.631,8.414,2.631c2.355,0,4.696-0.553,6.857-1.676c4.855-2.549,7.909-7.6,7.909-13.092V175.989z
                    "/>
            </svg>
        DocExport</h1></a>
    """,

    footer = """</body></html>""",

    css = """
        body { margin: 0 30px; }
        html { font-family: "Trebuchet MS", sans-serif; }
        h1, h2, h3, h4, h5, h6 { color: #3c4791; margin-bottom: -10px; }
        a { color: #3c4791; }
        a:active { cursor: progress; }
        input { color: #3c4791; accent-color: #3c4791; font-family: "Trebuchet MS", sans-serif; }
        input[type="submit"] { font-weight: bold; cursor: pointer; }
        .note-box {
            border: 2px solid #333; /* Thick solid border */
            background-color: #f9f9f9; /* Light grey background */
            padding: 0px 15px; /* top and  bottom inside box */
            border-radius: 5px;
        }
    """,

    home = """
        {% include 'header' %}
        <p style="color: #3c4791;"><b>Church service plan beautifier for ChurchSuite that exports service plans as docx files.<br/>Version {{ __version__ }}.
            Examples, documentation, and source code <a href="https://github.com/berwynhoyt/churchsuite">here</a>.</b></p>

        <form action="/docx/plans" >
            <input type="hidden" name="client_id" value="">
            <input type="submit" value="Download service plans">
        </form>

        <script>
            const params = new URLSearchParams(window.location.search)
            const form = document.querySelector('form')
            form.client_id.value = params.get('client_id')
            form.client_id.disabled = !form.client_id.value  // disable if no client_id specified
        </script>

        {% include 'footer' %}
    """,

    plans = """
        {% include 'header' %}

        <p><b>Upcoming service plans:</b></p>
        <ul>{% for day, plans in upcoming.items() %}
            <li>{{ day }}: {% for plan in plans %}
                <a id="plan_{{ plan.id }}" href="plan/{{ plan.id }}?title={{ plan.filename | urlencode }}" download="{{ plan.filename }}.docx">{{ plan.title }}</a>
                {{ '' if loop.last else ' | ' }}
            {% endfor %}</li>
        {% endfor %}</ul>
        <span style="margin-left: 60px;">=> <a href="#DownloadUpcoming" onclick="downloadMultiple(upcomingPlans); return false;"><b>download all above</b></a></span>

        <p><b>Past service plans:</b></p>
        <ul>{% for day, plans in past.items() %}
            <li>{{ day }}: {% for plan in plans %}
                <a id="plan_{{ plan.id }}" href="plan/{{ plan.id }}?title={{ plan.filename | urlencode }}" download="{{ plan.filename }}.docx">{{ plan.title }}</a>
                {{ '' if loop.last else ' | ' }}
            {% endfor %}</li>
        {% endfor %}</ul>

        <script>
            const upcomingPlans = [
                {% for plans in upcoming.values() %}
                    {% for plan in plans %}
                        {{ plan.id }},
                    {% endfor %}
                {% endfor %}
            ]
            function downloadMultiple(plans) {
                plans.forEach((plan_id, i) => {
                    // timeout delay prevents the browser from blocking simultaneous requests
                    setTimeout(() => {
                        document.getElementById("plan_" + plan_id).click()
                    }, i * 250)
                })
            }
        </script>

        {% include 'footer' %}
    """,
)

# Allow jinja to load the string templates defined above
string_loader = jinja2.DictLoader(vars(templates))
app.jinja_env.loader = jinja2.ChoiceLoader([string_loader, app.jinja_env.loader])


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.DEBUG, format=f'%(levelname)s: %(message)s')

    app.config['SESSION_COOKIE_SECURE'] = False # https not required for localhost debugging
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1' # allow debug using insecure http://localhost
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=True, host="0.0.0.0", port=port)
