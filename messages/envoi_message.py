"""
Envoi des e-mails Octix (Bienvenue & Code de réinitialisation) via Brevo.
=========================================================================

On passe par le relais SMTP de Brevo (et non par l'API HTTP) car les
e-mails Octix embarquent des images en pièces jointes intégrées (CID :
logo et GIF). L'API transactionnelle de Brevo ne gère pas les images CID,
alors que le relais SMTP transmet le message MIME tel quel.

Variables d'environnement :
    BREVO_SMTP_LOGIN    identifiant SMTP (du type xxxx@smtp-brevo.com)
    BREVO_SMTP_KEY      clé SMTP (commence par « xsmtpsib- »), PAS la clé API
    BREVO_SENDER_EMAIL  adresse d'expéditeur (vérifiée / domaine authentifié)
    BREVO_SENDER_NAME   nom affiché (optionnel, défaut : « Octix »)
"""

import re
import smtplib
import os
import sys
import logging
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from html import escape
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("octix_email")

BASE_DIR = Path(__file__).resolve().parent

SMTP_SERVER = "smtp-relay.brevo.com"
SMTP_PORT = 587
HUB_URL = "https://omni-lbhc.onrender.com"


def _get_config() -> tuple[dict | None, str | None]:
    """
    Lit la configuration Brevo depuis l'environnement.

    Retourne (config, None) si tout est présent,
    ou (None, message_d_erreur) s'il manque des variables.
    """
    config = {
        "login": os.environ.get("BREVO_SMTP_LOGIN", "").strip(),
        "key": os.environ.get("BREVO_SMTP_KEY", "").strip(),
        "sender_email": os.environ.get("BREVO_SENDER_EMAIL", "").strip(),
        "sender_name": os.environ.get("BREVO_SENDER_NAME", "Octix").strip(),
    }

    variables = {
        "login": "BREVO_SMTP_LOGIN",
        "key": "BREVO_SMTP_KEY",
        "sender_email": "BREVO_SENDER_EMAIL",
    }
    manquantes = [nom for cle, nom in variables.items() if not config[cle]]

    if manquantes:
        return None, (
            "Variable(s) d'environnement manquante(s) : "
            + ", ".join(manquantes)
        )

    return config, None


def _smtp_response(response) -> str:
    """Transforme proprement une réponse SMTP en texte lisible."""
    if isinstance(response, bytes):
        return response.decode("utf-8", errors="replace")
    return str(response)


def _nouveau_message(config: dict, destinataire: str, sujet: str) -> EmailMessage:
    """Crée un message avec les en-têtes communs (From, To, Date, Message-ID)."""
    msg = EmailMessage()

    msg["Subject"] = sujet
    msg["From"] = formataddr((config["sender_name"], config["sender_email"]))
    msg["To"] = destinataire
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(
        domain=config["sender_email"].split("@")[-1]
    )

    return msg


def _send_message_with_trace(
    server: smtplib.SMTP,
    msg: EmailMessage,
    expediteur: str,
    destinataire: str
) -> tuple[bool, str]:
    """
    Envoie le message en suivant précisément la transaction SMTP.

    On vérifie séparément :
        MAIL FROM
        RCPT TO
        DATA

    Aucun contenu du mail n'est écrit dans les logs.
    """

    # ---------------------------------------------------------
    # 1. MAIL FROM
    # ---------------------------------------------------------

    code, response = server.mail(expediteur)

    logger.info(
        "[SMTP] MAIL FROM <%s> -> %s %s",
        expediteur,
        code,
        _smtp_response(response)
    )

    if code >= 400:
        return (
            False,
            f"MAIL FROM refusé ({code}): "
            f"{_smtp_response(response)}"
        )

    # ---------------------------------------------------------
    # 2. RCPT TO
    # ---------------------------------------------------------

    code, response = server.rcpt(destinataire)

    logger.info(
        "[SMTP] RCPT TO <%s> -> %s %s",
        destinataire,
        code,
        _smtp_response(response)
    )

    if code >= 400:
        return (
            False,
            f"RCPT TO refusé ({code}): "
            f"{_smtp_response(response)}"
        )

    # ---------------------------------------------------------
    # 3. DATA
    # ---------------------------------------------------------

    code, response = server.data(msg.as_bytes())

    logger.info(
        "[SMTP] DATA -> %s %s",
        code,
        _smtp_response(response)
    )

    if code >= 400:
        return (
            False,
            f"DATA refusé ({code}): "
            f"{_smtp_response(response)}"
        )

    return (
        True,
        f"SMTP accepté ({code}): "
        f"{_smtp_response(response)}"
    )


def _transmettre(
    config: dict,
    msg: EmailMessage,
    destinataire: str
) -> tuple[bool, str]:
    """Ouvre la connexion au relais Brevo et envoie le message."""

    with smtplib.SMTP(
        SMTP_SERVER,
        SMTP_PORT,
        timeout=10
    ) as server:

        # TLS
        server.starttls()

        # Authentification Brevo (login SMTP + clé SMTP)
        server.login(
            config["login"],
            config["key"]
        )

        logger.info("[SMTP] Authentification Brevo réussie")

        # -------------------------------------------------
        # Transaction SMTP détaillée
        # -------------------------------------------------

        ok, result = _send_message_with_trace(
            server,
            msg,
            config["sender_email"],
            destinataire
        )

    if not ok:
        logger.error(
            "[EMAIL] Échec transaction SMTP vers %s : %s",
            destinataire,
            result
        )

    return ok, result


def envoyer_email_confirmation(
    destinataire: str,
    username: str
) -> tuple[bool, str]:
    """
    Envoie l'e-mail de bienvenue à `destinataire`.
    """

    config, err = _get_config()

    if err:
        logger.error(f"[EMAIL] {err}")
        return False, err

    try:

        # =====================================================
        # CONSTRUCTION DU MESSAGE
        # =====================================================

        msg = _nouveau_message(
            config,
            destinataire,
            "Ton compte Octix a été créé avec succès !"
        )

        msg.set_content(
            f"Bienvenue {username} ! "
            f"Ton compte Octix est prêt.\n"
            f"Accède à nos services ici : {HUB_URL}"
        )

        # -----------------------------------------------------
        # Version HTML
        # -----------------------------------------------------

        html_path = BASE_DIR / "email_dark.html"

        if not html_path.exists():
            return (
                False,
                f"Fichier {html_path.name} introuvable."
            )

        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()

        html = (
            html
            .replace("{{USERNAME}}", escape(username))
            .replace("{{HUB_URL}}", HUB_URL)
        )

        msg.add_alternative(html, subtype="html")

        # -----------------------------------------------------
        # Images intégrées
        # -----------------------------------------------------

        logo_path = BASE_DIR / "octix.png"
        gif_path = BASE_DIR / "tick-dark-octix.gif"

        html_part = msg.get_payload(1)

        if html_part is not None:

            if logo_path.exists():

                with open(logo_path, "rb") as f:
                    html_part.add_related(
                        f.read(),
                        maintype="image",
                        subtype="png",
                        cid="<octix_logo.png>"
                    )

            if gif_path.exists():

                with open(gif_path, "rb") as f:
                    html_part.add_related(
                        f.read(),
                        maintype="image",
                        subtype="gif",
                        cid="<tick_dark_icon>"
                    )

        # =====================================================
        # ENVOI VIA BREVO
        # =====================================================

        ok, result = _transmettre(config, msg, destinataire)

        if not ok:
            return False, result

        # =====================================================
        # SUCCÈS
        # =====================================================

        logger.info(
            "[EMAIL] E-mail accepté par Brevo pour %s : %s",
            destinataire,
            result
        )

        return True, result

    except smtplib.SMTPAuthenticationError:

        err_msg = (
            "Authentification Brevo refusée : vérifie "
            "BREVO_SMTP_LOGIN et BREVO_SMTP_KEY (clé SMTP, pas clé API)."
        )

        logger.error(f"[EMAIL] {err_msg}")

        return False, err_msg

    except Exception as e:

        err_msg = f"Échec d'envoi e-mail: {e}"

        logger.error(
            f"[EMAIL] {err_msg}"
        )

        return False, err_msg


def envoyer_code_reinitialisation(
    destinataire: str,
    username: str,
    code: str
) -> tuple[bool, str]:
    """
    Envoie le code à 6 chiffres pour
    la réinitialisation du mot de passe.
    """

    config, err = _get_config()

    if err:
        logger.error(f"[EMAIL] {err}")
        return False, err

    try:

        # =====================================================
        # CONSTRUCTION DU MESSAGE
        # =====================================================

        msg = _nouveau_message(
            config,
            destinataire,
            f"Ton code de réinitialisation Octix : {code}"
        )

        msg.set_content(
            f"Bonjour {username},\n\n"
            f"Voici ton code de réinitialisation Octix : "
            f"{code}\n"
            f"Il est valable 10 minutes. "
            f"Si tu n'es pas à l'origine de cette demande, "
            f"ignore cet e-mail."
        )

        # -----------------------------------------------------
        # Version HTML
        # -----------------------------------------------------

        html_path = BASE_DIR / "email_dark_code.html"

        if not html_path.exists():
            return (
                False,
                f"Fichier {html_path.name} introuvable."
            )

        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()

        html = (
            html
            .replace("{{USERNAME}}", escape(username))
            .replace("{{CODE}}", escape(str(code)))
        )

        msg.add_alternative(
            html,
            subtype="html"
        )

        # -----------------------------------------------------
        # Logo
        # -----------------------------------------------------

        # add_alternative() ne renvoie rien : on récupère la partie HTML
        # (la 2e du message) pour pouvoir y rattacher le logo.
        html_part = msg.get_payload(1)

        logo_path = BASE_DIR / "octix.png"

        if (
            html_part is not None
            and logo_path.exists()
        ):

            with open(logo_path, "rb") as f:
                html_part.add_related(
                    f.read(),
                    maintype="image",
                    subtype="png",
                    cid="<octix_logo.png>"
                )

        # =====================================================
        # ENVOI VIA BREVO
        # =====================================================

        ok, result = _transmettre(config, msg, destinataire)

        if not ok:
            return False, result

        logger.info(
            "[EMAIL] Code accepté par Brevo pour %s : %s",
            destinataire,
            result
        )

        return True, result

    except smtplib.SMTPAuthenticationError:

        err_msg = (
            "Authentification Brevo refusée : vérifie "
            "BREVO_SMTP_LOGIN et BREVO_SMTP_KEY (clé SMTP, pas clé API)."
        )

        logger.error(f"[EMAIL] {err_msg}")

        return False, err_msg

    except Exception as e:

        err_msg = f"Échec d'envoi code: {e}"

        logger.error(
            f"[EMAIL] {err_msg}"
        )

        return False, err_msg


def _html_vers_texte_brut(html: str) -> str:
    """
    Extraction très basique de texte à partir d'HTML, utilisée uniquement
    comme repli texte brut pour les e-mails admin (le rendu réel reste
    la version HTML fournie).
    """
    texte = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", html)
    texte = re.sub(r"(?s)<[^>]+>", " ", texte)
    texte = re.sub(r"\s+", " ", texte).strip()
    return texte or "Ce message ne peut être affiché qu'au format HTML."


def envoyer_email_admin(
    destinataires: list[str],
    sujet: str,
    html_content: str,
    pieces_jointes: list[dict] | None = None,
) -> dict[str, tuple[bool, str]]:
    """
    Envoie un e-mail avec un contenu HTML libre depuis l'espace admin Octix.

    Un message distinct est envoyé à chaque destinataire (ils ne se voient
    pas entre eux). Le HTML fourni n'est ni modifié ni échappé : il est
    envoyé tel quel comme corps du message.

    `pieces_jointes` est une liste optionnelle de dicts :
        {"nom": str, "contenu": bytes, "type_mime": str}
    Les mêmes pièces jointes sont attachées à chaque envoi.

    Retourne un dict {destinataire: (succes, message)}.
    """

    config, err = _get_config()

    if err:
        logger.error(f"[EMAIL][ADMIN] {err}")
        return {destinataire: (False, err) for destinataire in destinataires}

    pieces_jointes = pieces_jointes or []
    texte_brut = _html_vers_texte_brut(html_content)
    resultats: dict[str, tuple[bool, str]] = {}

    for destinataire in destinataires:
        try:
            msg = _nouveau_message(config, destinataire, sujet)
            msg.set_content(texte_brut)
            msg.add_alternative(html_content, subtype="html")

            for piece in pieces_jointes:
                type_mime = piece.get("type_mime") or "application/octet-stream"
                maintype, _, subtype = type_mime.partition("/")
                msg.add_attachment(
                    piece["contenu"],
                    maintype=maintype or "application",
                    subtype=subtype or "octet-stream",
                    filename=piece["nom"],
                )

            ok, result = _transmettre(config, msg, destinataire)
            resultats[destinataire] = (ok, result)

            if ok:
                logger.info(
                    "[EMAIL][ADMIN] E-mail accepté par Brevo pour %s : %s",
                    destinataire, result
                )
            else:
                logger.error(
                    "[EMAIL][ADMIN] Échec d'envoi pour %s : %s",
                    destinataire, result
                )

        except smtplib.SMTPAuthenticationError:
            err_msg = (
                "Authentification Brevo refusée : vérifie "
                "BREVO_SMTP_LOGIN et BREVO_SMTP_KEY (clé SMTP, pas clé API)."
            )
            logger.error(f"[EMAIL][ADMIN] {err_msg}")
            resultats[destinataire] = (False, err_msg)
            # Inutile de retenter les destinataires suivants : l'authentification
            # échouera de la même façon pour chacun d'eux.
            for restant in destinataires:
                if restant not in resultats:
                    resultats[restant] = (False, err_msg)
            break

        except Exception as e:
            err_msg = f"Échec d'envoi e-mail : {e}"
            logger.error(f"[EMAIL][ADMIN] {err_msg}")
            resultats[destinataire] = (False, err_msg)

    return resultats


# =============================================================
# TEST DIRECT
# =============================================================

if __name__ == "__main__":

    dest = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "jules.ecorcheville@gmail.com"
    )

    user = (
        sys.argv[2]
        if len(sys.argv) > 2
        else "TestUser"
    )

    ok, msg = envoyer_email_confirmation(
        dest,
        user
    )

    print(
        f"Résultat : "
        f"{'SUCCÈS' if ok else 'ÉCHEC'} "
        f"({msg})"
    )
