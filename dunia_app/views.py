import uuid
from io import BytesIO
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

from django.shortcuts import get_object_or_404, render, redirect
from django.templatetags.static import static
from django.urls import reverse
from django.views import generic
from django.db.models import Avg, BooleanField, Case, Count, Exists, F, IntegerField, OuterRef, Prefetch, Q, Value, When
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.http import FileResponse, Http404, JsonResponse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from .models import (
    CANDIDATURE_EMPLOI_STATUTS,
    CANDIDATURE_STATUTS,
    DOMAINES_FORMATION,
    Publication,
    Information,
    Cours,
    TYPE_CONTENU,
    CATEGORIES_COURS,
    Article,
    Comment,
    Candidature,
    CommunityAccessRequest,
    DemandeAideFinanciere,
    SessionReservation,
    SocialPost,
    TrainingSession,
    LearningProgress,
    Community,
    CommunityMembership,
    CommunityPost,
    Conversation,
    Credential,
    CourseEvaluation,
    EventRegistration,
    ImpactMetric,
    Initiative,
    JobPosting,
    JobApplication,
    LearnerProjectRequest,
    LearningGoal,
    ProjectCollaborator,
    Message,
    FeedComment,
    FeedLike,
    FeedShare,
    Friendship,
    Notification,
    Partner,
    ProfessionalEvent,
    ProjectSubmission,
    Campus,
    AnnualReport,
    Testimonial,
    TrainerProfile,
    UserCredential,
    UserProfile,
    BusinessProfile,
    BlogCategory,
    Challenge,
    ChallengeParticipation,
    ChallengePaymentAttempt,
    ChallengeWorkSubmission,
)
from .forms import (
    AccountNameForm,
    BusinessProfileForm,
    CommunityPostForm,
    CourseEvaluationForm,
    ApplicationTrackingForm,
    FinancialAidTrackingForm,
    JobApplicationForm,
    JobPostingForm,
    LearnerProjectRequestForm,
    MessageForm,
    CandidatureForm,
    ProjectSubmissionForm,
    RegistrationIdentityForm,
    RegistrationPasswordForm,
    CatalogFilterForm,
    UserProfileForm,
    ContactForm,
    FinancialAidForm,
    OrientationQuizForm,
    SessionReservationForm,
    SocialPostForm,
    CourseManagementForm,
    LearningGoalForm,
    ProjectCollaboratorInviteForm,
    TrainerApplicationForm,
)
from .services import (
    has_approved_role,
    record_audit,
    request_role,
    review_challenge_payment,
    submit_challenge_payment,
    submit_challenge_work,
    update_business_profile,
    transition_job_application,
    transition_candidature,
    review_community_access_request,
    invite_project_collaborators,
    respond_to_project_invitation,
)
from .throttling import rate_limit


@rate_limit('contact', limit=5, window=3600, include_user=False)
@require_POST
def contact_create(request):
    form = ContactForm(request.POST)
    if form.is_valid():
        form.save()
        messages.success(request, "Merci ! Vos informations ont bien été enregistrées.")
    else:
        messages.error(request, "Merci de vérifier les champs du formulaire.")
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or '/'
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        next_url = '/'
    return redirect(next_url)


def inscription(request):
    if request.user.is_authenticated:
        return redirect('tableau_bord')
    identity_key = 'inscription_identite'
    identity_data = request.session.get(identity_key)
    password_step = request.GET.get('etape') == 'mot-de-passe' or request.POST.get('etape') == 'mot-de-passe'

    if password_step and not identity_data:
        messages.info(request, 'Commencez par renseigner vos informations de base.')
        return redirect('inscription')

    if request.method == 'POST' and not password_step:
        form = RegistrationIdentityForm(request.POST)
        if form.is_valid():
            request.session[identity_key] = {
                'first_name': form.cleaned_data['first_name'],
                'last_name': form.cleaned_data['last_name'],
                'email': form.cleaned_data['email'],
            }
            return redirect(f"{reverse('inscription')}?etape=mot-de-passe")
        return render(request, 'dunia_app/inscription.html', {'form': form, 'password_step': False})

    if password_step:
        form = RegistrationPasswordForm(
            request.POST or None,
            identity_data=identity_data,
        )
        if request.method == 'POST' and form.is_valid():
            with transaction.atomic():
                user = User.objects.create_user(
                    username=f'dunia-{uuid.uuid4().hex}',
                    email=identity_data['email'],
                    first_name=identity_data['first_name'],
                    last_name=identity_data['last_name'],
                    password=form.cleaned_data['password1'],
                )
                UserProfile.objects.create(user=user, role='apprenant')
            request.session.pop(identity_key, None)
            login(request, user)
            messages.success(request, 'Votre compte apprenant est prêt. Bienvenue sur Dunia !')
            return redirect('tableau_bord')
        return render(request, 'dunia_app/inscription.html', {
            'form': form,
            'password_step': True,
            'identity_data': identity_data,
        })

    form = RegistrationIdentityForm()
    return render(request, 'dunia_app/inscription.html', {'form': form, 'password_step': False})


@login_required
def profil_modifier(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    account_form = AccountNameForm(request.POST or None, instance=request.user, prefix='compte')
    profile_form = UserProfileForm(request.POST or None, request.FILES or None, instance=profile, prefix='profil')
    if request.method == 'POST' and account_form.is_valid() and profile_form.is_valid():
        account_form.save()
        profile_form.save()
        messages.success(request, 'Votre profil a été mis à jour.')
        return redirect('tableau_bord')
    return render(request, 'dunia_app/profil_form.html', {
        'account_form': account_form,
        'profile_form': profile_form,
    })


def profil_public(request, username):
    user = get_object_or_404(User, username=username, is_active=True)
    is_self = request.user.is_authenticated and user.pk == request.user.pk
    if is_self:
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={'visible': False},
        )
    else:
        profile = get_object_or_404(
            UserProfile.objects.select_related('user'),
            user=user,
        )
    if not profile.visible and not is_self:
        raise Http404

    relation = None
    relation_state = ''
    friends_count = 0
    if request.user.is_authenticated and not is_self:
        relation = Friendship.objects.filter(
            Q(person_one=request.user, person_two=profile.user)
            | Q(person_one=profile.user, person_two=request.user)
        ).first()
        if relation:
            if relation.status == Friendship.ACCEPTED:
                relation_state = 'amis'
            elif relation.requested_by_id == request.user.pk:
                relation_state = 'envoyee'
            else:
                relation_state = 'recue'

    friends_count = Friendship.objects.filter(status=Friendship.ACCEPTED).filter(
        Q(person_one=profile.user) | Q(person_two=profile.user)
    ).count()
    friends = []
    accepted_friendships = Friendship.objects.filter(status=Friendship.ACCEPTED).filter(
        Q(person_one=profile.user) | Q(person_two=profile.user)
    ).select_related('person_one__profil_dunia', 'person_two__profil_dunia')[:9]
    for friendship in accepted_friendships:
        friend = friendship.other_user(profile.user)
        if hasattr(friend, 'profil_dunia') and friend.profil_dunia.visible:
            friends.append(friend)
    posts = SocialPost.objects.filter(auteur=profile.user, status=1).select_related(
        'auteur', 'auteur__profil_dunia'
    ).annotate(
        likes_count=Count('feed_likes', distinct=True),
        comments_count=Count('feed_comments', distinct=True),
        shares_count=Count('feed_shares', distinct=True),
    ).order_by('-date_creation')[:5]
    for post in posts:
        post.is_liked = request.user.is_authenticated and FeedLike.objects.filter(post=post, user=request.user).exists()
        post.recent_comments = list(post.feed_comments.select_related('auteur', 'auteur__profil_dunia').order_by('-date_creation')[:3])
    photos = SocialPost.objects.filter(auteur=profile.user, status=1).exclude(image='').exclude(image__isnull=True).order_by('-date_creation')[:6]

    return render(request, 'dunia_app/profil_public.html', {
        'profile': profile,
        'is_self': is_self,
        'relation': relation,
        'relation_state': relation_state,
        'friends_count': friends_count,
        'friends': friends,
        'photos': photos,
        'posts': posts,
    })


def amis(request):
    if not request.user.is_authenticated:
        return render(request, 'dunia_app/amis.html', {
            'is_guest': True,
            'amis': [],
            'demandes_recues': [],
            'demandes_envoyees': [],
            'suggestions': [],
        })

    relations = Friendship.objects.filter(
        Q(person_one=request.user) | Q(person_two=request.user)
    ).select_related(
        'person_one', 'person_two', 'person_one__profil_dunia', 'person_two__profil_dunia', 'requested_by'
    )
    accepted = [relation for relation in relations if relation.status == Friendship.ACCEPTED]
    received = [
        relation for relation in relations
        if relation.status == Friendship.PENDING and relation.requested_by_id != request.user.pk
    ]
    sent = [
        relation for relation in relations
        if relation.status == Friendship.PENDING and relation.requested_by_id == request.user.pk
    ]
    for relation in [*accepted, *received, *sent]:
        relation.autre = relation.other_user(request.user)
        if relation.status == Friendship.ACCEPTED:
            relation.autre.friendship = relation
    related_ids = {request.user.pk}
    related_ids.update(relation.other_user(request.user).pk for relation in relations)
    suggestions = UserProfile.objects.filter(
        visible=True,
        user__is_active=True,
    ).exclude(user_id__in=related_ids).select_related('user').order_by('user__first_name', 'user__username')[:12]
    return render(request, 'dunia_app/amis.html', {
        'is_guest': False,
        'friendships': accepted,
        'amis': [relation.autre for relation in accepted],
        'demandes_recues': received,
        'demandes_envoyees': sent,
        'suggestions': suggestions,
    })


@login_required
@require_POST
def demande_ami(request, user_id):
    cible = get_object_or_404(User, pk=user_id, is_active=True)
    if cible.pk == request.user.pk:
        messages.error(request, 'Vous ne pouvez pas vous ajouter vous-même.')
        return redirect('amis')
    get_object_or_404(UserProfile, user=cible, visible=True)
    first, second = sorted((request.user, cible), key=lambda user: user.pk)

    with transaction.atomic():
        relation = Friendship.objects.select_for_update().filter(person_one=first, person_two=second).first()
        if relation is None:
            Friendship.objects.create(person_one=first, person_two=second, requested_by=request.user)
            Notification.objects.create(
                destinataire=cible,
                type_notification='communaute',
                titre='Nouvelle demande d’amitié',
                message=f"{request.user.get_full_name() or request.user.username} souhaite rejoindre votre réseau.",
                url=reverse('amis'),
            )
            messages.success(request, 'Votre demande d’amitié a été envoyée.')
        elif relation.status == Friendship.ACCEPTED:
            messages.info(request, 'Vous êtes déjà amis.')
        elif relation.requested_by_id == request.user.pk:
            messages.info(request, 'Votre demande est déjà en attente.')
        else:
            relation.status = Friendship.ACCEPTED
            relation.date_acceptation = timezone.now()
            relation.save(update_fields=['status', 'date_acceptation'])
            Notification.objects.create(
                destinataire=relation.requested_by,
                type_notification='communaute',
                titre='Demande d’amitié acceptée',
                message=f"{request.user.get_full_name() or request.user.username} a accepté votre demande.",
                url=reverse('profil_public', args=[request.user.username]),
            )
            messages.success(request, 'Vous êtes maintenant amis.')

    return redirect('profil_public', username=cible.username)


@login_required
@require_POST
def demande_ami_action(request, friendship_id, action):
    relation = get_object_or_404(
        Friendship.objects.filter(Q(person_one=request.user) | Q(person_two=request.user)).select_related('requested_by'),
        pk=friendship_id,
    )
    is_requester = relation.requested_by_id == request.user.pk

    if action == 'accepter' and relation.status == Friendship.PENDING and not is_requester:
        relation.status = Friendship.ACCEPTED
        relation.date_acceptation = timezone.now()
        relation.save(update_fields=['status', 'date_acceptation'])
        Notification.objects.create(
            destinataire=relation.requested_by,
            type_notification='communaute',
            titre='Demande d’amitié acceptée',
            message=f"{request.user.get_full_name() or request.user.username} a accepté votre demande.",
            url=reverse('profil_public', args=[request.user.username]),
        )
        messages.success(request, 'Demande acceptée. Vous êtes maintenant amis.')
    elif action == 'refuser' and relation.status == Friendship.PENDING and not is_requester:
        relation.delete()
        messages.info(request, 'La demande a été refusée.')
    elif action == 'annuler' and relation.status == Friendship.PENDING and is_requester:
        relation.delete()
        messages.info(request, 'Votre demande a été annulée.')
    elif action == 'retirer' and relation.status == Friendship.ACCEPTED:
        relation.delete()
        messages.success(request, 'Cette personne a été retirée de vos amis.')
    else:
        raise Http404
    return redirect('amis')


@login_required
def tableau_bord(request):
    return render(request, 'dunia_app/tableau_bord.html', _tableau_bord_context(request))


def _tableau_bord_context(request, *, objectif_form=None):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    projets = list(
        ProjectSubmission.objects.filter(
            Q(auteur=request.user)
            | Q(collaborations__utilisateur=request.user, collaborations__statut='acceptee')
        ).distinct().select_related('auteur', 'formation').prefetch_related(
            'collaborations__utilisateur'
        ).order_by('-date_creation')[:6]
    )
    for projet in projets:
        if projet.auteur_id == request.user.pk:
            projet.invite_form = ProjectCollaboratorInviteForm(user=request.user, project=projet)
    context = {
        'profile': profile,
        'formations_suivies': Cours.objects.filter(progressions__user=request.user).distinct().order_by('-date_pub')[:6],
        'candidatures_formation': request.user.candidatures_formation.select_related('formation').order_by('-date_creation')[:5],
        'candidatures_emploi': request.user.candidatures_emploi.select_related('offre__entreprise').order_by('-date_creation')[:5],
        'total_candidatures': request.user.candidatures_formation.count() + request.user.candidatures_emploi.count(),
        'projets': projets,
        'invitations_projet': ProjectCollaborator.objects.filter(
            utilisateur=request.user,
            statut='en_attente',
        ).select_related('projet__auteur').order_by('-date_invitation')[:10],
        'objectifs': request.user.objectifs_apprentissage.all()[:10],
        'objectif_form': objectif_form or LearningGoalForm(),
        'certifications': UserCredential.objects.filter(utilisateur=request.user).select_related('certification'),
        'inscriptions_evenements': EventRegistration.objects.filter(
            participant=request.user,
            annulee_le__isnull=True,
            evenement__status=1,
            evenement__date_debut__gte=timezone.now(),
        ).select_related('evenement').order_by('evenement__date_debut')[:5],
        'communautes': request.user.communautes.filter(status=1)[:6],
        'notifications': request.user.notifications_dunia.all()[:5],
        'conversations_count': request.user.conversations_as_one.count() + request.user.conversations_as_two.count(),
        'demandes_role': request.user.demandes_role.all(),
        'profil_formateur': getattr(request.user, 'profil_formateur', None),
    }
    return context


@login_required
@require_POST
@rate_limit('learning_goal_create', limit=10, window=3600)
def learning_goal_create(request):
    form = LearningGoalForm(request.POST)
    if form.is_valid():
        objectif = form.save(commit=False)
        objectif.user = request.user
        objectif.save()
        messages.success(request, 'Votre objectif personnel a été ajouté.')
        return redirect(f"{reverse('tableau_bord')}#objectifs")
    return render(request, 'dunia_app/tableau_bord.html', _tableau_bord_context(request, objectif_form=form))


@login_required
@require_http_methods(['GET', 'POST'])
@rate_limit('learning_goal_update', limit=20, window=3600)
def learning_goal_edit(request, goal_id):
    objectif = get_object_or_404(LearningGoal, pk=goal_id, user=request.user)
    form = LearningGoalForm(request.POST or None, instance=objectif)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Votre objectif a été mis à jour.')
        return redirect(f"{reverse('tableau_bord')}#objectifs")
    return render(request, 'dunia_app/learning_goal_form.html', {
        'form': form,
        'objectif': objectif,
    })


@login_required
@require_POST
def learning_goal_action(request, goal_id, action):
    objectif = get_object_or_404(LearningGoal, pk=goal_id, user=request.user)
    if action == 'supprimer':
        objectif.delete()
        messages.success(request, 'Votre objectif a été supprimé.')
    elif action in {'atteindre', 'reprendre'}:
        objectif.statut = 'atteint' if action == 'atteindre' else 'en_cours'
        objectif.date_atteinte = timezone.now() if action == 'atteindre' else None
        objectif.save(update_fields=['statut', 'date_atteinte', 'date_modification'])
        messages.success(
            request,
            'Objectif marqué comme atteint.' if action == 'atteindre' else 'Objectif remis en cours.',
        )
    else:
        raise Http404
    return redirect(f"{reverse('tableau_bord')}#objectifs")


@login_required
def mes_formations(request):
    progressions = request.user.learning_progress.select_related('cours').order_by('-started_at')
    return render(request, 'dunia_app/mes_formations.html', {'progressions': progressions})


@login_required
@require_POST
def cours_demarrer(request, slug):
    cours = get_object_or_404(Cours, slug=slug, status=1)
    LearningProgress.objects.get_or_create(user=request.user, cours=cours)
    messages.success(request, 'Le cours a été ajouté à votre espace d’apprentissage.')
    return redirect('cours_detail', slug=cours.slug)


@login_required
@require_POST
def cours_terminer(request, slug):
    cours = get_object_or_404(Cours, slug=slug, status=1)
    progression, _ = LearningProgress.objects.get_or_create(user=request.user, cours=cours)
    if not progression.is_completed:
        progression.is_completed = True
        progression.completed_at = timezone.now()
        progression.save(update_fields=['is_completed', 'completed_at'])
        for credential in cours.certifications_requises.filter(status=1):
            cours_requis = credential.cours.count()
            cours_termines = LearningProgress.objects.filter(
                user=request.user,
                is_completed=True,
                cours__certifications_requises=credential,
            ).count()
            if cours_requis and cours_termines == cours_requis:
                UserCredential.objects.get_or_create(utilisateur=request.user, certification=credential)
        messages.success(request, 'Bravo, ce cours est marqué comme terminé !')
    return redirect('cours_detail', slug=cours.slug)


@rate_limit('comment_moderation', limit=10, window=600, include_user=False)
@require_POST
def comment_create(request):
    nom = request.POST.get('nom', '').strip()
    message = request.POST.get('message', '').strip()
    type_cible = request.POST.get('type_cible')
    object_id = request.POST.get('object_id')

    if nom and message and type_cible and object_id:
        comment = Comment(nom=nom, message=message)
        if type_cible == 'publication':
            comment.publication = get_object_or_404(Publication, pk=object_id, status=1)
        elif type_cible == 'article':
            comment.article = get_object_or_404(Article, pk=object_id, status=1)

        try:
            comment.full_clean()
            comment.save()
            messages.success(request, "Merci ! Votre commentaire est en attente de validation.")
        except DjangoValidationError:
            messages.error(request, "Commentaire invalide.")
    else:
        messages.error(request, "Merci de remplir votre nom et votre message.")

    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or '/'
    if not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = '/'
    return redirect(next_url)


class PublicationList(generic.ListView):
    template_name = "dunia_app/index.html"
    context_object_name = 'posts'
    paginate_by = 10

    def get_queryset(self):
        queryset = SocialPost.objects.filter(status=1).select_related(
            'auteur', 'auteur__profil_dunia'
        ).annotate(
            likes_count=Count('feed_likes', distinct=True),
            comments_count=Count('feed_comments', distinct=True),
            shares_count=Count('feed_shares', distinct=True),
        ).order_by('-date_creation', '-pk')
        search_term = self.request.GET.get('q', '').strip()
        if search_term:
            queryset = queryset.filter(
                Q(contenu__icontains=search_term)
                | Q(auteur__username__icontains=search_term)
                | Q(auteur__first_name__icontains=search_term)
                | Q(auteur__last_name__icontains=search_term)
            )
        if self.request.user.is_authenticated:
            queryset = queryset.annotate(is_liked=Exists(
                FeedLike.objects.filter(post=OuterRef('pk'), user=self.request.user)
            ))
        else:
            queryset = queryset.annotate(is_liked=Value(False, output_field=BooleanField()))
        return queryset.prefetch_related(Prefetch(
            'feed_comments',
            queryset=FeedComment.objects.select_related('auteur', 'auteur__profil_dunia').order_by('-date_creation')[:3],
            to_attr='recent_comments',
        ))

    def get_template_names(self):
        if self.request.GET.get('feed_fragment') == '1':
            return ['dunia_app/partials/feed_page.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['post_form'] = SocialPostForm() if self.request.user.is_authenticated else None
        context['publication_list'] = []
        context['actualites'] = []
        context['search_term'] = self.request.GET.get('q', '').strip()
        if context['page_obj'].number == 1:
            actualites = Publication.objects.filter(status=1).select_related(
                'auteur', 'auteur__profil_dunia'
            ).annotate(
                likes_count=Count('feed_likes', distinct=True),
                feed_comments_count=Count('feed_comments', distinct=True),
                approved_comments_count=Count('commentaires', filter=Q(commentaires__status=1), distinct=True),
                shares_count=Count('feed_shares', distinct=True),
            )
            if context['search_term']:
                actualites = actualites.filter(
                    Q(titre__icontains=context['search_term'])
                    | Q(contexte__icontains=context['search_term'])
                    | Q(auteur__username__icontains=context['search_term'])
                    | Q(auteur__first_name__icontains=context['search_term'])
                    | Q(auteur__last_name__icontains=context['search_term'])
                )
            if self.request.user.is_authenticated:
                actualites = actualites.annotate(is_liked=Exists(
                    FeedLike.objects.filter(publication=OuterRef('pk'), user=self.request.user)
                ))
            else:
                actualites = actualites.annotate(is_liked=Value(False, output_field=BooleanField()))
            actualites = list(actualites.prefetch_related(Prefetch(
                'feed_comments',
                queryset=FeedComment.objects.select_related('auteur', 'auteur__profil_dunia').order_by('-date_creation')[:3],
                to_attr='recent_comments',
            ), Prefetch(
                'commentaires',
                queryset=Comment.objects.filter(status=1).order_by('-date_creation')[:3],
                to_attr='recent_legacy_comments',
            )).order_by('-date_actuel', '-pk'))
            for publication in actualites:
                publication.total_comments_count = publication.feed_comments_count + publication.approved_comments_count
            context['actualites'] = actualites
            context['publication_list'] = actualites
        context['formations'] = Information.objects.filter(status=1).order_by('-date_pub')[:3]
        context['evenements'] = ProfessionalEvent.objects.filter(
            status=1,
            date_debut__gte=timezone.now(),
        ).order_by('date_debut')[:3]
        return context


@login_required
@rate_limit('social_post', limit=30, window=60)
@require_POST
def social_post_create(request):
    form = SocialPostForm(request.POST, request.FILES)
    if form.is_valid():
        post = form.save(commit=False)
        post.auteur = request.user
        post.status = 1
        post.save()
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'Votre publication a été ajoutée au fil.'})
        messages.success(request, 'Votre publication a été ajoutée au fil.')
    else:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'message': 'Vérifiez votre message et choisissez une image de 5 Mo maximum.',
                'errors': form.errors.get_json_data(),
            }, status=400)
        messages.error(request, 'Vérifiez votre message et choisissez une image de 5 Mo maximum.')
    return redirect('home')


def _feed_redirect(request, anchor=''):
    next_url = request.POST.get('next', '')
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        if anchor:
            next_url = f'{next_url.split("#", 1)[0]}#{anchor}'
        return redirect(next_url)
    return redirect(f'{reverse("home")}#{anchor}' if anchor else 'home')


@login_required
@require_POST
def feed_toggle_like(request, item_type, item_id):
    if item_type == 'post':
        item = get_object_or_404(SocialPost, pk=item_id, status=1)
        filters = {'user': request.user, 'post': item}
        count_filters = {'post': item}
    elif item_type == 'publication':
        item = get_object_or_404(Publication, pk=item_id, status=1)
        filters = {'user': request.user, 'publication': item}
        count_filters = {'publication': item}
    else:
        raise Http404

    like = FeedLike.objects.filter(**filters).first()
    if like:
        like.delete()
        is_liked = False
    else:
        FeedLike.objects.get_or_create(**filters)
        is_liked = True
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'is_liked': is_liked,
            'likes_count': FeedLike.objects.filter(**count_filters).count(),
        })
    return _feed_redirect(request, f'{item_type}-{item.pk}')


@login_required
@rate_limit('feed_comment', limit=30, window=60)
@require_POST
def feed_comment_create(request, item_type, item_id):
    contenu = request.POST.get('contenu', '').strip()
    if not contenu or len(contenu) > 2000:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'message': 'Un commentaire doit contenir entre 1 et 2 000 caractères.'}, status=400)
        messages.error(request, 'Un commentaire doit contenir entre 1 et 2 000 caractères.')
        return _feed_redirect(request, f'{item_type}-{item_id}-comments')

    comment = FeedComment(auteur=request.user, contenu=contenu)
    if item_type == 'post':
        comment.post = get_object_or_404(SocialPost, pk=item_id, status=1)
    elif item_type == 'publication':
        comment.publication = get_object_or_404(Publication, pk=item_id, status=1)
    else:
        raise Http404
    comment.save()
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        comment_count = FeedComment.objects.filter(
            post=comment.post,
        ).count() if comment.post_id else FeedComment.objects.filter(
            publication=comment.publication,
        ).count()
        if comment.publication_id:
            comment_count += Comment.objects.filter(publication=comment.publication, status=1).count()
        profile = getattr(comment.auteur, 'profil_dunia', None)
        avatar_url = profile.photo.url if profile and profile.photo else static('src/logo.webp')
        return JsonResponse({
            'comment_count': comment_count,
            'comment': {
                'author': comment.auteur.get_full_name() or comment.auteur.username,
                'author_url': reverse('profil_public', args=[comment.auteur.username]),
                'avatar_url': avatar_url,
                'content': comment.contenu,
                'created_at': timezone.localtime(comment.date_creation).strftime('%d/%m/%Y · %H:%M'),
            },
        })
    return _feed_redirect(request, f'{item_type}-{item_id}-comments')


@require_POST
def feed_record_share(request, item_type, item_id):
    if item_type == 'post':
        item = get_object_or_404(SocialPost, pk=item_id, status=1)
        share_target = {'post': item}
    elif item_type == 'publication':
        item = get_object_or_404(Publication, pk=item_id, status=1)
        share_target = {'publication': item}
    else:
        raise Http404

    FeedShare.objects.create(
        user=request.user if request.user.is_authenticated else None,
        **share_target,
    )
    return JsonResponse({'shares_count': item.feed_shares.count()})


def social_post_detail(request, post_id):
    post = get_object_or_404(
        SocialPost.objects.filter(status=1)
        .select_related('auteur', 'auteur__profil_dunia')
        .annotate(
            likes_count=Count('feed_likes', distinct=True),
            comments_count=Count('feed_comments', distinct=True),
            shares_count=Count('feed_shares', distinct=True),
        )
        .prefetch_related(Prefetch(
            'feed_comments',
            queryset=FeedComment.objects.select_related('auteur', 'auteur__profil_dunia').order_by('-date_creation')[:20],
            to_attr='recent_comments',
        )),
        pk=post_id,
    )
    post.is_liked = request.user.is_authenticated and FeedLike.objects.filter(post=post, user=request.user).exists()
    return render(request, 'dunia_app/social_post_detail.html', {'post': post})

class DetailView(generic.DetailView):
    model = Publication
    template_name = "dunia_app/detail.html"

    def get_queryset(self):
        return Publication.objects.filter(status=1).select_related('auteur', 'auteur__profil_dunia')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['comments'] = self.object.commentaires.filter(status=1)
        post = self.object
        post.recent_comments = list(post.feed_comments.select_related(
            'auteur', 'auteur__profil_dunia'
        ).order_by('-date_creation')[:3])
        post.recent_legacy_comments = list(context['comments'].order_by('-date_creation')[:3])
        post.likes_count = post.feed_likes.count()
        post.comments_count = post.feed_comments.count()
        post.shares_count = post.feed_shares.count()
        post.total_comments_count = post.comments_count + context['comments'].count()
        post.is_liked = self.request.user.is_authenticated and post.feed_likes.filter(user=self.request.user).exists()
        context['publication'] = post
        context['likes_count'] = post.likes_count
        context['is_liked'] = post.is_liked
        context['shares_count'] = post.shares_count
        return context


class InformationList(generic.ListView):
    template_name = "dunia_app/formation.html"
    context_object_name = "information_list"
    paginate_by = 10

    def get_queryset(self):
        sessions_a_venir = TrainingSession.objects.filter(
            status=1,
            date_debut__gte=timezone.localdate(),
        ).order_by('date_debut')
        queryset = Information.objects.filter(status=1).prefetch_related(
            Prefetch('sessions', queryset=sessions_a_venir, to_attr='sessions_a_venir'),
        )
        self.filter_form = CatalogFilterForm(self.request.GET)
        if self.filter_form.is_valid():
            filters = self.filter_form.cleaned_data
            if filters['q']:
                queryset = queryset.filter(Q(titre__icontains=filters['q']) | Q(contenue__icontains=filters['q']))
            for field in ('type_programme', 'domaine', 'niveau', 'format_formation'):
                if filters[field]:
                    queryset = queryset.filter(**{field: filters[field]})
            if filters['lieu']:
                queryset = queryset.filter(lieu__icontains=filters['lieu'])
            if filters['duree_max']:
                queryset = queryset.filter(heures__lte=filters['duree_max'])
        return queryset.order_by('-date_pub')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = self.filter_form
        context['sessions_a_venir'] = TrainingSession.objects.filter(
            status=1,
            date_debut__gte=timezone.localdate(),
            type_session='cohorte',
        ).select_related('formation').order_by('date_debut')[:6]
        return context


class InformationDetail(generic.DetailView):
    model = Information
    template_name = "dunia_app/info_detail.html"

    def get_queryset(self):
        return Information.objects.filter(status=1).prefetch_related('sessions')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sessions'] = self.object.sessions.filter(
            status=1,
            date_debut__gte=timezone.localdate(),
        ).order_by('date_debut')
        context['faqs'] = [
            *self.object.questions_frequentes.filter(status=1).values('question', 'reponse'),
        ]
        if not context['faqs']:
            context['faqs'] = [
                {'question': 'Comment se déroule l’admission ?', 'reponse': 'Envoyez votre candidature en ligne. L’équipe Dunia vous informera des prochaines étapes.'},
                {'question': 'Quel matériel faut-il prévoir ?', 'reponse': 'Le matériel dépend du programme. Les précisions sont communiquées avant le démarrage de la session.'},
                {'question': 'Comment connaître les horaires ?', 'reponse': 'Les horaires et le format sont indiqués pour chaque session disponible.'},
                {'question': 'Puis-je demander une aide financière ?', 'reponse': 'Vous pouvez envoyer une demande d’aide depuis cette page si cette formation le propose.'},
            ]
        return context


def orientation_quiz(request):
    recommendations = Information.objects.none()
    form = OrientationQuizForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        answers = form.cleaned_data
        queryset = Information.objects.filter(status=1)
        if answers['interests']:
            queryset = queryset.filter(domaine__in=answers['interests'])
        if answers['format_formation']:
            queryset = queryset.filter(format_formation__in=[answers['format_formation'], 'a_definir'])
        types_par_objectif = {
            'emploi': ['professionnelle', 'longue'],
            'reconversion': ['longue', 'professionnelle'],
            'decouverte': ['initiation'],
            'competences': ['professionnelle', 'longue'],
        }
        recommendations = queryset.annotate(
            niveau_score=Case(
                When(niveau=answers['niveau'], then=0),
                default=1,
                output_field=IntegerField(),
            ),
            objectif_score=Case(
                When(type_programme__in=types_par_objectif[answers['objectif']], then=0),
                default=1,
                output_field=IntegerField(),
            ),
        ).order_by('niveau_score', 'objectif_score', '-date_pub')[:6]
    return render(request, 'dunia_app/orientation_quiz.html', {
        'form': form,
        'recommendations': recommendations,
        'submitted': request.method == 'POST' and form.is_valid(),
    })


def calendrier_sessions(request):
    sessions = TrainingSession.objects.filter(
        status=1,
        date_debut__gte=timezone.localdate(),
    ).select_related('formation')
    type_session = request.GET.get('type', '')
    if type_session in {'cohorte', 'information'}:
        sessions = sessions.filter(type_session=type_session)
    return render(request, 'dunia_app/calendrier_sessions.html', {
        'sessions': sessions.order_by('date_debut', 'pk'),
        'type_session_active': type_session,
    })


@rate_limit('training_application', limit=10, window=3600, include_user=False)
def candidature_create(request, slug):
    formation = get_object_or_404(Information, slug=slug, status=1)
    form = CandidatureForm(request.POST or None, request.FILES or None, formation=formation)
    if request.method == 'POST' and form.is_valid():
        candidature = form.save(commit=False)
        candidature.formation = formation
        candidature.utilisateur = request.user if request.user.is_authenticated else None
        candidature.save()
        messages.success(request, 'Votre candidature a bien été envoyée. Conservez votre référence pour suivre son avancement.')
        return render(request, 'dunia_app/candidature_confirmation.html', {'candidature': candidature})
    return render(request, 'dunia_app/candidature_form.html', {'formation': formation, 'form': form})


def candidature_suivi(request):
    form = ApplicationTrackingForm(request.POST or None)
    candidature = None
    action_suivante = ''
    etape_courante = 0
    if request.method == 'POST' and form.is_valid():
        candidature = Candidature.objects.filter(
            reference=form.cleaned_data['reference'],
            email__iexact=form.cleaned_data['email'],
        ).select_related('formation', 'session').first()
        if candidature is None:
            messages.error(request, 'Aucune candidature ne correspond à ces informations.')
        else:
            etape_courante = next(
                (index for index, (code, _) in enumerate(CANDIDATURE_STATUTS, start=1)
                 if code == candidature.statut),
                0,
            )
            action_suivante = {
                'recue': 'Votre dossier est reçu. Surveillez votre e-mail : l’équipe Dunia vous informera si une étape complémentaire est nécessaire.',
                'test': 'Consultez votre e-mail pour les consignes et la date du test d’admission.',
                'documents': 'Transmettez les documents demandés en suivant les consignes envoyées par l’équipe Dunia.',
                'decision': 'Votre dossier est en cours d’étude. Aucune action n’est nécessaire pour le moment.',
                'confirmee': 'Contactez l’équipe Dunia pour confirmer votre place et préparer votre rentrée.',
                'refusee': 'Contactez un conseiller pour comprendre la décision ou explorer un autre parcours.',
            }.get(candidature.statut, '')
    return render(request, 'dunia_app/candidature_tracking.html', {
        'form': form,
        'candidature': candidature,
        'etapes': CANDIDATURE_STATUTS,
        'etape_courante': etape_courante,
        'action_suivante': action_suivante,
    })


def aide_financiere_create(request, slug):
    formation = get_object_or_404(Information, slug=slug, status=1)
    if not formation.bourse_disponible:
        raise Http404("Cette formation ne propose pas de demande d'aide financière.")
    form = FinancialAidForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        demande = form.save(commit=False)
        demande.formation = formation
        demande.save()
        return redirect('aide_financiere_confirmation', reference=demande.reference)
    return render(request, 'dunia_app/aide_financiere_form.html', {'formation': formation, 'form': form})


def aide_financiere_confirmation(request, reference):
    demande = get_object_or_404(
        DemandeAideFinanciere.objects.select_related('formation'),
        reference=reference,
    )
    return render(request, 'dunia_app/aide_financiere_confirmation.html', {'demande': demande})


@rate_limit('financial_aid_tracking', limit=10, window=900, include_user=False)
def aide_financiere_suivi(request):
    form = FinancialAidTrackingForm(request.POST or None)
    demande = None
    action_suivante = ''
    if request.method == 'POST' and form.is_valid():
        demande = DemandeAideFinanciere.objects.filter(
            reference=form.cleaned_data['reference'],
            email__iexact=form.cleaned_data['email'],
        ).select_related('formation').first()
        if demande is None:
            messages.error(request, 'Aucune demande ne correspond à ces informations.')
        else:
            action_suivante = {
                'recue': 'Votre demande est reçue. L’équipe Dunia l’étudiera et vous contactera par e-mail.',
                'etude': 'Votre demande est en cours d’étude. Aucune action n’est nécessaire pour le moment.',
                'recontact': 'L’équipe Dunia souhaite échanger avec vous. Surveillez votre e-mail et votre téléphone.',
                'cloturee': 'Le traitement de votre demande est terminé. Contactez l’équipe Dunia si vous avez une question.',
            }.get(demande.statut, '')
    return render(request, 'dunia_app/aide_financiere_suivi.html', {
        'form': form,
        'demande': demande,
        'action_suivante': action_suivante,
    })


def session_reservation_create(request, session_id):
    session = get_object_or_404(
        TrainingSession.objects.select_related('formation'),
        pk=session_id,
        status=1,
        type_session='information',
        date_debut__gte=timezone.localdate(),
    )
    form = SessionReservationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        if session.places_restantes <= 0:
            form.add_error(None, 'Cette session est complète.')
        else:
            try:
                with transaction.atomic():
                    places_maj = TrainingSession.objects.filter(pk=session.pk, places_restantes__gt=0).update(
                        places_restantes=F('places_restantes') - 1
                    )
                    if not places_maj:
                        form.add_error(None, 'Cette session vient d’être complète.')
                    else:
                        reservation = form.save(commit=False)
                        reservation.session = session
                        reservation.save()
            except IntegrityError:
                form.add_error('email', 'Cette adresse e-mail a déjà réservé une place pour cette session.')
            else:
                if not form.errors:
                    messages.success(request, 'Votre place est réservée. À bientôt chez Dunia !')
                    return redirect('info_detail', slug=session.formation.slug)
    return render(request, 'dunia_app/session_reservation.html', {'session': session, 'form': form})


def job_list(request):
    queryset = JobPosting.objects.filter(
        statut='publiee',
        entreprise__verifiee=True,
    ).filter(
        Q(date_limite__isnull=True) | Q(date_limite__gte=timezone.localdate())
    ).filter(
        Q(entreprise__user__is_staff=True)
        | Q(entreprise__user__is_superuser=True)
        | Q(
            entreprise__user__demandes_role__role='entreprise',
            entreprise__user__demandes_role__statut='approuve',
        )
    ).select_related('entreprise')
    type_offre = request.GET.get('type', '')
    domaine = request.GET.get('domaine', '')
    if type_offre:
        queryset = queryset.filter(type_offre=type_offre)
    if domaine:
        queryset = queryset.filter(domaine=domaine)
    return render(request, 'dunia_app/job_list.html', {
        'offres': queryset,
        'types_offre': JobPosting._meta.get_field('type_offre').choices,
        'domaines': DOMAINES_FORMATION,
        'type_active': type_offre,
        'domaine_active': domaine,
    })


@rate_limit('job_application', limit=10, window=3600)
def job_detail(request, slug):
    offres_publiques_approuvees = JobPosting.objects.select_related('entreprise').filter(
        Q(entreprise__user__is_staff=True)
        | Q(entreprise__user__is_superuser=True)
        | Q(
            entreprise__user__demandes_role__role='entreprise',
            entreprise__user__demandes_role__statut='approuve',
        )
    )
    offre = get_object_or_404(
        offres_publiques_approuvees,
        slug=slug,
        statut='publiee',
        entreprise__verifiee=True,
    )
    if offre.date_limite and offre.date_limite < timezone.localdate():
        raise Http404
    form = JobApplicationForm(request.POST or None, request.FILES or None)
    if request.method == 'POST':
        if not request.user.is_authenticated:
            messages.info(request, 'Connectez-vous pour postuler à cette offre.')
            return redirect(f"{reverse('connexion')}?next={request.path}")
        if offre.entreprise.user_id == request.user.pk:
            form.add_error(None, 'Vous ne pouvez pas postuler à une offre de votre organisation.')
        elif form.is_valid():
            try:
                with transaction.atomic():
                    application = form.save(commit=False)
                    application.offre = offre
                    application.candidat = request.user
                    application.save()
                    record_audit(request.user, application, 'candidature_emploi.creee', {
                        'offre_id': offre.pk,
                    })
                    Notification.objects.create(
                        destinataire=offre.entreprise.user,
                        type_notification='emploi',
                        titre='Nouvelle candidature',
                        message=f'{request.user.get_full_name() or request.user.username} a postulé à « {offre.titre} ».',
                        url=reverse('tableau_bord'),
                    )
            except IntegrityError:
                form.add_error(None, 'Vous avez déjà postulé à cette offre.')
            else:
                messages.success(request, 'Votre candidature a été envoyée.')
                return redirect('offre_detail', slug=offre.slug)
    return render(request, 'dunia_app/job_detail.html', {'offre': offre, 'form': form})


@login_required
def job_application_cv_download(request, application_id):
    candidature = get_object_or_404(
        JobApplication.objects.select_related('candidat', 'offre__entreprise__user'),
        pk=application_id,
    )
    est_candidat = candidature.candidat_id == request.user.pk
    est_admin = request.user.is_superuser or request.user.has_perm('dunia_app.view_jobapplication')
    entreprise = candidature.offre.entreprise
    est_proprietaire_entreprise = (
        entreprise.user_id == request.user.pk
        and entreprise.verifiee
        and has_approved_role(request.user, 'entreprise')
    )
    if not (est_candidat or est_admin or est_proprietaire_entreprise):
        raise Http404
    try:
        fichier = candidature.cv.open('rb')
    except (FileNotFoundError, OSError, ValueError):
        raise Http404('Le CV est introuvable.')
    response = FileResponse(
        fichier,
        as_attachment=True,
        filename=Path(candidature.cv.name).name,
        content_type='application/pdf',
    )
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, no-store'
    response['Pragma'] = 'no-cache'
    return response


@login_required
def candidature_document_download(request, candidature_id):
    candidature = get_object_or_404(Candidature, pk=candidature_id)
    est_candidat = candidature.utilisateur_id == request.user.pk
    est_admin = request.user.is_superuser or request.user.has_perm('dunia_app.view_candidature')
    if not (est_candidat or est_admin):
        raise Http404
    if not candidature.document:
        raise Http404('Aucun document n’est associé à ce dossier.')
    try:
        fichier = candidature.document.open('rb')
    except (FileNotFoundError, OSError, ValueError):
        raise Http404('Le document est introuvable.')
    response = FileResponse(
        fichier,
        as_attachment=True,
        filename=Path(candidature.document.name).name,
        content_type='application/pdf',
    )
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, no-store'
    response['Pragma'] = 'no-cache'
    return response


@login_required
def business_dashboard(request):
    offres = JobPosting.objects.annotate(candidatures_count=Count('candidatures')).order_by('-date_creation')
    entreprises = request.user.entreprises_dunia.prefetch_related(
        Prefetch('offres', queryset=offres),
    )
    demandes = LearnerProjectRequest.objects.filter(traite=False) if request.user.is_staff else LearnerProjectRequest.objects.none()
    return render(request, 'dunia_app/business_dashboard.html', {
        'entreprises': entreprises,
        'demandes_projets': demandes,
        'role_entreprise_valide': has_approved_role(request.user, 'entreprise'),
    })


@login_required
@require_http_methods(['GET', 'POST'])
def business_job_applications(request, business_id, job_id):
    if request.user.is_staff:
        if not request.user.has_perm('dunia_app.change_jobapplication'):
            raise PermissionDenied('Vous n’êtes pas autorisé à traiter les candidatures d’emploi.')
        entreprise = get_object_or_404(BusinessProfile, pk=business_id)
    else:
        if not has_approved_role(request.user, 'entreprise'):
            raise PermissionDenied('Votre rôle entreprise doit être validé.')
        entreprise = get_object_or_404(
            BusinessProfile,
            pk=business_id,
            user=request.user,
            verifiee=True,
        )
    offre = get_object_or_404(JobPosting, pk=job_id, entreprise=entreprise)

    if request.method == 'POST':
        try:
            candidature_id = int(request.POST.get('application_id', ''))
        except (TypeError, ValueError):
            messages.error(request, 'Sélectionnez une candidature valide.')
            return redirect('entreprise_candidatures', business_id=entreprise.pk, job_id=offre.pk)
        candidature = get_object_or_404(
            JobApplication,
            pk=candidature_id,
            offre=offre,
        )
        try:
            transition_job_application(
                candidature.pk,
                statut=request.POST.get('statut', ''),
                actor=request.user,
            )
        except (DjangoValidationError, PermissionDenied) as error:
            message = error.messages[0] if isinstance(error, DjangoValidationError) and error.messages else str(error)
            messages.error(request, message)
        else:
            messages.success(request, 'Le statut de la candidature a été mis à jour.')
        return redirect('entreprise_candidatures', business_id=entreprise.pk, job_id=offre.pk)

    candidatures = offre.candidatures.select_related('candidat').order_by('-date_creation')
    return render(request, 'dunia_app/business_applications.html', {
        'entreprise': entreprise,
        'offre': offre,
        'candidatures': candidatures,
        'statuts_candidature': CANDIDATURE_EMPLOI_STATUTS,
    })


@login_required
def business_profile_edit(request, business_id):
    if not has_approved_role(request.user, 'entreprise'):
        raise PermissionDenied('Votre rôle entreprise doit être validé avant de modifier ce profil.')
    entreprise = get_object_or_404(
        BusinessProfile,
        pk=business_id,
        user=request.user,
        verifiee=True,
    )
    form = BusinessProfileForm(request.POST or None, request.FILES or None, instance=entreprise)
    if request.method == 'POST' and form.is_valid():
        try:
            update_business_profile(
                entreprise.pk,
                actor=request.user,
                changes=form.cleaned_data,
            )
        except (DjangoValidationError, PermissionDenied) as error:
            if isinstance(error, DjangoValidationError):
                form.add_error(None, error.messages[0] if error.messages else str(error))
            else:
                raise
        else:
            messages.success(request, 'Profil modifié. Dunia devra vérifier de nouveau l’organisation et les offres publiées.')
            return redirect('espace_entreprises')
    return render(request, 'dunia_app/business_form.html', {
        'form': form,
        'entreprise': entreprise,
        'titre_page': 'Modifier mon organisation',
    })


@login_required
@rate_limit('business_registration', limit=5, window=3600)
def business_create(request):
    form = BusinessProfileForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            business = form.save(commit=False)
            business.user = request.user
            business.verifiee = False
            business.save()
            if not has_approved_role(request.user, 'entreprise'):
                request_role(request.user, 'entreprise')
            record_audit(request.user, business, 'entreprise.demande_verification', {})
        messages.success(request, 'Entreprise enregistrée. Elle sera visible après vérification par Dunia.')
        return redirect('espace_entreprises')
    return render(request, 'dunia_app/business_form.html', {'form': form})


@login_required
def business_job_create(request, business_id):
    if not has_approved_role(request.user, 'entreprise'):
        raise PermissionDenied('Votre rôle entreprise doit être validé avant de créer une offre.')
    business = get_object_or_404(
        BusinessProfile,
        pk=business_id,
        user=request.user,
        verifiee=True,
    )
    form = JobPostingForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        offer = form.save(commit=False)
        offer.entreprise = business
        offer.statut = 'a_valider'
        with transaction.atomic():
            offer.save()
            record_audit(request.user, offer, 'offre.soumise_validation', {})
        messages.success(request, 'Offre transmise à Dunia pour validation avant publication.')
        return redirect('espace_entreprises')
    return render(request, 'dunia_app/job_form.html', {'form': form, 'entreprise': business})


def project_gallery(request):
    collaborateurs = ProjectCollaborator.objects.filter(statut='acceptee').select_related('utilisateur')
    projets = ProjectSubmission.objects.filter(statut='publie').select_related(
        'auteur', 'formation'
    ).prefetch_related(Prefetch(
        'collaborations',
        queryset=collaborateurs,
        to_attr='collaborateurs_acceptes',
    ))
    domaine = request.GET.get('domaine', '')
    if domaine:
        projets = projets.filter(formation__domaine=domaine)
    return render(request, 'dunia_app/project_gallery.html', {
        'projets': projets,
        'domaines': DOMAINES_FORMATION,
        'domaine_active': domaine,
    })


@login_required
def project_submit(request):
    form = ProjectSubmissionForm(request.POST or None, request.FILES or None, auteur=request.user)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                project = form.save(commit=False)
                project.auteur = request.user
                project.statut = 'a_valider'
                project.save()
                invitations = invite_project_collaborators(
                    project.pk,
                    form.cleaned_data['collaborateurs'],
                    actor=request.user,
                )
        except DjangoValidationError as error:
            form.add_error('collaborateurs', error)
        else:
            message = 'Projet envoyé à Dunia pour validation avant publication dans la galerie.'
            if invitations:
                message += f' Invitations envoyées à {invitations} coéquipier(s).'
            messages.success(request, message)
            return redirect('tableau_bord')
    return render(request, 'dunia_app/project_form.html', {'form': form})


@login_required
@require_http_methods(['GET', 'POST'])
@rate_limit('project_edit', limit=10, window=3600)
def project_edit(request, project_id):
    projet = get_object_or_404(
        ProjectSubmission.objects.filter(
            Q(auteur=request.user)
            | Q(collaborations__utilisateur=request.user, collaborations__statut='acceptee')
        ).distinct(),
        pk=project_id,
    )
    ancien_statut = projet.statut
    form = ProjectSubmissionForm(
        request.POST or None,
        request.FILES or None,
        instance=projet,
        auteur=request.user,
    )
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            projet = form.save(commit=False)
            projet.statut = 'a_valider'
            projet.save()
            record_audit(request.user, projet, 'projet.modifie_soumis_validation', {
                'ancien_statut': ancien_statut,
                'nouveau_statut': projet.statut,
            })
        messages.success(request, 'Projet modifié et transmis à Dunia pour validation avant republication.')
        return redirect(f"{reverse('tableau_bord')}#projets")
    return render(request, 'dunia_app/project_form.html', {'form': form, 'projet': projet})


@login_required
@require_POST
@rate_limit('project_collaborator_invite', limit=20, window=3600)
def project_collaborator_invite(request, project_id):
    project = get_object_or_404(ProjectSubmission, pk=project_id, auteur=request.user)
    form = ProjectCollaboratorInviteForm(request.POST, user=request.user, project=project)
    if not form.is_valid():
        messages.error(request, 'Sélectionnez un ou plusieurs amis Dunia encore disponibles pour cette équipe.')
        return redirect(f"{reverse('tableau_bord')}#projets")
    try:
        invitations = invite_project_collaborators(
            project.pk,
            form.cleaned_data['collaborateurs'],
            actor=request.user,
        )
    except DjangoValidationError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f'{invitations} invitation(s) envoyée(s).')
    return redirect(f"{reverse('tableau_bord')}#projets")


@login_required
@require_POST
def project_invitation_action(request, invitation_id, action):
    if action not in {'accepter', 'refuser'}:
        raise Http404
    statut = 'acceptee' if action == 'accepter' else 'refusee'
    try:
        respond_to_project_invitation(invitation_id, statut=statut, actor=request.user)
    except DjangoValidationError as error:
        messages.error(request, str(error))
    else:
        messages.success(
            request,
            'Vous avez rejoint l’équipe du projet.' if statut == 'acceptee' else 'Invitation refusée.',
        )
    return redirect(f"{reverse('tableau_bord')}#invitations-projets")


def community_list(request):
    communities = Community.objects.filter(status=1).annotate(member_count=Count('membres')).select_related('formation')
    return render(request, 'dunia_app/community_list.html', {'communautes': communities})


@login_required
def community_detail(request, slug):
    community = get_object_or_404(Community.objects.filter(status=1).select_related('formation'), slug=slug)
    membre = CommunityMembership.objects.filter(community=community, user=request.user).exists()
    demande_acces = None
    if community.privee and not membre:
        demande_acces = CommunityAccessRequest.objects.filter(
            communaute=community,
            utilisateur=request.user,
        ).first()
    form = CommunityPostForm()
    if request.method == 'POST' and 'rejoindre' in request.POST:
        if community.privee:
            raise PermissionDenied('Une communauté privée nécessite une demande d’accès approuvée.')
        CommunityMembership.objects.get_or_create(community=community, user=request.user)
        messages.success(request, f"Vous avez rejoint {community.nom}.")
        return redirect('communaute_detail', slug=community.slug)
    if request.method == 'POST' and 'demander_acces' in request.POST:
        if not community.privee or membre:
            raise Http404
        demande_acces, creee = CommunityAccessRequest.objects.get_or_create(
            communaute=community,
            utilisateur=request.user,
        )
        if not creee and demande_acces.statut != 'en_attente':
            ancien_statut = demande_acces.statut
            demande_acces.statut = 'en_attente'
            demande_acces.revue_par = None
            demande_acces.date_revue = None
            demande_acces.save(update_fields=['statut', 'revue_par', 'date_revue', 'date_modification'])
            record_audit(request.user, demande_acces, 'communaute.demande_acces_renouvelee', {
                'ancien_statut': ancien_statut,
            })
            messages.success(request, 'Votre nouvelle demande d’accès a été transmise à l’équipe Dunia.')
        elif creee:
            record_audit(request.user, demande_acces, 'communaute.demande_acces', {})
            messages.success(request, 'Votre demande d’accès a été transmise à l’équipe Dunia.')
        else:
            messages.info(request, 'Votre demande d’accès est déjà en cours de traitement.')
        return redirect('communaute_detail', slug=community.slug)
    if request.method == 'POST' and 'contenu' in request.POST:
        if not membre:
            messages.error(request, 'Rejoignez cette communauté pour y publier.')
        else:
            form = CommunityPostForm(request.POST)
            if form.is_valid():
                post = form.save(commit=False)
                post.community = community
                post.auteur = request.user
                post.save()
                messages.success(request, 'Votre message a été publié.')
                return redirect('communaute_detail', slug=community.slug)
    else:
        form = CommunityPostForm()
    return render(request, 'dunia_app/community_detail.html', {
        'communaute': community,
        'membre': membre,
        'demande_acces': demande_acces,
        'form': form,
        'publications': community.publications.select_related('auteur')[:50] if membre else [],
    })


def trainer_list(request):
    formateurs = TrainerProfile.objects.filter(status=1).select_related('user')
    return render(request, 'dunia_app/trainer_list.html', {'formateurs': formateurs})


def credential_list(request):
    certifications = Credential.objects.filter(status=1).prefetch_related(
        Prefetch('cours', queryset=Cours.objects.filter(status=1)),
        Prefetch('formations', queryset=Information.objects.filter(status=1)),
    ).select_related('partenaire')
    return render(request, 'dunia_app/credential_list.html', {'certifications': certifications})


@login_required
def user_credential_download(request, reference):
    attribution = get_object_or_404(
        UserCredential.objects.select_related('utilisateur', 'certification'),
        reference=reference,
        utilisateur=request.user,
    )
    buffer = BytesIO()
    page_width, page_height = landscape(A4)
    document = canvas.Canvas(buffer, pagesize=(page_width, page_height), pageCompression=1)
    document.setTitle(f"Certificat — {attribution.certification.nom}")
    document.setAuthor('Dunia')
    document.setFillColor(HexColor('#f8fafc'))
    document.rect(0, 0, page_width, page_height, stroke=0, fill=1)
    document.setStrokeColor(HexColor('#173b70'))
    document.setLineWidth(4)
    document.roundRect(24, 24, page_width - 48, page_height - 48, 16, stroke=1, fill=0)
    document.setStrokeColor(HexColor('#37b7c8'))
    document.setLineWidth(1)
    document.roundRect(34, 34, page_width - 68, page_height - 68, 12, stroke=1, fill=0)
    document.setFillColor(HexColor('#173b70'))
    document.setFont('Helvetica-Bold', 17)
    document.drawCentredString(page_width / 2, page_height - 78, 'DUNIA')
    document.setFillColor(HexColor('#0f172a'))
    document.setFont('Helvetica-Bold', 27)
    document.drawCentredString(page_width / 2, page_height - 132, 'CERTIFICAT DE RÉUSSITE')
    document.setFillColor(HexColor('#475569'))
    document.setFont('Helvetica', 14)
    document.drawCentredString(page_width / 2, page_height - 176, 'Ce document atteste que')
    nom = attribution.utilisateur.get_full_name() or attribution.utilisateur.get_username()
    document.setFillColor(HexColor('#173b70'))
    document.setFont('Helvetica-Bold', 23)
    document.drawCentredString(page_width / 2, page_height - 218, nom)
    document.setFillColor(HexColor('#475569'))
    document.setFont('Helvetica', 14)
    document.drawCentredString(page_width / 2, page_height - 254, 'a obtenu la certification')
    document.setFillColor(HexColor('#0f172a'))
    document.setFont('Helvetica-Bold', 19)
    lignes = simpleSplit(attribution.certification.nom, 'Helvetica-Bold', 19, page_width - 120)
    y = page_height - 292
    for ligne in lignes[:2]:
        document.drawCentredString(page_width / 2, y, ligne)
        y -= 26
    document.setFillColor(HexColor('#475569'))
    document.setFont('Helvetica', 12)
    document.drawCentredString(page_width / 2, 102, f"Délivré le {timezone.localtime(attribution.date_obtention).strftime('%d/%m/%Y')}")
    document.drawCentredString(page_width / 2, 78, f"Référence de vérification : {attribution.reference}")
    document.setFillColor(HexColor('#0e7490'))
    document.setFont('Helvetica', 9)
    verification_path = reverse('credential_verify', args=[attribution.reference])
    document.drawCentredString(page_width / 2, 58, f"Vérification publique : {request.build_absolute_uri(verification_path)}")
    document.save()
    buffer.seek(0)
    filename = f"certificat-dunia-{attribution.reference.hex[:8]}.pdf"
    return FileResponse(buffer, as_attachment=True, filename=filename, content_type='application/pdf')


def credential_verify(request, reference):
    attribution = get_object_or_404(
        UserCredential.objects.select_related('certification'),
        reference=reference,
    )
    return render(request, 'dunia_app/credential_verify.html', {'attribution': attribution})


@login_required
@rate_limit('trainer_application', limit=5, window=3600)
def trainer_apply(request):
    if has_approved_role(request.user, 'formateur'):
        messages.info(request, 'Votre rôle formateur est déjà validé.')
        return redirect('formateur_cours')
    profile, _ = TrainerProfile.objects.get_or_create(user=request.user, defaults={'status': 0})
    form = TrainerApplicationForm(request.POST or None, instance=profile)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            profile = form.save(commit=False)
            profile.user = request.user
            profile.status = 0
            profile.save()
            request_role(request.user, 'formateur')
        messages.success(request, 'Votre demande de profil formateur a été transmise à Dunia.')
        return redirect('tableau_bord')
    return render(request, 'dunia_app/trainer_application_form.html', {'form': form})


@login_required
def formateur_cours(request):
    if not has_approved_role(request.user, 'formateur'):
        raise PermissionDenied('Votre rôle formateur doit être validé pour gérer des cours.')
    cours = Cours.objects.filter(formateur=request.user).order_by('-date_modif', '-pk')
    return render(request, 'dunia_app/trainer_courses.html', {'cours_list': cours})


@login_required
def formateur_cours_creer(request):
    if not has_approved_role(request.user, 'formateur'):
        raise PermissionDenied('Votre rôle formateur doit être validé pour gérer des cours.')
    form = CourseManagementForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        cours = form.save(commit=False)
        cours.formateur = request.user
        cours.status = 0
        cours.workflow_status = 'a_valider'
        cours.save()
        record_audit(request.user, cours, 'cours.soumis_validation', {'statut': cours.workflow_status})
        messages.success(request, 'Votre cours a été transmis à Dunia pour validation.')
        return redirect('formateur_cours')
    return render(request, 'dunia_app/course_management_form.html', {'form': form, 'titre_page': 'Proposer un cours'})


@login_required
def formateur_cours_modifier(request, cours_id):
    if not has_approved_role(request.user, 'formateur'):
        raise PermissionDenied('Votre rôle formateur doit être validé pour gérer des cours.')
    cours = get_object_or_404(Cours, pk=cours_id, formateur=request.user)
    form = CourseManagementForm(request.POST or None, request.FILES or None, instance=cours)
    if request.method == 'POST' and form.is_valid():
        cours = form.save(commit=False)
        cours.status = 0
        cours.workflow_status = 'a_valider'
        cours.save()
        record_audit(request.user, cours, 'cours.modifie_et_soumis', {'statut': cours.workflow_status})
        messages.success(request, 'Les modifications ont été transmises à Dunia pour validation.')
        return redirect('formateur_cours')
    return render(request, 'dunia_app/course_management_form.html', {
        'form': form,
        'cours': cours,
        'titre_page': 'Modifier un cours',
    })


def learner_directory(request):
    domaines = DOMAINES_FORMATION
    profils = UserProfile.objects.filter(visible=True, role='apprenant').select_related('user')
    if request.user.is_authenticated:
        profils = profils.exclude(user=request.user)
    domaine = request.GET.get('domaine', '')
    if domaine in dict(domaines):
        profils = profils.filter(user__projets__statut='publie', user__projets__competences__icontains=dict(domaines)[domaine]).distinct()
    profils = list(profils)
    if request.user.is_authenticated:
        relations = Friendship.objects.filter(
            Q(person_one=request.user) | Q(person_two=request.user)
        ).select_related('person_one', 'person_two')
        relations_by_user = {relation.other_user(request.user).pk: relation for relation in relations}
        for profil in profils:
            relation = relations_by_user.get(profil.user_id)
            if not relation:
                profil.relation_state = ''
            elif relation.status == Friendship.ACCEPTED:
                profil.relation_state = 'amis'
            elif relation.requested_by_id == request.user.pk:
                profil.relation_state = 'envoyee'
            else:
                profil.relation_state = 'recue'
    return render(request, 'dunia_app/learner_directory.html', {
        'profils': profils,
        'domaines': domaines,
        'domaine_active': domaine,
    })


def professional_events(request):
    evenements = ProfessionalEvent.objects.filter(status=1, date_debut__gte=timezone.now())
    if request.user.is_authenticated:
        evenements = evenements.annotate(inscription_active=Exists(EventRegistration.objects.filter(
            evenement_id=OuterRef('pk'),
            participant=request.user,
            annulee_le__isnull=True,
        )))
    else:
        evenements = evenements.annotate(inscription_active=Value(False, output_field=BooleanField()))
    return render(request, 'dunia_app/professional_events.html', {'evenements': evenements})


@login_required
@require_POST
def event_register(request, slug):
    evenement = get_object_or_404(ProfessionalEvent, slug=slug, status=1, date_debut__gte=timezone.now())
    with transaction.atomic():
        inscription, creee = EventRegistration.objects.get_or_create(
            evenement=evenement,
            participant=request.user,
        )
        if not creee:
            if inscription.annulee_le is None:
                messages.info(request, 'Vous êtes déjà inscrit à cet événement.')
                return redirect('evenements_pro')
            if evenement.places:
                places_maj = ProfessionalEvent.objects.filter(
                    pk=evenement.pk,
                    places_restantes__gt=0,
                ).update(places_restantes=F('places_restantes') - 1)
                if not places_maj:
                    messages.error(request, 'Cet événement affiche complet.')
                    return redirect('evenements_pro')
            inscription.annulee_le = None
            inscription.status = 1
            inscription.save(update_fields=['annulee_le', 'status'])
            messages.success(request, 'Votre inscription à cet événement est réactivée.')
            return redirect('evenements_pro')
        if evenement.places:
            places_maj = ProfessionalEvent.objects.filter(
                pk=evenement.pk,
                places_restantes__gt=0,
            ).update(places_restantes=F('places_restantes') - 1)
            if not places_maj:
                inscription.delete()
                messages.error(request, 'Cet événement affiche complet.')
                return redirect('evenements_pro')
    messages.success(request, 'Votre inscription à cet événement est enregistrée.')
    return redirect('evenements_pro')


@login_required
@require_POST
def event_cancel(request, slug):
    evenement = get_object_or_404(ProfessionalEvent, slug=slug, status=1)
    with transaction.atomic():
        inscription = EventRegistration.objects.select_for_update().filter(
            evenement=evenement,
            participant=request.user,
        ).first()
        if inscription is None:
            raise Http404
        if inscription.annulee_le is not None:
            messages.info(request, 'Votre inscription est déjà annulée.')
            return redirect('evenements_pro')
        if evenement.date_debut <= timezone.now():
            messages.error(request, 'Une inscription ne peut plus être annulée après le début de l’événement.')
            return redirect('evenements_pro')
        inscription.annulee_le = timezone.now()
        inscription.save(update_fields=['annulee_le'])
        if evenement.places:
            ProfessionalEvent.objects.filter(
                pk=evenement.pk,
                places_restantes__lt=F('places'),
            ).update(places_restantes=F('places_restantes') + 1)
    messages.success(request, 'Votre inscription a été annulée et la place libérée.')
    return redirect('evenements_pro')


@login_required
def course_evaluate(request, slug):
    cours = get_object_or_404(Cours, slug=slug, status=1)
    progression = request.user.learning_progress.filter(cours=cours).first()
    if not progression or not progression.is_completed:
        messages.error(request, 'Terminez le cours pour pouvoir le noter.')
        return redirect('cours_detail', slug=cours.slug)
    evaluation_existante = CourseEvaluation.objects.filter(cours=cours, auteur=request.user).first()
    form = CourseEvaluationForm(request.POST or None, instance=evaluation_existante)
    if request.method == 'POST' and form.is_valid():
        evaluation = form.save(commit=False)
        evaluation.cours = cours
        evaluation.auteur = request.user
        evaluation.save()
        messages.success(request, 'Merci pour votre avis !')
        return redirect('cours_detail', slug=cours.slug)
    return render(request, 'dunia_app/course_evaluation_form.html', {'cours': cours, 'form': form})


def initiative_list(request):
    return render(request, 'dunia_app/initiative_list.html', {
        'initiatives': Initiative.objects.filter(status=1),
        'temoignages': Testimonial.objects.filter(status=1).select_related('formation')[:6],
        'partenaires': Partner.objects.filter(status=1),
        'metriques': ImpactMetric.objects.filter(status=1),
        'rapports': AnnualReport.objects.filter(status=1),
        'campus': Campus.objects.filter(status=1).prefetch_related('formations'),
        'evenements': ProfessionalEvent.objects.filter(status=1, date_debut__gte=timezone.now())[:6],
    })


def challenge_list(request):
    challenges = Challenge.objects.filter(status=1)
    return render(request, 'dunia_app/challenge_list.html', {'challenges': challenges})


def challenge_detail(request, slug):
    challenge = get_object_or_404(Challenge, slug=slug, status=1)
    participation = None
    remise_ouverte = (
        (not challenge.date_debut or timezone.now() >= challenge.date_debut)
        and (not challenge.date_fin or timezone.now() <= challenge.date_fin)
    )
    peut_soumettre = False
    if request.user.is_authenticated:
        participation = ChallengeParticipation.objects.filter(
            challenge=challenge, participant=request.user
        ).first()
        if participation:
            participation.tentatives_paiement_liste = participation.tentatives_paiement.all()
            participation.soumissions_travail_liste = participation.soumissions_travail.all()
            participation.derniere_soumission = participation.soumissions_travail_liste.first()
            paiement_ok = challenge.est_gratuit or participation.paiement_statut == 'confirme'
            soumission_corrigeable = (
                not participation.derniere_soumission
                or participation.derniere_soumission.statut == 'a_corriger'
            )
            peut_soumettre = remise_ouverte and paiement_ok and soumission_corrigeable
    return render(request, 'dunia_app/challenge_detail.html', {
        'challenge': challenge,
        'participation': participation,
        'remise_ouverte': remise_ouverte,
        'peut_soumettre': peut_soumettre,
    })


@login_required
@require_POST
def challenge_enroll(request, slug):
    challenge = get_object_or_404(Challenge, slug=slug, status=1)
    payment_status = 'en_attente' if not challenge.est_gratuit else 'sans_objet'
    participation, created = ChallengeParticipation.objects.get_or_create(
        challenge=challenge,
        participant=request.user,
        defaults={'paiement_statut': payment_status},
    )
    if created:
        if challenge.est_gratuit:
            messages.success(request, 'Votre inscription au défi gratuit est confirmée.')
        else:
            messages.info(request, 'Votre demande est enregistrée. Suivez les instructions de paiement ; l’accès sera ouvert après confirmation.')
    else:
        messages.info(request, 'Vous êtes déjà inscrit à ce défi.')
    return redirect('challenge_detail', slug=challenge.slug)


@login_required
@rate_limit('challenge_submission', limit=10, window=60)
@require_POST
def challenge_submit(request, slug):
    challenge = get_object_or_404(Challenge, slug=slug, status=1)
    participation = get_object_or_404(
        ChallengeParticipation,
        challenge=challenge,
        participant=request.user,
    )
    try:
        submit_challenge_work(
            participation.pk,
            travail=request.POST.get('travail', ''),
            actor=request.user,
        )
    except DjangoValidationError as error:
        messages.error(request, error.messages[0] if error.messages else 'Cette remise ne peut pas être enregistrée.')
    else:
        messages.success(request, 'Votre travail a été transmis pour évaluation.')
    return redirect('challenge_detail', slug=challenge.slug)


@login_required
@rate_limit('challenge_payment', limit=5, window=3600)
@require_POST
def challenge_report_payment(request, slug):
    challenge = get_object_or_404(Challenge, slug=slug, status=1)
    participation = get_object_or_404(
        ChallengeParticipation,
        challenge=challenge,
        participant=request.user,
    )
    try:
        submit_challenge_payment(
            participation.pk,
            reference=request.POST.get('reference_paiement', ''),
            actor=request.user,
        )
    except DjangoValidationError as error:
        messages.error(request, error.messages[0] if error.messages else 'Référence de paiement invalide.')
    else:
        messages.success(request, 'Référence enregistrée. L’équipe Dunia doit confirmer le paiement avant l’ouverture du défi.')
    return redirect('challenge_detail', slug=challenge.slug)


def impact_dashboard(request):
    return render(request, 'dunia_app/impact.html', {
        'metriques': ImpactMetric.objects.filter(status=1),
        'rapports': AnnualReport.objects.filter(status=1),
        'formateurs': TrainerProfile.objects.filter(status=1).select_related('user'),
        'partenaires': Partner.objects.filter(status=1),
    })


def campus_list(request):
    return render(request, 'dunia_app/campus_list.html', {
        'campus': Campus.objects.filter(status=1).prefetch_related('formations'),
    })


def project_request_create(request):
    form = LearnerProjectRequestForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Votre projet a été transmis à Dunia. Notre équipe vous recontactera.')
        return redirect('projet_client')
    return render(request, 'dunia_app/project_request_form.html', {'form': form})


@login_required
@require_POST
def notification_mark_read(request, notification_id):
    notification = get_object_or_404(Notification, pk=notification_id, destinataire=request.user)
    notification.lue = True
    notification.save(update_fields=['lue'])
    next_url = request.POST.get('next', '')
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(next_url)
    return redirect('tableau_bord')


def messagerie(request):
    if not request.user.is_authenticated:
        return render(request, 'dunia_app/messagerie.html', {
            'conversations': [],
            'is_guest': True,
        })

    conversations = list(Conversation.objects.filter(
        Q(participant_one=request.user) | Q(participant_two=request.user)
    ).select_related(
        'participant_one', 'participant_two', 'participant_one__profil_dunia', 'participant_two__profil_dunia'
    ).annotate(
        unread_count=Count('messages', filter=Q(messages__read_at__isnull=True) & ~Q(messages__sender=request.user), distinct=True)
    ).prefetch_related(Prefetch(
        'messages',
        queryset=Message.objects.select_related('sender').order_by('-created_at', '-pk')[:1],
        to_attr='latest_messages',
    )).order_by('-updated_at', '-pk'))
    for conversation in conversations:
        conversation.interlocuteur = conversation.other_participant(request.user)
        conversation.latest_message = conversation.latest_messages[0] if conversation.latest_messages else None
    return render(request, 'dunia_app/messagerie.html', {
        'conversations': conversations,
        'is_guest': False,
    })


@login_required
def conversation_detail(request, conversation_id):
    conversation = get_object_or_404(
        Conversation.objects.filter(Q(participant_one=request.user) | Q(participant_two=request.user)),
        pk=conversation_id,
    )
    if request.method == 'POST':
        form = MessageForm(request.POST)
        if form.is_valid():
            message = form.save(commit=False)
            message.conversation = conversation
            message.sender = request.user
            message.save()
            conversation.save(update_fields=['updated_at'])
            recipient = conversation.other_participant(request.user)
            Notification.objects.create(
                destinataire=recipient,
                type_notification='message',
                titre='Nouveau message',
                message=f'{request.user.get_full_name() or request.user.username} vous a envoyé un message.',
                url=reverse('conversation_detail', args=[conversation.pk]),
            )
            return redirect('conversation_detail', conversation_id=conversation.pk)
    else:
        form = MessageForm()
    conversation.messages.exclude(sender=request.user).filter(read_at__isnull=True).update(read_at=timezone.now())
    return render(request, 'dunia_app/conversation_detail.html', {
        'conversation': conversation,
        'interlocuteur': conversation.other_participant(request.user),
        'messages_conversation': conversation.messages.select_related('sender', 'sender__profil_dunia'),
        'form': form,
    })


@login_required
def conversation_demarrer(request, username):
    autre = get_object_or_404(User, username=username, is_active=True)
    if autre.pk == request.user.pk:
        return redirect('messagerie')
    premier, second = sorted((request.user, autre), key=lambda user: user.pk)
    conversation, _ = Conversation.objects.get_or_create(participant_one=premier, participant_two=second)
    return redirect('conversation_detail', conversation_id=conversation.pk)


class CoursList(generic.ListView):
    template_name = "dunia_app/cours.html"
    context_object_name = "cours_list"
    paginate_by = 12

    def get_queryset(self):
        queryset = Cours.objects.filter(status=1)
        cat = self.request.GET.get('cat')
        type_ = self.request.GET.get('type')
        if cat:
            queryset = queryset.filter(categorie=cat)
        if type_:
            queryset = queryset.filter(type_contenu=type_)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = CATEGORIES_COURS
        context['types'] = TYPE_CONTENU
        context['cat_active'] = self.request.GET.get('cat', '')
        context['type_active'] = self.request.GET.get('type', '')
        return context


class CoursDetail(generic.DetailView):
    model = Cours
    template_name = "dunia_app/cours_detail.html"
    context_object_name = 'cours'

    def get_queryset(self):
        return Cours.objects.filter(status=1).select_related('formateur')

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        Cours.objects.filter(pk=obj.pk).update(vues=F('vues') + 1)
        obj.refresh_from_db()
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['suggestions'] = Cours.objects.filter(status=1).exclude(pk=self.object.pk)[:6]
        context['progression'] = None
        context['note_moyenne'] = self.object.evaluations.filter(status=1).aggregate(moyenne=Avg('note'))['moyenne']
        context['evaluations'] = self.object.evaluations.filter(status=1).select_related('auteur')[:8]
        if self.request.user.is_authenticated:
            context['progression'] = self.request.user.learning_progress.filter(cours=self.object).first()
        return context

def decouvrir(request):
    return render(request, 'dunia_app/decouvrir.html')


def services(request):
    return render(request, 'dunia_app/service.html')

def posts(request):
    return render(request, 'dunia_app/post.html')

class articleList(generic.ListView):
    template_name = "dunia_app/article_list.html"
    context_object_name = 'article_list'
    paginate_by = 6

    def get_queryset(self):
        queryset = Article.objects.filter(status=1).select_related('auteur', 'categorie').annotate(
            comments_count=Count('commentaires', filter=Q(commentaires__status=1))
        )
        categorie = self.kwargs.get('slug')
        if categorie:
            queryset = queryset.filter(categorie__slug=categorie, categorie__status=1)
        return queryset.order_by('-date_publication')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = BlogCategory.objects.filter(status=1).annotate(
            articles_count=Count('articles', filter=Q(articles__status=1))
        )
        context['articles_a_la_une'] = Article.objects.filter(
            status=1, a_la_une=True
        ).select_related('auteur', 'categorie')[:3]
        context['categorie_active'] = self.kwargs.get('slug', '')
        return context

class articleDetail(generic.DetailView):
    model = Article
    template_name = "dunia_app/article_detail.html"
    slug_field = 'lien'
    slug_url_kwarg = 'slug'

    def get_queryset(self):
        return Article.objects.filter(status=1).select_related('auteur', 'categorie')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['comments'] = self.object.commentaires.filter(status=1)
        return context