import os
from django.core.management.base import BaseCommand
from dunia_app.models import Publication, Information, Cours, Article


class Command(BaseCommand):
    help = "Convertit toutes les images publiées existantes en WebP"

    def add_arguments(self, parser):
        parser.add_argument(
            '--supprimer-anciens',
            action='store_true',
            help="Supprime les anciens fichiers (jpg/png) une fois convertis en webp",
        )

    def handle(self, *args, **options):
        total = 0
        for modele, champ, nom in [
            (Publication, 'image', 'Publication'),
            (Information, 'photo', 'Information'),
            (Article,'image','Article'),
            (Cours, 'miniature', 'Cours'),
        ]:
            objets = modele.objects.exclude(**{champ: ''}).exclude(**{champ: None})
            self.stdout.write(f"{nom} : {objets.count()} image(s) à vérifier...")

            for obj in objets:
                fichier = getattr(obj, champ)
                if fichier and not fichier.name.lower().endswith('.webp'):
                    ancien_chemin = fichier.path if os.path.isfile(fichier.path) else None
                    obj.save()
                    total += 1
                    self.stdout.write(f"  OK : {obj} converti")

                    if options['supprimer_anciens'] and ancien_chemin and os.path.isfile(ancien_chemin):
                        os.remove(ancien_chemin)

        self.stdout.write(self.style.SUCCESS(f"\nTerminé : {total} image(s) converties en WebP."))