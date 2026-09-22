"""
Envoi d'annonces Octix (ponctuelles, pas des newsletters récurrentes).
=======================================================================

Réutilise le même compte Gmail + mot de passe d'application que
`envoi_message.py` (variables `MDP` dans le `.env`), mais permet un
objet et un contenu HTML libres, avec des images intégrées (CID)
fournies par l'admin au moment de l'envoi.

Chaque destinataire reçoit un e-mail individuel (jamais de "To" ou
"Cc" groupé) pour ne jamais exposer la liste des adresses Octix
entre elles.
"""

import os
import smtplib
import logging
import time
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("octix_annonce")

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "octix.org@gmail.com"
SENDER_NAME = "Octix"


def _get_app_password() -> str:
    raw_mdp = os.environ.get("MDP", "")
    return raw_mdp.replace(" ", "").strip()


def envoyer_annonce(
    destinataires: list[str],
    objet: str,
    html: str,
    images: list[dict],
    pause_secondes: float = 0.4,
) -> dict:
    """
    Envoie l'annonce à chaque destinataire individuellement.

    `images` : liste de dicts {"cid": str, "filename": str,
    "mimetype": "image/png"|"image/gif"|..., "data": bytes}.
    Le HTML peut référencer une image avec `src="cid:{cid}"`.

    Retourne un rapport :
        {
            "envoyes": [...],
            "echecs": [{"email": ..., "erreur": ...}, ...],
        }
    """

    app_password = _get_app_password()
    rapport = {"envoyes": [], "echecs": []}

    if not app_password:
        err = "Variable d'environnement 'MDP' manquante."
        logger.error("[ANNONCE] %s", err)
        for dest in destinataires:
            rapport["echecs"].append({"email": dest, "erreur": err})
        return rapport

    if not destinataires:
        return rapport

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SENDER_EMAIL, app_password)
            logger.info("[SMTP] Authentification Gmail réussie pour annonce.")

            for dest in destinataires:
                try:
                    msg = EmailMessage()
                    msg["Subject"] = objet
                    msg["From"] = f"{SENDER_NAME} <{SENDER_EMAIL}>"
                    msg["To"] = dest
                    msg["Date"] = formatdate(localtime=True)
                    msg["Message-ID"] = make_msgid(domain="octix.org")

                    msg.set_content(
                        "Ce message nécessite un client compatible HTML pour "
                        "être affiché correctement."
                    )
                    html_part = msg.add_alternative(html, subtype="html")

                    for img in images:
                        html_part.add_related(
                            img["data"],
                            maintype=img["mimetype"].split("/")[0],
                            subtype=img["mimetype"].split("/")[1],
                            cid=f"<{img['cid']}>",
                        )

                    code, response = server.mail(SENDER_EMAIL)
                    if code >= 400:
                        raise smtplib.SMTPResponseException(code, response)

                    code, response = server.rcpt(dest)
                    if code >= 400:
                        raise smtplib.SMTPResponseException(code, response)

                    code, response = server.data(msg.as_bytes())
                    if code >= 400:
                        raise smtplib.SMTPResponseException(code, response)

                    rapport["envoyes"].append(dest)
                    logger.info("[ANNONCE] Envoyé à %s (%s)", dest, code)

                except Exception as exc:
                    logger.error("[ANNONCE] Échec vers %s : %s", dest, exc)
                    rapport["echecs"].append({"email": dest, "erreur": str(exc)})

                # Petite pause pour rester raisonnable vis-à-vis de Gmail
                # (limite ~500 envois/24h sur un compte Gmail gratuit).
                time.sleep(pause_secondes)

    except Exception as exc:
        err = f"Connexion SMTP impossible : {exc}"
        logger.error("[ANNONCE] %s", err)
        deja_traites = {d for d in rapport["envoyes"]} | {
            e["email"] for e in rapport["echecs"]
        }
        for dest in destinataires:
            if dest not in deja_traites:
                rapport["echecs"].append({"email": dest, "erreur": err})

    return rapport
