from flask import Flask, current_app

app = Flask(__name__)


def background_thread():
    return current_app.name
