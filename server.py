"""
Voxa — Shared Flask server
Toutes les apps Dash se montent sur ce serveur unique.
C'est ce serveur qui est exporté comme application WSGI.
"""

from flask import Flask

server = Flask(__name__)