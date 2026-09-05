"""Connexion et espace personnel Octix."""

import os
from functools import wraps

import requests
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

OCTIX_URL = os.environ.get("OCTIX_URL", "http://localhost:5050")
compte_bp = Blueprint("compte", __name__)


def _auth_headers():
    token = session.get("octix_token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def _json_or_empty(response):
    try:
        return response.json() if response.content else {}
    except ValueError:
        return {}


def _octix_login(username, password):
    try:
        response = requests.post(
            f"{OCTIX_URL}/login",
            json={"username": username, "password": password},
            timeout=5,
        )
        data = _json_or_empty(response)
        if response.status_code == 200:
            return True, data
        return False, data.get("error", "Pseudo ou mot de passe incorrect.")
    except requests.exceptions.RequestException:
        return False, "Octix est injoignable pour le moment. Réessaie dans un instant."


def _request(method, path, payload=None):
    try:
        response = requests.request(
            method,
            f"{OCTIX_URL}{path}",
            json=payload,
            headers=_auth_headers(),
            timeout=5,
        )
        return response.status_code, _json_or_empty(response)
    except requests.exceptions.RequestException:
        return 503, {"error": "Octix est injoignable pour le moment."}


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if "octix_token" not in session:
            flash("Connecte-toi pour ouvrir ton espace Octix.", "info")
            return redirect(url_for("compte.connexion", next=request.path))
        return view_func(*args, **kwargs)
    return wrapped


@compte_bp.route("/connexion", methods=["GET", "POST"])
def connexion():
    if "octix_token" in session and request.method == "GET":
        return redirect(url_for("compte.mon_compte"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            flash("Entre ton pseudo et ton mot de passe.", "error")
            return render_template("login.html")

        ok, result = _octix_login(username, password)
        if not ok:
            flash(result, "error")
            return render_template("login.html", username=username)

        session["octix_token"] = result.get("token")
        session["octix_username"] = result.get("username", username)
        return redirect(url_for("compte.mon_compte"))

    return render_template("login.html")


@compte_bp.route("/deconnexion")
def deconnexion():
    session.pop("octix_token", None)
    session.pop("octix_username", None)
    flash("Tu es déconnecté.", "success")
    return redirect(url_for("compte.connexion"))


@compte_bp.route("/compte")
@compte_bp.route("/mon-compte")
@login_required
def mon_compte():
    status, profil = _request("GET", "/account/me")
    if status == 401:
        session.clear()
        flash("Ta session a expiré, reconnecte-toi.", "error")
        return redirect(url_for("compte.connexion"))
    if status != 200:
        flash(profil.get("error", "Impossible de charger ton compte pour le moment."), "error")
        return redirect(url_for("compte.connexion"))

    progress_status, progress = _request("GET", "/account/learncode-progress")
    if progress_status != 200:
        progress = {"has_progress": False}
    return render_template("account.html", profil=profil, progress=progress)


@compte_bp.route("/compte/role", methods=["POST"])
@compte_bp.route("/mon-compte/role", methods=["POST"])
@login_required
def changer_role():
    role = request.form.get("classroom_role", "")
    if role not in ("eleve", "prof"):
        flash("Rôle Classroom invalide.", "error")
        return redirect(url_for("compte.mon_compte"))
    status, result = _request("PUT", "/account/classroom-role", {"classroom_role": role})
    flash(
        "Profil Classroom mis à jour." if status == 200 else result.get("error", "Impossible de mettre à jour le profil Classroom."),
        "success" if status == 200 else "error",
    )
    return redirect(url_for("compte.mon_compte"))


@compte_bp.route("/compte/mot-de-passe", methods=["POST"])
@compte_bp.route("/mon-compte/mot-de-passe", methods=["POST"])
@login_required
def changer_mot_de_passe():
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    if len(new_password) < 6:
        flash("Le nouveau mot de passe doit contenir au moins 6 caractères.", "error")
        return redirect(url_for("compte.mon_compte"))
    status, result = _request("PUT", "/account/password", {
        "current_password": current_password,
        "new_password": new_password,
    })
    flash(
        "Mot de passe changé avec succès." if status == 200 else result.get("error", "Impossible de changer le mot de passe."),
        "success" if status == 200 else "error",
    )
    return redirect(url_for("compte.mon_compte"))


@compte_bp.route("/compte/supprimer", methods=["POST"])
@compte_bp.route("/mon-compte/supprimer", methods=["POST"])
@login_required
def supprimer_compte():
    password = request.form.get("password", "")
    status, result = _request("DELETE", "/account", {"password": password})
    if status == 200:
        session.clear()
        flash("Ton compte Octix a été supprimé.", "success")
        return redirect(url_for("compte.connexion"))
    flash(result.get("error", "Impossible de supprimer le compte."), "error")
    return redirect(url_for("compte.mon_compte"))
