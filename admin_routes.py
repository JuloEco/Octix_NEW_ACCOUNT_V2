"""Espace d'administration Octix.

Accès strictement réservé au compte "Jules" (vérifié via la session
authentifiée par Octix, pas via une donnée modifiable côté client).
"""

import os
from functools import wraps

import requests
from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from compte_routes import login_required
from messages.envoi_message import envoyer_email_admin

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# Comparaison insensible à la casse/espaces, mais le seul compte autorisé
# reste "Jules".
ADMIN_USERNAME = "jules"

OCTIX_URL = os.environ.get("OCTIX_URL", "http://localhost:5050")
OCTIX_INTERNAL_KEY = os.environ.get("OCTIX_INTERNAL_KEY")

# Vercel limite la taille du corps d'une requête (~4,5 Mo). On garde une
# marge pour les en-têtes/texte du formulaire.
TAILLE_MAX_PIECES_JOINTES = 4 * 1024 * 1024


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


def _internal_headers():
    return {"X-Internal-Key": OCTIX_INTERNAL_KEY} if OCTIX_INTERNAL_KEY else {}


def octix_get_all_emails():
    """
    Récupère la liste de tous les e-mails de comptes Octix via l'endpoint
    interne GET /admin/users du service Octix (protégé par X-Internal-Key).

    Réponse attendue : {"users": [{"email": "...", ...}, ...]}

    Retourne (emails, erreur). `emails` est une liste (non vide si succès),
    ou None en cas d'échec, auquel cas `erreur` explique pourquoi.
    """
    try:
        response = requests.get(
            f"{OCTIX_URL}/admin/users",
            headers=_internal_headers(),
            timeout=10,
        )
    except requests.exceptions.RequestException:
        return None, "Octix est injoignable pour le moment."

    if response.status_code == 404:
        return None, (
            "L'endpoint /admin/users n'existe pas encore côté Octix : "
            "il faut l'ajouter au service d'authentification pour pouvoir "
            "envoyer un e-mail à tous les comptes."
        )
    if response.status_code == 401:
        return None, "Clé interne Octix invalide ou manquante (OCTIX_INTERNAL_KEY)."
    if response.status_code != 200:
        return None, f"Erreur Octix HTTP {response.status_code} lors de la récupération des comptes."

    try:
        data = response.json()
        users = data.get("users", [])
    except ValueError:
        return None, "Réponse Octix invalide lors de la récupération des comptes."

    emails = sorted({u["email"].strip() for u in users if u.get("email")})
    if not emails:
        return None, "Aucune adresse e-mail trouvée parmi les comptes Octix."
    return emails, None


def _lire_pieces_jointes(fichiers):
    """Lit les fichiers uploadés et vérifie la taille totale."""
    pieces = []
    taille_totale = 0

    for fichier in fichiers:
        if not fichier or not fichier.filename:
            continue
        contenu = fichier.read()
        if not contenu:
            continue
        taille_totale += len(contenu)
        if taille_totale > TAILLE_MAX_PIECES_JOINTES:
            raise ValueError(
                "Les pièces jointes dépassent la taille maximale autorisée "
                f"({TAILLE_MAX_PIECES_JOINTES // (1024 * 1024)} Mo au total)."
            )
        pieces.append({
            "nom": fichier.filename,
            "contenu": contenu,
            "type_mime": fichier.mimetype or "application/octet-stream",
        })

    return pieces


@admin_bp.route("/emails", methods=["GET", "POST"])
@admin_required
def envoyer_emails():
    if request.method == "POST":
        envoyer_a_tous = request.form.get("envoyer_a_tous") == "on"
        sujet = request.form.get("sujet", "").strip()
        contenu_html = request.form.get("contenu_html", "")
        destinataires_brut = request.form.get("destinataires", "").strip()

        try:
            pieces_jointes = _lire_pieces_jointes(request.files.getlist("pieces_jointes"))
        except ValueError as exc:
            flash(str(exc), "error")
            pieces_jointes = None

        erreur_destinataires = None
        if envoyer_a_tous:
            destinataires, erreur_destinataires = octix_get_all_emails()
            destinataires = destinataires or []
        else:
            destinataires = [
                d.strip()
                for d in destinataires_brut.replace("\n", ",").split(",")
                if d.strip()
            ]

        if pieces_jointes is None:
            pass  # erreur déjà signalée par flash ci-dessus
        elif not sujet:
            flash("Indique un sujet.", "error")
        elif not contenu_html.strip():
            flash("Le contenu HTML ne peut pas être vide.", "error")
        elif erreur_destinataires:
            flash(erreur_destinataires, "error")
        elif not destinataires:
            flash("Indique au moins un destinataire, ou coche « Envoyer à tout le monde ».", "error")
        else:
            resultats = envoyer_email_admin(destinataires, sujet, contenu_html, pieces_jointes)
            reussites = [d for d, (ok, _) in resultats.items() if ok]
            echecs = [(d, msg) for d, (ok, msg) in resultats.items() if not ok]

            if reussites:
                if envoyer_a_tous:
                    flash(f"E-mail envoyé à {len(reussites)} compte(s) Octix.", "success")
                else:
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
