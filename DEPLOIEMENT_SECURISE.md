# Déploiement sécurisé de Dunia

## Paramètres de production

Définir les variables dans le gestionnaire de secrets/environnement de l’hébergeur; ne pas committer de secret dans le dépôt.

| Variable | Configuration requise |
| --- | --- |
| `DJANGO_DEBUG` | `False` en production. |
| `DJANGO_SECRET_KEY` | Clé aléatoire forte, unique à l’environnement, conservée hors du dépôt. |
| `DJANGO_ALLOWED_HOSTS` | Liste séparée par des virgules contenant uniquement les noms d’hôtes servis. |
| `DJANGO_DATABASE_URL` | URL PostgreSQL de production (`postgresql://utilisateur:mot-de-passe@hote:5432/dunia?sslmode=require`). Encoder les caractères spéciaux du mot de passe dans l’URL. SQLite reste réservé au développement. |
| `DJANGO_DB_CONN_MAX_AGE` | Durée maximale de réutilisation d’une connexion PostgreSQL en secondes (60 par défaut). |
| `DJANGO_CACHE_BACKEND` | Backend de cache partagé entre tous les workers; requis en production pour appliquer les limitations de débit de façon cohérente. |
| `DJANGO_CACHE_LOCATION` | Emplacement du cache correspondant au backend choisi; Redis est recommandé (`redis://` ou `rediss://`). |
| `DJANGO_SECURE_SSL_REDIRECT` | `True` une fois HTTPS actif de bout en bout ou correctement déclaré au proxy de confiance. |
| `DJANGO_SESSION_COOKIE_SECURE` | `True` en production. |
| `DJANGO_CSRF_COOKIE_SECURE` | `True` en production. |
| `DJANGO_PRIVATE_MEDIA_ROOT` | Répertoire de fichiers privés situé hors de `MEDIA_ROOT` et non servi par le serveur web. |
| `DJANGO_SECURE_HSTS_SECONDS` | Commencer à `0`; passer à `31536000` après validation complète de HTTPS. |
| `DJANGO_DEFAULT_FROM_EMAIL` | Adresse d’expédition réelle, requise en production. |
| `DJANGO_EMAIL_BACKEND` | Backend courriel; SMTP sécurisé est utilisé par défaut en production. Un backend de fournisseur tiers peut être fourni ici. |
| `DJANGO_EMAIL_HOST`, `DJANGO_EMAIL_PORT` | Hôte et port SMTP (`587` par défaut en production). |
| `DJANGO_EMAIL_HOST_USER`, `DJANGO_EMAIL_HOST_PASSWORD` | Identifiants SMTP, fournis exclusivement par le gestionnaire de secrets. |
| `DJANGO_EMAIL_USE_TLS`, `DJANGO_EMAIL_USE_SSL`, `DJANGO_EMAIL_TIMEOUT` | Sécurité et délai SMTP; TLS est activé par défaut en production. TLS et SSL ne peuvent pas être activés simultanément. |

N’ajouter `DJANGO_SECURE_PROXY_SSL_HEADER` que si le proxy supprime les en-têtes transmis par le client et écrit lui-même l’en-tête de protocole de confiance. Ne pas activer les sous-domaines HSTS ou le preload sans vérifier tous les sous-domaines et la possibilité de retour arrière. Définir `DJANGO_CSRF_TRUSTED_ORIGINS` seulement si le déploiement utilise réellement des origines distinctes.

## Construire et démarrer l’application

Le dépôt fournit le point d’entrée WSGI `dunia_one.wsgi:application`; `runserver` et le mode Tailwind `--watch` sont réservés au développement. Sur une plateforme Linux, configurer au préalable les variables requises dans son gestionnaire de secrets, puis exécuter pendant la release :

```sh
python -m pip install -r requirements.txt
npm ci
npm run build:css
python manage.py check --deploy
python manage.py collectstatic --noinput
```

Appliquer ensuite les migrations selon la procédure de sauvegarde et de déplacement des documents privés ci-dessous, puis démarrer les workers avec un serveur WSGI, par exemple :

```sh
gunicorn dunia_one.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 3 --access-logfile - --error-logfile -
```

Le proxy HTTPS ou le service d’hébergement doit transmettre les requêtes vers Gunicorn, servir `/static/` depuis `STATIC_ROOT` (le dossier `staticfiles/` après collecte) et servir les médias publics `/media/` depuis le stockage média persistant. **Ne jamais exposer `DJANGO_PRIVATE_MEDIA_ROOT`**; les documents privés restent servis par les vues autorisées. Le volume de médias et celui des pièces privées doivent être persistants et sauvegardés séparément. La base de production doit être PostgreSQL et le cache doit être partagé entre les workers, par exemple Redis; les dépendances nécessaires sont dans `requirements.txt`.

Pour une première mise en service : valider d’abord les variables et `check --deploy` sur un environnement de préproduction, tester la restauration de la base et des médias, effectuer les migrations de pièces privées en fenêtre de maintenance, puis tester le site derrière le vrai proxy. Le contrôle de déploiement signale volontairement l’absence de HSTS tant que `DJANGO_SECURE_HSTS_SECONDS` reste à `0`; augmenter cette valeur seulement après confirmation que HTTPS est correctement configuré sur tout le domaine.

Exécuter les tests fonctionnels en CI ou en préproduction avec une base isolée — **jamais avec l’URL de la base réelle de production** :

```sh
python manage.py test dunia_app
python manage.py makemigrations --check --dry-run
python manage.py check --deploy
```

La suite teste également la résolution et l’accès GET sans erreur serveur des 82 routes applicatives nommées, ainsi que l’entrée et la connexion de l’administration Django; les codes `302`, `403`, `404` ou `405` restent normaux pour une page protégée, une ressource absente ou une méthode non autorisée. Exécuter `check --deploy` et `collectstatic` avec la configuration de production, puis tester en préproduction les parcours avec des données représentatives, l’envoi des courriels et les accès de chaque rôle.

## Mise en production des pièces privées

Les CV et documents de candidature sont maintenant sauvegardés hors de `MEDIA_ROOT`, servis uniquement par des vues authentifiées, en téléchargement, sans cache public. L’accès est limité au candidat, au propriétaire approuvé de l’offre ou à l’équipe disposant de la permission adaptée.

Avant le déploiement, pendant une fenêtre de maintenance :

1. Sauvegarder la base et l’ensemble de `MEDIA_ROOT`; vérifier qu’une restauration est possible.
2. Déployer le code sans rouvrir le trafic.
3. Lancer `deplacer_documents_prives` sans option destructive pour obtenir le bilan. Cette première exécution est une simulation en lecture seule.
4. Examiner les fichiers absents et les erreurs; résoudre les cas signalés avant de continuer.
5. Lancer la même commande avec `--apply`. Chaque copie est vérifiée par SHA-256 et l’original n’est retiré qu’après vérification.
6. Appliquer les migrations, vérifier que les nouveaux téléchargements autorisés fonctionnent, puis rétablir le trafic.

La migration 0027 reprend les cours déjà publiés, crée les demandes de rôle nécessaires aux formateurs actifs et entreprises déjà vérifiées, conserve les références et travaux historiques de défis, et marque comme retenues les places des admissions déjà confirmées sans modifier les compteurs existants. Elle s’arrête si les dates/capacités existantes violent les nouvelles contraintes; corriger alors les lignes concernées explicitement après analyse, sans ajustement automatique des places.

La migration 0028 ajoute des limites de taille aux images et fichiers téléversés, ainsi qu’une vérification d’extension et de signature pour les brochures et rapports PDF. Elle ne modifie ni ne supprime les médias historiques; les formulaires rejettent les nouveaux fichiers qui ne respectent pas ces règles.

La migration 0029 ajoute une référence UUID unique à chaque demande d’aide financière existante, crée les demandes d’accès aux communautés privées et ajoute l’état d’annulation aux inscriptions événementielles. La référence est ajoutée temporairement comme nullable, remplie avec une UUID distincte par ligne, puis rendue unique et obligatoire. Vérifier la sauvegarde et le plan de migration sur une copie de la base avant production.

## Contrôles de déploiement

- Exécuter `manage.py check --deploy` avec les variables de production réelles.
- Vérifier le certificat HTTPS, la redirection, les cookies, l’origine CSRF et la détection du protocole par le proxy.
- Vérifier qu’un utilisateur non autorisé ne peut ni télécharger un CV ni ouvrir un document de candidature.
- Vérifier que les fichiers privés ne sont pas présents sous la racine publique des médias et que leurs permissions système sont restrictives.
- Tester les limitations de débit avec le cache partagé de production, pas uniquement avec le cache local de développement.
- Tester une sauvegarde et une restauration de la base, des médias publics et du répertoire privé.
