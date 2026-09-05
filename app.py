"""Portail de compte Octix.

Le portail centralise l'inscription, la récupération de mot de passe et les
pages publiques de l'identité Octix. La connexion et la gestion du compte
sont isolées dans ``compte_routes.py``.
"""

import os
import secrets
import time
from urllib.parse import quote

import requests
from flask import Flask, flash, redirect, render_template, request, url_for

from compte_routes import compte_bp
from messages.envoi_message import envoyer_code_reinitialisation, envoyer_email_confirmation

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "octix_portal_secret")
app.register_blueprint(compte_bp)

OCTIX_URL = os.environ.get("OCTIX_URL", "http://localhost:5050")
OCTIX_INTERNAL_KEY = os.environ.get("OCTIX_INTERNAL_KEY")

APPS = [
    {"key": "opsiom", "name": "Opsiom", "tagline": "Recherche IA", "file": "opsiom.png", "description": "Expérimentation, modèles et outils d'intelligence artificielle."},
    {"key": "omnia", "name": "Omnia", "tagline": "Apprentissage du code", "file": "omnia.png", "description": "Apprendre à programmer avec un parcours clair et progressif."},
    {"key": "axiom", "name": "Axiom", "tagline": "Jeux vidéo", "file": "axiom.png", "description": "Les expériences ludiques et multijoueurs de l'écosystème."},
]

RESET_CODES = {}
CODE_DUREE_VALIDITE = 10 * 60
TENTATIVES_MAX = 5


def _internal_headers():
    return {"X-Internal-Key": OCTIX_INTERNAL_KEY} if OCTIX_INTERNAL_KEY else {}


def octix_register(username, password, email, classroom_role):
    try:
        response = requests.post(
            f"{OCTIX_URL}/register",
            json={
                "username": username,
                "password": password,
                "email": email,
                "classroom_role": classroom_role,
            },
            timeout=15,
        )
        app.logger.info("Octix /register -> HTTP %s : %s", response.status_code, response.text[:500])
        if response.status_code in (200, 201):
            return True, None
        if response.status_code == 409:
            return False, "Ce nom d'utilisateur ou cet e-mail est déjà utilisé."
        try:
            data = response.json()
            error = data.get("error") or data.get("message") or data.get("detail")
        except Exception:
            error = None
        return False, error or f"Erreur Octix HTTP {response.status_code}."
    except requests.exceptions.Timeout:
        return False, "Octix met trop de temps à répondre. Réessaie dans quelques secondes."
    except requests.exceptions.ConnectionError:
        return False, "Impossible de joindre le serveur Octix."
    except requests.exceptions.RequestException as exc:
        app.logger.exception("Erreur HTTP vers Octix API : %r", exc)
        return False, "Une erreur de communication avec Octix est survenue."


def octix_get_email(username):
    try:
        response = requests.get(
            f"{OCTIX_URL}/user/{quote(username, safe='')}/email",
            headers=_internal_headers(),
            timeout=5,
        )
        return response.json().get("email") if response.status_code == 200 else None
    except requests.exceptions.RequestException:
        return None


def octix_reset_password(username, new_password):
    try:
        response = requests.post(
            f"{OCTIX_URL}/reset-password",
            json={"username": username, "new_password": new_password},
            headers=_internal_headers(),
            timeout=5,
        )
        if response.status_code == 200:
            return True, None
        try:
            return False, response.json().get("error", "Erreur lors de la réinitialisation.")
        except Exception:
            return False, "Erreur lors de la réinitialisation."
    except requests.exceptions.RequestException:
        return False, "Octix est injoignable pour le moment. Réessaie dans un instant."


def generer_code():
    return f"{secrets.randbelow(1_000_000):06d}"


@app.context_processor
def inject_global_context():
    return {"octix_apps": APPS}


@app.route("/")
def home():
    return render_template("home.html", apps=APPS)


@app.route("/inscription", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        classroom_role = request.form.get("classroom_role", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")

        if not username or not email or not password or not classroom_role:
            flash("Merci de remplir tous les champs.", "error")
        elif "@" not in email or "." not in email.split("@")[-1]:
            flash("Cet e-mail ne semble pas valide.", "error")
        elif classroom_role not in ("prof", "eleve"):
            flash("Merci de choisir Professeur ou Élève.", "error")
        elif len(password) < 6:
            flash("Le mot de passe doit contenir au moins 6 caractères.", "error")
        elif password != password2:
            flash("Les deux mots de passe ne correspondent pas.", "error")
        else:
            ok, error = octix_register(username, password, email, classroom_role)
            if ok:
                succes_email, msg_email = envoyer_email_confirmation(email, username)
                app.logger.info("Résultat e-mail de bienvenue : succes=%s, msg=%s", succes_email, msg_email)
                return render_template(
                    "register.html",
                    success=True,
                    username=username,
                    email_sent=succes_email,
                )
            flash(error, "error")

    return render_template("register.html", success=False)


# Alias de compatibilité avec d'anciens liens.
@app.route("/register")
def register_legacy():
    return redirect(url_for("register"), code=301)


@app.route("/pourquoi-email")
def why_email():
    return render_template("why_email.html")


@app.route("/apps")
def apps_page():
    return render_template("apps.html", apps=APPS)


@app.route("/a-propos")
def about():
    return render_template("about.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")


@app.route("/mot-de-passe-oublie", methods=["GET", "POST"])
def mot_de_passe_oublie():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        if not username:
            flash("Merci d'indiquer un pseudo.", "error")
            return render_template("forgot_password.html", step="request")

        email = octix_get_email(username)
        if email:
            code = generer_code()
            RESET_CODES[username] = {
                "code": code,
                "expires_at": time.time() + CODE_DUREE_VALIDITE,
                "attempts": 0,
            }
            succes, message = envoyer_code_reinitialisation(email, username, code)
            app.logger.info("Résultat e-mail reset : succes=%s, msg=%s", succes, message)

        # Réponse volontairement identique si le pseudo n'existe pas.
        return render_template("forgot_password.html", step="verify", username=username)

    return render_template("forgot_password.html", step="request")


@app.route("/reinitialiser-mot-de-passe", methods=["POST"])
def reinitialiser_mot_de_passe():
    username = request.form.get("username", "").strip()
    code = request.form.get("code", "").strip()
    password = request.form.get("password", "")
    password2 = request.form.get("password2", "")
    entry = RESET_CODES.get(username)

    if password != password2:
        flash("Les deux mots de passe ne correspondent pas.", "error")
        return render_template("forgot_password.html", step="verify", username=username)
    if len(password) < 6:
        flash("Le mot de passe doit contenir au moins 6 caractères.", "error")
        return render_template("forgot_password.html", step="verify", username=username)
    if not entry:
        flash("Ce code a expiré ou n'existe plus. Redemande un code.", "error")
        return render_template("forgot_password.html", step="request")
    if time.time() > entry["expires_at"]:
        RESET_CODES.pop(username, None)
        flash("Ce code a expiré. Redemande-en un nouveau.", "error")
        return render_template("forgot_password.html", step="request")
    if entry["attempts"] >= TENTATIVES_MAX:
        RESET_CODES.pop(username, None)
        flash("Trop de tentatives. Redemande un nouveau code.", "error")
        return render_template("forgot_password.html", step="request")
    if code != entry["code"]:
        entry["attempts"] += 1
        flash("Code incorrect.", "error")
        return render_template("forgot_password.html", step="verify", username=username)

    ok, error = octix_reset_password(username, password)
    RESET_CODES.pop(username, None)
    if not ok:
        flash(error, "error")
        return render_template("forgot_password.html", step="request")
    return render_template("forgot_password.html", step="done")


@app.errorhandler(404)
def not_found(_error):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(debug=True, port=5051)
