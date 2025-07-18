from flask import Flask

app = Flask(__name__)
app.secret_key = "supersecretkey"  # Change to a strong secret key in production

from app import routes
