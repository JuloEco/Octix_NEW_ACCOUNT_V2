# Octix Account Portal v2

Cette version réorganise le portail de compte Octix sans modifier le mécanisme SMTP qui fonctionne actuellement.

## Routes principales

- `/` : accueil du portail
- `/inscription` : création d'un compte Octix
- `/connexion` : connexion
- `/compte` et `/mon-compte` : espace personnel
- `/deconnexion` : déconnexion
- `/mot-de-passe-oublie` : récupération du mot de passe
- `/pourquoi-email` : explication sur l'utilisation de l'e-mail
- `/apps` : écosystème Octix
- `/a-propos` : présentation du portail
- `/contact` : support
- `/register` : ancien lien, redirigé vers `/inscription`

## Organisation

- `app.py` : routes publiques, inscription et récupération
- `compte_routes.py` : connexion et gestion du compte
- `templates/` : pages HTML Jinja séparées
- `static/css/octix.css` : design responsive commun
- `static/js/octix.js` : menu mobile, mots de passe, interactions
- `messages/` : e-mails Octix, conservés

## Variables d'environnement

Les variables existantes restent utilisées :

- `OCTIX_URL`
- `OCTIX_INTERNAL_KEY`
- `SECRET_KEY`
- `MDP` pour le mot de passe d'application Gmail

## Responsive

Le portail est conçu pour ordinateur, tablette et smartphone avec navigation mobile, formulaires adaptatifs, grilles réduites et boutons tactiles.
