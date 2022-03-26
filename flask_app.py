import time
from flask import Flask, Response, jsonify


flask_app = Flask(__name__)


@flask_app.route('/flask')
def home():
    time.sleep(10)
    return Response('Hello to flask', 200)


@flask_app.route('/')
def data():
    return jsonify([{'id': 1}, {'id': 2}])


app = flask_app.wsgi_app
