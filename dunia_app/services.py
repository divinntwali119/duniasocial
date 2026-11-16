from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone

from .models import (
    CANDIDATURE_EMPLOI_STATUTS,
    CANDIDATURE_STATUTS,
    COURS_STATUTS,
    OFFRE_STATUTS,
    ChallengePaymentAttempt,
    ChallengeParticipation,
    ChallengeWorkSubmission,
    BusinessProfile,
    Candidature,
    CommunityAccessRequest,
    CommunityMembership,
    Cours,
    Friendship,
    JobApplication,
    JobPosting,
    RoleRequest,
    TrainerProfile,
    TrainingSession,
    AuditLog,
    Notification,
    ProjectCollaborator,
    ProjectSubmission,
)
from django.urls import reverse


_TERMINAL_CANDIDATURE_STATUTS = {'confirmee', 'refusee'}
_UNSET = object()


def _actor_can_manage(actor, permission):
    return bool(
        actor
        and actor.is_authenticated
        and (actor.is_superuser or actor.has_perm(permission))
    )


def has_approved_role(user, role):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    return RoleRequest.objects.filter(user=user, role=role, statut='approuve').exists()


def record_audit(actor, instance, action, details=None):
    if not instance.pk:
        return None
    if not actor or not getattr(actor, 'is_authenticated', False):
        actor = None
    return AuditLog.objects.create(
        actor=actor,
        content_type=ContentType.objects.get_for_model(instance, for_concrete_model=False),
        object_id=str(instance.pk),
        action=action,
        details=details or {},
    )


def request_role(user, role):
    if not user or not user.is_authenticated:
        raise PermissionDenied('Connectez-vous pour demander ce rôle.')
    if role not in dict(RoleRequest._meta.get_field('role').choices):
        raise ValidationError('Ce rôle ne peut pas être demandé.')

    demande, _ = RoleRequest.objects.get_or_create(
        user=user,
        role=role,
        defaults={'statut': 'en_attente'},
    )
    if demande.statut == 'approuve':
        return demande
    if demande.statut != 'en_attente':
        ancien_statut = demande.statut
        demande.statut = 'en_attente'
        demande.date_decision = None
        demande.decision_par = None
        demande.commentaire = ''
        demande.save(update_fields=['statut', 'date_decision', 'decision_par', 'commentaire'])
        record_audit(user, demande, 'role.demande_renouvelee', {'ancien_statut': ancien_statut})
    else:
        record_audit(user, demande, 'role.demande', {'role': role})
    return demande


@transaction.atomic
def review_role_request(demande_id, *, statut, actor, commentaire=''):
    if not _actor_can_manage(actor, 'dunia_app.change_rolerequest'):
        raise PermissionDenied('Seul un membre autorisé de l’équipe peut traiter cette demande.')
    if statut not in {'approuve', 'refuse'}:
        raise ValidationError('Décision de rôle invalide.')

    demande = RoleRequest.objects.select_for_update().select_related('user').get(pk=demande_id)
    ancien_statut = demande.statut
    if ancien_statut == statut:
        return demande

    demande.statut = statut
    demande.decision_par = actor
    demande.date_decision = timezone.now()
    demande.commentaire = commentaire[:500]
    demande.save(update_fields=['statut', 'decision_par', 'date_decision', 'commentaire'])

    if demande.role == 'formateur':
        profile = TrainerProfile.objects.filter(user=demande.user).first()
        if profile:
            profile.status = 1 if statut == 'approuve' else 0
            profile.save(update_fields=['status'])
        if statut == 'refuse':
            cours_queryset = Cours.objects.select_for_update().filter(
                formateur=demande.user,
                workflow_status='publie',
            )
            for cours in cours_queryset:
                cours.workflow_status = 'a_valider'
                cours.status = 0
                cours.save(update_fields=['workflow_status', 'status', 'date_modif'])
                record_audit(actor, cours, 'cours.revalidation_requise', {
                    'raison': 'role_formateur_retire',
                })
    elif demande.role == 'entreprise' and statut == 'refuse':
        entreprises = BusinessProfile.objects.filter(user=demande.user)
        for entreprise in entreprises:
            _renvoyer_offres_en_validation(entreprise, actor=actor)

    record_audit(actor, demande, 'role.decision', {
        'ancien_statut': ancien_statut,
        'nouveau_statut': statut,
        'commentaire': demande.commentaire,
    })
    return demande


@transaction.atomic
def review_community_access_request(demande_id, *, statut, actor):
    if not _actor_can_manage(actor, 'dunia_app.change_communityaccessrequest'):
        raise PermissionDenied('Seul un membre autorisé de l’équipe peut traiter cette demande.')
    if statut not in {'approuvee', 'refusee'}:
        raise ValidationError('Décision d’accès invalide.')

    demande = CommunityAccessRequest.objects.select_for_update().select_related(
        'communaute', 'utilisateur'
    ).get(pk=demande_id)
    if demande.statut == statut:
        return demande
    if demande.statut != 'en_attente':
        raise ValidationError('Cette demande a déjà été traitée.')

    demande.statut = statut
    demande.revue_par = actor
    demande.date_revue = timezone.now()
    demande.save(update_fields=['statut', 'revue_par', 'date_revue', 'date_modification'])

    if statut == 'approuvee':
        CommunityMembership.objects.get_or_create(
            community=demande.communaute,
            user=demande.utilisateur,
        )

    decision = 'acceptée' if statut == 'approuvee' else 'refusée'
    Notification.objects.create(
        destinataire=demande.utilisateur,
        type_notification='communaute',
        titre='Demande d’accès traitée',
        message=f"Votre demande pour {demande.communaute.nom} a été {decision}.",
        url=reverse('communaute_detail', args=[demande.communaute.slug]),
    )
    record_audit(actor, demande, 'communaute.demande_acces_traitee', {
        'statut': statut,
        'communaute_id': demande.communaute_id,
        'utilisateur_id': demande.utilisateur_id,
    })
    return demande


@transaction.atomic
def invite_project_collaborators(project_id, users, *, actor):
    if not actor or not actor.is_authenticated:
        raise PermissionDenied('Connectez-vous pour inviter des coéquipiers.')
    project = ProjectSubmission.objects.select_for_update().get(pk=project_id, auteur=actor)
    users = list(users)
    if len(users) > 8:
        raise ValidationError('Un projet peut inviter au maximum 8 coéquipiers à la fois.')
    invitations_creees = 0
    for user in users:
        if user.pk == actor.pk:
            raise ValidationError('Vous ne pouvez pas vous inviter vous-même.')
        if not user.is_active or not Friendship.objects.filter(
            status=Friendship.ACCEPTED,
        ).filter(
            Q(person_one=actor, person_two=user) | Q(person_one=user, person_two=actor)
        ).exists():
            raise ValidationError('Vous ne pouvez inviter que des amis Dunia actifs.')
        invitation = ProjectCollaborator.objects.select_for_update().filter(
            projet=project,
            utilisateur=user,
        ).first()
        if invitation and invitation.statut == 'acceptee':
            continue
        if invitation and invitation.statut == 'en_attente':
            continue
        if invitation:
            invitation.statut = 'en_attente'
            invitation.invite_par = actor
            invitation.date_invitation = timezone.now()
            invitation.date_decision = None
            invitation.save(update_fields=['statut', 'invite_par', 'date_invitation', 'date_decision'])
        else:
            invitation = ProjectCollaborator.objects.create(
                projet=project,
                utilisateur=user,
                invite_par=actor,
            )
        Notification.objects.create(
            destinataire=user,
            type_notification='projet',
            titre='Invitation à collaborer',
            message=f"{actor.get_full_name() or actor.get_username()} vous invite à collaborer sur « {project.titre} ».",
            url=f"{reverse('tableau_bord')}#projets",
        )
        record_audit(actor, invitation, 'projet.collaborateur_invite', {
            'projet_id': project.pk,
            'utilisateur_id': user.pk,
        })
        invitations_creees += 1
    return invitations_creees


@transaction.atomic
def respond_to_project_invitation(invitation_id, *, statut, actor):
    if not actor or not actor.is_authenticated:
        raise PermissionDenied('Connectez-vous pour répondre à cette invitation.')
    if statut not in {'acceptee', 'refusee'}:
        raise ValidationError('Réponse à l’invitation invalide.')
    invitation = ProjectCollaborator.objects.select_for_update().select_related(
        'projet', 'projet__auteur', 'utilisateur'
    ).filter(pk=invitation_id, utilisateur=actor).first()
    if not invitation:
        raise PermissionDenied('Cette invitation ne vous appartient pas.')
    if invitation.statut != 'en_attente':
        raise ValidationError('Cette invitation a déjà été traitée.')
    invitation.statut = statut
    invitation.date_decision = timezone.now()
    invitation.save(update_fields=['statut', 'date_decision'])

    libelle = 'acceptée' if statut == 'acceptee' else 'refusée'
    Notification.objects.create(
        destinataire=invitation.projet.auteur,
        type_notification='projet',
        titre='Réponse à une invitation de projet',
        message=f"{actor.get_full_name() or actor.get_username()} a {libelle} l’invitation pour « {invitation.projet.titre} ».",
        url=f"{reverse('tableau_bord')}#projets",
    )
    record_audit(actor, invitation, 'projet.invitation_repondue', {
        'projet_id': invitation.projet_id,
        'statut': statut,
    })
    return invitation


@transaction.atomic
def set_course_workflow_status(cours_id, *, statut, actor):
    if not _actor_can_manage(actor, 'dunia_app.change_cours'):
        raise PermissionDenied('Seul un membre autorisé de l’équipe peut valider un cours.')
    if statut not in dict(COURS_STATUTS):
        raise ValidationError('Statut de cours invalide.')

    cours = Cours.objects.select_for_update().get(pk=cours_id)
    ancien_statut = cours.workflow_status
    if ancien_statut == statut:
        return cours
    cours.workflow_status = statut
    cours.status = 1 if statut == 'publie' else 0
    if statut == 'publie':
        cours.full_clean()
    cours.save(update_fields=['workflow_status', 'status', 'date_modif'])
    record_audit(actor, cours, 'cours.statut', {
        'ancien_statut': ancien_statut,
        'nouveau_statut': statut,
    })
    return cours


@transaction.atomic
def set_job_posting_status(offre_id, *, statut, actor):
    if not _actor_can_manage(actor, 'dunia_app.change_jobposting'):
        raise PermissionDenied('Seul un membre autorisé de l’équipe peut valider une offre.')
    if statut not in dict(OFFRE_STATUTS):
        raise ValidationError('Statut d’offre invalide.')

    offre = JobPosting.objects.select_for_update().select_related('entreprise__user').get(pk=offre_id)
    if statut == 'publiee':
        if not offre.entreprise.verifiee or not has_approved_role(offre.entreprise.user, 'entreprise'):
            raise ValidationError('L’organisation et le rôle entreprise doivent être approuvés avant la publication.')
        if offre.date_limite and offre.date_limite < timezone.localdate():
            raise ValidationError('Une offre expirée ne peut pas être publiée.')

    ancien_statut = offre.statut
    if ancien_statut == statut:
        return offre
    offre.statut = statut
    offre.save(update_fields=['statut', 'date_modification'])
    record_audit(actor, offre, 'offre.statut', {
        'ancien_statut': ancien_statut,
        'nouveau_statut': statut,
    })
    return offre


def _renvoyer_offres_en_validation(entreprise, *, actor):
    offres = JobPosting.objects.select_for_update().filter(
        entreprise=entreprise,
        statut='publiee',
    )
    for offre in offres:
        offre.statut = 'a_valider'
        offre.save(update_fields=['statut', 'date_modification'])
        record_audit(actor, offre, 'offre.revalidation_requise', {
            'raison': 'organisation_non_verifiee',
        })


@transaction.atomic
def set_business_profile_verification(entreprise_id, *, verifiee, actor):
    if not _actor_can_manage(actor, 'dunia_app.change_businessprofile'):
        raise PermissionDenied('Seul un membre autorisé de l’équipe peut vérifier une organisation.')

    entreprise = BusinessProfile.objects.select_for_update().get(pk=entreprise_id)
    ancienne_verification = entreprise.verifiee
    if ancienne_verification == verifiee:
        return entreprise
    entreprise.verifiee = verifiee
    entreprise.save(update_fields=['verifiee'])
    record_audit(actor, entreprise, 'entreprise.verification', {
        'ancienne_verification': ancienne_verification,
        'nouvelle_verification': verifiee,
    })
    if not verifiee:
        _renvoyer_offres_en_validation(entreprise, actor=actor)
    return entreprise


@transaction.atomic
def update_business_profile(entreprise_id, *, actor, changes):
    entreprise = BusinessProfile.objects.select_for_update().get(pk=entreprise_id)
    if (
        not actor
        or not actor.is_authenticated
        or entreprise.user_id != actor.pk
        or not has_approved_role(actor, 'entreprise')
    ):
        raise PermissionDenied('Seul le propriétaire dont le rôle entreprise est approuvé peut gérer ce profil.')

    champs_autorises = {'nom', 'description', 'logo', 'email', 'telephone', 'ville', 'site_web'}
    champs_modifies = []
    for champ, valeur in changes.items():
        if champ not in champs_autorises:
            raise ValidationError('Le formulaire contient un champ de profil non autorisé.')
        if getattr(entreprise, champ) != valeur:
            setattr(entreprise, champ, valeur)
            champs_modifies.append(champ)
    if not champs_modifies:
        return entreprise

    etait_verifiee = entreprise.verifiee
    champs_sauves = list(champs_modifies)
    if etait_verifiee:
        entreprise.verifiee = False
        champs_sauves.append('verifiee')
    entreprise.save(update_fields=champs_sauves)
    record_audit(actor, entreprise, 'entreprise.profil_modifie', {
        'champs': champs_modifies,
        'verification_reinitialisee': etait_verifiee,
    })
    if etait_verifiee:
        _renvoyer_offres_en_validation(entreprise, actor=actor)
    return entreprise


@transaction.atomic
def transition_job_application(application_id, *, statut, actor):
    if statut not in dict(CANDIDATURE_EMPLOI_STATUTS):
        raise ValidationError('Statut de candidature d’emploi invalide.')

    application = JobApplication.objects.select_for_update().select_related(
        'offre__entreprise__user',
    ).get(pk=application_id)
    entreprise = application.offre.entreprise
    if _actor_can_manage(actor, 'dunia_app.change_jobapplication'):
        pass
    elif (
        not actor
        or not actor.is_authenticated
        or entreprise.user_id != actor.pk
        or not entreprise.verifiee
        or not has_approved_role(actor, 'entreprise')
    ):
        raise PermissionDenied('Seule l’entreprise propriétaire approuvée peut traiter cette candidature.')

    ancien_statut = application.statut
    if ancien_statut == statut:
        return application
    application.statut = statut
    application.save(update_fields=['statut'])
    record_audit(actor, application, 'candidature_emploi.statut', {
        'ancien_statut': ancien_statut,
        'nouveau_statut': statut,
        'offre_id': application.offre_id,
    })
    return application


@transaction.atomic
def transition_candidature(candidature_id, *, statut, actor=None, session_id=_UNSET, formation_id=None, commentaire=''):
    if statut not in dict(CANDIDATURE_STATUTS):
        raise ValidationError('Statut de candidature invalide.')

    candidature = Candidature.objects.select_for_update().get(pk=candidature_id)
    ancien_statut = candidature.statut
    ancienne_session_id = candidature.session_id
    ancienne_formation_id = candidature.formation_id
    ancienne_place_retenue = candidature.place_retenue
    nouvelle_session_id = ancienne_session_id if session_id is _UNSET else session_id
    formation_id = formation_id or candidature.formation_id

    if ancien_statut in _TERMINAL_CANDIDATURE_STATUTS and statut != ancien_statut:
        if not _actor_can_manage(actor, 'dunia_app.change_candidature'):
            raise PermissionDenied('Seul un administrateur autorisé peut rouvrir une candidature clôturée.')

    session_changee = nouvelle_session_id != ancienne_session_id
    statut_change = statut != ancien_statut
    formation_changee = formation_id != ancienne_formation_id
    if not session_changee and not statut_change and not formation_changee:
        return candidature

    doit_retenir_place = statut == 'confirmee' and nouvelle_session_id is not None
    if session_changee or statut_change or formation_changee:
        if not _actor_can_manage(actor, 'dunia_app.change_candidature'):
            raise PermissionDenied('Seul un membre autorisé de l’équipe peut modifier une candidature.')
    if nouvelle_session_id is not None and not TrainingSession.objects.filter(
        pk=nouvelle_session_id,
        formation_id=formation_id,
    ).exists():
        raise ValidationError('La session choisie ne correspond pas à cette formation.')
    if ancienne_place_retenue and (not doit_retenir_place or session_changee):
        TrainingSession.objects.filter(
            pk=ancienne_session_id,
            places_restantes__lt=F('places_totales'),
        ).update(places_restantes=F('places_restantes') + 1)

    place_retenue = ancienne_place_retenue and doit_retenir_place and not session_changee
    if doit_retenir_place and (session_changee or not ancienne_place_retenue):
        session = TrainingSession.objects.filter(
            pk=nouvelle_session_id,
            formation_id=formation_id,
            type_session='cohorte',
            status=1,
            date_debut__gte=timezone.localdate(),
        ).first()
        if not session:
            raise ValidationError('La cohorte choisie est invalide, masquée ou déjà commencée.')
        places_maj = TrainingSession.objects.filter(
            pk=session.pk,
            places_restantes__gt=0,
        ).update(places_restantes=F('places_restantes') - 1)
        if not places_maj:
            raise ValidationError('Cette cohorte n’a plus de place disponible.')
        place_retenue = True

    candidature.formation_id = formation_id
    candidature.session_id = nouvelle_session_id
    candidature.statut = statut
    candidature.place_retenue = place_retenue
    candidature.save(update_fields=[
        'formation', 'session', 'statut', 'place_retenue', 'date_modification',
    ])

    if statut_change:
        record_audit(actor, candidature, 'candidature.statut', {
            'ancien_statut': ancien_statut,
            'nouveau_statut': statut,
            'commentaire': commentaire[:500],
        })
    if session_changee:
        record_audit(actor, candidature, 'candidature.session', {
            'ancienne_session_id': ancienne_session_id,
            'nouvelle_session_id': nouvelle_session_id,
        })
    if formation_changee:
        record_audit(actor, candidature, 'candidature.formation', {
            'ancienne_formation_id': ancienne_formation_id,
            'nouvelle_formation_id': formation_id,
        })
    return candidature


@transaction.atomic
def submit_challenge_payment(participation_id, *, reference, actor):
    participation = ChallengeParticipation.objects.select_for_update().select_related('challenge').get(
        pk=participation_id,
        participant=actor,
    )
    challenge = participation.challenge
    reference = (reference or '').strip()
    if challenge.est_gratuit:
        raise ValidationError('Ce défi est gratuit et ne nécessite pas de paiement.')
    if participation.paiement_statut == 'confirme':
        raise ValidationError('Le paiement de cette participation est déjà confirmé.')
    if participation.tentatives_paiement.filter(statut='en_attente').exists():
        raise ValidationError('Une tentative de paiement est déjà en attente de vérification.')
    if not reference:
        raise ValidationError('Saisissez la référence du paiement.')

    try:
        with transaction.atomic():
            attempt = ChallengePaymentAttempt.objects.create(
                participation=participation,
                reference=reference[:120],
                montant=challenge.prix,
                devise=challenge.devise,
                soumise_par=actor,
            )
    except IntegrityError as error:
        raise ValidationError('Une tentative de paiement est déjà en attente de vérification.') from error
    participation.paiement_statut = 'en_attente'
    participation.reference_paiement = attempt.reference
    participation.save(update_fields=['paiement_statut', 'reference_paiement'])
    record_audit(actor, attempt, 'defi.paiement_soumis', {
        'participation_id': participation.pk,
        'montant': str(attempt.montant),
        'devise': attempt.devise,
    })
    return attempt


@transaction.atomic
def review_challenge_payment(attempt_id, *, statut, actor, commentaire=''):
    if not _actor_can_manage(actor, 'dunia_app.change_challengepaymentattempt'):
        raise PermissionDenied('Seul un membre autorisé de l’équipe peut vérifier un paiement.')
    if statut not in {'confirme', 'refuse'}:
        raise ValidationError('Décision de paiement invalide.')

    attempt = ChallengePaymentAttempt.objects.select_for_update().select_related('participation').get(pk=attempt_id)
    participation = ChallengeParticipation.objects.select_for_update().select_related('challenge').get(
        pk=attempt.participation_id,
    )
    if attempt.statut != 'en_attente':
        raise ValidationError('Cette tentative de paiement a déjà été traitée.')
    tentatives_suivantes = ChallengePaymentAttempt.objects.filter(participation=participation)
    if attempt.date_soumission is None:
        tentatives_suivantes = tentatives_suivantes.filter(pk__gt=attempt.pk)
    else:
        tentatives_suivantes = tentatives_suivantes.filter(
            Q(date_soumission__gt=attempt.date_soumission)
            | Q(date_soumission=attempt.date_soumission, pk__gt=attempt.pk)
        )
    tentative_plus_recente = tentatives_suivantes.exists()
    if tentative_plus_recente:
        raise ValidationError('Traitez d’abord la tentative de paiement la plus récente.')

    ancien_statut = attempt.statut
    attempt.statut = statut
    attempt.decision_par = actor
    attempt.date_decision = timezone.now()
    attempt.commentaire_decision = commentaire[:500]
    attempt.save(update_fields=['statut', 'decision_par', 'date_decision', 'commentaire_decision'])

    participation.paiement_statut = statut
    participation.reference_paiement = attempt.reference
    participation.save(update_fields=['paiement_statut', 'reference_paiement'])

    record_audit(actor, attempt, 'defi.paiement_decision', {
        'ancien_statut': ancien_statut,
        'nouveau_statut': statut,
        'commentaire': attempt.commentaire_decision,
    })
    return attempt


@transaction.atomic
def submit_challenge_work(participation_id, *, travail, actor):
    participation = ChallengeParticipation.objects.select_for_update().select_related('challenge').get(
        pk=participation_id,
        participant=actor,
    )
    challenge = participation.challenge
    travail = (travail or '').strip()
    maintenant = timezone.now()
    if not travail:
        raise ValidationError('Ajoutez un lien ou une description avant de soumettre votre travail.')
    if len(travail) > 10000:
        raise ValidationError('Le travail ne peut dépasser 10 000 caractères.')
    if challenge.date_debut and maintenant < challenge.date_debut:
        raise ValidationError('La période de remise de ce défi n’a pas encore commencé.')
    if challenge.date_fin and maintenant > challenge.date_fin:
        raise ValidationError('La période de remise de ce défi est terminée.')
    if not challenge.est_gratuit and participation.paiement_statut != 'confirme':
        raise ValidationError('La remise est accessible après confirmation du paiement.')

    derniere = participation.soumissions_travail.order_by('-version', '-pk').first()
    if derniere and derniere.statut != 'a_corriger':
        raise ValidationError('Une nouvelle version est possible après un retour « à corriger ».')
    version = derniere.version + 1 if derniere else 1
    try:
        with transaction.atomic():
            soumission = ChallengeWorkSubmission.objects.create(
                participation=participation,
                version=version,
                travail=travail,
            )
    except IntegrityError as error:
        raise ValidationError('Une remise vient d’être enregistrée. Rechargez la page avant de réessayer.') from error
    participation.travail = travail
    participation.travail_statut = 'a_evaluer'
    participation.date_soumission = soumission.date_soumission
    participation.save(update_fields=['travail', 'travail_statut', 'date_soumission'])
    record_audit(actor, soumission, 'defi.travail_soumis', {
        'participation_id': participation.pk,
        'version': version,
    })
    return soumission


@transaction.atomic
def review_challenge_work(submission_id, *, statut, retour='', actor):
    if not _actor_can_manage(actor, 'dunia_app.change_challengeworksubmission'):
        raise PermissionDenied('Seul un membre autorisé de l’équipe peut évaluer un travail.')
    if statut not in {'valide', 'a_corriger'}:
        raise ValidationError('Décision d’évaluation invalide.')

    soumission = ChallengeWorkSubmission.objects.select_for_update().select_related('participation').get(
        pk=submission_id,
    )
    derniere = soumission.participation.soumissions_travail.order_by('-version', '-pk').first()
    if derniere is None or derniere.pk != soumission.pk:
        raise ValidationError('Seule la version la plus récente peut être évaluée.')
    if soumission.statut != 'a_evaluer':
        raise ValidationError('Cette version a déjà été évaluée; la décision et le retour sont conservés.')
    ancien_statut = soumission.statut
    soumission.statut = statut
    soumission.retour = retour[:4000]
    soumission.date_evaluation = timezone.now()
    soumission.evalue_par = actor
    soumission.save(update_fields=['statut', 'retour', 'date_evaluation', 'evalue_par'])

    participation = soumission.participation
    participation.travail_statut = statut
    participation.save(update_fields=['travail_statut'])
    record_audit(actor, soumission, 'defi.travail_evalue', {
        'ancien_statut': ancien_statut,
        'nouveau_statut': statut,
        'retour': soumission.retour,
    })
    return soumission
