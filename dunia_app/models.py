from django.db import models
# Create your models here.
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator
import uuid
import os
from django.dispatch import receiver
from django.db.models.signals import pre_delete
from django.utils.text import slugify
from django.utils import timezone
from .utils import convertir_en_webp
from .storage import PrivateMediaStorage
from .validators import MaxFileSizeValidator, validate_pdf_signature


private_media_storage = PrivateMediaStorage()

STATUS =((0,"masquer"),(1,"public"))
CHOIX = (
        (1,"Gratuit en presentiel"),
         (2,"Payant en ligne"),
         (3,"Payant en presentiel"),
         (4,"En ligne")
         )
TYPE_PROGRAMME = (
    ('longue', 'Formation longue'),
    ('professionnelle', 'Formation professionnelle'),
    ('initiation', 'Cours gratuit ou d’initiation'),
)
DOMAINES_FORMATION = (
    ('developpement', 'Développement'),
    ('design', 'Design'),
    ('bureautique', 'Bureautique'),
    ('langues', 'Langues'),
    ('marketing', 'Marketing numérique'),
    ('data', 'Data et intelligence artificielle'),
    ('entrepreneuriat', 'Entrepreneuriat'),
)
NIVEAUX_FORMATION = (
    ('debutant', 'Débutant'),
    ('intermediaire', 'Intermédiaire'),
    ('avance', 'Avancé'),
    ('tous_niveaux', 'Tous niveaux'),
)
FORMATS_FORMATION = (
    ('a_definir', 'À définir'),
    ('presentiel', 'Présentiel'),
    ('en_ligne', 'En ligne'),
    ('hybride', 'Hybride'),
)
CANDIDATURE_STATUTS = (
    ('recue', 'Candidature reçue'),
    ('test', 'Test d’admission'),
    ('documents', 'Dépôt de documents'),
    ('decision', 'Décision en cours'),
    ('confirmee', 'Admission confirmée'),
    ('refusee', 'Candidature clôturée'),
)
TYPES_SESSION = (
    ('cohorte', 'Cohorte de formation'),
    ('information', 'Session d’information'),
)
COURS_STATUTS = (
    ('brouillon', 'Brouillon'),
    ('a_valider', 'À valider'),
    ('publie', 'Publié'),
    ('refuse', 'Refusé'),
)
ROLE_DEMANDES = (
    ('formateur', 'Formateur'),
    ('entreprise', 'Entreprise'),
)
ROLE_DEMANDE_STATUTS = (
    ('en_attente', 'En attente'),
    ('approuve', 'Approuvée'),
    ('refuse', 'Refusée'),
)
STATUTS_AIDE = (
    ('recue', 'Demande reçue'),
    ('etude', 'À l’étude'),
    ('recontact', 'À recontacter'),
    ('cloturee', 'Clôturée'),
)
PROFIL_ROLES = (
    ('apprenant', 'Apprenant'),
    ('formateur', 'Formateur'),
    ('entreprise', 'Entreprise'),
)
OFFRE_STATUTS = (
    ('brouillon', 'Brouillon'),
    ('a_valider', 'À valider'),
    ('publiee', 'Publiée'),
    ('refusee', 'Refusée'),
    ('cloturee', 'Clôturée'),
)
OFFRE_TYPES = (
    ('stage', 'Stage'),
    ('emploi', 'Emploi'),
    ('alternance', 'Alternance'),
    ('freelance', 'Mission freelance'),
)
CANDIDATURE_EMPLOI_STATUTS = (
    ('recue', 'Reçue'),
    ('etude', 'En étude'),
    ('entretien', 'Entretien'),
    ('retenue', 'Retenue'),
    ('refusee', 'Non retenue'),
)
PROJET_STATUTS = (
    ('brouillon', 'Brouillon'),
    ('a_valider', 'À valider'),
    ('publie', 'Publié'),
    ('refuse', 'À corriger'),
)
NOTIFICATION_TYPES = (
    ('message', 'Message'),
    ('candidature', 'Candidature'),
    ('emploi', 'Emploi'),
    ('communaute', 'Communauté'),
    ('cours', 'Cours'),
    ('evenement', 'Événement'),
    ('systeme', 'Information Dunia'),
)

class Publication(models.Model):
    voir = models.IntegerField(default=0)
    auteur= models.ForeignKey(User,on_delete=models.CASCADE,related_name='blog_publications')
    titre= models.CharField( unique=True,max_length=200)
    contexte= models.TextField()
    image = models.ImageField(
        upload_to='publication_image/',
        blank=True,
        null=True,
        validators=[MaxFileSizeValidator(10 * 1024 * 1024)],
    )
    date_actuel = models.DateTimeField( auto_now_add=True)
    date_modif = models.DateTimeField( auto_now=True)
    slug= models.SlugField(unique=True,blank=True)
    status =models.IntegerField(choices= STATUS, default = 0)

    class Meta:
        ordering=['-date_actuel']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.titre)
        nouveau = convertir_en_webp(self.image)
        if nouveau:
            self.image = nouveau
        super().save(*args, **kwargs)


    def __str__(self):
        return self.titre


@receiver(pre_delete,sender=Publication)
def delete_publication_image(sender, instance,**kwargs):
    if instance.image:
        if os.path.isfile(instance.image.path):
            os.remove (instance.image.path)





class SocialPost(models.Model):
    auteur = models.ForeignKey(User, on_delete=models.CASCADE, related_name='publications_sociales')
    contenu = models.TextField(max_length=4000)
    image = models.ImageField(
        upload_to='publications_sociales/',
        blank=True,
        null=True,
        validators=[MaxFileSizeValidator(5 * 1024 * 1024)],
    )
    status = models.IntegerField(choices=STATUS, default=1)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_creation']

    def __str__(self):
        return f"Publication de {self.auteur}"


class FeedLike(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='likes_fil')
    post = models.ForeignKey('SocialPost', on_delete=models.CASCADE, related_name='feed_likes', blank=True, null=True)
    publication = models.ForeignKey(Publication, on_delete=models.CASCADE, related_name='feed_likes', blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(post__isnull=False, publication__isnull=True)
                    | models.Q(post__isnull=True, publication__isnull=False)
                ),
                name='feed_like_has_one_target',
            ),
            models.UniqueConstraint(
                fields=['user', 'post'],
                condition=models.Q(post__isnull=False),
                name='unique_social_post_like',
            ),
            models.UniqueConstraint(
                fields=['user', 'publication'],
                condition=models.Q(publication__isnull=False),
                name='unique_publication_like',
            ),
        ]

    def __str__(self):
        return f"J’aime de {self.user}"


class FeedComment(models.Model):
    auteur = models.ForeignKey(User, on_delete=models.CASCADE, related_name='commentaires_fil')
    post = models.ForeignKey(SocialPost, on_delete=models.CASCADE, related_name='feed_comments', blank=True, null=True)
    publication = models.ForeignKey(Publication, on_delete=models.CASCADE, related_name='feed_comments', blank=True, null=True)
    contenu = models.TextField(max_length=2000)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date_creation']
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(post__isnull=False, publication__isnull=True)
                    | models.Q(post__isnull=True, publication__isnull=False)
                ),
                name='feed_comment_has_one_target',
            ),
        ]

    def __str__(self):
        return f"Commentaire de {self.auteur}"


class FeedShare(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, related_name='partages_fil', blank=True, null=True)
    post = models.ForeignKey(SocialPost, on_delete=models.CASCADE, related_name='feed_shares', blank=True, null=True)
    publication = models.ForeignKey(Publication, on_delete=models.CASCADE, related_name='feed_shares', blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_creation']
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(post__isnull=False, publication__isnull=True)
                    | models.Q(post__isnull=True, publication__isnull=False)
                ),
                name='feed_share_has_one_target',
            ),
        ]

    def __str__(self):
        return f"Partage de {self.user or 'visiteur'}"


class Information(models.Model):

    module=models.IntegerField()
    heures=  models.IntegerField(default=0)
    lieu= models.CharField(max_length=50)
    titre= models.CharField( unique=True,max_length=50)
    contenue= models.TextField()
    photo = models.ImageField(
        upload_to='information_image/',
        blank=True,
        null=True,
        validators=[MaxFileSizeValidator(10 * 1024 * 1024)],
    )
    date_pub = models.DateTimeField( auto_now_add=True)
    date_mf = models.DateTimeField( auto_now=True)
    slug = models.SlugField(unique=True, blank=True)
    status =models.IntegerField(choices= STATUS, default = 0)
    choix =models.IntegerField(choices= CHOIX, default = 1)
    type_programme = models.CharField(max_length=20, choices=TYPE_PROGRAMME, default='initiation')
    domaine = models.CharField(max_length=20, choices=DOMAINES_FORMATION, default='developpement')
    niveau = models.CharField(max_length=20, choices=NIVEAUX_FORMATION, default='debutant')
    format_formation = models.CharField(max_length=20, choices=FORMATS_FORMATION, default='a_definir')
    prerequis = models.TextField(blank=True)
    objectifs = models.TextField(blank=True)
    competences = models.TextField(blank=True)
    contenu_modules = models.TextField(blank=True, verbose_name="Contenu des modules")
    frais = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    bourse_disponible = models.BooleanField(default=False)
    paiement_echelonne = models.BooleanField(default=False)
    brochure = models.FileField(
        upload_to='brochures/',
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(['pdf']),
            validate_pdf_signature,
            MaxFileSizeValidator(20 * 1024 * 1024),
        ],
    )
    partenaires = models.ManyToManyField('Partner', related_name='formations', blank=True)
    place = models.IntegerField(default=0)
    place_restante = models.IntegerField(default=0)
    dates_activite= models.CharField(max_length=50, default="A definir")
    class Meta:
        ordering=['-date_pub']



    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.titre)
        nouveau = convertir_en_webp(self.photo)
        if nouveau:
            self.photo = nouveau
        super().save(*args, **kwargs)

    def __str__(self):
        return self.titre




@receiver(pre_delete, sender=Information)
def delete_information_image(sender, instance, **kwargs):
    if instance.photo:
        if os.path.isfile(instance.photo.path):
            os.remove(instance.photo.path)
    if instance.brochure and os.path.isfile(instance.brochure.path):
        os.remove(instance.brochure.path)


class TrainingSession(models.Model):
    formation = models.ForeignKey(Information, on_delete=models.CASCADE, related_name='sessions')
    titre = models.CharField(max_length=150, blank=True)
    type_session = models.CharField(max_length=20, choices=TYPES_SESSION, default='cohorte')
    date_debut = models.DateField()
    date_fin = models.DateField(blank=True, null=True)
    horaires = models.CharField(max_length=100, blank=True)
    lieu = models.CharField(max_length=100, blank=True)
    format_formation = models.CharField(max_length=20, choices=FORMATS_FORMATION, default='a_definir')
    places_totales = models.PositiveIntegerField(default=0)
    places_restantes = models.PositiveIntegerField(default=0)
    status = models.IntegerField(choices=STATUS, default=1)

    class Meta:
        ordering = ['date_debut', 'pk']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(date_fin__isnull=True) | models.Q(date_fin__gte=models.F('date_debut')),
                name='training_session_end_after_start',
            ),
            models.CheckConstraint(
                condition=models.Q(places_restantes__lte=models.F('places_totales')),
                name='training_session_remaining_within_capacity',
            ),
        ]

    def clean(self):
        if self.date_fin and self.date_fin < self.date_debut:
            raise ValidationError({'date_fin': "La date de fin doit suivre la date de démarrage."})
        if self.places_restantes > self.places_totales:
            raise ValidationError({'places_restantes': "Les places restantes ne peuvent dépasser la capacité totale."})

    def save(self, *args, **kwargs):
        if self.pk is None and self.places_totales and self.places_restantes == 0:
            self.places_restantes = self.places_totales
        super().save(*args, **kwargs)

    def __str__(self):
        return self.titre or f"{self.formation.titre} — {self.date_debut:%d/%m/%Y}"


class FormationFAQ(models.Model):
    formation = models.ForeignKey(Information, on_delete=models.CASCADE, related_name='questions_frequentes')
    question = models.CharField(max_length=250)
    reponse = models.TextField()
    ordre = models.PositiveSmallIntegerField(default=0)
    status = models.IntegerField(choices=STATUS, default=1)

    class Meta:
        ordering = ['ordre', 'pk']
        verbose_name = 'Question fréquente de formation'
        verbose_name_plural = 'Questions fréquentes de formation'

    def __str__(self):
        return f"{self.formation.titre} — {self.question}"


class SessionReservation(models.Model):
    session = models.ForeignKey(TrainingSession, on_delete=models.CASCADE, related_name='reservations')
    nom = models.CharField(max_length=100)
    email = models.EmailField()
    telephone = models.CharField(max_length=20, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_creation']
        constraints = [
            models.UniqueConstraint(fields=['session', 'email'], name='unique_session_reservation_email')
        ]

    def __str__(self):
        return f"{self.nom} — {self.session}"


class Candidature(models.Model):
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    formation = models.ForeignKey(Information, on_delete=models.PROTECT, related_name='candidatures')
    utilisateur = models.ForeignKey(User, on_delete=models.SET_NULL, related_name='candidatures_formation', blank=True, null=True)
    session = models.ForeignKey(
        TrainingSession, on_delete=models.SET_NULL, related_name='candidatures', blank=True, null=True
    )
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    email = models.EmailField()
    telephone = models.CharField(max_length=20)
    motivation = models.TextField()
    document = models.FileField(
        upload_to='candidatures/documents/',
        storage=private_media_storage,
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(['pdf']),
            validate_pdf_signature,
            MaxFileSizeValidator(5 * 1024 * 1024),
        ],
    )
    statut = models.CharField(max_length=20, choices=CANDIDATURE_STATUTS, default='recue')
    place_retenue = models.BooleanField(default=False, editable=False)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_creation']

    def clean(self):
        if self.session_id and self.formation_id and self.session.formation_id != self.formation_id:
            raise ValidationError({'session': "La session choisie ne correspond pas à cette formation."})

    def __str__(self):
        return f"{self.prenom} {self.nom} — {self.formation.titre}"


class DemandeAideFinanciere(models.Model):
    formation = models.ForeignKey(Information, on_delete=models.PROTECT, related_name='demandes_aide')
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    email = models.EmailField()
    telephone = models.CharField(max_length=20)
    montant_souhaite = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    situation = models.TextField()
    statut = models.CharField(max_length=20, choices=STATUTS_AIDE, default='recue')
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_creation']

    def __str__(self):
        return f"{self.prenom} {self.nom} — {self.formation.titre}"




TYPE_CONTENU = (
    ('video', 'Vidéo'),
    ('audio', 'Audio'),
    ('pdf', 'PDF'),
)

CATEGORIES_COURS = (
    ('dev', 'Développement'),
    ('design', 'Design'),
    ('bureautique', 'Bureautique'),
    ('langues', 'Langues'),
)

class Cours(models.Model):
    formateur = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cours')
    titre = models.CharField(max_length=200, unique=True)
    description = models.TextField()

    type_contenu = models.CharField(max_length=10, choices=TYPE_CONTENU, default='video')
    video = models.FileField(
        upload_to='cours_video/',
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(['mp4', 'webm', 'mov']),
            MaxFileSizeValidator(100 * 1024 * 1024),
        ],
    )
    audio = models.FileField(
        upload_to='cours_audio/',
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(['mp3', 'm4a', 'ogg', 'wav']),
            MaxFileSizeValidator(50 * 1024 * 1024),
        ],
    )
    pdf = models.FileField(
        upload_to='cours_pdf/',
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(['pdf']),
            validate_pdf_signature,
            MaxFileSizeValidator(10 * 1024 * 1024),
        ],
    )

    miniature = models.ImageField(
        upload_to='cours_miniature/',
        blank=True,
        null=True,
        validators=[MaxFileSizeValidator(5 * 1024 * 1024)],
    )
    duree = models.CharField(max_length=8, blank=True, help_text="Format mm:ss — vidéo/audio uniquement")
    nb_pages = models.PositiveIntegerField(blank=True, null=True, help_text="Nombre de pages — PDF uniquement")

    categorie = models.CharField(max_length=20, choices=CATEGORIES_COURS, default='dev')
    vues = models.PositiveIntegerField(default=0)
    date_pub = models.DateTimeField(auto_now_add=True)
    date_modif = models.DateTimeField(auto_now=True)
    slug = models.SlugField(unique=True, blank=True)
    status = models.IntegerField(choices=STATUS, default=0)
    workflow_status = models.CharField(max_length=20, choices=COURS_STATUTS, default='brouillon')

    class Meta:
        ordering = ['-date_pub']
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(status=1, workflow_status='publie')
                    | models.Q(status=0, workflow_status__in=['brouillon', 'a_valider', 'refuse'])
                ),
                name='course_publication_matches_workflow',
            ),
        ]

    def clean(self):
        fichiers = {'video': self.video, 'audio': self.audio, 'pdf': self.pdf}
        if not fichiers.get(self.type_contenu):
            raise ValidationError(
                f"Merci d'ajouter un fichier {self.get_type_contenu_display()} : "
                f"le type de contenu sélectionné est « {self.get_type_contenu_display()} »."
            )

    def save(self, *args, **kwargs):
        if self.workflow_status == 'brouillon' and self.status == 1:
            self.workflow_status = 'publie'
        else:
            self.status = 1 if self.workflow_status == 'publie' else 0
        if not self.slug:
            self.slug = slugify(self.titre)
        nouveau = convertir_en_webp(self.miniature)
        if nouveau:
            self.miniature = nouveau
        super().save(*args, **kwargs)

    def get_fichier(self):
        return {'video': self.video, 'audio': self.audio, 'pdf': self.pdf}.get(self.type_contenu)

    def __str__(self):
        return self.titre


@receiver(pre_delete, sender=Cours)
def delete_cours_fichiers(sender, instance, **kwargs):
    for champ in (instance.video, instance.audio, instance.pdf, instance.miniature):
        if champ and os.path.isfile(champ.path):
            os.remove(champ.path)




class Contact(models.Model):
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    telephone = models.CharField(max_length=20)
    email = models.EmailField()
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_creation']

    def __str__(self):
        return f"{self.prenom} {self.nom}"





class BlogCategory(models.Model):
    nom = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    description = models.CharField(max_length=240, blank=True)
    status = models.IntegerField(choices=STATUS, default=1)

    class Meta:
        ordering = ['nom']
        verbose_name = 'Catégorie du blog'
        verbose_name_plural = 'Catégories du blog'

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nom)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nom


# models.py
class Article(models.Model):
    titre = models.CharField(max_length=200)
    contenu = models.TextField()
    image = models.ImageField(
        upload_to='articles/',
        null=True,
        blank=True,
        validators=[MaxFileSizeValidator(10 * 1024 * 1024)],
    )
    date_publication = models.DateTimeField(auto_now_add=True)
    auteur = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blog_articles')
    date_modif = models.DateTimeField( auto_now=True)
    lien = models.SlugField(unique=True, blank=True)
    status =models.IntegerField(choices= STATUS, default = 0)
    categorie = models.ForeignKey(BlogCategory, on_delete=models.SET_NULL, related_name='articles', blank=True, null=True)
    a_la_une = models.BooleanField(default=False, verbose_name='Mettre à la une')

    class Meta:
            ordering=['-date_publication']

    def save(self, *args, **kwargs):
            if not self.lien:
                self.lien = slugify(self.titre)
            nouveau = convertir_en_webp(self.image)
            if nouveau:
                self.image = nouveau
            super().save(*args, **kwargs)

        def __str__(self):
            return self.titre



@receiver(pre_delete,sender= Article)
def delete_article_image(sender, instance,**kwargs):
    if instance.image:
        if os.path.isfile(instance.image.path):
            os.remove (instance.image.path)






class Comment(models.Model):
    publication = models.ForeignKey(Publication, on_delete=models.CASCADE, related_name='commentaires', blank=True, null=True)
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='commentaires', blank=True, null=True)
    nom = models.CharField(max_length=100)
    message = models.TextField()
    date_creation = models.DateTimeField(auto_now_add=True)
    status = models.IntegerField(choices=STATUS, default=0)  # 0 = en attente de validation

    class Meta:
        ordering = ['-date_creation']

    def clean(self):
        if not self.publication and not self.article:
            raise ValidationError("Un commentaire doit être lié à une publication ou à un article.")
        if self.publication and self.article:
            raise ValidationError("Un commentaire ne peut pas être lié à la fois à une publication et à un article.")

    def __str__(self):
        cible = self.publication or self.article
        return f"{self.nom} sur « {cible} »"


class Conversation(models.Model):
    participant_one = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='conversations_as_one'
    )
    participant_two = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='conversations_as_two'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(
                fields=['participant_one', 'participant_two'],
                name='unique_direct_conversation',
            ),
            models.CheckConstraint(
                condition=models.Q(participant_one__lt=models.F('participant_two')),
                name='conversation_participants_ordered',
            ),
        ]

    def save(self, *args, **kwargs):
        if self.participant_one_id and self.participant_two_id:
            if self.participant_one_id == self.participant_two_id:
                raise ValidationError("Une conversation doit réunir deux personnes différentes.")
            if self.participant_one_id > self.participant_two_id:
                self.participant_one_id, self.participant_two_id = (
                    self.participant_two_id,
                    self.participant_one_id,
                )
        super().save(*args, **kwargs)

    def other_participant(self, user):
        if user.pk == self.participant_one_id:
            return self.participant_two
        if user.pk == self.participant_two_id:
            return self.participant_one
        raise ValueError("Cet utilisateur ne participe pas à la conversation.")

    def __str__(self):
        return f"{self.participant_one} ↔ {self.participant_two}"


class Message(models.Model):
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name='messages'
    )
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='messages_envoyes')
    content = models.TextField(max_length=4000)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at', 'pk']

    def clean(self):
        if self.conversation_id and self.sender_id not in (
            self.conversation.participant_one_id,
            self.conversation.participant_two_id,
        ):
            raise ValidationError("L’expéditeur doit participer à cette conversation.")

    def __str__(self):
        return f"Message de {self.sender} — {self.created_at:%d/%m/%Y %H:%M}"


class LearningProgress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='learning_progress')
    cours = models.ForeignKey(Cours, on_delete=models.CASCADE, related_name='progressions')
    is_completed = models.BooleanField(default=False)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at']
        constraints = [
            models.UniqueConstraint(fields=['user', 'cours'], name='unique_user_course_progress')
        ]

    def __str__(self):
        etat = "terminé" if self.is_completed else "en cours"
        return f"{self.user} — {self.cours} ({etat})"


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profil_dunia')
    role = models.CharField(max_length=20, choices=PROFIL_ROLES, default='apprenant')
    bio = models.TextField(blank=True)
    telephone = models.CharField(max_length=20, blank=True)
    ville = models.CharField(max_length=100, blank=True)
    photo = models.ImageField(
        upload_to='profils/',
        blank=True,
        null=True,
        validators=[MaxFileSizeValidator(5 * 1024 * 1024)],
    )
    linkedin = models.URLField(blank=True)
    github = models.URLField(blank=True)
    portfolio = models.URLField(blank=True)
    visible = models.BooleanField(default=True)
    date_modification = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profil de {self.user.get_full_name() or self.user.username}"


class Friendship(models.Model):
    PENDING = 'pending'
    ACCEPTED = 'accepted'
    STATUS_CHOICES = (
        (PENDING, 'En attente'),
        (ACCEPTED, 'Acceptée'),
    )

    person_one = models.ForeignKey(User, on_delete=models.CASCADE, related_name='friendships_as_one')
    person_two = models.ForeignKey(User, on_delete=models.CASCADE, related_name='friendships_as_two')
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='demandes_amitie_envoyees')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=PENDING)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_acceptation = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-date_creation']
        constraints = [
            models.UniqueConstraint(fields=['person_one', 'person_two'], name='unique_friendship_pair'),
            models.CheckConstraint(
                condition=models.Q(person_one__lt=models.F('person_two')),
                name='friendship_people_ordered',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(requested_by=models.F('person_one'))
                    | models.Q(requested_by=models.F('person_two'))
                ),
                name='friendship_requester_is_participant',
            ),
        ]

    def save(self, *args, **kwargs):
        if self.person_one_id and self.person_two_id:
            if self.person_one_id == self.person_two_id:
                raise ValidationError("Une personne ne peut pas s’ajouter elle-même.")
            if self.person_one_id > self.person_two_id:
                self.person_one_id, self.person_two_id = self.person_two_id, self.person_one_id
            if self.requested_by_id not in (self.person_one_id, self.person_two_id):
                raise ValidationError("Le demandeur doit faire partie de cette relation.")
        super().save(*args, **kwargs)

    def other_user(self, user):
        if user.pk == self.person_one_id:
            return self.person_two
        if user.pk == self.person_two_id:
            return self.person_one
        raise ValueError("Cet utilisateur ne fait pas partie de cette relation.")

    def __str__(self):
        return f"{self.person_one} — {self.person_two} ({self.get_status_display()})"


class TrainerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profil_formateur')
    titre = models.CharField(max_length=120, blank=True)
    experience = models.TextField(blank=True)
    certifications = models.TextField(blank=True)
    domaines = models.CharField(max_length=200, blank=True)
    status = models.IntegerField(choices=STATUS, default=0)

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class RoleRequest(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='demandes_role')
    role = models.CharField(max_length=20, choices=ROLE_DEMANDES)
    statut = models.CharField(max_length=20, choices=ROLE_DEMANDE_STATUTS, default='en_attente')
    date_demande = models.DateTimeField(auto_now_add=True)
    date_decision = models.DateTimeField(blank=True, null=True)
    decision_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name='decisions_demandes_role',
        blank=True,
        null=True,
    )
    commentaire = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ['-date_demande']
        constraints = [
            models.UniqueConstraint(fields=['user', 'role'], name='unique_user_role_request'),
        ]

    def __str__(self):
        return f"{self.user} — {self.get_role_display()} ({self.get_statut_display()})"


class BusinessProfile(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='entreprises_dunia')
    nom = models.CharField(max_length=160)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField()
    logo = models.ImageField(
        upload_to='entreprises/',
        blank=True,
        null=True,
        validators=[MaxFileSizeValidator(5 * 1024 * 1024)],
    )
    email = models.EmailField()
    telephone = models.CharField(max_length=20, blank=True)
    ville = models.CharField(max_length=100, blank=True)
    site_web = models.URLField(blank=True)
    verifiee = models.BooleanField(default=False)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nom']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nom)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nom


class JobPosting(models.Model):
    entreprise = models.ForeignKey(BusinessProfile, on_delete=models.CASCADE, related_name='offres')
    titre = models.CharField(max_length=180)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField()
    type_offre = models.CharField(max_length=20, choices=OFFRE_TYPES, default='stage')
    domaine = models.CharField(max_length=20, choices=DOMAINES_FORMATION, default='developpement')
    lieu = models.CharField(max_length=120, blank=True)
    format_emploi = models.CharField(max_length=20, choices=FORMATS_FORMATION, default='presentiel')
    date_limite = models.DateField(blank=True, null=True)
    statut = models.CharField(max_length=20, choices=OFFRE_STATUTS, default='a_valider')
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_creation']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.titre)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.titre} — {self.entreprise.nom}"


class JobApplication(models.Model):
    offre = models.ForeignKey(JobPosting, on_delete=models.CASCADE, related_name='candidatures')
    candidat = models.ForeignKey(User, on_delete=models.CASCADE, related_name='candidatures_emploi')
    motivation = models.TextField()
    cv = models.FileField(
        upload_to='candidatures_emploi/cv/',
        storage=private_media_storage,
        validators=[
            FileExtensionValidator(['pdf']),
            validate_pdf_signature,
            MaxFileSizeValidator(5 * 1024 * 1024),
        ],
    )
    statut = models.CharField(max_length=20, choices=CANDIDATURE_EMPLOI_STATUTS, default='recue')
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_creation']
        constraints = [models.UniqueConstraint(fields=['offre', 'candidat'], name='unique_job_application')]

    def __str__(self):
        return f"{self.candidat} — {self.offre.titre}"


class ProjectSubmission(models.Model):
    auteur = models.ForeignKey(User, on_delete=models.CASCADE, related_name='projets')
    formation = models.ForeignKey(Information, on_delete=models.SET_NULL, related_name='projets', blank=True, null=True)
    titre = models.CharField(max_length=180)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField()
    competences = models.CharField(max_length=300, blank=True)
    url_demo = models.URLField(blank=True)
    url_code = models.URLField(blank=True)
    image = models.ImageField(
        upload_to='projets/',
        blank=True,
        null=True,
        validators=[MaxFileSizeValidator(5 * 1024 * 1024)],
    )
    statut = models.CharField(max_length=20, choices=PROJET_STATUTS, default='a_valider')
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_creation']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.titre)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.titre


class Community(models.Model):
    nom = models.CharField(max_length=120)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField()
    formation = models.ForeignKey(Information, on_delete=models.SET_NULL, related_name='communautes', blank=True, null=True)
    membres = models.ManyToManyField(User, through='CommunityMembership', related_name='communautes')
    status = models.IntegerField(choices=STATUS, default=1)
    privee = models.BooleanField(default=False)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nom']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nom)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nom


class CommunityMembership(models.Model):
    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name='adhesions')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='adhesions_communaute')
    date_adhesion = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['community', 'user'], name='unique_community_member')]
        ordering = ['date_adhesion']

    def __str__(self):
        return f"{self.user} — {self.community}"


class CommunityPost(models.Model):
    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name='publications')
    auteur = models.ForeignKey(User, on_delete=models.CASCADE, related_name='publications_communaute')
    contenu = models.TextField(max_length=4000)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_creation']

    def __str__(self):
        return f"Publication de {self.auteur} dans {self.community}"


class Testimonial(models.Model):
    auteur = models.ForeignKey(User, on_delete=models.SET_NULL, related_name='temoignages', blank=True, null=True)
    nom_affiche = models.CharField(max_length=120)
    situation = models.CharField(max_length=160, blank=True)
    formation = models.ForeignKey(Information, on_delete=models.SET_NULL, related_name='temoignages', blank=True, null=True)
    parcours = models.TextField()
    statut_professionnel = models.CharField(max_length=160, blank=True)
    photo = models.ImageField(
        upload_to='temoignages/',
        blank=True,
        null=True,
        validators=[MaxFileSizeValidator(10 * 1024 * 1024)],
    )
    status = models.IntegerField(choices=STATUS, default=0)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_creation']

    def __str__(self):
        return self.nom_affiche


class ProfessionalEvent(models.Model):
    titre = models.CharField(max_length=180)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField()
    organisateur = models.CharField(max_length=160, blank=True)
    lieu = models.CharField(max_length=160, blank=True)
    format_evenement = models.CharField(max_length=20, choices=FORMATS_FORMATION, default='presentiel')
    date_debut = models.DateTimeField()
    date_fin = models.DateTimeField(blank=True, null=True)
    places = models.PositiveIntegerField(default=0, help_text='0 signifie sans limite de places')
    places_restantes = models.PositiveIntegerField(default=0)
    status = models.IntegerField(choices=STATUS, default=0)

    class Meta:
        ordering = ['date_debut']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(date_fin__isnull=True) | models.Q(date_fin__gte=models.F('date_debut')),
                name='professional_event_end_after_start',
            ),
            models.CheckConstraint(
                condition=models.Q(places=0) | models.Q(places_restantes__lte=models.F('places')),
                name='professional_event_remaining_within_capacity',
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.titre)
        if self.pk is None and self.places and self.places_restantes == 0:
            self.places_restantes = self.places
        super().save(*args, **kwargs)

    def __str__(self):
        return self.titre


class EventRegistration(models.Model):
    evenement = models.ForeignKey(ProfessionalEvent, on_delete=models.CASCADE, related_name='inscriptions')
    participant = models.ForeignKey(User, on_delete=models.CASCADE, related_name='inscriptions_evenement')
    date_inscription = models.DateTimeField(auto_now_add=True)
    status = models.IntegerField(choices=STATUS, default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['evenement', 'participant'], name='unique_event_registration')]
        ordering = ['date_inscription']

    def __str__(self):
        return f"{self.participant} — {self.evenement}"


class CourseEvaluation(models.Model):
    cours = models.ForeignKey(Cours, on_delete=models.CASCADE, related_name='evaluations')
    auteur = models.ForeignKey(User, on_delete=models.CASCADE, related_name='evaluations_cours')
    note = models.PositiveSmallIntegerField(choices=[(n, str(n)) for n in range(1, 6)])
    commentaire = models.TextField(blank=True, max_length=2000)
    status = models.IntegerField(choices=STATUS, default=1)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_creation']
        constraints = [models.UniqueConstraint(fields=['cours', 'auteur'], name='unique_course_evaluation')]

    def __str__(self):
        return f"{self.cours} — {self.note}/5"


class Credential(models.Model):
    nom = models.CharField(max_length=140)
    description = models.TextField(blank=True)
    cours = models.ManyToManyField(Cours, related_name='certifications_requises', blank=True)
    formations = models.ManyToManyField(Information, related_name='certifications', blank=True)
    partenaire = models.ForeignKey('Partner', on_delete=models.SET_NULL, related_name='certifications', blank=True, null=True)
    status = models.IntegerField(choices=STATUS, default=1)

    def __str__(self):
        return self.nom


class UserCredential(models.Model):
    utilisateur = models.ForeignKey(User, on_delete=models.CASCADE, related_name='certifications')
    certification = models.ForeignKey(Credential, on_delete=models.CASCADE, related_name='attributions')
    date_obtention = models.DateTimeField(auto_now_add=True)
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['utilisateur', 'certification'], name='unique_user_credential')]
        ordering = ['-date_obtention']

    def __str__(self):
        return f"{self.utilisateur} — {self.certification}"


class Partner(models.Model):
    nom = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    logo = models.ImageField(
        upload_to='partenaires/',
        blank=True,
        null=True,
        validators=[MaxFileSizeValidator(10 * 1024 * 1024)],
    )
    site_web = models.URLField(blank=True)
    status = models.IntegerField(choices=STATUS, default=1)

    class Meta:
        ordering = ['nom']

    def __str__(self):
        return self.nom


class ImpactMetric(models.Model):
    titre = models.CharField(max_length=120)
    valeur = models.PositiveIntegerField(default=0)
    unite = models.CharField(max_length=40, blank=True)
    ordre = models.PositiveSmallIntegerField(default=0)
    status = models.IntegerField(choices=STATUS, default=1)

    class Meta:
        ordering = ['ordre', 'pk']

    def __str__(self):
        return f"{self.titre} : {self.valeur} {self.unite}".strip()


class Notification(models.Model):
    destinataire = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications_dunia')
    type_notification = models.CharField(max_length=20, choices=NOTIFICATION_TYPES, default='systeme')
    titre = models.CharField(max_length=160)
    message = models.CharField(max_length=500)
    url = models.CharField(max_length=300, blank=True)
    lue = models.BooleanField(default=False)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_creation']

    def __str__(self):
        return f"{self.destinataire} — {self.titre}"


class AuditLog(models.Model):
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name='evenements_audit',
        blank=True,
        null=True,
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT, related_name='dunia_audit_logs')
    object_id = models.CharField(max_length=64)
    action = models.CharField(max_length=80)
    details = models.JSONField(default=dict, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_creation', '-pk']
        indexes = [
            models.Index(fields=['content_type', 'object_id', '-date_creation'], name='audit_object_date_idx'),
        ]

    def __str__(self):
        return f"{self.action} — {self.content_type} #{self.object_id}"


class LearnerProjectRequest(models.Model):
    nom = models.CharField(max_length=120)
    organisation = models.CharField(max_length=160)
    email = models.EmailField()
    telephone = models.CharField(max_length=20, blank=True)
    type_projet = models.CharField(max_length=100, blank=True)
    description = models.TextField()
    date_creation = models.DateTimeField(auto_now_add=True)
    traite = models.BooleanField(default=False)

    class Meta:
        ordering = ['-date_creation']

    def __str__(self):
        return f"{self.organisation} — {self.type_projet or 'Projet apprenant'}"


class Initiative(models.Model):
    titre = models.CharField(max_length=180)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField()
    image = models.ImageField(
        upload_to='initiatives/',
        blank=True,
        null=True,
        validators=[MaxFileSizeValidator(10 * 1024 * 1024)],
    )
    date_debut = models.DateField(blank=True, null=True)
    date_fin = models.DateField(blank=True, null=True)
    lieu = models.CharField(max_length=140, blank=True)
    status = models.IntegerField(choices=STATUS, default=0)

    class Meta:
        ordering = ['-date_debut', 'titre']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.titre)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.titre


class Campus(models.Model):
    nom = models.CharField(max_length=140, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    ville = models.CharField(max_length=100)
    adresse = models.CharField(max_length=240)
    description = models.TextField(blank=True)
    informations_pratiques = models.TextField(blank=True)
    photo = models.ImageField(
        upload_to='campus/',
        blank=True,
        null=True,
        validators=[MaxFileSizeValidator(10 * 1024 * 1024)],
    )
    formations = models.ManyToManyField(Information, related_name='campus', blank=True)
    status = models.IntegerField(choices=STATUS, default=0)

    class Meta:
        ordering = ['ville', 'nom']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nom)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nom} — {self.ville}"


class AnnualReport(models.Model):
    annee = models.PositiveSmallIntegerField(unique=True)
    resume = models.TextField()
    apprenants_formes = models.PositiveIntegerField(default=0)
    formations_terminees = models.PositiveIntegerField(default=0)
    taux_reussite = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    taux_insertion = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    fichier = models.FileField(
        upload_to='rapports_annuels/',
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(['pdf']),
            validate_pdf_signature,
            MaxFileSizeValidator(20 * 1024 * 1024),
        ],
    )
    status = models.IntegerField(choices=STATUS, default=0)

    class Meta:
        ordering = ['-annee']
        verbose_name = 'Rapport annuel'
        verbose_name_plural = 'Rapports annuels'

    def __str__(self):
        return f"Rapport annuel {self.annee}"


class Challenge(models.Model):
    titre = models.CharField(max_length=180)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField()
    consignes = models.TextField(blank=True)
    prix = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)], help_text='0 signifie gratuit.')
    devise = models.CharField(max_length=3, default='XOF')
    instructions_paiement = models.TextField(blank=True, help_text='Informations de paiement manuel pour les défis payants.')
    date_debut = models.DateTimeField(blank=True, null=True)
    date_fin = models.DateTimeField(blank=True, null=True)
    status = models.IntegerField(choices=STATUS, default=0)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_creation']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(date_fin__isnull=True) | models.Q(date_debut__isnull=True) | models.Q(date_fin__gte=models.F('date_debut')),
                name='challenge_end_after_start',
            ),
            models.CheckConstraint(
                condition=models.Q(prix__gte=0),
                name='challenge_price_nonnegative',
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.titre)
        super().save(*args, **kwargs)

    @property
    def est_gratuit(self):
        return self.prix == 0

    def __str__(self):
        return self.titre


class ChallengeParticipation(models.Model):
    PAIEMENT_STATUTS = (
        ('sans_objet', 'Sans objet'),
        ('en_attente', 'Paiement à confirmer'),
        ('confirme', 'Paiement confirmé'),
        ('refuse', 'Paiement refusé'),
    )
    TRAVAIL_STATUTS = (
        ('non_soumis', 'Pas encore remis'),
        ('a_evaluer', 'À évaluer'),
        ('valide', 'Validé'),
        ('a_corriger', 'À corriger'),
    )

    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name='participations')
    participant = models.ForeignKey(User, on_delete=models.CASCADE, related_name='participations_challenges')
    paiement_statut = models.CharField(max_length=16, choices=PAIEMENT_STATUTS, default='sans_objet')
    reference_paiement = models.CharField(max_length=120, blank=True)
    travail = models.TextField(blank=True, help_text='Lien ou description de la réalisation.')
    travail_statut = models.CharField(max_length=16, choices=TRAVAIL_STATUTS, default='non_soumis')
    date_inscription = models.DateTimeField(auto_now_add=True)
    date_soumission = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-date_inscription']
        constraints = [models.UniqueConstraint(fields=['challenge', 'participant'], name='unique_challenge_participation')]

    def __str__(self):
        return f"{self.participant} — {self.challenge}"


class ChallengePaymentAttempt(models.Model):
    STATUTS = (
        ('en_attente', 'À confirmer'),
        ('confirme', 'Confirmé'),
        ('refuse', 'Refusé'),
    )

    participation = models.ForeignKey(
        ChallengeParticipation,
        on_delete=models.CASCADE,
        related_name='tentatives_paiement',
    )
    reference = models.CharField(max_length=120)
    montant = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    devise = models.CharField(max_length=3, blank=True)
    statut = models.CharField(max_length=16, choices=STATUTS, default='en_attente')
    soumise_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name='tentatives_paiement_soumises',
        blank=True,
        null=True,
    )
    date_soumission = models.DateTimeField(default=timezone.now, blank=True, null=True)
    decision_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name='decisions_tentatives_paiement',
        blank=True,
        null=True,
    )
    date_decision = models.DateTimeField(blank=True, null=True)
    commentaire_decision = models.CharField(max_length=500, blank=True)
    historique_importe = models.BooleanField(default=False, editable=False)

    class Meta:
        ordering = ['-date_soumission', '-pk']
        constraints = [
            models.CheckConstraint(condition=models.Q(reference__gt=''), name='challenge_payment_reference_not_empty'),
            models.CheckConstraint(condition=models.Q(montant__gte=0), name='challenge_payment_amount_nonnegative'),
            models.UniqueConstraint(
                fields=['participation'],
                condition=models.Q(statut='en_attente'),
                name='unique_pending_challenge_payment',
            ),
        ]

    def __str__(self):
        return f"{self.participation} — {self.reference} ({self.get_statut_display()})"


class ChallengeWorkSubmission(models.Model):
    STATUTS = (
        ('a_evaluer', 'À évaluer'),
        ('valide', 'Validé'),
        ('a_corriger', 'À corriger'),
    )

    participation = models.ForeignKey(
        ChallengeParticipation,
        on_delete=models.CASCADE,
        related_name='soumissions_travail',
    )
    version = models.PositiveIntegerField()
    travail = models.TextField(max_length=10000)
    statut = models.CharField(max_length=16, choices=STATUTS, default='a_evaluer')
    retour = models.TextField(blank=True, max_length=4000)
    date_soumission = models.DateTimeField(default=timezone.now, blank=True, null=True)
    date_evaluation = models.DateTimeField(blank=True, null=True)
    evalue_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name='soumissions_travail_evaluees',
        blank=True,
        null=True,
    )
    historique_importe = models.BooleanField(default=False, editable=False)

    class Meta:
        ordering = ['-version', '-pk']
        constraints = [
            models.UniqueConstraint(fields=['participation', 'version'], name='unique_challenge_work_version'),
        ]

    def __str__(self):
        return f"{self.participation} — version {self.version}"

