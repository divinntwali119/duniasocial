# Guide complet du projet Dunia

> Guide de prise en main, d’état des fonctionnalités et de déploiement. État audité dans le workspace le **13 novembre 2026**. Les données, services et paramètres d’hébergement réels doivent être vérifiés avant une mise en ligne.

## 1. Résumé de l’état actuel

| Élément | État vérifié |
| --- | --- |
| Application | Monolithe Django rendu côté serveur, une application principale `dunia_app` |
| Versions du workspace | Django 6.0.6, Python 3.14, Tailwind CSS 4, DaisyUI 5, Pillow |
| Routes | 76 routes applicatives nommées, plus l’administration Django |
| Tests | 60 tests Django réussis au dernier contrôle |
| Base locale | SQLite; migrations 0001–0026 appliquées, 0027–0028 encore en attente dans la base du workspace |
| Production prévue | PostgreSQL, cache partagé (Redis recommandé), Gunicorn, HTTPS, stockage persistant |
| Déploiement réel | Pas encore provisionné par le dépôt : domaine, hébergeur, base, cache, SMTP et volumes restent à configurer |

Le smoke test résout les routes nommées et envoie une requête GET pour vérifier qu’elles ne produisent pas d’erreur serveur. Il ne garantit pas à lui seul tous les parcours métiers, droits, méthodes POST ou intégrations externes. Les codes `302`, `403`, `404` et `405` sont possibles et peuvent être normaux selon la connexion, les droits, les données et la méthode HTTP.

## 2. Ce que l’application contient déjà

### Comptes, profils et réseau social

- Inscription d’un compte apprenant, connexion, déconnexion et réinitialisation de mot de passe.
- Profils de membres, demandes de rôle formateur ou entreprise et annuaire des apprenants/formateurs.
- Fil d’actualité combinant publications éditoriales et publications de membres; réactions, commentaires, partages et pagination avec interactions JavaScript.
- Demandes d’amitié, messagerie directe, états de lecture et notifications dans l’application.
- Communautés publiques ou privées, adhésion et publications réservées aux membres.

L’application utilise le modèle `User` standard de Django, sans modèle utilisateur personnalisé. Les boutons Google/Microsoft affichés sur certaines pages sont des éléments d’interface désactivés : aucun parcours OAuth n’est configuré.

### Formations et apprentissage

- Catalogue de formations avec filtres, orientation, pages de détail, FAQ et calendrier des sessions.
- Candidatures avec référence de suivi, demandes d’aide financière et réservation de sessions d’information.
- Gestion des capacités et des places de sessions; une admission confirmée peut retenir une place.
- Cours vidéo, audio ou PDF, espace formateur, suivi de progression, évaluations et attribution des certifications liées à un cours.

### Entreprises, emploi, projets et événements

- Profils d’entreprise et validation distincte du rôle et du profil de l’organisation.
- Offres d’emploi ou de stage soumises à validation; candidatures avec CV et suivi des statuts.
- Galerie de projets, dépôt de projets soumis à modération et demandes de projets clients.
- Défis gratuits ou payants, inscriptions, travaux remis en plusieurs versions et retours de l’équipe.
- Événements professionnels avec inscription et contrôle des places.

**Paiements des défis :** le processus est manuel. Le membre déclare une référence et l’équipe confirme ou refuse le paiement depuis l’administration; aucune passerelle de paiement n’est intégrée.

### Contenu, administration et impact

- Publications, articles, catégories, commentaires modérés, pages de découverte/services, initiatives, campus, partenaires, témoignages, rapports et indicateurs d’impact.
- Administration Django pour gérer le contenu et effectuer les validations prévues.
- Journal d’audit pour des décisions et transitions métier importantes.
- Deux commandes de gestion : conversion d’images en WebP et déplacement des documents privés.

La référence complète des chemins et noms de routes est [dunia_app/urls.py](dunia_app/urls.py). Les vues et règles d’accès sont dans [dunia_app/views.py](dunia_app/views.py), les modèles dans [dunia_app/models.py](dunia_app/models.py), les services métier dans [dunia_app/services.py] et l’administration dans [dunia_app/admin.py](dunia_app/admin.py).

## 3. Règles d’accès et protections à préserver

- Les pages et actions de compte requièrent une session connectée; les actions de formateur/entreprise vérifient le rôle approuvé et la propriété des ressources.
- Les offres d’emploi doivent être validées avant publication. La modification d’un profil d’entreprise vérifié peut invalider la vérification et renvoyer ses offres en revue.
- Les cours créés ou modifiés par un formateur sont soumis à approbation avant publication.
- Les transitions de candidatures et les réservations de places utilisent des règles métier transactionnelles. Ne pas modifier directement leurs statuts ou compteurs en contournant les services existants.
- Les paiements et remises de défis conservent les tentatives, versions et décisions nécessaires à l’historique.
- Les CV et justificatifs de candidature sont privés : ils sont stockés hors des médias publics et délivrés par des vues qui vérifient les autorisations. Ne jamais rendre le répertoire privé accessible via le serveur web ou une URL publique.
- Les formulaires appliquent des validations, des limites d’upload et, pour les PDF concernés, une vérification de signature. Des protections anti-abus existent pour certains formulaires et actions.

Les règles transactionnelles se trouvent principalement dans [dunia_app/services.py](dunia_app/services.py), les validations dans [dunia_app/forms.py](dunia_app/forms.py) et [dunia_app/validators.py](dunia_app/validators.py), le stockage privé dans [dunia_app/storage.py](dunia_app/storage.py).

## 4. Organisation du dépôt

| Chemin | Rôle |
| --- | --- |
| [dunia_one/settings.py](dunia_one/settings.py) | Réglages, variables d’environnement et sécurité |
| [dunia_one/urls.py](dunia_one/urls.py) | Routage racine : application et administration |
| [dunia_one/wsgi.py](dunia_one/wsgi.py) | Point d’entrée WSGI pour Gunicorn |
| [dunia_app/models.py](dunia_app/models.py) | Modèles métier et contraintes |
| [dunia_app/views.py](dunia_app/views.py) | Vues HTTP et parcours utilisateurs |
| [dunia_app/services.py](dunia_app/services.py) | Workflows, permissions et transitions métier |
| [dunia_app/forms.py](dunia_app/forms.py) | Formulaires et validation des saisies |
| [dunia_app/urls.py](dunia_app/urls.py) | Routes applicatives |
| [dunia_app/templates/dunia_app](dunia_app/templates/dunia_app) | Pages et composants HTML |
| [dunia_app/static](dunia_app/static) | Sources CSS/JS et ressources statiques |
| [dunia_app/migrations](dunia_app/migrations) | Historique du schéma et reprises de données |
| [dunia_app/tests.py](dunia_app/tests.py) | Tests des vues, services, permissions, migrations et templates |
| [dunia_app/management/commands](dunia_app/management/commands) | Commandes de maintenance des fichiers |
| [DEPLOIEMENT_SECURISE.md](DEPLOIEMENT_SECURISE.md) | Procédure détaillée de production et migration des fichiers privés |

## 5. Installation et démarrage local

### Prérequis

- Une version de Python compatible avec Django 6.0; Python 3.14 est celle du workspace audité.
- Node.js/npm pour Tailwind et DaisyUI.

### Installation initiale

Depuis la racine du dépôt :

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
npm ci
```

Pour une base locale neuve ou jetable, appliquer le schéma et créer éventuellement un compte d’administration :

```sh
python manage.py migrate
python manage.py createsuperuser
```

**Attention à la base existante :** avant `migrate` sur une base qui contient des données, consulter son état et faire une sauvegarde. Dans la base SQLite de ce workspace, les migrations 0027 et 0028 sont en attente; la 0027 comprend une reprise de données et de nouvelles contraintes. Consulter [DEPLOIEMENT_SECURISE.md](DEPLOIEMENT_SECURISE.md) avant de les appliquer à une base déjà peuplée.

Lancer le développement Django et Tailwind ensemble :

```sh
npm run dev
```

La tâche VS Code **Dunia: Django + Tailwind dev** active `.venv` avant de lancer ce script. Autres commandes de développement : `python manage.py runserver` pour Django seul et `npm run dev:css` pour Tailwind en mode surveillance.

Le projet ne charge pas automatiquement un fichier `.env`. Les valeurs nécessaires doivent être fournies dans l’environnement du processus ou par l’outil de secrets de la plateforme.

## 6. Tests et contrôles

Les commandes ci-dessous supposent que `.venv` est activé :

```sh
npm test
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py showmigrations dunia_app
```

Au dernier contrôle, les **60 tests** passaient, `check` ne relevait aucun problème et `makemigrations --check --dry-run` ne détectait pas de changement de modèle manquant. Le test de routage couvre les 76 routes nommées et l’entrée de l’administration.

Exécuter les tests sur une base de test jetable, en CI ou en préproduction. **Ne pas utiliser les identifiants de la base réelle de production pour la suite de tests** : Django crée et détruit une base de test.

Les contrôles statiques utiles avant une livraison sont :

```sh
python manage.py check --deploy
npm run build:css
python manage.py collectstatic --noinput
```

`check --deploy` doit être lancé avec les réglages de l’environnement cible; il peut signaler HSTS tant que la valeur est à `0`. `collectstatic` copie les ressources vers `STATIC_ROOT`.

## 7. Ce qui reste à faire

### Indispensable avant le trafic de production

1. Choisir et provisionner un hébergeur Linux, un domaine, une base PostgreSQL, un cache partagé (Redis recommandé), un service SMTP et des volumes persistants.
2. Fournir les vrais secrets et noms d’hôtes par le gestionnaire de secrets de l’hébergeur; ne pas les mettre dans Git, le README ou un fichier `.env` committé.
3. Configurer le proxy TLS/HTTPS, la redirection HTTPS, l’origine CSRF, la livraison des fichiers statiques et la livraison des médias publics.
4. Définir où persistent les uploads. Le réglage actuel de `MEDIA_ROOT` est `BASE_DIR/media` (sans variable d’environnement dédiée) : monter un volume persistant à cet emplacement ou prévoir un changement de configuration avant de choisir un autre chemin. Définir `DJANGO_PRIVATE_MEDIA_ROOT` sur un volume persistant distinct, hors de `MEDIA_ROOT` et non public.
5. Vérifier les migrations de la base cible. L’état connu ci-dessus concerne uniquement la base SQLite locale; l’état d’une future base de production devra être contrôlé séparément.
6. Sauvegarder puis tester une restauration de PostgreSQL, des médias publics et des documents privés.
7. Effectuer un déploiement de préproduction et vérifier les courriels réels, les droits par rôle, les parcours principaux et le proxy avant d’ouvrir le trafic.

### Travaux d’évolution possibles

Ces éléments ne bloquent pas le fonctionnement actuel, mais sont absents ou limités et peuvent devenir des chantiers selon les besoins du produit :

- Authentification Google/Microsoft : les boutons existent, mais OAuth n’est pas branché.
- Paiement en ligne des défis : aujourd’hui, traitement manuel des références.
- Notifications automatiques par courriel pour les événements métier : les notifications dans l’application existent, mais les communications automatiques complètes ne sont pas un workflow actuellement configuré.
- File de tâches asynchrones : aucun Celery/worker n’est configuré; les traitements lourds restent à concevoir si le volume le nécessite.
- Stockage objet/CDN pour médias : le stockage configuré est le système de fichiers; une migration vers S3 ou équivalent n’est pas incluse.
- Observabilité de production : centralisation des journaux, alertes, métriques et surveillance des sauvegardes à mettre en place sur la plateforme.
- Tests navigateur/end-to-end en préproduction : les tests Django couvrent de nombreux parcours, mais le smoke test des routes ne remplace pas les essais réels sur mobile, bureau, e-mail et fichiers.
- API REST : aucune API publique n’est actuellement configurée; l’interface est principalement rendue par Django.

## 8. Déployer l’application

Le déploiement ci-dessous est une procédure générique Linux/PaaS. Les écrans et options exacts dépendent de l’hébergeur choisi. Les dépendances serveur (Gunicorn, PostgreSQL et Redis) sont listées dans [requirements.txt](requirements.txt); les scripts front-end se trouvent dans [package.json](package.json).

### Étape A — Provisionner l’environnement

Créer/configurer :

- Une application Python/Linux qui peut exécuter Gunicorn.
- Une base PostgreSQL persistante, avec sauvegardes.
- Un cache accessible par tous les workers, idéalement Redis.
- Un domaine avec certificat TLS et proxy/load balancer configuré.
- Un fournisseur SMTP et une adresse expéditeur vérifiée.
- Un volume persistant pour les médias publics, monté sur `BASE_DIR/media` avec la configuration actuelle.
- Un volume privé distinct, par exemple `/srv/dunia-private`, protégé par des permissions système restrictives.

Le dossier `staticfiles/` est produit par `collectstatic`; l’hébergeur ou le proxy doit servir `/static/` depuis cette destination. Les médias publics `/media/` doivent être servis par un serveur web, un CDN ou un stockage adapté. Le stockage privé ne doit jamais être inclus dans ces emplacements publics. La route de développement Django pour `/media/` n’est pas présente en production.

### Étape B — Définir les variables d’environnement

Configurer dans le gestionnaire de secrets de la plateforme, au minimum :

| Variable | Valeur à fournir |
| --- | --- |
| `DJANGO_DEBUG` | `False` |
| `DJANGO_SECRET_KEY` | Clé aléatoire forte, secrète et propre à cet environnement |
| `DJANGO_ALLOWED_HOSTS` | Hôtes exacts servis, séparés par des virgules; en son absence la valeur locale ne contient que localhost/testserver |
| `DJANGO_DATABASE_URL` | URL PostgreSQL, TLS recommandé, mot de passe avec caractères réservés encodés |
| `DJANGO_CACHE_BACKEND` | `django.core.cache.backends.redis.RedisCache` pour Redis |
| `DJANGO_CACHE_LOCATION` | URL Redis `redis://…` ou `rediss://…` accessible par les workers |
| `DJANGO_DEFAULT_FROM_EMAIL` | Adresse expéditeur réelle et validée |
| `DJANGO_EMAIL_HOST` | Hôte SMTP réel; requis si le backend SMTP Django est utilisé |
| `DJANGO_EMAIL_HOST_USER`, `DJANGO_EMAIL_HOST_PASSWORD` | Identifiants SMTP s’ils sont requis par le fournisseur |
| `DJANGO_PRIVATE_MEDIA_ROOT` | Chemin absolu du volume privé, hors de `MEDIA_ROOT` et non servi publiquement |

Le backend SMTP est le défaut en production : `DJANGO_EMAIL_PORT` vaut `587`, TLS est activé par défaut et le délai vaut 10 secondes. Ajuster si le fournisseur impose une autre configuration. Un backend de courriel tiers peut être choisi avec `DJANGO_EMAIL_BACKEND`.

La redirection HTTPS et les cookies sécurisés sont activés par défaut quand `DJANGO_DEBUG=False`. `DJANGO_CSRF_TRUSTED_ORIGINS` ne doit contenir que les origines réellement nécessaires. Ne définir `DJANGO_SECURE_PROXY_SSL_HEADER` que si le proxy supprime les en-têtes client et écrit lui-même l’en-tête HTTPS de confiance. Garder `DJANGO_SECURE_HSTS_SECONDS=0` jusqu’à validation de HTTPS; augmenter ensuite prudemment. Ne pas activer les sous-domaines ou le preload sans vérifier l’ensemble du domaine.

### Étape C — Construire et vérifier une release

Dans la release ou le pipeline de CI :

```sh
python -m pip install -r requirements.txt
npm ci
npm run build:css
python manage.py check --deploy
python manage.py collectstatic --noinput
```

Exécuter la suite de tests dans CI/préproduction sur une base isolée. Ne pas lancer `npm test` avec l’URL ni les identifiants de la base réelle de production.

### Étape D — Migrer les données avec précaution

Pour une base déjà peuplée, suivre précisément [la procédure sécurisée](DEPLOIEMENT_SECURISE.md) :

1. Mettre l’application en maintenance ou empêcher temporairement les écritures.
2. Sauvegarder PostgreSQL, les médias publics et le stockage privé; vérifier la possibilité de restauration.
3. Vérifier l’état des migrations de la base cible. Ne pas supposer que son état est celui de SQLite local.
4. Exécuter `python manage.py deplacer_documents_prives` en simulation (sans option destructive) et résoudre tous les écarts.
5. Après validation, lancer la commande avec `--apply`; les copies sont vérifiées avant suppression des anciennes copies.
6. Examiner le plan puis appliquer les migrations nécessaires avec `python manage.py migrate`.
7. Vérifier les téléchargements autorisés et refusés avant de rétablir les écritures.

La migration 0027 inclut une reprise de données et peut s’arrêter si certaines données historiques violent les contraintes nouvellement introduites. Analyser et corriger ces cas explicitement après sauvegarde; ne pas forcer ou ignorer l’erreur. La migration 0028 ajoute des validations d’uploads sans supprimer les médias historiques.

Sur une base entièrement neuve, initialiser les migrations puis créer un superutilisateur conformément au processus sécurisé de l’hébergeur. La migration d’une base de production existante n’est pas équivalente à une installation neuve.

### Étape E — Démarrer l’application

Utiliser `dunia_one.wsgi:application` avec un serveur WSGI, par exemple Gunicorn :

```sh
gunicorn dunia_one.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 3 --access-logfile - --error-logfile -
```

Adapter le nombre de workers et le port aux limites de l’hébergeur. Le proxy doit transmettre les requêtes à Gunicorn, assurer HTTPS et diriger les fichiers statiques/publics vers le stockage configuré.

### Étape F — Vérifier après déploiement

En préproduction puis après activation contrôlée :

- Ouvrir la page d’accueil, découverte, catalogue, cours, articles, emploi, communauté et connexion de l’administration.
- Tester inscription, connexion, déconnexion, réinitialisation avec réception d’un vrai courriel.
- Tester candidature, réservation et capacités; vérifier les confirmations affichées et l’enregistrement des dossiers. Les courriels métier automatiques restent à développer selon les besoins.
- Tester un compte apprenant, un formateur approuvé, une entreprise autorisée et un visiteur non connecté.
- Vérifier les fichiers statiques, l’ajout d’un média public et le refus d’accès à un document privé par un tiers.
- Vérifier HTTPS, redirection, CSRF, cookies, logs de démarrage, cache partagé et sauvegarde/restauration.

### Retour arrière

Préparer le retour à la version précédente et à la sauvegarde de base/médias avant les migrations. Si une migration ou le transfert de documents échoue, garder le site en maintenance, conserver les rapports et les copies originales, restaurer selon la procédure de l’hébergeur et ne pas supprimer manuellement les fichiers. Valider les procédures de rollback sur une préproduction avant la première mise en production.

## 9. Documents complémentaires

- [README.md](README.md) : guide rapide de développement, commandes et architecture.
- [DEPLOIEMENT_SECURISE.md](DEPLOIEMENT_SECURISE.md) : variables de production, sécurité HTTPS, documents privés et migration des données.
- [dunia_app/urls.py](dunia_app/urls.py) : liste canonique des URL applicatives.
- [dunia_app/tests.py](dunia_app/tests.py) : couverture automatisée et vérifications des routes.
