"""Espace d'administration Octix.

Accès strictement réservé au compte "Jules" (vérifié via la session
authentifiée par Octix, pas via une donnée modifiable côté client).
"""

from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from compte_routes import login_required
from messages.envoi_message import envoyer_email_admin

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# Comparaison insensible à la casse/espaces, mais le seul compte autorisé
# reste "Jules".
ADMIN_USERNAME = "jules"


def admin_required(view_func):
    """Exige une session Octix valide ET que l'utilisateur soit "Jules"."""

    @wraps(view_func)
    @login_required
    def wrapped(*args, **kwargs):
        username = (session.get("octix_username") or "").strip().lower()
        if username != ADMIN_USERNAME:
            # 403 : on ne masque pas l'existence de la route, mais seul
            # "Jules" peut effectivement s'y connecter et l'utiliser.
            abort(403)
        return view_func(*args, **kwargs)

    return wrapped


@admin_bp.route("/emails", methods=["GET", "POST"])
@admin_required
def envoyer_emails():
    if request.method == "POST":
        destinataires_brut = request.form.get("destinataires", "").strip()
        sujet = request.form.get("sujet", "").strip()
        contenu_html = request.form.get("contenu_html", "")

        destinataires = [
            d.strip()
            for d in destinataires_brut.replace("\n", ",").split(",")
            if d.strip()
        ]

        if not destinataires:
            flash("Indique au moins un destinataire.", "error")
        elif not sujet:
            flash("Indique un sujet.", "error")
        elif not contenu_html.strip():
            flash("Le contenu HTML ne peut pas être vide.", "error")
        else:
            resultats = envoyer_email_admin(destinataires, sujet, contenu_html)
            reussites = [d for d, (ok, _) in resultats.items() if ok]
            echecs = [(d, msg) for d, (ok, msg) in resultats.items() if not ok]

            if reussites:
                flash(f"E-mail envoyé à : {', '.join(reussites)}.", "success")
            for destinataire, message in echecs:
                flash(f"Échec pour {destinataire} : {message}", "error")

            return redirect(url_for("admin.envoyer_emails"))

    return render_template(
        "admin_emails.html",
        destinataires=request.form.get("destinataires", ""),
        sujet=request.form.get("sujet", ""),
        contenu_html=request.form.get("contenu_html", ""),
    )
