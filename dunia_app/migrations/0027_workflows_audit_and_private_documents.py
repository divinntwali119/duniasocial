import django.core.validators
import django.db.models.deletion
import django.utils.timezone
import dunia_app.storage
import dunia_app.validators
from django.conf import settings
from django.db import migrations, models
from django.db.models import F, Q


def migrate_legacy_data(apps, schema_editor):
    database = schema_editor.connection.alias
    Cours = apps.get_model('dunia_app', 'Cours')
    TrainingSession = apps.get_model('dunia_app', 'TrainingSession')
    ProfessionalEvent = apps.get_model('dunia_app', 'ProfessionalEvent')
    Challenge = apps.get_model('dunia_app', 'Challenge')
    TrainerProfile = apps.get_model('dunia_app', 'TrainerProfile')
    BusinessProfile = apps.get_model('dunia_app', 'BusinessProfile')
    RoleRequest = apps.get_model('dunia_app', 'RoleRequest')
    ChallengeParticipation = apps.get_model('dunia_app', 'ChallengeParticipation')
    ChallengePaymentAttempt = apps.get_model('dunia_app', 'ChallengePaymentAttempt')
    ChallengeWorkSubmission = apps.get_model('dunia_app', 'ChallengeWorkSubmission')
    Candidature = apps.get_model('dunia_app', 'Candidature')

    invalid_data = {
        'sessions avec dates incohérentes': TrainingSession.objects.using(database).filter(
            date_fin__lt=F('date_debut'),
        ).count(),
        'sessions dépassant leur capacité': TrainingSession.objects.using(database).filter(
            places_restantes__gt=F('places_totales'),
        ).count(),
        'événements avec dates incohérentes': ProfessionalEvent.objects.using(database).filter(
            date_fin__lt=F('date_debut'),
        ).count(),
        'événements dépassant leur capacité': ProfessionalEvent.objects.using(database).filter(
            places__gt=0,
            places_restantes__gt=F('places'),
        ).count(),
        'défis avec dates incohérentes': Challenge.objects.using(database).filter(
            date_fin__lt=F('date_debut'),
            date_debut__isnull=False,
        ).count(),
        'défis avec prix négatif': Challenge.objects.using(database).filter(prix__lt=0).count(),
    }
    problems = [f'{label}: {count}' for label, count in invalid_data.items() if count]
    if problems:
        raise RuntimeError(
            'Migration annulée : corrigez explicitement les données incompatibles avant de réessayer ('
            + '; '.join(problems)
            + ').'
        )

    # Keep the existing public state when the new workflow field is introduced.
    Cours.objects.using(database).filter(status=1).update(workflow_status='publie')
    Candidature.objects.using(database).filter(
        statut='confirmee',
        session__isnull=False,
    ).update(place_retenue=True)

    # Preserve pre-existing approved accounts so the new gates do not block them.
    trainer_ids = TrainerProfile.objects.using(database).filter(status=1).values_list('user_id', flat=True)
    for user_id in trainer_ids.iterator():
        RoleRequest.objects.using(database).get_or_create(
            user_id=user_id,
            role='formateur',
            defaults={
                'statut': 'approuve',
                'commentaire': 'Approbation historique importée depuis un profil formateur actif.',
            },
        )

    company_user_ids = BusinessProfile.objects.using(database).filter(
        verifiee=True,
    ).values_list('user_id', flat=True).distinct()
    for user_id in company_user_ids.iterator():
        RoleRequest.objects.using(database).get_or_create(
            user_id=user_id,
            role='entreprise',
            defaults={
                'statut': 'approuve',
                'commentaire': 'Approbation historique importée depuis une organisation vérifiée.',
            },
        )

    payment_statuses = {'en_attente', 'confirme', 'refuse'}
    work_statuses = {'a_evaluer', 'valide', 'a_corriger'}
    participations = ChallengeParticipation.objects.using(database).all().values(
        'pk',
        'participant_id',
        'paiement_statut',
        'reference_paiement',
        'travail',
        'travail_statut',
        'date_soumission',
    )
    for participation in participations.iterator():
        reference = (participation['reference_paiement'] or '').strip()
        if reference and not ChallengePaymentAttempt.objects.using(database).filter(
            participation_id=participation['pk'],
        ).exists():
            old_status = participation['paiement_statut']
            status = old_status if old_status in payment_statuses else 'en_attente'
            comment = ''
            if status != 'en_attente':
                comment = 'Décision historique importée; la date, le montant et le décideur d’origine ne sont pas disponibles.'
            ChallengePaymentAttempt.objects.using(database).create(
                participation_id=participation['pk'],
                reference=reference[:120],
                montant=None,
                devise='',
                statut=status,
                soumise_par_id=participation['participant_id'],
                date_soumission=None,
                commentaire_decision=comment,
                historique_importe=True,
            )
            if status != old_status:
                ChallengeParticipation.objects.using(database).filter(
                    pk=participation['pk'],
                ).update(paiement_statut=status)

        work = participation['travail'] or ''
        old_submission_date = participation['date_soumission']
        if (work.strip() or old_submission_date) and not ChallengeWorkSubmission.objects.using(database).filter(
            participation_id=participation['pk'],
        ).exists():
            old_status = participation['travail_statut']
            status = old_status if old_status in work_statuses else 'a_evaluer'
            submission = ChallengeWorkSubmission.objects.using(database).create(
                participation_id=participation['pk'],
                version=1,
                travail=work,
                statut=status,
                historique_importe=True,
            )
            if old_submission_date:
                ChallengeWorkSubmission.objects.using(database).filter(pk=submission.pk).update(
                    date_soumission=old_submission_date,
                )
            else:
                ChallengeWorkSubmission.objects.using(database).filter(pk=submission.pk).update(
                    date_soumission=None,
                )
            if status != old_status:
                ChallengeParticipation.objects.using(database).filter(
                    pk=participation['pk'],
                ).update(travail_statut=status)


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('dunia_app', '0026_alter_challenge_prix'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('object_id', models.CharField(max_length=64)),
                ('action', models.CharField(max_length=80)),
                ('details', models.JSONField(blank=True, default=dict)),
                ('date_creation', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='evenements_audit',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('content_type', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='dunia_audit_logs',
                    to='contenttypes.contenttype',
                )),
            ],
            options={'ordering': ['-date_creation', '-pk']},
        ),
        migrations.CreateModel(
            name='ChallengePaymentAttempt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reference', models.CharField(max_length=120)),
                ('montant', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('devise', models.CharField(blank=True, max_length=3)),
                ('statut', models.CharField(
                    choices=[('en_attente', 'À confirmer'), ('confirme', 'Confirmé'), ('refuse', 'Refusé')],
                    default='en_attente',
                    max_length=16,
                )),
                ('date_soumission', models.DateTimeField(blank=True, default=django.utils.timezone.now, null=True)),
                ('date_decision', models.DateTimeField(blank=True, null=True)),
                ('commentaire_decision', models.CharField(blank=True, max_length=500)),
                ('historique_importe', models.BooleanField(default=False, editable=False)),
                ('decision_par', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='decisions_tentatives_paiement',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('participation', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='tentatives_paiement',
                    to='dunia_app.challengeparticipation',
                )),
                ('soumise_par', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='tentatives_paiement_soumises',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['-date_soumission', '-pk']},
        ),
        migrations.CreateModel(
            name='ChallengeWorkSubmission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('version', models.PositiveIntegerField()),
                ('travail', models.TextField(max_length=10000)),
                ('statut', models.CharField(
                    choices=[('a_evaluer', 'À évaluer'), ('valide', 'Validé'), ('a_corriger', 'À corriger')],
                    default='a_evaluer',
                    max_length=16,
                )),
                ('retour', models.TextField(blank=True, max_length=4000)),
                ('date_soumission', models.DateTimeField(blank=True, default=django.utils.timezone.now, null=True)),
                ('date_evaluation', models.DateTimeField(blank=True, null=True)),
                ('historique_importe', models.BooleanField(default=False, editable=False)),
                ('evalue_par', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='soumissions_travail_evaluees',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('participation', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='soumissions_travail',
                    to='dunia_app.challengeparticipation',
                )),
            ],
            options={'ordering': ['-version', '-pk']},
        ),
        migrations.CreateModel(
            name='RoleRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('formateur', 'Formateur'), ('entreprise', 'Entreprise')], max_length=20)),
                ('statut', models.CharField(
                    choices=[('en_attente', 'En attente'), ('approuve', 'Approuvée'), ('refuse', 'Refusée')],
                    default='en_attente',
                    max_length=20,
                )),
                ('date_demande', models.DateTimeField(auto_now_add=True)),
                ('date_decision', models.DateTimeField(blank=True, null=True)),
                ('commentaire', models.CharField(blank=True, max_length=500)),
                ('decision_par', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='decisions_demandes_role',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='demandes_role',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['-date_demande']},
        ),
        migrations.AddField(
            model_name='candidature',
            name='place_retenue',
            field=models.BooleanField(default=False, editable=False),
        ),
        migrations.AddField(
            model_name='cours',
            name='workflow_status',
            field=models.CharField(
                choices=[('brouillon', 'Brouillon'), ('a_valider', 'À valider'), ('publie', 'Publié'), ('refuse', 'Refusé')],
                default='brouillon',
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='candidature',
            name='document',
            field=models.FileField(
                blank=True,
                null=True,
                storage=dunia_app.storage.PrivateMediaStorage(),
                upload_to='candidatures/documents/',
                validators=[
                    django.core.validators.FileExtensionValidator(['pdf']),
                    dunia_app.validators.validate_pdf_signature,
                    dunia_app.validators.MaxFileSizeValidator(5 * 1024 * 1024),
                ],
            ),
        ),
        migrations.AlterField(
            model_name='cours',
            name='audio',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='cours_audio/',
                validators=[
                    django.core.validators.FileExtensionValidator(['mp3', 'm4a', 'ogg', 'wav']),
                    dunia_app.validators.MaxFileSizeValidator(50 * 1024 * 1024),
                ],
            ),
        ),
        migrations.AlterField(
            model_name='cours',
            name='miniature',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to='cours_miniature/',
                validators=[dunia_app.validators.MaxFileSizeValidator(5 * 1024 * 1024)],
            ),
        ),
        migrations.AlterField(
            model_name='cours',
            name='pdf',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='cours_pdf/',
                validators=[
                    django.core.validators.FileExtensionValidator(['pdf']),
                    dunia_app.validators.validate_pdf_signature,
                    dunia_app.validators.MaxFileSizeValidator(10 * 1024 * 1024),
                ],
            ),
        ),
        migrations.AlterField(
            model_name='cours',
            name='video',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='cours_video/',
                validators=[
                    django.core.validators.FileExtensionValidator(['mp4', 'webm', 'mov']),
                    dunia_app.validators.MaxFileSizeValidator(100 * 1024 * 1024),
                ],
            ),
        ),
        migrations.AlterField(
            model_name='jobapplication',
            name='cv',
            field=models.FileField(
                storage=dunia_app.storage.PrivateMediaStorage(),
                upload_to='candidatures_emploi/cv/',
                validators=[
                    django.core.validators.FileExtensionValidator(['pdf']),
                    dunia_app.validators.validate_pdf_signature,
                    dunia_app.validators.MaxFileSizeValidator(5 * 1024 * 1024),
                ],
            ),
        ),
        migrations.AlterField(
            model_name='jobposting',
            name='statut',
            field=models.CharField(
                choices=[
                    ('brouillon', 'Brouillon'),
                    ('a_valider', 'À valider'),
                    ('publiee', 'Publiée'),
                    ('refusee', 'Refusée'),
                    ('cloturee', 'Clôturée'),
                ],
                default='a_valider',
                max_length=20,
            ),
        ),
        migrations.RunPython(migrate_legacy_data, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='challenge',
            constraint=models.CheckConstraint(
                condition=Q(date_fin__isnull=True) | Q(date_debut__isnull=True) | Q(date_fin__gte=F('date_debut')),
                name='challenge_end_after_start',
            ),
        ),
        migrations.AddConstraint(
            model_name='challenge',
            constraint=models.CheckConstraint(condition=Q(prix__gte=0), name='challenge_price_nonnegative'),
        ),
        migrations.AddConstraint(
            model_name='cours',
            constraint=models.CheckConstraint(
                condition=(
                    Q(status=1, workflow_status='publie')
                    | Q(status=0, workflow_status__in=['brouillon', 'a_valider', 'refuse'])
                ),
                name='course_publication_matches_workflow',
            ),
        ),
        migrations.AddConstraint(
            model_name='professionalevent',
            constraint=models.CheckConstraint(
                condition=Q(date_fin__isnull=True) | Q(date_fin__gte=F('date_debut')),
                name='professional_event_end_after_start',
            ),
        ),
        migrations.AddConstraint(
            model_name='professionalevent',
            constraint=models.CheckConstraint(
                condition=Q(places=0) | Q(places_restantes__lte=F('places')),
                name='professional_event_remaining_within_capacity',
            ),
        ),
        migrations.AddConstraint(
            model_name='trainingsession',
            constraint=models.CheckConstraint(
                condition=Q(date_fin__isnull=True) | Q(date_fin__gte=F('date_debut')),
                name='training_session_end_after_start',
            ),
        ),
        migrations.AddConstraint(
            model_name='trainingsession',
            constraint=models.CheckConstraint(
                condition=Q(places_restantes__lte=F('places_totales')),
                name='training_session_remaining_within_capacity',
            ),
        ),
        migrations.AddIndex(
            model_name='auditlog',
            index=models.Index(fields=['content_type', 'object_id', '-date_creation'], name='audit_object_date_idx'),
        ),
        migrations.AddConstraint(
            model_name='challengepaymentattempt',
            constraint=models.CheckConstraint(
                condition=Q(reference__gt=''),
                name='challenge_payment_reference_not_empty',
            ),
        ),
        migrations.AddConstraint(
            model_name='challengepaymentattempt',
            constraint=models.CheckConstraint(
                condition=Q(montant__gte=0),
                name='challenge_payment_amount_nonnegative',
            ),
        ),
        migrations.AddConstraint(
            model_name='challengepaymentattempt',
            constraint=models.UniqueConstraint(
                condition=Q(statut='en_attente'),
                fields=('participation',),
                name='unique_pending_challenge_payment',
            ),
        ),
        migrations.AddConstraint(
            model_name='challengeworksubmission',
            constraint=models.UniqueConstraint(
                fields=('participation', 'version'),
                name='unique_challenge_work_version',
            ),
        ),
        migrations.AddConstraint(
            model_name='rolerequest',
            constraint=models.UniqueConstraint(fields=('user', 'role'), name='unique_user_role_request'),
        ),
    ]