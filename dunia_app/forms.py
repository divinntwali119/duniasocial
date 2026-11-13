from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, SetPasswordForm
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.validators import FileExtensionValidator
from django.utils import timezone
from .models import (
    CANDIDATURE_STATUTS,
    DOMAINES_FORMATION,
    FORMATS_FORMATION,
    NIVEAUX_FORMATION,
    TYPE_PROGRAMME,
    Candidature,
    BusinessProfile,
    CommunityPost,
    CourseEvaluation,
    DemandeAideFinanciere,
    Contact,
    Information,
    JobApplication,
    JobPosting,
    Message,
    LearnerProjectRequest,
    ProjectSubmission,
    SocialPost,
    SessionReservation,
    Cours,
    TrainerProfile,
    TrainingSession,
    UserProfile,
)
from .validators import MaxFileSizeValidator, validate_pdf_signature


INPUT_CLASS = 'input input-bordered w-full'
SELECT_CLASS = 'select select-bordered w-full'
TEXTAREA_CLASS = 'textarea textarea-bordered w-full'

class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ['nom', 'prenom', 'telephone', 'email']


class CatalogFilterForm(forms.Form):
    q = forms.CharField(required=False, label='Mot-clé', widget=forms.TextInput(attrs={
        'class': INPUT_CLASS, 'placeholder': 'Ex. développement web',
    }))
    type_programme = forms.ChoiceField(required=False, label='Type de programme', choices=[('', 'Tous les programmes'), *TYPE_PROGRAMME], widget=forms.Select(attrs={'class': SELECT_CLASS}))
    domaine = forms.ChoiceField(required=False, label='Domaine', choices=[('', 'Tous les domaines'), *DOMAINES_FORMATION], widget=forms.Select(attrs={'class': SELECT_CLASS}))
    niveau = forms.ChoiceField(required=False, label='Niveau', choices=[('', 'Tous les niveaux'), *NIVEAUX_FORMATION], widget=forms.Select(attrs={'class': SELECT_CLASS}))
    format_formation = forms.ChoiceField(required=False, label='Format', choices=[('', 'Tous les formats'), *FORMATS_FORMATION], widget=forms.Select(attrs={'class': SELECT_CLASS}))
    lieu = forms.CharField(required=False, label='Ville ou lieu', widget=forms.TextInput(attrs={
        'class': INPUT_CLASS, 'placeholder': 'Ex. Abidjan',
    }))
    duree_max = forms.IntegerField(required=False, label='Durée maximale (heures)', min_value=1, widget=forms.NumberInput(attrs={
        'class': INPUT_CLASS, 'placeholder': 'Ex. 40',
    }))


class OrientationQuizForm(forms.Form):
    OBJECTIFS = (
        ('emploi', 'Me préparer à un emploi'),
        ('reconversion', 'Réussir une reconversion'),
        ('decouverte', 'Découvrir un domaine'),
        ('competences', 'Renforcer mes compétences'),
    )
    interests = forms.MultipleChoiceField(
        label='Quels domaines vous intéressent ?',
        choices=DOMAINES_FORMATION,
        widget=forms.SelectMultiple(attrs={'class': 'select select-bordered w-full min-h-40'}),
    )
    niveau = forms.ChoiceField(label='Votre niveau actuel', choices=NIVEAUX_FORMATION, widget=forms.Select(attrs={'class': SELECT_CLASS}))
    objectif = forms.ChoiceField(label='Votre objectif', choices=OBJECTIFS, widget=forms.Select(attrs={'class': SELECT_CLASS}))
    format_formation = forms.ChoiceField(
        label='Format préféré', required=False,
        choices=[('', 'Sans préférence'), *FORMATS_FORMATION],
        widget=forms.Select(attrs={'class': SELECT_CLASS}),
    )


class CandidatureForm(forms.ModelForm):
    document = forms.FileField(
        required=False,
        label='Document complémentaire (PDF, 5 Mo maximum)',
        validators=[
            FileExtensionValidator(allowed_extensions=['pdf']),
            validate_pdf_signature,
            MaxFileSizeValidator(5 * 1024 * 1024),
        ],
        widget=forms.ClearableFileInput(attrs={'class': 'file-input file-input-bordered w-full'}),
    )

    class Meta:
        model = Candidature
        fields = ['session', 'nom', 'prenom', 'email', 'telephone', 'motivation', 'document']
        labels = {
            'session': 'Cohorte souhaitée (facultatif)',
            'nom': 'Nom',
            'prenom': 'Prénom',
            'email': 'Adresse e-mail',
            'telephone': 'Téléphone',
            'motivation': 'Pourquoi souhaitez-vous rejoindre cette formation ?',
        }
        widgets = {
            'session': forms.Select(attrs={'class': SELECT_CLASS}),
            'nom': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'prenom': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'email': forms.EmailInput(attrs={'class': INPUT_CLASS}),
            'telephone': forms.TelInput(attrs={'class': INPUT_CLASS}),
            'motivation': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 4}),
        }

    def __init__(self, *args, formation=None, **kwargs):
        super().__init__(*args, **kwargs)
        sessions = TrainingSession.objects.filter(
            status=1,
            type_session='cohorte',
            date_debut__gte=timezone.localdate(),
            places_restantes__gt=0,
        )
        if formation:
            sessions = sessions.filter(formation=formation)
        self.fields['session'].queryset = sessions.order_by('date_debut')
        self.fields['session'].empty_label = 'Je choisirai plus tard'

    def clean_document(self):
        document = self.cleaned_data.get('document')
        if document and document.size > 5 * 1024 * 1024:
            raise forms.ValidationError('Le document doit faire 5 Mo ou moins.')
        return document


class ApplicationTrackingForm(forms.Form):
    reference = forms.UUIDField(label='Référence de candidature', widget=forms.TextInput(attrs={
        'class': INPUT_CLASS, 'placeholder': 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx',
    }))
    email = forms.EmailField(label='Adresse e-mail utilisée', widget=forms.EmailInput(attrs={
        'class': INPUT_CLASS, 'placeholder': 'vous@exemple.com',
    }))


class SessionReservationForm(forms.ModelForm):
    class Meta:
        model = SessionReservation
        fields = ['nom', 'email', 'telephone']
        labels = {'nom': 'Nom complet', 'email': 'Adresse e-mail', 'telephone': 'Téléphone (facultatif)'}
        widgets = {
            'nom': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'email': forms.EmailInput(attrs={'class': INPUT_CLASS}),
            'telephone': forms.TelInput(attrs={'class': INPUT_CLASS}),
        }


class FinancialAidForm(forms.ModelForm):
    class Meta:
        model = DemandeAideFinanciere
        fields = ['nom', 'prenom', 'email', 'telephone', 'montant_souhaite', 'situation']
        labels = {
            'nom': 'Nom',
            'prenom': 'Prénom',
            'email': 'Adresse e-mail',
            'telephone': 'Téléphone',
            'montant_souhaite': 'Montant souhaité (facultatif)',
            'situation': 'Présentez brièvement votre situation',
        }
        widgets = {
            'nom': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'prenom': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'email': forms.EmailInput(attrs={'class': INPUT_CLASS}),
            'telephone': forms.TelInput(attrs={'class': INPUT_CLASS}),
            'montant_souhaite': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': '0', 'step': '0.01'}),
            'situation': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 4}),
        }


class RegistrationIdentityForm(forms.Form):
    first_name = forms.CharField(max_length=150, label='Prénom', widget=forms.TextInput(attrs={
        'class': INPUT_CLASS, 'autocomplete': 'given-name', 'placeholder': 'Votre prénom',
    }))
    last_name = forms.CharField(max_length=150, label='Nom', widget=forms.TextInput(attrs={
        'class': INPUT_CLASS, 'autocomplete': 'family-name', 'placeholder': 'Votre nom',
    }))
    email = forms.EmailField(label='Adresse e-mail', widget=forms.EmailInput(attrs={
        'class': INPUT_CLASS, 'autocomplete': 'email', 'placeholder': 'vous@exemple.com',
    }))

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Un compte utilise déjà cette adresse e-mail.')
        return email


class RegistrationPasswordForm(forms.Form):
    password1 = forms.CharField(label='Mot de passe', strip=False, widget=forms.PasswordInput(attrs={
        'class': INPUT_CLASS, 'autocomplete': 'new-password',
    }))
    password2 = forms.CharField(label='Confirmer le mot de passe', strip=False, widget=forms.PasswordInput(attrs={
        'class': INPUT_CLASS, 'autocomplete': 'new-password',
    }))

    def __init__(self, *args, identity_data=None, **kwargs):
        self.identity_data = identity_data or {}
        super().__init__(*args, **kwargs)

    def clean_password1(self):
        password = self.cleaned_data.get('password1')
        if password:
            user = User(
                first_name=self.identity_data.get('first_name', ''),
                last_name=self.identity_data.get('last_name', ''),
                email=self.identity_data.get('email', ''),
            )
            validate_password(password, user=user)
        return password

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            self.add_error('password2', 'Les deux mots de passe ne correspondent pas.')
        return cleaned_data


class StyledAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Nom d’utilisateur ou adresse e-mail'
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CLASS

    def clean(self):
        username = self.cleaned_data.get('username', '')
        if '@' in username:
            matches = User.objects.filter(email__iexact=username)
            if matches.count() == 1:
                self.cleaned_data['username'] = matches.get().get_username()
        return super().clean()


class StyledPasswordResetForm(PasswordResetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].widget.attrs['class'] = INPUT_CLASS


class StyledSetPasswordForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CLASS


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['bio', 'telephone', 'ville', 'photo', 'linkedin', 'github', 'portfolio', 'visible']
        labels = {
            'bio': 'À propos de moi', 'telephone': 'Téléphone', 'ville': 'Ville',
            'photo': 'Photo de profil', 'linkedin': 'LinkedIn', 'github': 'GitHub',
            'portfolio': 'Portfolio', 'visible': 'Afficher mon profil dans la communauté',
        }

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo and photo.size > 5 * 1024 * 1024:
            raise forms.ValidationError('La photo de profil ne peut dépasser 5 Mo.')
        return photo
        widgets = {
            'bio': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 4}),
            'telephone': forms.TelInput(attrs={'class': INPUT_CLASS}),
            'ville': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'photo': forms.ClearableFileInput(attrs={'class': 'file-input file-input-bordered w-full'}),
            'linkedin': forms.URLInput(attrs={'class': INPUT_CLASS}),
            'github': forms.URLInput(attrs={'class': INPUT_CLASS}),
            'portfolio': forms.URLInput(attrs={'class': INPUT_CLASS}),
        }


class AccountNameForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        labels = {'first_name': 'Prénom', 'last_name': 'Nom', 'email': 'Adresse e-mail'}
        widgets = {
            'first_name': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'last_name': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'email': forms.EmailInput(attrs={'class': INPUT_CLASS}),
        }

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.exclude(pk=self.instance.pk).filter(email__iexact=email).exists():
            raise forms.ValidationError('Un autre compte utilise déjà cette adresse e-mail.')
        return email


class BusinessProfileForm(forms.ModelForm):
    class Meta:
        model = BusinessProfile
        fields = ['nom', 'description', 'logo', 'email', 'telephone', 'ville', 'site_web']
        labels = {
            'nom': 'Nom de l’organisation', 'description': 'Présentation', 'logo': 'Logo',
            'email': 'Adresse professionnelle', 'telephone': 'Téléphone', 'ville': 'Ville', 'site_web': 'Site web',
        }
        widgets = {
            'nom': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'description': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 4}),
            'logo': forms.ClearableFileInput(attrs={'class': 'file-input file-input-bordered w-full'}),
            'email': forms.EmailInput(attrs={'class': INPUT_CLASS}),
            'telephone': forms.TelInput(attrs={'class': INPUT_CLASS}),
            'ville': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'site_web': forms.URLInput(attrs={'class': INPUT_CLASS}),
        }

    def clean_logo(self):
        logo = self.cleaned_data.get('logo')
        if logo and logo.size > 5 * 1024 * 1024:
            raise forms.ValidationError('Le logo ne peut dépasser 5 Mo.')
        return logo


class JobPostingForm(forms.ModelForm):
    class Meta:
        model = JobPosting
        fields = ['titre', 'description', 'type_offre', 'domaine', 'lieu', 'format_emploi', 'date_limite']
        labels = {
            'titre': 'Intitulé du poste', 'description': 'Description et profil recherché',
            'type_offre': 'Type de contrat', 'domaine': 'Domaine', 'lieu': 'Ville ou lieu',
            'format_emploi': 'Format', 'date_limite': 'Date limite de candidature',
        }
        widgets = {
            'titre': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'description': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 6}),
            'type_offre': forms.Select(attrs={'class': SELECT_CLASS}),
            'domaine': forms.Select(attrs={'class': SELECT_CLASS}),
            'lieu': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'format_emploi': forms.Select(attrs={'class': SELECT_CLASS}),
            'date_limite': forms.DateInput(attrs={'class': INPUT_CLASS, 'type': 'date'}),
        }


class JobApplicationForm(forms.ModelForm):
    cv = forms.FileField(
        label='CV (PDF, 5 Mo maximum)',
        validators=[
            FileExtensionValidator(allowed_extensions=['pdf']),
            validate_pdf_signature,
            MaxFileSizeValidator(5 * 1024 * 1024),
        ],
        widget=forms.ClearableFileInput(attrs={'class': 'file-input file-input-bordered w-full'}),
    )

    class Meta:
        model = JobApplication
        fields = ['motivation', 'cv']
        labels = {'motivation': 'Message de motivation'}
        widgets = {'motivation': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 5})}

    def clean_cv(self):
        cv = self.cleaned_data.get('cv')
        if cv and cv.size > 5 * 1024 * 1024:
            raise forms.ValidationError('Le CV doit faire 5 Mo ou moins.')
        return cv


class TrainerApplicationForm(forms.ModelForm):
    class Meta:
        model = TrainerProfile
        fields = ['titre', 'experience', 'certifications', 'domaines']
        labels = {
            'titre': 'Titre professionnel',
            'experience': 'Expérience',
            'certifications': 'Certifications',
            'domaines': 'Domaines d’expertise',
        }
        widgets = {
            'titre': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'experience': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 5}),
            'certifications': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 4}),
            'domaines': forms.TextInput(attrs={'class': INPUT_CLASS}),
        }


class CourseManagementForm(forms.ModelForm):
    video = forms.FileField(required=False, widget=forms.ClearableFileInput(attrs={
        'class': 'file-input file-input-bordered w-full',
    }), validators=[
        FileExtensionValidator(allowed_extensions=['mp4', 'webm', 'mov']),
        MaxFileSizeValidator(100 * 1024 * 1024),
    ])
    audio = forms.FileField(required=False, widget=forms.ClearableFileInput(attrs={
        'class': 'file-input file-input-bordered w-full',
    }), validators=[
        FileExtensionValidator(allowed_extensions=['mp3', 'm4a', 'ogg', 'wav']),
        MaxFileSizeValidator(50 * 1024 * 1024),
    ])
    pdf = forms.FileField(required=False, validators=[
        FileExtensionValidator(allowed_extensions=['pdf']),
        validate_pdf_signature,
        MaxFileSizeValidator(10 * 1024 * 1024),
    ], widget=forms.ClearableFileInput(attrs={
        'class': 'file-input file-input-bordered w-full',
    }))

    class Meta:
        model = Cours
        fields = [
            'titre', 'description', 'type_contenu', 'video', 'audio', 'pdf',
            'miniature', 'duree', 'nb_pages', 'categorie',
        ]
        widgets = {
            'titre': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'description': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 6}),
            'type_contenu': forms.Select(attrs={'class': SELECT_CLASS}),
            'miniature': forms.ClearableFileInput(attrs={'class': 'file-input file-input-bordered w-full'}),
            'duree': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'mm:ss'}),
            'nb_pages': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': '1'}),
            'categorie': forms.Select(attrs={'class': SELECT_CLASS}),
        }

    def clean(self):
        cleaned_data = super().clean()
        type_contenu = cleaned_data.get('type_contenu')
        if type_contenu and not cleaned_data.get(type_contenu):
            self.add_error(type_contenu, 'Ajoutez le fichier correspondant au type de contenu choisi.')
        return cleaned_data

    def clean_miniature(self):
        miniature = self.cleaned_data.get('miniature')
        if miniature and miniature.size > 5 * 1024 * 1024:
            raise forms.ValidationError('La miniature ne peut dépasser 5 Mo.')
        return miniature


class ProjectSubmissionForm(forms.ModelForm):
    class Meta:
        model = ProjectSubmission
        fields = ['formation', 'titre', 'description', 'competences', 'url_demo', 'url_code', 'image']
        labels = {
            'formation': 'Formation liée (facultatif)', 'titre': 'Nom du projet', 'description': 'Présentation du projet',
            'competences': 'Compétences utilisées', 'url_demo': 'Lien vers la démonstration',
            'url_code': 'Lien vers le code', 'image': 'Image de couverture',
        }
        widgets = {
            'formation': forms.Select(attrs={'class': SELECT_CLASS}),
            'titre': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'description': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 5}),
            'competences': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ex. Django, UX, stratégie digitale'}),
            'url_demo': forms.URLInput(attrs={'class': INPUT_CLASS}),
            'url_code': forms.URLInput(attrs={'class': INPUT_CLASS}),
            'image': forms.ClearableFileInput(attrs={'class': 'file-input file-input-bordered w-full'}),
        }

    def __init__(self, *args, auteur=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['formation'].queryset = Information.objects.filter(status=1)
        self.fields['formation'].required = False


class CommunityPostForm(forms.ModelForm):
    class Meta:
        model = CommunityPost
        fields = ['contenu']
        labels = {'contenu': 'Votre message'}
        widgets = {'contenu': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 3, 'placeholder': 'Partager une question, une idée ou une ressource…'})}


class SocialPostForm(forms.ModelForm):
    class Meta:
        model = SocialPost
        fields = ['contenu', 'image']
        labels = {'contenu': 'Que souhaitez-vous partager ?', 'image': 'Ajouter une photo'}
        widgets = {
            'contenu': forms.Textarea(attrs={
                'class': 'textarea min-h-11 w-full resize-none rounded-2xl border-0 bg-base-200/70 focus:outline-none focus:ring-2 focus:ring-primary/40',
                'rows': 1,
                'maxlength': 4000,
                'placeholder': 'Partagez une idée, une réussite ou une question…',
                'data-autosize': 'true',
            }),
            'image': forms.ClearableFileInput(attrs={'class': 'file-input file-input-bordered w-full'}),
        }

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image and image.size > 5 * 1024 * 1024:
            raise forms.ValidationError('La photo doit faire 5 Mo ou moins.')
        return image


class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ['content']
        labels = {'content': 'Votre message'}
        widgets = {'content': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 3, 'maxlength': 4000, 'placeholder': 'Écrivez votre message…'})}


class CourseEvaluationForm(forms.ModelForm):
    class Meta:
        model = CourseEvaluation
        fields = ['note', 'commentaire']
        labels = {'note': 'Votre note', 'commentaire': 'Votre avis (facultatif)'}
        widgets = {
            'note': forms.Select(attrs={'class': SELECT_CLASS}),
            'commentaire': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 3}),
        }


class LearnerProjectRequestForm(forms.ModelForm):
    class Meta:
        model = LearnerProjectRequest
        fields = ['nom', 'organisation', 'email', 'telephone', 'type_projet', 'description']
        labels = {
            'nom': 'Votre nom', 'organisation': 'Organisation', 'email': 'Adresse e-mail',
            'telephone': 'Téléphone', 'type_projet': 'Nature du projet', 'description': 'Décrivez le besoin',
        }
        widgets = {
            'nom': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'organisation': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'email': forms.EmailInput(attrs={'class': INPUT_CLASS}),
            'telephone': forms.TelInput(attrs={'class': INPUT_CLASS}),
            'type_projet': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ex. site web, campagne numérique'}),
            'description': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 5}),
        }



















