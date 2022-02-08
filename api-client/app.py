from flask import Flask, render_template, redirect

app = Flask(__name__)


@app.route("/")
def main():
    return render_template("base.html", title="Home")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html", title="Privacy Policy")


@app.route("/terms")
def terms():
    return render_template("terms.html", title="Terms and Conditions")


@app.errorhandler(404)
def error(error):
    return redirect("/")
