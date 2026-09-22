"""
Outil d'annonces Octix.
========================

Trois étapes, protégées par un mot de passe admin séparé
(`ANNONCE_ADMIN_PASSWORD` dans le `.env`, à ne pas confondre avec un
compte Octix classique) :

    1. /admin/annonces/nouvelle  -> Objet + fichiers (images à intégrer)
    2. /admin/annonces/html      -> Corps HTML de l'e-mail (textarea)
    3. /admin/annonces/apercu    -> Aperçu rendu + confirmation d'envoi

Comme l'app est déployée sur du serverless (Vercel), on ne peut pas
compter sur une variable en mémoire ou un fichier temporaire pour
faire le lien entre les 3 requêtes HTTP (elles peuvent atterrir sur
des instances différentes). Les données (objet, images encodées,
HTML) voyagent donc dans des champs cachés de formulaire d'une étape
à l'autre, jusqu'à l'envoi final.
"""

import base64
import os
from functools import wraps

import requests
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from messages.envoi_annonce import envoyer_annonce
from dotenv import load_dotenv
load_dotenv()

annonce_bp = Blueprint("annonce", __name__, url_prefix="/admin/annonces")

OCTIX_URL = os.environ.get("OCTIX_URL", "http://localhost:5050")
OCTIX_INTERNAL_KEY = os.environ.get("OCTIX_INTERNAL_KEY")
ANNONCE_ADMIN_PASSWORD = os.environ.get("ANNONCE_ADMIN_PASSWORD", "mdpa")

MIMETYPES_AUTORISES = {
    "image/png": "png",
    "image/gif": "gif",
    "image/jpeg": "jpg",
}
TAILLE_MAX_IMAGE = 3 * 1024 * 1024  # 3 Mo par image


def _internal_headers():
    return {"X-Internal-Key": OCTIX_INTERNAL_KEY} if OCTIX_INTERNAL_KEY else {}


def octix_get_all_emails():
    """
    Récupère la liste (username, email) de tous les comptes Octix.

    ATTENTION : suppose que l'API Octix expose GET /users. Si ce
    n'est pas encore le cas côté service d'authentification, il faut
    l'ajouter (voir note en fin de réponse).
    """
    try:
        response = requests.get(
            f"{OCTIX_URL}/users",
            headers=_internal_headers(),
            timeout=10,
        )
        if response.status_code != 200:
            return None, f"Octix a répondu {response.status_code} sur /users."
        data = response.json()
        utilisateurs = data.get("users", data) if isinstance(data, dict) else data
        emails = [u["email"] for u in utilisateurs if u.get("email")]
        return emails, None
    except requests.exceptions.RequestException as exc:
        return None, f"Octix est injoignable pour récupérer les inscrits ({exc})."
    except (ValueError, KeyError, TypeError) as exc:
        return None, f"Réponse inattendue de l'API Octix ({exc})."


def _construire_apercu(corps_html: str, images: list[dict]) -> str:
    """Remplace les cid: par des data URI, uniquement pour l'aperçu navigateur."""
    apercu_html = corps_html
    for img in images:
        if img.get("data_b64"):
            data_uri = f"data:{img['mimetype']};base64,{img['data_b64']}"
            apercu_html = apercu_html.replace(f"cid:{img['cid']}", data_uri)
    return apercu_html


def admin_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("annonce_admin"):
            flash("Accès réservé — connecte-toi à l'outil d'annonces.", "info")
            return redirect(url_for("annonce.connexion", next=request.path))
        return view_func(*args, **kwargs)
    return wrapped


@annonce_bp.route("/connexion", methods=["GET", "POST"])
def connexion():
    if request.method == "POST":
        mot_de_passe = request.form.get("mot_de_passe", "")
        if not ANNONCE_ADMIN_PASSWORD:
            flash("ANNONCE_ADMIN_PASSWORD n'est pas configuré côté serveur.", "error")
        elif mot_de_passe == ANNONCE_ADMIN_PASSWORD:
            session["annonce_admin"] = True
            return redirect(url_for("annonce.nouvelle"))
        else:
            flash("Mot de passe incorrect.", "error")
    return render_template("annonce_connexion.html")


@annonce_bp.route("/deconnexion")
def deconnexion():
    session.pop("annonce_admin", None)
    flash("Déconnecté de l'outil d'annonces.", "success")
    return redirect(url_for("annonce.connexion"))


@annonce_bp.route("/nouvelle", methods=["GET", "POST"])
@admin_required
def nouvelle():
    if request.method == "POST":
        objet = request.form.get("objet", "").strip()

        if not objet:
            flash("L'objet est obligatoire.", "error")
            return render_template("annonce_nouvelle.html")

        images = []
        fichiers = request.files.getlist("images")
        for index, fichier in enumerate(fichiers, start=1):
            if not fichier or not fichier.filename:
                continue
            if fichier.mimetype not in MIMETYPES_AUTORISES:
                flash(f"Format non supporté : {fichier.filename} (PNG, JPG ou GIF uniquement).", "error")
                return render_template("annonce_nouvelle.html")

            contenu = fichier.read()
            if len(contenu) > TAILLE_MAX_IMAGE:
                flash(f"{fichier.filename} dépasse 3 Mo.", "error")
                return render_template("annonce_nouvelle.html")

            images.append({
                "cid": f"image{index}",
                "filename": fichier.filename,
                "mimetype": fichier.mimetype,
                "data_b64": base64.b64encode(contenu).decode("ascii"),
            })

        emails, erreur = octix_get_all_emails()
        if erreur:
            flash(erreur, "error")
            return render_template("annonce_nouvelle.html")

        return render_template(
            "annonce_html.html",
            objet=objet,
            images=images,
            nb_destinataires=len(emails),
        )

    return render_template("annonce_nouvelle.html")


@annonce_bp.route("/html", methods=["GET", "POST"])
@admin_required
def html_step():
    if request.method != "POST" or not request.form.get("objet"):
        flash("Commence par remplir l'objet et les fichiers de l'annonce.", "info")
        return redirect(url_for("annonce.nouvelle"))

    objet = request.form.get("objet", "")
    corps_html = request.form.get("corps_html", "").strip()

    # Les images voyagent en champs cachés depuis l'étape précédente.
    images = []
    index = 0
    while True:
        cid = request.form.get(f"images-{index}-cid")
        if cid is None:
            break
        images.append({
            "cid": cid,
            "filename": request.form.get(f"images-{index}-filename", ""),
            "mimetype": request.form.get(f"images-{index}-mimetype", ""),
            "data_b64": request.form.get(f"images-{index}-data", ""),
        })
        index += 1

    if not corps_html:
        flash("Le contenu HTML est obligatoire.", "error")
        return render_template("annonce_html.html", objet=objet, images=images, nb_destinataires=None)

    return render_template(
        "annonce_apercu.html",
        objet=objet,
        images=images,
        corps_html=corps_html,
        apercu_html=_construire_apercu(corps_html, images),
    )


@annonce_bp.route("/apercu", methods=["POST"])
@admin_required
def apercu():
    objet = request.form.get("objet", "")
    corps_html = request.form.get("corps_html", "")

    images = []
    index = 0
    while True:
        cid = request.form.get(f"images-{index}-cid")
        if cid is None:
            break
        images.append({
            "cid": cid,
            "filename": request.form.get(f"images-{index}-filename", ""),
            "mimetype": request.form.get(f"images-{index}-mimetype", ""),
            "data_b64": request.form.get(f"images-{index}-data", ""),
        })
        index += 1

    if not objet or not corps_html:
        flash("Session incomplète, recommence la création de l'annonce.", "error")
        return redirect(url_for("annonce.nouvelle"))

    if request.form.get("confirmer") != "1":
        # Simple re-affichage (ne devrait pas arriver depuis l'UI normale).
        return render_template(
            "annonce_apercu.html", objet=objet, images=images, corps_html=corps_html,
            apercu_html=_construire_apercu(corps_html, images),
        )

    emails, erreur = octix_get_all_emails()
    if erreur:
        flash(erreur, "error")
        return render_template(
            "annonce_apercu.html", objet=objet, images=images, corps_html=corps_html,
            apercu_html=_construire_apercu(corps_html, images),
        )

    images_bytes = [
        {
            "cid": img["cid"],
            "mimetype": img["mimetype"],
            "data": base64.b64decode(img["data_b64"]),
        }
        for img in images
    ]

    rapport = envoyer_annonce(emails, objet, corps_html, images_bytes)

    return render_template(
        "annonce_resultat.html",
        objet=objet,
        nb_envoyes=len(rapport["envoyes"]),
        nb_echecs=len(rapport["echecs"]),
        echecs=rapport["echecs"],
    )
