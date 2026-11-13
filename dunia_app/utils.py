import os
from io import BytesIO
from PIL import Image
from django.core.files.base import ContentFile


def convertir_en_webp(champ_image, qualite=80):
    """
    Convertit une image uploadée (ImageField) en WebP.
    Retourne un ContentFile prêt à réassigner au champ,
    ou None si aucune conversion n'est nécessaire.
    """
    if not champ_image or champ_image.name.lower().endswith('.webp'):
        return None

    image = Image.open(champ_image)
    image = image.convert('RGBA') if image.mode in ('RGBA', 'P') else image.convert('RGB')

    buffer = BytesIO()
    image.save(buffer, format='WEBP', quality=qualite)
    buffer.seek(0)

    nom_original = os.path.splitext(os.path.basename(champ_image.name))[0]
    return ContentFile(buffer.read(), name=f"{nom_original}.webp")