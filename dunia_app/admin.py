from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils.html import format_html
from .models import (
    AuditLog,
    AnnualReport,
    BlogCategory,
    BusinessProfile,
    Candidature,
    Comment,
    Conversation,
    CommunityAccessRequest,
    Community,
    CommunityMembership,
    CommunityPost,
    CourseEvaluation,
    Credential,
    DemandeAideFinanciere,
    EventRegistration,
    FeedComment,
    FeedLike,
    FeedShare,
    Friendship,
    FormationFAQ,
    ImpactMetric,
    Initiative,
    JobApplication,
    JobPosting,
    LearnerProjectRequest,
    LearningProgress,
    Message,
    Notification,
    Partner,
    Publication,
    ProfessionalEvent,
    ProjectSubmission,
    ProjectCollaborator,
    RoleRequest,
    Information,
    Cours,
    TrainerProfile,
    Testimonial,
    Contact,
    Article,
    SessionReservation,
    SocialPost,
    TrainingSession,
    UserCredential,
    UserProfile,
    Campus,
    Challenge,
    ChallengeParticipation,
    ChallengePaymentAttempt,
    ChallengeWorkSubmission,
)
from .services import (
    record_audit,
    review_challenge_payment,
    review_challenge_work,
    review_role_request,
    set_course_workflow_status,
    set_business_profile_verification,
    set_job_posting_status,
    transition_job_application,
    transition_candidature,
    review_community_access_request,
)


@admin.register(RoleRequest)
class RoleRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'statut', 'date_demande', 'date_decision', 'decision_par')
    list_filter = ('role', 'statut', 'date_demande')
    search_fields = ('user__username', 'user__email', 'user__first_name', 'user__last_name')
    autocomplete_fields = ('user',)
    readonly_fields = ('user', 'role', 'date_demande', 'date_decision', 'decision_par')
    actions = ('approuver_demandes', 'refuser_demandes')

    def save_model(self, request, obj, form, change):
        if change:
            ancien = RoleRequest.objects.get(pk=obj.pk)
            if obj.statut != ancien.statut:
                try:
                    review_role_request(
                        obj.pk,
                        statut=obj.statut,
                        actor=request.user,
                        commentaire=obj.commentaire,
                    )
                except (PermissionDenied, ValidationError) as error:
                    self.message_user(request, str(error), level='ERROR')
                obj.refresh_from_db()
                return
        super().save_model(request, obj, form, change)
        if change and obj.commentaire != ancien.commentaire:
            record_audit(request.user, obj, 'role.commentaire_modifie', {
                'ancien_commentaire': ancien.commentaire,
                'nouveau_commentaire': obj.commentaire,
            })

    @admin.action(description='Approuver les demandes de rôle sélectionnées')
    def approuver_demandes(self, request, queryset):
        self._traiter_demandes(request, queryset, 'approuve')

    @admin.action(description='Refuser les demandes de rôle sélectionnées')
    def refuser_demandes(self, request, queryset):
        self._traiter_demandes(request, queryset, 'refuse')

    def _traiter_demandes(self, request, queryset, statut):
        for demande in queryset:
            try:
                review_role_request(demande.pk, statut=statut, actor=request.user)
            except (PermissionDenied, ValidationError) as error:
                self.message_user(request, f'{demande}: {error}', level='ERROR')


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('date_creation', 'actor', 'action', 'content_type', 'object_id')
    list_filter = ('action', 'content_type', 'date_creation')
    search_fields = ('actor__username', 'action', 'object_id')
    readonly_fields = ('actor', 'content_type', 'object_id', 'action', 'details', 'date_creation')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FeedShare)
class FeedShareAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'post', 'publication', 'date_creation')
    list_filter = ('date_creation',)
    search_fields = ('user__username', 'post__contenu', 'publication__titre')
    autocomplete_fields = ('user', 'post', 'publication')
    readonly_fields = ('date_creation',)


@admin.register(Challenge)
class ChallengeAdmin(admin.ModelAdmin):
    list_display = ('titre', 'prix', 'devise', 'status', 'date_debut', 'date_fin')
    list_filter = ('status', 'devise')
    search_fields = ('titre', 'description', 'consignes')
    prepopulated_fields = {'slug': ('titre',)}


class ChallengePaymentAttemptInline(admin.TabularInline):
    model = ChallengePaymentAttempt
    extra = 0
    can_delete = False
    show_change_link = True
    readonly_fields = ('reference', 'montant', 'devise', 'statut', 'soumise_par', 'date_soumission', 'decision_par', 'date_decision', 'commentaire_decision')

    def has_add_permission(self, request, obj=None):
        return False


class ChallengeWorkSubmissionInline(admin.TabularInline):
    model = ChallengeWorkSubmission
    extra = 0
    can_delete = False
    show_change_link = True
    readonly_fields = ('version', 'travail', 'statut', 'retour', 'date_soumission', 'date_evaluation', 'evalue_par')

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ChallengeParticipation)
class ChallengeParticipationAdmin(admin.ModelAdmin):
    list_display = ('participant', 'challenge', 'paiement_statut', 'travail_statut', 'date_inscription', 'date_soumission')
    list_filter = ('paiement_statut', 'travail_statut', 'challenge')
    search_fields = ('participant__username', 'participant__email', 'challenge__titre', 'reference_paiement')
    autocomplete_fields = ('participant', 'challenge')
    readonly_fields = (
        'participant', 'challenge', 'paiement_statut', 'reference_paiement', 'travail', 'travail_statut',
        'date_inscription', 'date_soumission',
    )
    inlines = [ChallengePaymentAttemptInline, ChallengeWorkSubmissionInline]

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ChallengePaymentAttempt)
class ChallengePaymentAttemptAdmin(admin.ModelAdmin):
    list_display = ('reference', 'participation', 'montant', 'devise', 'statut', 'date_soumission', 'decision_par')
    list_filter = ('statut', 'devise', 'date_soumission')
    search_fields = ('reference', 'participation__participant__username', 'participation__participant__email', 'participation__challenge__titre')
    autocomplete_fields = ('participation',)
    readonly_fields = ('participation', 'reference', 'montant', 'devise', 'soumise_par', 'date_soumission', 'decision_par', 'date_decision')

    def save_model(self, request, obj, form, change):
        if not change:
            return
        ancien = ChallengePaymentAttempt.objects.get(pk=obj.pk)
        if obj.statut != ancien.statut:
            try:
                review_challenge_payment(
                    obj.pk,
                    statut=obj.statut,
                    actor=request.user,
                    commentaire=obj.commentaire_decision,
                )
            except (PermissionDenied, ValidationError) as error:
                self.message_user(request, str(error), level='ERROR')
            obj.refresh_from_db()

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ChallengeWorkSubmission)
class ChallengeWorkSubmissionAdmin(admin.ModelAdmin):
    list_display = ('participation', 'version', 'statut', 'date_soumission', 'date_evaluation', 'evalue_par')
    list_filter = ('statut', 'date_soumission', 'date_evaluation')
    search_fields = ('participation__participant__username', 'participation__participant__email', 'participation__challenge__titre', 'travail')
    autocomplete_fields = ('participation',)
    readonly_fields = ('participation', 'version', 'travail', 'date_soumission', 'date_evaluation', 'evalue_par')

    def save_model(self, request, obj, form, change):
        if not change:
            return
        ancien = ChallengeWorkSubmission.objects.get(pk=obj.pk)
        if obj.statut != ancien.statut or obj.retour != ancien.retour:
            try:
                review_challenge_work(
                    obj.pk,
                    statut=obj.statut,
                    retour=obj.retour,
                    actor=request.user,
                )
            except (PermissionDenied, ValidationError) as error:
                self.message_user(request, str(error), level='ERROR')
            obj.refresh_from_db()

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class TrainingSessionInline(admin.TabularInline):
    model = TrainingSession
    extra = 0
    fields = ('titre', 'type_session', 'date_debut', 'date_fin', 'format_formation', 'lieu', 'horaires', 'places_totales', 'places_restantes', 'status')


class FormationFAQInline(admin.TabularInline):
    model = FormationFAQ
    extra = 1
    fields = ('question', 'reponse', 'ordre', 'status')


@admin.register(Publication)
class PublicationAdmin(admin.ModelAdmin):
    list_display = ('titre', 'slug', 'status', 'date_actuel')
    list_filter = ('status', 'date_actuel')
    search_fields = ('titre', 'contexte', 'voir')


@admin.register(Information)
class InformationAdmin(admin.ModelAdmin):
    list_display = ('titre', 'type_programme', 'domaine', 'niveau', 'format_formation', 'lieu', 'status', 'date_pub')
    list_filter = ('status', 'type_programme', 'domaine', 'niveau', 'format_formation', 'date_pub')
    search_fields = ('titre', 'contenue', 'objectifs', 'lieu')
    inlines = [TrainingSessionInline, FormationFAQInline]


@admin.register(Cours)
class CoursAdmin(admin.ModelAdmin):
    list_display = ('titre', 'type_contenu', 'categorie', 'formateur', 'vues', 'workflow_status', 'date_pub')
    list_filter = ('type_contenu', 'categorie', 'workflow_status', 'date_pub')
    search_fields = ('titre', 'description')
    prepopulated_fields = {'slug': ('titre',)}
    readonly_fields = ('status', 'workflow_status')
    actions = ('publier_cours', 'refuser_cours')

    def save_model(self, request, obj, form, change):
        contenu_modifie = bool(change and any(field != 'vues' for field in form.changed_data))
        if contenu_modifie:
            obj.workflow_status = 'a_valider'
            obj.status = 0
        super().save_model(request, obj, form, change)
        if contenu_modifie:
            record_audit(request.user, obj, 'cours.modifie_et_soumis', {'statut': obj.workflow_status})

    @admin.action(description='Approuver et publier les cours sélectionnés')
    def publier_cours(self, request, queryset):
        self._changer_statut(request, queryset, 'publie')

    @admin.action(description='Refuser les cours sélectionnés')
    def refuser_cours(self, request, queryset):
        self._changer_statut(request, queryset, 'refuse')

    def _changer_statut(self, request, queryset, statut):
        for cours in queryset:
            try:
                set_course_workflow_status(cours.pk, statut=statut, actor=request.user)
            except (PermissionDenied, ValidationError) as error:
                self.message_user(request, f'{cours}: {error}', level='ERROR')


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ('nom', 'prenom', 'telephone', 'email', 'date_creation')
    search_fields = ('nom', 'prenom', 'telephone', 'email')


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ('titre', 'lien', 'auteur', 'status', 'date_publication')
    list_filter = ('status', 'date_publication')
    search_fields = ('titre', 'contenu')
    prepopulated_fields = {'lien': ('titre',)}





@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('nom', 'cible', 'status', 'date_creation')
    list_filter = ('status', 'date_creation')
    search_fields = ('nom', 'message')
    list_editable = ('status',)
    actions = ['approuver']

    def cible(self, obj):
        return obj.publication or obj.article
    cible.short_description = "Publié sur"

    @admin.action(description="Approuver les commentaires sélectionnés")
    def approuver(self, request, queryset):
        queryset.update(status=1)


@admin.register(Candidature)
class CandidatureAdmin(admin.ModelAdmin):
    list_display = ('prenom', 'nom', 'formation', 'session', 'email', 'statut', 'date_creation')
    list_filter = ('statut', 'formation', 'date_creation')
    search_fields = ('prenom', 'nom', 'email', 'reference', 'formation__titre')
    fields = (
        'reference', 'formation', 'session', 'utilisateur', 'nom', 'prenom', 'email',
        'telephone', 'motivation', 'document_download_link', 'statut', 'place_retenue',
        'date_creation', 'date_modification',
    )
    readonly_fields = ('reference', 'document_download_link', 'date_creation', 'date_modification', 'place_retenue')
    autocomplete_fields = ('formation', 'session')

    @admin.display(description='Document PDF')
    def document_download_link(self, obj):
        if not obj.document:
            return 'Aucun document'
        return format_html(
            '<a href="{}">Télécharger le document PDF</a>',
            reverse('candidature_document_download', args=[obj.pk]),
        )

    def save_model(self, request, obj, form, change):
        if not change:
            statut_demande = obj.statut
            session_demandee = obj.session_id
            formation_demandee = obj.formation_id
            obj.statut = 'recue'
            super().save_model(request, obj, form, change)
            record_audit(request.user, obj, 'candidature.creee', {'statut': obj.statut})
            if statut_demande != 'recue':
                try:
                    transition_candidature(
                        obj.pk,
                        statut=statut_demande,
                        actor=request.user,
                        session_id=session_demandee,
                        formation_id=formation_demandee,
                    )
                except (PermissionDenied, ValidationError) as error:
                    self.message_user(request, str(error), level='ERROR')
                    obj.statut = 'recue'
                    obj.place_retenue = False
                else:
                    obj.refresh_from_db()
            return

        ancienne = Candidature.objects.get(pk=obj.pk)
        champs_dossier_modifies = [
            field for field in form.changed_data
            if field not in {'statut', 'session', 'formation'}
        ]
        try:
            mise_a_jour = transition_candidature(
                obj.pk,
                statut=obj.statut,
                actor=request.user,
                session_id=obj.session_id,
                formation_id=obj.formation_id,
            )
            obj.place_retenue = mise_a_jour.place_retenue
        except (PermissionDenied, ValidationError) as error:
            self.message_user(request, str(error), level='ERROR')
            obj.statut = ancienne.statut
            obj.session_id = ancienne.session_id
            obj.formation_id = ancienne.formation_id
            obj.place_retenue = ancienne.place_retenue
        super().save_model(request, obj, form, change)
        if champs_dossier_modifies:
            record_audit(request.user, obj, 'candidature.dossier_modifie', {
                'champs': champs_dossier_modifies,
            })

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TrainingSession)
class TrainingSessionAdmin(admin.ModelAdmin):
    list_display = ('titre', 'formation', 'type_session', 'date_debut', 'format_formation', 'places_restantes', 'status')
    list_filter = ('status', 'type_session', 'format_formation', 'date_debut')
    search_fields = ('titre', 'formation__titre', 'lieu')
    autocomplete_fields = ('formation',)


@admin.register(SessionReservation)
class SessionReservationAdmin(admin.ModelAdmin):
    list_display = ('nom', 'email', 'session', 'date_creation')
    list_filter = ('session__type_session', 'date_creation')
    search_fields = ('nom', 'email', 'session__formation__titre')
    autocomplete_fields = ('session',)
    readonly_fields = ('date_creation',)


@admin.register(DemandeAideFinanciere)
class DemandeAideFinanciereAdmin(admin.ModelAdmin):
    list_display = ('prenom', 'nom', 'formation', 'montant_souhaite', 'statut', 'date_creation')
    list_filter = ('statut', 'formation', 'date_creation')
    search_fields = ('prenom', 'nom', 'email', 'formation__titre')
    autocomplete_fields = ('formation',)
    readonly_fields = ('date_creation',)


@admin.register(BlogCategory)
class BlogCategoryAdmin(admin.ModelAdmin):
    list_display = ('nom', 'slug', 'status')
    list_filter = ('status',)
    search_fields = ('nom', 'description')
    prepopulated_fields = {'slug': ('nom',)}


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'ville', 'visible', 'date_modification')
    list_filter = ('role', 'visible')
    search_fields = ('user__username', 'user__email', 'user__first_name', 'user__last_name', 'ville')
    autocomplete_fields = ('user',)
    readonly_fields = ('role',)


@admin.register(TrainerProfile)
class TrainerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'titre', 'status')
    list_filter = ('status',)
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'domaines')
    autocomplete_fields = ('user',)
    readonly_fields = ('status',)


@admin.register(BusinessProfile)
class BusinessProfileAdmin(admin.ModelAdmin):
    list_display = ('nom', 'user', 'ville', 'verifiee', 'date_creation')
    list_filter = ('verifiee', 'ville')
    search_fields = ('nom', 'email', 'user__username', 'ville')
    autocomplete_fields = ('user',)
    prepopulated_fields = {'slug': ('nom',)}

    def get_readonly_fields(self, request, obj=None):
        return ('user',) if obj else ()

    def save_model(self, request, obj, form, change):
        if not change:
            obj.verifiee = False
            super().save_model(request, obj, form, change)
            return
        ancienne = BusinessProfile.objects.get(pk=obj.pk)
        champs_modifies = [field for field in form.changed_data if field != 'verifiee']
        if champs_modifies:
            verification_demandee = obj.verifiee
            obj.verifiee = ancienne.verifiee
            super().save_model(request, obj, form, change)
            if ancienne.verifiee:
                try:
                    set_business_profile_verification(
                        obj.pk,
                        verifiee=False,
                        actor=request.user,
                    )
                except (PermissionDenied, ValidationError) as error:
                    self.message_user(request, str(error), level='ERROR')
            obj.refresh_from_db()
            record_audit(request.user, obj, 'entreprise.profil_modifie_admin', {
                'champs': champs_modifies,
            })
            if ancienne.verifiee or verification_demandee:
                self.message_user(
                    request,
                    'La modification du profil annule sa vérification; les offres publiées doivent être revues.',
                    level='WARNING',
                )
            return
        if obj.verifiee != ancienne.verifiee:
            nouvelle_verification = obj.verifiee
            obj.verifiee = ancienne.verifiee
            super().save_model(request, obj, form, change)
            try:
                set_business_profile_verification(
                    obj.pk,
                    verifiee=nouvelle_verification,
                    actor=request.user,
                )
            except (PermissionDenied, ValidationError) as error:
                self.message_user(request, str(error), level='ERROR')
            obj.refresh_from_db()
            return
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(JobPosting)
class JobPostingAdmin(admin.ModelAdmin):
    list_display = ('titre', 'entreprise', 'type_offre', 'domaine', 'statut', 'date_limite')
    list_filter = ('statut', 'type_offre', 'domaine', 'format_emploi')
    search_fields = ('titre', 'description', 'entreprise__nom')
    autocomplete_fields = ('entreprise',)
    prepopulated_fields = {'slug': ('titre',)}
    actions = ('publier_offres', 'refuser_offres')

    def save_model(self, request, obj, form, change):
        contenu_modifie = any(field != 'statut' for field in form.changed_data)
        if not change:
            statut_demande = obj.statut
            obj.statut = 'a_valider'
            super().save_model(request, obj, form, change)
            record_audit(request.user, obj, 'offre.creee_admin', {'statut': obj.statut})
            if statut_demande != 'a_valider':
                self._changer_statut(request, [obj], statut_demande)
            return

        ancienne = JobPosting.objects.get(pk=obj.pk)
        if contenu_modifie:
            obj.statut = 'a_valider'
            super().save_model(request, obj, form, change)
            record_audit(request.user, obj, 'offre.modifiee_et_soumise', {'ancien_statut': ancienne.statut})
            if ancienne.statut != 'a_valider':
                self.message_user(request, 'Le contenu modifié repasse en validation avant toute republication.')
            return

        if obj.statut != ancienne.statut:
            self._changer_statut(request, [obj], obj.statut)
            obj.refresh_from_db()
            return
        super().save_model(request, obj, form, change)

    @admin.action(description='Approuver et publier les offres sélectionnées')
    def publier_offres(self, request, queryset):
        self._changer_statut(request, queryset, 'publiee')

    @admin.action(description='Refuser les offres sélectionnées')
    def refuser_offres(self, request, queryset):
        self._changer_statut(request, queryset, 'refusee')

    def _changer_statut(self, request, offres, statut):
        for offre in offres:
            try:
                set_job_posting_status(offre.pk, statut=statut, actor=request.user)
            except (PermissionDenied, ValidationError) as error:
                self.message_user(request, f'{offre}: {error}', level='ERROR')


@admin.register(JobApplication)
class JobApplicationAdmin(admin.ModelAdmin):
    list_display = ('candidat', 'offre', 'statut', 'date_creation')
    list_filter = ('statut', 'date_creation')
    search_fields = ('candidat__username', 'candidat__email', 'offre__titre')
    autocomplete_fields = ('candidat', 'offre')
    fields = ('offre', 'candidat', 'motivation', 'cv_download_link', 'statut', 'date_creation')
    readonly_fields = ('candidat', 'offre', 'motivation', 'cv_download_link', 'date_creation')

    @admin.display(description='CV PDF')
    def cv_download_link(self, obj):
        if not obj.cv:
            return 'Aucun CV'
        return format_html(
            '<a href="{}">Télécharger le CV PDF</a>',
            reverse('job_application_cv_download', args=[obj.pk]),
        )

    def save_model(self, request, obj, form, change):
        if not change:
            return
        ancienne = JobApplication.objects.get(pk=obj.pk)
        if obj.statut != ancienne.statut:
            try:
                transition_job_application(obj.pk, statut=obj.statut, actor=request.user)
            except (PermissionDenied, ValidationError) as error:
                self.message_user(request, str(error), level='ERROR')
            obj.refresh_from_db()

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ProjectCollaboratorInline(admin.TabularInline):
    model = ProjectCollaborator
    extra = 0
    can_delete = False
    fields = ('utilisateur', 'invite_par', 'statut', 'date_invitation', 'date_decision')
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ProjectSubmission)
class ProjectSubmissionAdmin(admin.ModelAdmin):
    list_display = ('titre', 'auteur', 'formation', 'statut', 'date_creation')
    list_filter = ('statut', 'date_creation')
    search_fields = ('titre', 'description', 'auteur__username')
    autocomplete_fields = ('auteur', 'formation')
    prepopulated_fields = {'slug': ('titre',)}
    inlines = [ProjectCollaboratorInline]


@admin.register(Community)
class CommunityAdmin(admin.ModelAdmin):
    list_display = ('nom', 'formation', 'privee', 'status', 'date_creation')
    list_filter = ('status', 'privee')
    search_fields = ('nom', 'description')
    autocomplete_fields = ('formation',)
    prepopulated_fields = {'slug': ('nom',)}


@admin.register(CommunityMembership)
class CommunityMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'community', 'date_adhesion')
    list_filter = ('community', 'date_adhesion')
    search_fields = ('user__username', 'community__nom')
    autocomplete_fields = ('user', 'community')
    readonly_fields = ('date_adhesion',)


@admin.register(CommunityAccessRequest)
class CommunityAccessRequestAdmin(admin.ModelAdmin):
    list_display = ('communaute', 'utilisateur', 'statut', 'date_creation', 'date_revue', 'revue_par')
    list_filter = ('statut', 'communaute', 'date_creation')
    search_fields = ('communaute__nom', 'utilisateur__username', 'utilisateur__email')
    autocomplete_fields = ('communaute', 'utilisateur', 'revue_par')
    readonly_fields = ('communaute', 'utilisateur', 'statut', 'date_creation', 'date_modification', 'date_revue', 'revue_par')
    actions = ('approuver_demandes', 'refuser_demandes')

    @admin.action(description='Approuver les demandes d’accès sélectionnées')
    def approuver_demandes(self, request, queryset):
        self._traiter_demandes(request, queryset, 'approuvee')

    @admin.action(description='Refuser les demandes d’accès sélectionnées')
    def refuser_demandes(self, request, queryset):
        self._traiter_demandes(request, queryset, 'refusee')

    def _traiter_demandes(self, request, queryset, statut):
        for demande in queryset:
            try:
                review_community_access_request(demande.pk, statut=statut, actor=request.user)
            except (PermissionDenied, ValidationError) as error:
                self.message_user(request, f'{demande}: {error}', level='ERROR')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CommunityPost)
class CommunityPostAdmin(admin.ModelAdmin):
    list_display = ('auteur', 'community', 'date_creation')
    list_filter = ('community', 'date_creation')
    search_fields = ('contenu', 'auteur__username', 'community__nom')
    autocomplete_fields = ('auteur', 'community')
    readonly_fields = ('date_creation',)


@admin.register(ProfessionalEvent)
class ProfessionalEventAdmin(admin.ModelAdmin):
    list_display = ('titre', 'date_debut', 'lieu', 'places', 'places_restantes', 'status')
    list_filter = ('status', 'format_evenement', 'date_debut')
    search_fields = ('titre', 'description', 'lieu', 'organisateur')
    prepopulated_fields = {'slug': ('titre',)}


@admin.register(EventRegistration)
class EventRegistrationAdmin(admin.ModelAdmin):
    list_display = ('participant', 'evenement', 'status', 'date_inscription')
    list_filter = ('status', 'evenement', 'date_inscription')
    search_fields = ('participant__username', 'evenement__titre')
    autocomplete_fields = ('participant', 'evenement')
    readonly_fields = ('date_inscription',)


@admin.register(CourseEvaluation)
class CourseEvaluationAdmin(admin.ModelAdmin):
    list_display = ('cours', 'auteur', 'note', 'status', 'date_creation')
    list_filter = ('status', 'note', 'date_creation')
    search_fields = ('cours__titre', 'auteur__username', 'commentaire')
    autocomplete_fields = ('cours', 'auteur')
    readonly_fields = ('date_creation',)


@admin.register(Credential)
class CredentialAdmin(admin.ModelAdmin):
    list_display = ('nom', 'status', 'partenaire')
    list_filter = ('status', 'partenaire')
    search_fields = ('nom', 'description')
    filter_horizontal = ('cours', 'formations')


@admin.register(UserCredential)
class UserCredentialAdmin(admin.ModelAdmin):
    list_display = ('utilisateur', 'certification', 'date_obtention', 'reference')
    search_fields = ('utilisateur__username', 'certification__nom', 'reference')
    autocomplete_fields = ('utilisateur', 'certification')
    readonly_fields = ('date_obtention', 'reference')


@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display = ('nom', 'status')
    list_filter = ('status',)
    search_fields = ('nom', 'description')


@admin.register(ImpactMetric)
class ImpactMetricAdmin(admin.ModelAdmin):
    list_display = ('titre', 'valeur', 'unite', 'ordre', 'status')
    list_filter = ('status',)
    search_fields = ('titre',)
    ordering = ('ordre',)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('destinataire', 'type_notification', 'titre', 'lue', 'date_creation')
    list_filter = ('type_notification', 'lue', 'date_creation')
    search_fields = ('destinataire__username', 'titre', 'message')
    autocomplete_fields = ('destinataire',)
    readonly_fields = ('date_creation',)


@admin.register(LearnerProjectRequest)
class LearnerProjectRequestAdmin(admin.ModelAdmin):
    list_display = ('organisation', 'nom', 'email', 'type_projet', 'traite', 'date_creation')
    list_filter = ('traite', 'date_creation')
    search_fields = ('organisation', 'nom', 'email', 'description')
    readonly_fields = ('date_creation',)
    list_editable = ('traite',)


@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ('nom_affiche', 'formation', 'statut_professionnel', 'status', 'date_creation')
    list_filter = ('status', 'formation', 'date_creation')
    search_fields = ('nom_affiche', 'parcours', 'statut_professionnel')
    autocomplete_fields = ('auteur', 'formation')
    readonly_fields = ('date_creation',)


@admin.register(Initiative)
class InitiativeAdmin(admin.ModelAdmin):
    list_display = ('titre', 'date_debut', 'date_fin', 'lieu', 'status')
    list_filter = ('status', 'date_debut')
    search_fields = ('titre', 'description', 'lieu')
    prepopulated_fields = {'slug': ('titre',)}


@admin.register(Campus)
class CampusAdmin(admin.ModelAdmin):
    list_display = ('nom', 'ville', 'status')
    list_filter = ('status', 'ville')
    search_fields = ('nom', 'ville', 'adresse')
    filter_horizontal = ('formations',)
    prepopulated_fields = {'slug': ('nom',)}


@admin.register(AnnualReport)
class AnnualReportAdmin(admin.ModelAdmin):
    list_display = ('annee', 'apprenants_formes', 'formations_terminees', 'taux_reussite', 'status')
    list_filter = ('status', 'annee')
    search_fields = ('resume',)


@admin.register(LearningProgress)
class LearningProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'cours', 'is_completed', 'started_at', 'completed_at')
    list_filter = ('is_completed', 'started_at')
    search_fields = ('user__username', 'cours__titre')
    autocomplete_fields = ('user', 'cours')


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('sender', 'conversation', 'created_at', 'read_at')
    list_filter = ('created_at', 'read_at')
    search_fields = ('sender__username', 'content')
    autocomplete_fields = ('sender', 'conversation')
    readonly_fields = ('created_at',)


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('participant_one', 'participant_two', 'created_at', 'updated_at')
    search_fields = ('participant_one__username', 'participant_two__username')
    autocomplete_fields = ('participant_one', 'participant_two')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(FormationFAQ)
class FormationFAQAdmin(admin.ModelAdmin):
    list_display = ('question', 'formation', 'ordre', 'status')
    list_filter = ('status', 'formation')
    search_fields = ('question', 'reponse', 'formation__titre')
    autocomplete_fields = ('formation',)


@admin.register(SocialPost)
class SocialPostAdmin(admin.ModelAdmin):
    list_display = ('auteur', 'status', 'date_creation')
    list_filter = ('status', 'date_creation')
    search_fields = ('auteur__username', 'auteur__first_name', 'auteur__last_name', 'contenu')
    autocomplete_fields = ('auteur',)
    readonly_fields = ('date_creation', 'date_modification')


@admin.register(FeedLike)
class FeedLikeAdmin(admin.ModelAdmin):
    list_display = ('user', 'post', 'publication', 'date_creation')
    search_fields = ('user__username', 'post__contenu', 'publication__titre')
    autocomplete_fields = ('user', 'post', 'publication')
    readonly_fields = ('date_creation',)


@admin.register(FeedComment)
class FeedCommentAdmin(admin.ModelAdmin):
    list_display = ('auteur', 'post', 'publication', 'date_creation')
    search_fields = ('auteur__username', 'contenu')
    autocomplete_fields = ('auteur', 'post', 'publication')
    readonly_fields = ('date_creation',)


@admin.register(Friendship)
class FriendshipAdmin(admin.ModelAdmin):
    list_display = ('person_one', 'person_two', 'requested_by', 'status', 'date_creation')
    list_filter = ('status', 'date_creation')
    search_fields = ('person_one__username', 'person_two__username', 'requested_by__username')
    autocomplete_fields = ('person_one', 'person_two', 'requested_by')
    readonly_fields = ('date_creation', 'date_acceptation')