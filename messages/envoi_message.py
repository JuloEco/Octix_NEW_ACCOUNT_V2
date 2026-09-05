"""
Envoi des e-mails Octix (Bienvenue & Code de réinitialisation).
==============================================================
"""

import smtplib
import os
import sys
import logging
from email.message import EmailMessage
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("octix_email")

BASE_DIR = Path(__file__).resolve().parent

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "octix.org@gmail.com"
HUB_URL = "https://omni-lbhc.onrender.com"


def _get_app_password() -> str:
    """Récupère et nettoie la clé MDP depuis l'environnement."""
    raw_mdp = os.environ.get("MDP", "")
    return raw_mdp.replace(" ", "").strip()


def _smtp_response(response) -> str:
    """Transforme proprement une réponse SMTP en texte lisible."""
    if isinstance(response, bytes):
        return response.decode("utf-8", errors="replace")
    return str(response)


def _send_message_with_trace(
    server: smtplib.SMTP,
    msg: EmailMessage,
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

    code, response = server.mail(SENDER_EMAIL)

    logger.info(
        "[SMTP] MAIL FROM <%s> -> %s %s",
        SENDER_EMAIL,
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


def envoyer_email_confirmation(
    destinataire: str,
    username: str
) -> tuple[bool, str]:
    """
    Envoie l'e-mail de bienvenue à `destinataire`.
    """

    app_password = _get_app_password()

    if not app_password:
        err = "Variable d'environnement 'MDP' manquante."
        logger.error(f"[EMAIL] {err}")
        return False, err

    try:

        # =====================================================
        # CONSTRUCTION DU MESSAGE
        # =====================================================

        msg = EmailMessage()

        msg["Subject"] = (
            "Ton compte Octix a été créé avec succès !"
        )

        msg["From"] = SENDER_EMAIL
        msg["To"] = destinataire

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
            .replace("{{USERNAME}}", username)
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
        # CONNEXION SMTP
        # =====================================================

        with smtplib.SMTP(
            SMTP_SERVER,
            SMTP_PORT,
            timeout=10
        ) as server:

            # TLS
            server.starttls()

            # Authentification Gmail
            server.login(
                SENDER_EMAIL,
                app_password
            )

            logger.info(
                "[SMTP] Authentification Gmail réussie pour <%s>",
                SENDER_EMAIL
            )

            # -------------------------------------------------
            # Transaction SMTP détaillée
            # -------------------------------------------------

            ok, result = _send_message_with_trace(
                server,
                msg,
                destinataire
            )

            if not ok:

                logger.error(
                    "[EMAIL] Échec transaction SMTP vers %s : %s",
                    destinataire,
                    result
                )

                return False, result

        # =====================================================
        # SUCCÈS
        # =====================================================

        logger.info(
            "[EMAIL] E-mail accepté par Gmail pour %s : %s",
            destinataire,
            result
        )

        return True, result

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

    app_password = _get_app_password()

    if not app_password:
        err = "Variable d'environnement 'MDP' manquante."
        logger.error(f"[EMAIL] {err}")
        return False, err

    try:

        # =====================================================
        # CONSTRUCTION DU MESSAGE
        # =====================================================

        msg = EmailMessage()

        msg["Subject"] = (
            f"Ton code de réinitialisation Octix : {code}"
        )

        msg["From"] = SENDER_EMAIL
        msg["To"] = destinataire

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
            .replace("{{USERNAME}}", username)
            .replace("{{CODE}}", code)
        )

        html_part = msg.add_alternative(
            html,
            subtype="html"
        )

        # -----------------------------------------------------
        # Logo
        # -----------------------------------------------------

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
        # CONNEXION SMTP
        # =====================================================

        with smtplib.SMTP(
            SMTP_SERVER,
            SMTP_PORT,
            timeout=10
        ) as server:

            server.starttls()

            server.login(
                SENDER_EMAIL,
                app_password
            )

            logger.info(
                "[SMTP] Authentification Gmail réussie pour <%s>",
                SENDER_EMAIL
            )

            # -------------------------------------------------
            # Transaction SMTP détaillée
            # -------------------------------------------------

            ok, result = _send_message_with_trace(
                server,
                msg,
                destinataire
            )

            if not ok:

                logger.error(
                    "[EMAIL] Échec transaction SMTP vers %s : %s",
                    destinataire,
                    result
                )

                return False, result

        logger.info(
            "[EMAIL] Code accepté par Gmail pour %s : %s",
            destinataire,
            result
        )

        return True, result

    except Exception as e:

        err_msg = f"Échec d'envoi code: {e}"

        logger.error(
            f"[EMAIL] {err_msg}"
        )

        return False, err_msg


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
