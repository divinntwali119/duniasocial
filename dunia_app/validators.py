from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible


@deconstructible
class MaxFileSizeValidator:
    def __init__(self, max_bytes):
        self.max_bytes = max_bytes

    def __call__(self, uploaded_file):
        if uploaded_file and uploaded_file.size > self.max_bytes:
            limite_mo = self.max_bytes // (1024 * 1024)
            raise ValidationError(f'Le fichier ne peut dépasser {limite_mo} Mo.')

    def __eq__(self, other):
        return isinstance(other, MaxFileSizeValidator) and self.max_bytes == other.max_bytes


def validate_pdf_signature(uploaded_file):
    """Reject files with a PDF extension whose opening signature is not a PDF header."""
    if not uploaded_file:
        return
    try:
        position = uploaded_file.tell()
        uploaded_file.seek(0)
        signature = uploaded_file.read(5)
        uploaded_file.seek(position)
    except (AttributeError, OSError):
        raise ValidationError('Le fichier PDF n’a pas pu être vérifié.')
    if signature != b'%PDF-':
        raise ValidationError('Le fichier doit être un véritable document PDF.')
