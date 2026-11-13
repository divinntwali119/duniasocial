import hashlib
import os
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from dunia_app.models import Candidature, JobApplication


class Command(BaseCommand):
    help = 'Déplace les CV et justificatifs déjà stockés dans MEDIA_ROOT vers le stockage privé.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Copie et vérifie les fichiers avant de supprimer leur ancienne copie publique.',
        )

    def handle(self, *args, **options):
        media_root = Path(settings.MEDIA_ROOT).resolve()
        private_root = Path(settings.PRIVATE_MEDIA_ROOT).resolve()
        apply_changes = options['apply']
        examined = moved = already_private = missing = 0
        errors = []

        for model, field_name in ((JobApplication, 'cv'), (Candidature, 'document')):
            rows = model.objects.exclude(**{f'{field_name}': ''}).values_list('pk', field_name)
            for object_id, stored_name in rows.iterator():
                examined += 1
                relative_path = Path(stored_name)
                if relative_path.is_absolute() or '..' in relative_path.parts:
                    errors.append(f'{model.__name__} #{object_id}: chemin de fichier invalide')
                    continue

                source = (media_root / relative_path).resolve()
                destination = (private_root / relative_path).resolve()
                if not source.is_relative_to(media_root) or not destination.is_relative_to(private_root):
                    errors.append(f'{model.__name__} #{object_id}: chemin hors du répertoire autorisé')
                    continue

                if not source.is_file():
                    if destination.is_file():
                        already_private += 1
                    else:
                        missing += 1
                        errors.append(f'{model.__name__} #{object_id}: fichier source et destination absents')
                    continue

                if not apply_changes:
                    moved += 1
                    continue

                self._ensure_private_parent(destination.parent, private_root)
                temporary = destination.with_name(f'.{destination.name}.private-copy')
                try:
                    if destination.exists():
                        if self._sha256(source) != self._sha256(destination):
                            raise OSError('la destination privée existe avec un contenu différent')
                        os.chmod(destination, 0o600)
                    else:
                        with source.open('rb') as source_file, temporary.open('wb') as destination_file:
                            shutil.copyfileobj(source_file, destination_file)
                        shutil.copystat(source, temporary)
                        os.chmod(temporary, 0o600)
                        if self._sha256(source) != self._sha256(temporary):
                            raise OSError('la vérification SHA-256 de la copie a échoué')
                        os.replace(temporary, destination)

                    source.unlink()
                    self._remove_empty_parents(source.parent, media_root)
                    moved += 1
                except OSError as error:
                    if temporary.exists():
                        temporary.unlink()
                    errors.append(f'{model.__name__} #{object_id}: {error}')

        action = 'déplacé(s)' if apply_changes else 'à déplacer'
        self.stdout.write(
            f'{examined} document(s) contrôlé(s), {moved} {action}, '
            f'{already_private} déjà privé(s), {missing} introuvable(s).'
        )
        if errors:
            raise CommandError(f'{len(errors)} problème(s) détecté(s); aucun fichier source en erreur n’a été supprimé.')
        if not apply_changes and moved:
            self.stdout.write('Aucun fichier n’a été modifié. Relancez avec --apply pour déplacer les documents.')

    @staticmethod
    def _sha256(path):
        digest = hashlib.sha256()
        with path.open('rb') as file_obj:
            for chunk in iter(lambda: file_obj.read(1024 * 1024), b''):
                digest.update(chunk)
        return digest.digest()

    @staticmethod
    def _remove_empty_parents(directory, root):
        current = directory
        while current != root and root in current.parents:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent

    @staticmethod
    def _ensure_private_parent(directory, root):
        root.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(root, 0o700)
        current = root
        for component in directory.relative_to(root).parts:
            current = current / component
            current.mkdir(mode=0o700, exist_ok=True)
            os.chmod(current, 0o700)