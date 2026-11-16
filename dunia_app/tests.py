from datetime import timedelta
from pathlib import Path
import uuid
import tempfile
from types import SimpleNamespace

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import RequestFactory, TestCase, TransactionTestCase
from django.test import override_settings
from django.urls import URLPattern, resolve, reverse
from django.utils import timezone

from .models import (
	AuditLog,
	Article,
	BlogCategory,
	BusinessProfile,
	Candidature,
	Community,
	CommunityMembership,
	CommunityPost,
	Comment,
		Challenge,
		ChallengeParticipation,
		ChallengePaymentAttempt,
		ChallengeWorkSubmission,
	Conversation,
		Contact,
	Credential,
		CommunityAccessRequest,
	DemandeAideFinanciere,
	EventRegistration,
	FeedComment,
	FeedLike,
	FeedShare,
	Friendship,
	FormationFAQ,
	Information,
	JobApplication,
	JobPosting,
	LearningProgress,
	LearningGoal,
	Message,
	Notification,
	ProfessionalEvent,
	Publication,
	RoleRequest,
	ProjectSubmission,
	ProjectCollaborator,
	SessionReservation,
	SocialPost,
	TrainerProfile,
	TrainingSession,
	UserCredential,
	UserProfile,
	Cours,
)
from .admin import BusinessProfileAdmin
from .services import (
	has_approved_role,
	request_role,
	review_challenge_payment,
	review_challenge_work,
	review_role_request,
	set_business_profile_verification,
	set_course_workflow_status,
	set_job_posting_status,
	submit_challenge_payment,
	submit_challenge_work,
	transition_job_application,
	transition_candidature,
	update_business_profile,
	review_community_access_request,
	invite_project_collaborators,
	respond_to_project_invitation,
)
from .forms import UserProfileForm


class FormationFeaturesTests(TestCase):
	def setUp(self):
		self.formation = Information.objects.create(
			module=6,
			heures=40,
			lieu='Abidjan',
			titre='Développement web',
			contenue='Apprenez à créer des applications web.',
			status=1,
			type_programme='professionnelle',
			domaine='developpement',
			niveau='debutant',
			format_formation='presentiel',
			contenu_modules='Introduction\nCréation d’interfaces web',
			frais=150000,
			bourse_disponible=True,
			paiement_echelonne=True,
		)

	def test_catalogue_filters_by_domaine(self):
		response = self.client.get(reverse('home_b'), {'domaine': 'developpement'})

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, self.formation.titre)
		self.assertEqual(list(response.context['information_list']), [self.formation])

	def test_catalogue_programme_button_opens_details_dialog(self):
		response = self.client.get(reverse('home_b'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, f'data-dialog-open="#programme-{self.formation.pk}"')
		self.assertContains(response, f'id="programme-{self.formation.pk}"')
		self.assertContains(response, 'Candidater')
		self.assertContains(response, 'Contenu des modules')

	def test_orientation_quiz_recommends_matching_programme(self):
		response = self.client.post(reverse('orientation_quiz'), {
			'interests': ['developpement'],
			'niveau': 'debutant',
			'objectif': 'emploi',
			'format_formation': 'presentiel',
		})

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, self.formation.titre)
		self.assertEqual(list(response.context['recommendations']), [self.formation])

	def test_orientation_quiz_ranks_by_goal(self):
		initiation = Information.objects.create(
			module=2,
			heures=10,
			lieu='En ligne',
			titre='Initiation au développement',
			contenue='Découvrez les bases du développement.',
			status=1,
			type_programme='initiation',
			domaine='developpement',
			niveau='debutant',
			format_formation='presentiel',
		)

		response = self.client.post(reverse('orientation_quiz'), {
			'interests': ['developpement'],
			'niveau': 'debutant',
			'objectif': 'decouverte',
			'format_formation': 'presentiel',
		})

		self.assertEqual(response.context['recommendations'][0], initiation)

	def test_calendar_and_programme_detail_show_upcoming_sessions(self):
		date_debut = timezone.localdate() + timedelta(days=14)
		TrainingSession.objects.create(
			formation=self.formation,
			titre='Cohorte de novembre',
			type_session='cohorte',
			date_debut=date_debut,
			format_formation='presentiel',
			places_totales=12,
			places_restantes=8,
			status=1,
		)
		FormationFAQ.objects.create(
			formation=self.formation,
			question='Faut-il apporter un ordinateur ?',
			reponse='Oui, un ordinateur portable est recommandé.',
			ordre=1,
			status=1,
		)
		TrainingSession.objects.create(
			formation=self.formation,
			titre='Réunion découverte',
			type_session='information',
			date_debut=date_debut + timedelta(days=2),
			format_formation='en_ligne',
			places_totales=20,
			places_restantes=20,
			status=1,
		)

		response = self.client.get(reverse('calendrier_sessions'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Cohorte de novembre')
		self.assertContains(response, 'Réunion découverte')

		response = self.client.get(reverse('calendrier_sessions'), {'type': 'information'})
		self.assertEqual(len(response.context['sessions']), 1)

		response = self.client.get(reverse('info_detail', args=[self.formation.slug]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Création d’interfaces web')
		self.assertContains(response, 'Cohorte de novembre')
		self.assertContains(response, 'Faut-il apporter un ordinateur ?')

	def test_candidature_can_be_submitted_and_tracked_by_reference_and_email(self):
		response = self.client.post(reverse('candidature_create', args=[self.formation.slug]), {
			'nom': 'Diallo',
			'prenom': 'Awa',
			'email': 'awa@example.com',
			'telephone': '+22501020304',
			'motivation': 'Je souhaite développer mes compétences numériques.',
			'session': '',
		})

		candidature = Candidature.objects.get(email='awa@example.com')
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, str(candidature.reference))

		response = self.client.post(reverse('candidature_suivi'), {
			'reference': str(candidature.reference),
			'email': 'awa@example.com',
		})
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context['candidature'], candidature)
		self.assertEqual(response.context['etape_courante'], 1)
		self.assertContains(response, 'Votre dossier est reçu.')

		response = self.client.post(reverse('candidature_suivi'), {
			'reference': str(candidature.reference),
			'email': 'autre@example.com',
		})
		self.assertIsNone(response.context['candidature'])
		self.assertContains(response, 'Aucune candidature ne correspond')

	def test_training_application_rejects_oversized_pdf(self):
		large_pdf = SimpleUploadedFile(
			'justificatif.pdf',
			b'%PDF-' + (b'x' * (5 * 1024 * 1024)),
			content_type='application/pdf',
		)
		response = self.client.post(reverse('candidature_create', args=[self.formation.slug]), {
			'nom': 'Diallo',
			'prenom': 'Awa',
			'email': 'awa@example.com',
			'telephone': '+22501020304',
			'motivation': 'Je souhaite développer mes compétences numériques.',
			'session': '',
			'document': large_pdf,
		})

		self.assertEqual(response.status_code, 200)
		self.assertEqual(Candidature.objects.filter(email='awa@example.com').count(), 0)
		self.assertContains(response, 'Le fichier ne peut dépasser 5 Mo.')

	def test_session_reservation_reduces_places_and_prevents_duplicate_booking(self):
		session = TrainingSession.objects.create(
			formation=self.formation,
			type_session='information',
			date_debut=timezone.localdate() + timedelta(days=14),
			format_formation='presentiel',
			places_totales=2,
			places_restantes=2,
			status=1,
		)
		url = reverse('session_reservation_create', args=[session.pk])
		reservation_data = {'nom': 'Awa Diallo', 'email': 'awa@example.com', 'telephone': '+22501020304'}

		first_response = self.client.post(url, reservation_data)
		self.assertEqual(first_response.status_code, 302)
		session.refresh_from_db()
		self.assertEqual(session.places_restantes, 1)

		duplicate_response = self.client.post(url, reservation_data)
		session.refresh_from_db()
		self.assertEqual(duplicate_response.status_code, 200)
		self.assertContains(duplicate_response, 'déjà réservé')
		self.assertEqual(session.places_restantes, 1)
		self.assertEqual(SessionReservation.objects.filter(session=session).count(), 1)

	def test_financial_aid_request_can_be_sent(self):
		response = self.client.post(reverse('aide_financiere_create', args=[self.formation.slug]), {
			'nom': 'Diallo',
			'prenom': 'Awa',
			'email': 'awa@example.com',
			'telephone': '+22501020304',
			'montant_souhaite': '50000',
			'situation': 'Je souhaite financer ma formation progressivement.',
		})

		self.assertEqual(response.status_code, 302)
		demande = DemandeAideFinanciere.objects.get()
		self.assertEqual(response.url, reverse('aide_financiere_confirmation', args=[demande.reference]))
		confirmation = self.client.get(response.url)
		self.assertEqual(confirmation.status_code, 200)
		self.assertContains(confirmation, str(demande.reference))

		suivi_url = reverse('aide_financiere_suivi')
		suivi = self.client.post(suivi_url, {
			'reference': str(demande.reference),
			'email': 'awa@example.com',
		})
		self.assertEqual(suivi.status_code, 200)
		self.assertEqual(suivi.context['demande'], demande)
		self.assertContains(suivi, 'Demande reçue')

		demande.statut = 'etude'
		demande.save(update_fields=['statut'])
		suivi = self.client.post(suivi_url, {
			'reference': str(demande.reference),
			'email': 'autre@example.com',
		})
		self.assertIsNone(suivi.context['demande'])
		self.assertContains(suivi, 'Aucune demande ne correspond')

		suivi = self.client.post(suivi_url, {
			'reference': str(demande.reference),
			'email': 'awa@example.com',
		})
		self.assertContains(suivi, 'À l’étude')

	def test_aid_tracking_requires_matching_reference_and_email(self):
		first = DemandeAideFinanciere.objects.create(
			formation=self.formation,
			nom='Diallo',
			prenom='Awa',
			email='awa@example.com',
			telephone='+22501020304',
			situation='Situation de test.',
		)
		second = DemandeAideFinanciere.objects.create(
			formation=self.formation,
			nom='Kone',
			prenom='Mariam',
			email='mariam@example.com',
			telephone='+22505060708',
			situation='Autre situation de test.',
		)
		response = self.client.post(reverse('aide_financiere_suivi'), {
			'reference': str(first.reference),
			'email': second.email,
		})
		self.assertIsNone(response.context['demande'])
		self.assertNotContains(response, second.prenom)


class PlatformFeaturesTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			username='awa-apprenante',
			password='Strong!Passphrase2026',
			email='awa@example.com',
			first_name='Awa',
			last_name='Diallo',
		)
		self.profile = UserProfile.objects.create(user=self.user, role='apprenant', ville='Abidjan')
		self.formateur = User.objects.create_user(username='formateur', password='Strong!Passphrase2026')
		TrainerProfile.objects.create(user=self.formateur, titre='Développeur senior', status=1)
		RoleRequest.objects.create(user=self.formateur, role='formateur', statut='approuve')
		self.cours = Cours.objects.create(
			formateur=self.formateur,
			titre='Python pour le web',
			description='Construire une application web de bout en bout.',
			type_contenu='video',
			status=1,
		)
		self.entreprise_user = User.objects.create_user(username='entreprise', password='Strong!Passphrase2026')
		self.entreprise = BusinessProfile.objects.create(
			user=self.entreprise_user,
			nom='Studio Avenir',
			description='Organisation partenaire.',
			email='contact@avenir.example',
			verifiee=True,
		)
		RoleRequest.objects.create(user=self.entreprise_user, role='entreprise', statut='approuve')
		self.offre = JobPosting.objects.create(
			entreprise=self.entreprise,
			titre='Développeur junior',
			description='Participez à des projets numériques utiles.',
			type_offre='stage',
			domaine='developpement',
			statut='publiee',
		)
		self.communaute = Community.objects.create(
			nom='Apprenants web',
			description='Un espace pour progresser ensemble.',
			status=1,
		)
		self.evenement = ProfessionalEvent.objects.create(
			titre='Rencontre des talents',
			description='Une rencontre professionnelle.',
			date_debut=timezone.now() + timedelta(days=14),
			places=1,
			status=1,
		)

	def test_home_preserves_existing_publications_and_circle_shortcuts(self):
		publication = Publication.objects.create(
			auteur=self.user,
			titre='Une actualité de la communauté',
			contexte='Une nouvelle publication à découvrir.',
			status=1,
		)
		response = self.client.get(reverse('home'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Challenge')
		self.assertContains(response, 'Cours')
		self.assertContains(response, 'Équipe')
		self.assertContains(response, 'Certifs')
		self.assertContains(response, f'href="{reverse("challenge_list")}"')
		self.assertContains(response, f'href="{reverse("formateurs")}"')
		self.assertContains(response, f'href="{reverse("credential_list")}"')
		self.assertContains(response, 'Fil d’actualité')
		self.assertContains(response, 'aria-label="Navigation principale"')
		self.assertContains(response, 'aria-label="Navigation principale mobile"')
		self.assertContains(response, 'data-navigation-skeleton="feed"')
		self.assertContains(response, 'aria-label="Ouvrir le menu principal"')
		self.assertContains(response, 'id="explore-menu-modal"')
		self.assertContains(response, 'src/favicon.svg')
		self.assertContains(response, 'grid h-12')
		self.assertContains(response, 'dunia-navbar-logo')
		self.assertNotContains(response, 'rounded-l-3xl')
		self.assertContains(response, 'class="space-y-0 sm:space-y-4"')
		self.assertContains(response, 'grid max-w-[1600px] grid-cols-1 gap-0 px-0 py-0')
		self.assertContains(response, 'name="q"')
		self.assertContains(response, publication.titre)
		self.assertContains(response, 'rounded-xl border border-base-300 bg-base-100')
		self.assertIn(publication, response.context['actualites'])
		self.assertLess(
			response.content.find(b'aria-label="Participer au fil"'),
			response.content.find('aria-label="Accès rapides"'.encode('utf-8')),
		)
		menu_html = response.content.split(b'<dialog id="explore-menu-modal"', 1)[1].split(b'</dialog>', 1)[0]
		self.assertNotIn(b'text-primary">Dunia</p>', menu_html)
		header_html = response.content.split(b'<header', 1)[1].split(b'</header>', 1)[0]
		brand_html = header_html.split(b'<a href="/"', 1)[1].split(b'</a>', 1)[0]
		self.assertIn(b'dunia-navbar-logo', brand_html)
		self.assertNotIn(b'<img', brand_html)
		mobile_nav_start = response.content.index(b'<nav class="grid h-10 grid-cols-5 lg:hidden"')
		self.assertGreater(response.content.index(b'</header>', mobile_nav_start), mobile_nav_start)
		mobile_nav = response.content[mobile_nav_start:].split(b'</nav>', 1)[0]
		self.assertEqual(mobile_nav.count(b'<a ') + mobile_nav.count(b'<button '), 5)
		self.assertEqual(mobile_nav.count(b'fill="currentColor"'), 5)
		self.assertNotIn(b'Notifications', mobile_nav)
		self.assertIn(b'aria-label="Amis"', mobile_nav)
		self.assertIn(b'href="/amis/"', mobile_nav)
		self.assertNotIn(b'href="/communautes/"', mobile_nav)
		self.assertIn(b'href="/communautes/"', response.content.split(b'<dialog id="explore-menu-modal"', 1)[1].split(b'</dialog>', 1)[0])

		SocialPost.objects.create(auteur=self.user, contenu='Une annonce pour trouver un mentor Django.')
		SocialPost.objects.create(auteur=self.user, contenu='Un message sans rapport avec le sujet.')
		search_response = self.client.get(reverse('home'), {'q': 'mentor'})
		self.assertEqual(search_response.status_code, 200)
		self.assertContains(search_response, 'mentor Django')
		self.assertNotContains(search_response, 'sans rapport avec le sujet')
		self.assertEqual(search_response.context['search_term'], 'mentor')

	def test_publication_card_opens_modal_and_published_detail_works(self):
		publication = Publication.objects.create(
			auteur=self.user,
			titre='Actualité consultable',
			contexte='Contenu visible dans la fenêtre modale.',
			status=1,
		)
		feed = self.client.get(reverse('home'))
		self.assertEqual(feed.status_code, 200)
		self.assertContains(feed, f'data-dialog-open="#publication-modal-publication-{publication.pk}"')
		self.assertContains(feed, f'id="publication-modal-publication-{publication.pk}"')
		self.assertEqual(self.client.get(reverse('detail', args=[publication.slug])).status_code, 200)

	def test_challenge_free_enrollment_and_submission(self):
		challenge = Challenge.objects.create(
			titre='Défi gratuit de conception',
			description='Réalisez une maquette accessible.',
			consignes='Partagez un lien ou décrivez votre réalisation.',
			status=1,
		)
		self.assertEqual(self.client.get(reverse('challenge_list')).status_code, 200)
		self.assertEqual(self.client.post(reverse('challenge_enroll', args=[challenge.slug])).status_code, 302)
		self.client.force_login(self.user)
		joined = self.client.post(reverse('challenge_enroll', args=[challenge.slug]))
		self.assertRedirects(joined, reverse('challenge_detail', args=[challenge.slug]))
		participation = ChallengeParticipation.objects.get(challenge=challenge, participant=self.user)
		self.assertEqual(participation.paiement_statut, 'sans_objet')
		submitted = self.client.post(reverse('challenge_submit', args=[challenge.slug]), {'travail': 'https://example.test/maquette'})
		self.assertRedirects(submitted, reverse('challenge_detail', args=[challenge.slug]))
		participation.refresh_from_db()
		self.assertEqual(participation.travail_statut, 'a_evaluer')
		self.assertEqual(participation.travail, 'https://example.test/maquette')

	def test_paid_challenge_stays_locked_until_admin_confirms_payment(self):
		challenge = Challenge.objects.create(
			titre='Défi payant de prototypage',
			description='Créez un prototype.',
			prix='5000',
			instructions_paiement='Payer par transfert puis envoyer la référence.',
			status=1,
		)
		self.client.force_login(self.user)
		self.client.post(reverse('challenge_enroll', args=[challenge.slug]))
		participation = ChallengeParticipation.objects.get(challenge=challenge, participant=self.user)
		self.assertEqual(participation.paiement_statut, 'en_attente')
		self.client.post(reverse('challenge_report_payment', args=[challenge.slug]), {'reference_paiement': 'TX-123'})
		participation.refresh_from_db()
		self.assertEqual(participation.paiement_statut, 'en_attente')
		self.assertEqual(participation.reference_paiement, 'TX-123')
		self.client.post(reverse('challenge_submit', args=[challenge.slug]), {'travail': 'Mon projet'})
		participation.refresh_from_db()
		self.assertEqual(participation.travail_statut, 'non_soumis')
		participation.paiement_statut = 'confirme'
		participation.save(update_fields=['paiement_statut'])
		self.client.post(reverse('challenge_submit', args=[challenge.slug]), {'travail': 'Mon projet'})
		participation.refresh_from_db()
		self.assertEqual(participation.travail_statut, 'a_evaluer')

	def test_global_toolbar_and_mobile_navigation_remain_available(self):
		response = self.client.get(reverse('home_b'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'dunia-navbar-logo')
		self.assertContains(response, 'aria-label="Rechercher" title="Rechercher"')
		self.assertContains(response, 'aria-label="Notifications" title="Notifications"')
		self.assertContains(response, 'aria-label="Ouvrir le menu principal"')
		self.assertLess(response.content.find(b'aria-label="Rechercher"'), response.content.find(b'aria-label="Notifications"'))
		self.assertLess(response.content.find(b'aria-label="Notifications"'), response.content.find(b'aria-label="Ouvrir le menu principal"'))
		self.assertContains(response, 'aria-label="Navigation principale mobile"')
		self.assertContains(response, 'data-navigation-skeleton="listing"')
		mobile_nav_start = response.content.index(b'<nav class="grid h-12 gap-x-1 px-1 grid-cols-5 lg:hidden"')
		mobile_nav = response.content[mobile_nav_start:].split(b'</nav>', 1)[0]
		self.assertEqual(mobile_nav.count(b'<a ') + mobile_nav.count(b'<button '), 5)
		self.assertEqual(mobile_nav.count(b'fill="currentColor"'), 5)
		self.assertNotIn(b'Notifications', mobile_nav)
		self.assertIn(b'aria-label="Amis"', mobile_nav)
		self.assertIn(b'h-12 gap-x-1 px-1 grid-cols-5', mobile_nav)

	def test_messaging_guest_sees_login_without_private_messages(self):
		response = self.client.get(reverse('messagerie'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Discussions privées')
		self.assertContains(response, 'Connectez-vous pour retrouver vos conversations')
		self.assertContains(response, 'data-navigation-skeleton="messages"')
		self.assertContains(response, 'Se connecter')
		self.assertContains(response, 'aria-label="Ouvrir le menu principal"')
		self.assertContains(response, 'aria-label="Amis"')
		self.assertNotIn(b'href="/communautes/"', response.content.split(b'<nav class="grid', 1)[1].split(b'</nav>', 1)[0])
		self.assertNotContains(response, 'class="footer sm:footer-horizontal')
		self.assertNotContains(response, 'data-conversation-link')

	def test_messaging_inbox_loads_conversations_and_hides_footer(self):
		interlocuteur = User.objects.create_user(username='messages-awa', password='Strong!Passphrase2026')
		conversation = Conversation.objects.create(participant_one=self.user, participant_two=interlocuteur)
		Message.objects.create(conversation=conversation, sender=interlocuteur, content='Parlons de la prochaine formation.')
		self.client.force_login(self.user)

		response = self.client.get(reverse('messagerie'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Parlons de la prochaine formation.')
		self.assertContains(response, 'data-conversation-search')
		self.assertContains(response, 'data-conversation-filter="unread"')
		self.assertContains(response, 'data-messaging-content')
		self.assertContains(response, 'data-navigation-skeleton="messages"')
		self.assertContains(response, 'js/messaging.js')
		self.assertNotContains(response, 'class="footer sm:footer-horizontal')

	def test_authenticated_home_uses_compact_publish_composer(self):
		self.client.force_login(self.user)
		response = self.client.get(reverse('home'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'data-post-composer')
		self.assertContains(response, 'Partager quelque chose avec la communauté…')
		self.assertContains(response, 'data-post-announcement')
		self.assertContains(response, 'Ajouter une photo')
		self.assertLess(
			response.content.find(b'data-post-composer'),
			response.content.find('aria-label="Accès rapides"'.encode('utf-8')),
		)

	def test_registration_uses_two_steps_and_creates_an_authenticated_learner(self):
		identity_response = self.client.post(reverse('inscription'), {
			'first_name': 'Mariam',
			'last_name': 'Kone',
			'email': 'mariam@example.com',
		})
		self.assertRedirects(identity_response, f"{reverse('inscription')}?etape=mot-de-passe")
		password_page = self.client.get(identity_response.url)
		self.assertContains(password_page, 'Choisissez un mot de passe')

		response = self.client.post(identity_response.url, {
			'etape': 'mot-de-passe',
			'password1': 'Unique!DuniaPassword2026',
			'password2': 'Unique!DuniaPassword2026',
		})

		self.assertRedirects(response, reverse('tableau_bord'))
		user = User.objects.get(email='mariam@example.com')
		self.assertEqual(user.profil_dunia.role, 'apprenant')
		self.assertFalse(TrainerProfile.objects.filter(user=user).exists())
		self.assertTrue(user.check_password('Unique!DuniaPassword2026'))
		self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

	def test_dashboard_and_member_templates_render(self):
		self.client.force_login(self.user)
		category = BlogCategory.objects.create(nom='Conseils', status=1)
		article = Article.objects.create(
			titre='Apprendre en pratiquant',
			contenu='Un article de test.',
			auteur=self.formateur,
			categorie=category,
			status=1,
		)
		progression = LearningProgress.objects.create(user=self.user, cours=self.cours, is_completed=True)
		credential = Credential.objects.create(nom='Badge Python', status=1)
		self.cours.certifications_requises.add(credential)
		attribution = UserCredential.objects.create(utilisateur=self.user, certification=credential)

		paths = [
			reverse('tableau_bord'),
			reverse('profil_modifier'),
			reverse('profil_public', args=[self.user.username]),
			reverse('amis'),
			reverse('mes_formations'),
			reverse('cours_list'),
			reverse('cours_detail', args=[self.cours.slug]),
			reverse('cours_evaluer', args=[self.cours.slug]),
			reverse('credential_list'),
			reverse('credential_verify', args=[attribution.reference]),
			reverse('offres_emploi'),
			reverse('offre_detail', args=[self.offre.slug]),
			reverse('espace_entreprises'),
			reverse('entreprise_creer'),
			reverse('galerie_projets'),
			reverse('projet_deposer'),
			reverse('communautes'),
			reverse('communaute_detail', args=[self.communaute.slug]),
			reverse('formateurs'),
			reverse('annuaire_apprenants'),
			reverse('evenements_pro'),
			reverse('initiatives'),
			reverse('impact'),
			reverse('campus_list'),
			reverse('projet_client'),
			reverse('messagerie'),
			reverse('article_list'),
			reverse('article_detail', args=[article.lien]),
			reverse('articles_categorie', args=[category.slug]),
			reverse('decouvrir'),
			reverse('service'),
			reverse('post'),
		]
		for path in paths:
			with self.subTest(path=path):
				response = self.client.get(path)
				self.assertEqual(response.status_code, 200)

		self.assertEqual(progression.cours, self.cours)
		dashboard_response = self.client.get(reverse('tableau_bord'))
		self.assertContains(dashboard_response, 'Résumé de votre activité')
		self.assertContains(dashboard_response, 'data-navigation-skeleton="dashboard"')
		self.assertContains(dashboard_response, 'bg-linear-to-br from-blue-950 via-primary to-cyan-600')
		self.assertContains(dashboard_response, 'Mon apprentissage')
		self.assertNotContains(dashboard_response, 'bg-gradient-to-br')
		self.assertContains(dashboard_response, reverse('user_credential_download', args=[attribution.reference]))

	def test_public_comment_is_moderated_and_redirects_to_safe_local_url(self):
		publication = Publication.objects.create(
			auteur=self.user,
			titre='Publication commentable',
			contexte='Une publication visible.',
			status=1,
		)

		response = self.client.post(reverse('comment_create'), {
			'nom': 'Awa Diallo',
			'message': 'Merci pour cette information.',
			'type_cible': 'publication',
			'object_id': publication.pk,
			'next': 'https://example.invalid/redirect-externe',
		})

		self.assertRedirects(response, reverse('home'))
		comment = Comment.objects.get(publication=publication)
		self.assertEqual(comment.status, 0)
		self.assertEqual(comment.message, 'Merci pour cette information.')

	def test_trainer_application_and_approved_management_pages_work(self):
		self.client.force_login(self.user)
		application = self.client.get(reverse('formateur_demande'))
		self.assertEqual(application.status_code, 200)
		self.assertTrue(TrainerProfile.objects.filter(user=self.user, status=0).exists())

		self.client.force_login(self.formateur)
		for path in (
			reverse('formateur_cours'),
			reverse('formateur_cours_creer'),
			reverse('formateur_cours_modifier', args=[self.cours.pk]),
		):
			with self.subTest(path=path):
				self.assertEqual(self.client.get(path).status_code, 200)

		self.client.force_login(self.entreprise_user)
		self.assertEqual(
			self.client.get(reverse('entreprise_modifier', args=[self.entreprise.pk])).status_code,
			200,
		)

	def test_social_feed_posts_likes_comments_and_pagination(self):
		self.client.force_login(self.user)
		create_response = self.client.post(reverse('social_post_create'), {
			'contenu': 'Je partage une petite réussite avec la communauté.',
		})
		self.assertRedirects(create_response, reverse('home'))
		post = SocialPost.objects.get(auteur=self.user)
		async_create_response = self.client.post(
			reverse('social_post_create'),
			{'contenu': 'Une publication créée sans rechargement.'},
			HTTP_X_REQUESTED_WITH='XMLHttpRequest',
		)
		self.assertEqual(async_create_response.status_code, 200)
		self.assertTrue(async_create_response.json()['success'])
		self.assertTrue(SocialPost.objects.filter(contenu='Une publication créée sans rechargement.').exists())

		like_url = reverse('feed_toggle_like', args=['post', post.pk])
		self.client.post(like_url)
		self.assertEqual(FeedLike.objects.filter(user=self.user, post=post).count(), 1)
		self.client.post(like_url)
		self.assertFalse(FeedLike.objects.filter(user=self.user, post=post).exists())
		like_response = self.client.post(like_url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
		self.assertEqual(like_response.status_code, 200)
		self.assertTrue(like_response.json()['is_liked'])
		self.assertEqual(like_response.json()['likes_count'], 1)
		unlike_response = self.client.post(like_url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
		self.assertFalse(unlike_response.json()['is_liked'])
		self.assertEqual(unlike_response.json()['likes_count'], 0)

		comment_response = self.client.post(
			reverse('feed_comment_create', args=['post', post.pk]),
			{'contenu': 'Bravo pour cette publication !'},
		)
		self.assertRedirects(comment_response, f"{reverse('home')}#post-{post.pk}-comments")
		self.assertEqual(FeedComment.objects.filter(post=post, auteur=self.user).count(), 1)
		async_comment_response = self.client.post(
			reverse('feed_comment_create', args=['post', post.pk]),
			{'contenu': 'Commentaire envoyé sans rechargement.'},
			HTTP_X_REQUESTED_WITH='XMLHttpRequest',
		)
		self.assertEqual(async_comment_response.status_code, 200)
		self.assertEqual(async_comment_response.json()['comment_count'], 2)
		self.assertEqual(async_comment_response.json()['comment']['content'], 'Commentaire envoyé sans rechargement.')

		share_response = self.client.post(reverse('feed_record_share', args=['post', post.pk]))
		self.assertEqual(share_response.status_code, 200)
		self.assertEqual(share_response.json()['shares_count'], 1)
		self.assertEqual(FeedShare.objects.filter(post=post).count(), 1)
		detail_response = self.client.get(reverse('social_post_detail', args=[post.pk]))
		self.assertEqual(detail_response.status_code, 200)
		self.assertContains(detail_response, f'data-share-endpoint="/fil/post/{post.pk}/partager/"')
		self.assertContains(detail_response, 'data-share-count-label')

		for number in range(10):
			SocialPost.objects.create(auteur=self.user, contenu=f'Publication de pagination {number}')
		response = self.client.get(reverse('home'), {'page': 2, 'feed_fragment': '1'})
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'data-feed-page')
		self.assertContains(response, 'Je partage une petite réussite')

	def test_social_interactions_require_login(self):
		post = SocialPost.objects.create(auteur=self.user, contenu='Publication de test')
		response = self.client.post(reverse('feed_toggle_like', args=['post', post.pk]))
		self.assertEqual(response.status_code, 302)
		self.assertFalse(FeedLike.objects.filter(post=post).exists())

	def test_friend_requests_can_be_sent_accepted_and_cancelled(self):
		ami = User.objects.create_user(username='ami', password='Strong!Passphrase2026', first_name='Mariam')
		UserProfile.objects.create(user=ami, role='apprenant', visible=True)
		self.client.force_login(self.user)

		response = self.client.post(reverse('demande_ami', args=[ami.pk]))
		self.assertRedirects(response, reverse('profil_public', args=[ami.username]))
		relation = Friendship.objects.get(person_one=self.user, person_two=ami)
		self.assertEqual(relation.status, Friendship.PENDING)
		self.assertTrue(Notification.objects.filter(destinataire=ami, titre='Nouvelle demande d’amitié').exists())

		self.client.force_login(ami)
		self.assertContains(self.client.get(reverse('amis')), self.user.first_name)
		self.client.post(reverse('demande_ami_action', args=[relation.pk, 'accepter']))
		relation.refresh_from_db()
		self.assertEqual(relation.status, Friendship.ACCEPTED)

		self.client.force_login(self.user)
		self.client.post(reverse('demande_ami_action', args=[relation.pk, 'retirer']))
		self.assertFalse(Friendship.objects.filter(pk=relation.pk).exists())

	def test_friends_page_uses_reference_sections_and_invitation_actions(self):
		inviter = User.objects.create_user(username='inviteur', first_name='Moussa')
		UserProfile.objects.create(user=inviter, role='apprenant', visible=True)
		suggestion = User.objects.create_user(username='suggestion', first_name='Fatou')
		UserProfile.objects.create(user=suggestion, role='apprenant', visible=True, ville='Dakar')
		self.client.force_login(inviter)
		self.client.post(reverse('demande_ami', args=[self.user.pk]))
		self.client.force_login(self.user)

		response = self.client.get(reverse('amis'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Ami(e)s')
		self.assertContains(response, 'id="invitation-recue"')
		self.assertContains(response, 'Confirmer')
		self.assertContains(response, 'Supprimer')
		self.assertContains(response, 'Vous connaissez peut-être')
		self.assertContains(response, 'Tous(tes) les ami(e)s')
		self.assertContains(response, 'Dakar')

	def test_friends_guest_sees_login_without_private_friend_data(self):
		ami = User.objects.create_user(username='ami-prive', first_name='Mariam')
		UserProfile.objects.create(user=ami, role='apprenant', visible=True)
		Friendship.objects.create(person_one=self.user, person_two=ami, requested_by=self.user, status=Friendship.ACCEPTED)

		response = self.client.get(reverse('amis'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'data-navigation-skeleton="friends"')
		self.assertContains(response, 'Connectez-vous pour consulter vos invitations reçues.')
		self.assertContains(response, 'href="/connexion/?next=/amis/"')
		self.assertNotContains(response, 'Mariam')
		self.assertNotIn(b'href="/connexion/?next=/amis/"', response.content.split(b'<nav class="grid', 1)[1].split(b'</nav>', 1)[0])

	def test_friends_guest_sees_login_without_private_relations(self):
		private_friend = User.objects.create_user(username='ami-prive', first_name='Ami privé')
		UserProfile.objects.create(user=private_friend, role='apprenant', visible=True)
		self.client.force_login(private_friend)
		self.client.post(reverse('demande_ami', args=[self.user.pk]))
		self.client.logout()

		response = self.client.get(reverse('amis'))

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.context['is_guest'])
		self.assertContains(response, 'data-navigation-skeleton="friends"')
		self.assertContains(response, 'Connectez-vous pour consulter vos invitations reçues.')
		self.assertContains(response, 'Se connecter')
		self.assertNotContains(response, 'Ami privé')
		self.assertNotContains(response, 'demande_ami_action')

	def test_public_profile_uses_cover_tabs_and_member_sidebars(self):
		ami = User.objects.create_user(username='ami-profil', first_name='Mariam')
		UserProfile.objects.create(user=ami, role='apprenant', visible=True)
		Friendship.objects.create(
			person_one=self.user,
			person_two=ami,
			requested_by=self.user,
			status=Friendship.ACCEPTED,
		)
		response = self.client.get(reverse('profil_public', args=[self.user.username]))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'En-tête du profil')
		self.assertContains(response, 'data-navigation-skeleton="profile"')
		self.assertContains(response, 'wrap-break-word')
		self.assertContains(response, 'Sections du profil')
		self.assertContains(response, 'Informations personnelles')
		self.assertContains(response, 'Ami(e)s')
		self.assertContains(response, 'Photos')
		self.assertContains(response, 'Mariam')
		self.assertContains(response, 'Publications')

	def test_hidden_profile_is_not_publicly_accessible(self):
		self.profile.visible = False
		self.profile.save(update_fields=['visible'])
		response = self.client.get(reverse('profil_public', args=[self.user.username]))
		self.assertEqual(response.status_code, 404)
		self.client.force_login(self.user)
		self.assertEqual(self.client.get(reverse('profil_public', args=[self.user.username])).status_code, 200)

	def test_owner_can_open_profile_when_legacy_account_has_no_profile(self):
		legacy_user = User.objects.create_user(username='dunia', password='Strong!Passphrase2026')
		self.client.force_login(legacy_user)

		response = self.client.get(reverse('profil_public', args=[legacy_user.username]))

		self.assertEqual(response.status_code, 200)
		self.assertFalse(legacy_user.profil_dunia.visible)

	def test_missing_profile_is_not_created_or_exposed_to_other_visitors(self):
		legacy_user = User.objects.create_user(username='legacy-member', password='Strong!Passphrase2026')

		response = self.client.get(reverse('profil_public', args=[legacy_user.username]))

		self.assertEqual(response.status_code, 404)
		self.assertFalse(UserProfile.objects.filter(user=legacy_user).exists())

	def test_course_progress_awards_credentials(self):
		credential = Credential.objects.create(nom='Certificat Django', status=1)
		self.cours.certifications_requises.add(credential)
		self.client.force_login(self.user)

		start = self.client.post(reverse('cours_demarrer', args=[self.cours.slug]))
		self.assertEqual(start.status_code, 302)
		finish = self.client.post(reverse('cours_terminer', args=[self.cours.slug]))
		self.assertEqual(finish.status_code, 302)
		self.assertTrue(LearningProgress.objects.get(user=self.user, cours=self.cours).is_completed)
		self.assertTrue(UserCredential.objects.filter(utilisateur=self.user, certification=credential).exists())

	def test_multi_course_credential_requires_every_prerequisite_course(self):
		second_course = Cours.objects.create(
			formateur=self.formateur,
			titre='Accessibilité des interfaces',
			description='Construire des interfaces accessibles.',
			type_contenu='video',
			status=1,
		)
		credential = Credential.objects.create(nom='Parcours web complet', status=1)
		credential.cours.add(self.cours, second_course)
		self.client.force_login(self.user)

		for cours in (self.cours, second_course):
			self.client.post(reverse('cours_demarrer', args=[cours.slug]))
			self.client.post(reverse('cours_terminer', args=[cours.slug]))
			if cours == self.cours:
				self.assertFalse(UserCredential.objects.filter(utilisateur=self.user, certification=credential).exists())

		self.assertTrue(UserCredential.objects.filter(utilisateur=self.user, certification=credential).exists())

	def test_credentials_can_be_downloaded_and_verified_without_public_identity(self):
		credential = Credential.objects.create(nom='Certificat Django', description='Certification de test.', status=1)
		self.cours.certifications_requises.add(credential)
		self.client.force_login(self.user)
		self.client.post(reverse('cours_demarrer', args=[self.cours.slug]))
		self.client.post(reverse('cours_terminer', args=[self.cours.slug]))
		attribution = UserCredential.objects.get(utilisateur=self.user, certification=credential)

		download = self.client.get(reverse('user_credential_download', args=[attribution.reference]))
		self.assertEqual(download.status_code, 200)
		self.assertEqual(download['Content-Type'], 'application/pdf')
		self.assertIn('attachment;', download['Content-Disposition'])
		pdf_content = b''.join(download.streaming_content)
		self.assertTrue(pdf_content.startswith(b'%PDF-'))

		self.client.logout()
		verification = self.client.get(reverse('credential_verify', args=[attribution.reference]))
		self.assertEqual(verification.status_code, 200)
		self.assertContains(verification, credential.nom)
		self.assertContains(verification, str(attribution.reference))
		self.assertNotContains(verification, self.user.username)

		autre = User.objects.create_user(username='autre-titulaire', password='Strong!Passphrase2026')
		self.client.force_login(autre)
		forbidden_download = self.client.get(reverse('user_credential_download', args=[attribution.reference]))
		self.assertEqual(forbidden_download.status_code, 404)

	def test_published_credential_catalog_is_available(self):
		credential = Credential.objects.create(nom='Certification active', status=1)
		Credential.objects.create(nom='Certification cachée', status=0)
		cours_cache = Cours.objects.create(
			formateur=self.formateur,
			titre='Cours non publié secret',
			description='Contenu interne.',
			type_contenu='video',
			status=0,
		)
		credential.cours.add(cours_cache)
		response = self.client.get(reverse('credential_list'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Certification active')
		self.assertNotContains(response, 'Certification cachée')
		self.assertNotContains(response, cours_cache.titre)

	def test_community_membership_and_posts_require_membership(self):
		self.client.force_login(self.user)
		join_response = self.client.post(reverse('communaute_detail', args=[self.communaute.slug]), {'rejoindre': '1'})
		self.assertEqual(join_response.status_code, 302)
		self.assertTrue(CommunityMembership.objects.filter(community=self.communaute, user=self.user).exists())

		post_response = self.client.post(reverse('communaute_detail', args=[self.communaute.slug]), {'contenu': 'Bonjour la communauté !'})
		self.assertEqual(post_response.status_code, 302)
		self.assertEqual(CommunityPost.objects.get(community=self.communaute, auteur=self.user).contenu, 'Bonjour la communauté !')

	def test_private_community_access_request_hides_posts_until_approval(self):
		private = Community.objects.create(nom='Groupe privé', description='Accès réservé.', status=1, privee=True)
		CommunityMembership.objects.create(community=private, user=self.formateur)
		CommunityPost.objects.create(community=private, auteur=self.formateur, contenu='Échange réservé aux membres.')
		self.client.force_login(self.user)
		url = reverse('communaute_detail', args=[private.slug])
		response = self.client.get(url)
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Demander l’accès')
		self.assertNotContains(response, 'Échange réservé aux membres.')

		response = self.client.post(url, {'demander_acces': '1'})
		self.assertRedirects(response, url)
		demande = CommunityAccessRequest.objects.get(communaute=private, utilisateur=self.user)
		self.assertEqual(demande.statut, 'en_attente')
		self.assertFalse(CommunityMembership.objects.filter(community=private, user=self.user).exists())
		response = self.client.get(url)
		self.assertContains(response, 'Demande en attente')
		self.assertNotContains(response, 'Échange réservé aux membres.')

		administrateur = User.objects.create_superuser(
			username='community-admin',
			email='community-admin@example.com',
			password='Strong!Passphrase2026',
		)
		review_community_access_request(demande.pk, statut='approuvee', actor=administrateur)
		self.assertTrue(CommunityMembership.objects.filter(community=private, user=self.user).exists())
		self.assertTrue(Notification.objects.filter(destinataire=self.user, type_notification='communaute').exists())
		response = self.client.get(url)
		self.assertContains(response, 'Échange réservé aux membres.')

		CommunityMembership.objects.filter(community=private, user=self.user).delete()
		response = self.client.get(url)
		self.assertContains(response, 'Redemander l’accès')
		self.client.post(url, {'demander_acces': '1'})
		demande.refresh_from_db()
		self.assertEqual(demande.statut, 'en_attente')
		self.assertFalse(CommunityMembership.objects.filter(community=private, user=self.user).exists())

	def test_event_registration_is_idempotent_and_respects_capacity(self):
		self.client.force_login(self.user)
		url = reverse('evenement_inscription', args=[self.evenement.slug])
		first = self.client.post(url)
		second = self.client.post(url)

		self.assertEqual(first.status_code, 302)
		self.assertEqual(second.status_code, 302)
		self.assertEqual(EventRegistration.objects.filter(evenement=self.evenement, participant=self.user).count(), 1)
		self.evenement.refresh_from_db()
		self.assertEqual(self.evenement.places_restantes, 0)
		self.assertTrue(EventRegistration.objects.get(evenement=self.evenement, participant=self.user).annulee_le is None)
		self.assertContains(self.client.get(reverse('evenements_pro')), 'Vous êtes inscrit')

		cancel_url = reverse('evenement_annulation', args=[self.evenement.slug])
		cancelled = self.client.post(cancel_url)
		self.assertRedirects(cancelled, reverse('evenements_pro'))
		registration = EventRegistration.objects.get(evenement=self.evenement, participant=self.user)
		self.assertIsNotNone(registration.annulee_le)
		self.evenement.refresh_from_db()
		self.assertEqual(self.evenement.places_restantes, 1)

		rejoined = self.client.post(url)
		self.assertRedirects(rejoined, reverse('evenements_pro'))
		registration.refresh_from_db()
		self.assertIsNone(registration.annulee_le)
		self.evenement.refresh_from_db()
		self.assertEqual(self.evenement.places_restantes, 0)

		autre = User.objects.create_user(username='another-learner', password='Strong!Passphrase2026')
		self.client.force_login(autre)
		self.client.post(url)
		self.assertFalse(EventRegistration.objects.filter(evenement=self.evenement, participant=autre).exists())

	def test_event_cancellation_requires_existing_registration_and_post(self):
		self.client.force_login(self.user)
		url = reverse('evenement_annulation', args=[self.evenement.slug])
		self.assertEqual(self.client.get(url).status_code, 405)
		self.assertEqual(self.client.post(url).status_code, 404)

	def test_profile_form_renders_styled_widgets_from_meta(self):
		form = UserProfileForm()
		self.assertIn('textarea', str(form['bio']))
		self.assertIn('textarea-bordered', str(form['bio']))
		self.assertIn('file-input-bordered', str(form['photo']))

	def test_new_training_session_starts_with_full_capacity(self):
		session = TrainingSession.objects.create(
			formation=Information.objects.create(
				module=1,
				heures=10,
				lieu='Abidjan',
				titre='Initiation à la donnée',
				contenue='Découvrir les données.',
				status=1,
			),
			type_session='information',
			date_debut=timezone.localdate() + timedelta(days=8),
			places_totales=4,
			status=1,
		)
		self.assertEqual(session.places_restantes, 4)

	def test_job_application_uploads_pdf_and_notifies_company(self):
		self.client.force_login(self.user)
		with tempfile.TemporaryDirectory() as media_root, tempfile.TemporaryDirectory() as private_root, override_settings(
			MEDIA_ROOT=media_root,
			PRIVATE_MEDIA_ROOT=private_root,
		):
			response = self.client.post(reverse('offre_detail', args=[self.offre.slug]), {
				'motivation': 'Je souhaite rejoindre votre équipe.',
				'cv': SimpleUploadedFile('cv.pdf', b'%PDF-1.4 test document', content_type='application/pdf'),
			})
			application = JobApplication.objects.get(offre=self.offre, candidat=self.user)
			self.assertTrue(application.cv.storage.exists(application.cv.name))
			self.assertFalse((Path(media_root) / application.cv.name).exists())
			with self.assertRaises(ValueError):
				application.cv.url

		self.assertEqual(response.status_code, 302)
		self.assertTrue(Notification.objects.filter(destinataire=self.entreprise_user, type_notification='emploi').exists())

	def test_job_application_cv_is_private_and_scoped_to_candidate_and_company(self):
		with tempfile.TemporaryDirectory() as media_root, tempfile.TemporaryDirectory() as private_root, override_settings(
			MEDIA_ROOT=media_root,
			PRIVATE_MEDIA_ROOT=private_root,
		):
			application = JobApplication.objects.create(
				offre=self.offre,
				candidat=self.user,
				motivation='Je souhaite rejoindre votre équipe.',
				cv=SimpleUploadedFile('cv-prive.pdf', b'%PDF-1.4 contenu de test', content_type='application/pdf'),
			)
			self.assertFalse((Path(media_root) / application.cv.name).exists())
			with self.assertRaises(ValueError):
				application.cv.url

			self.client.force_login(self.user)
			candidate_download = self.client.get(reverse('job_application_cv_download', args=[application.pk]))
			self.assertEqual(candidate_download.status_code, 200)
			candidate_download.close()

			outsider = User.objects.create_user(username='lecteur-non-autorise', password='Strong!Passphrase2026')
			self.client.force_login(outsider)
			self.assertEqual(self.client.get(reverse('job_application_cv_download', args=[application.pk])).status_code, 404)
			self.assertEqual(
				self.client.get(reverse('entreprise_candidatures', args=[self.entreprise.pk, self.offre.pk])).status_code,
				403,
			)
			RoleRequest.objects.create(user=outsider, role='entreprise', statut='approuve')
			self.assertEqual(
				self.client.get(reverse('entreprise_candidatures', args=[self.entreprise.pk, self.offre.pk])).status_code,
				404,
			)

			self.client.force_login(self.entreprise_user)
			page = self.client.get(reverse('entreprise_candidatures', args=[self.entreprise.pk, self.offre.pk]))
			self.assertEqual(page.status_code, 200)
			self.assertContains(page, reverse('job_application_cv_download', args=[application.pk]))
			company_download = self.client.get(reverse('job_application_cv_download', args=[application.pk]))
			self.assertEqual(company_download.status_code, 200)
			company_download.close()

			updated = self.client.post(reverse('entreprise_candidatures', args=[self.entreprise.pk, self.offre.pk]), {
				'application_id': application.pk,
				'statut': 'entretien',
			})
			self.assertEqual(updated.status_code, 302)
		application.refresh_from_db()
		self.assertEqual(application.statut, 'entretien')
		self.assertTrue(AuditLog.objects.filter(action='candidature_emploi.statut').exists())

	def test_job_application_rejects_a_pdf_with_invalid_signature(self):
		self.client.force_login(self.user)
		with tempfile.TemporaryDirectory() as private_root, override_settings(PRIVATE_MEDIA_ROOT=private_root):
			response = self.client.post(reverse('offre_detail', args=[self.offre.slug]), {
				'motivation': 'Je souhaite rejoindre votre équipe.',
				'cv': SimpleUploadedFile('faux.pdf', b'<html>not a PDF</html>', content_type='application/pdf'),
			})
		self.assertEqual(response.status_code, 200)
		self.assertFalse(JobApplication.objects.filter(offre=self.offre, candidat=self.user).exists())

	def test_project_submission_is_held_for_review(self):
		self.client.force_login(self.user)
		response = self.client.post(reverse('projet_deposer'), {
			'titre': 'Application de suivi',
			'description': 'Une application pour suivre les apprentissages.',
			'competences': 'Django, UX',
			'formation': '',
			'url_demo': '',
			'url_code': '',
		})

		self.assertEqual(response.status_code, 302)
		self.assertEqual(ProjectSubmission.objects.get(auteur=self.user).statut, 'a_valider')

	def test_project_invitation_requires_acceptance_before_team_membership(self):
		ami = User.objects.create_user(
			username='mariam-equipe',
			password='Strong!Passphrase2026',
			first_name='Mariam',
			last_name='Kone',
		)
		Friendship.objects.create(
			person_one=self.user,
			person_two=ami,
			requested_by=self.user,
			status=Friendship.ACCEPTED,
		)
		self.client.force_login(self.user)
		response = self.client.post(reverse('projet_deposer'), {
			'titre': 'Outil collaboratif',
			'description': 'Un outil éducatif conçu en équipe.',
			'competences': 'Django, UX',
			'formation': '',
			'url_demo': '',
			'url_code': '',
			'collaborateurs': [str(ami.pk)],
		})

		self.assertEqual(response.status_code, 302)
		projet = ProjectSubmission.objects.get(auteur=self.user)
		invitation = ProjectCollaborator.objects.get(projet=projet, utilisateur=ami)
		self.assertEqual(projet.statut, 'a_valider')
		self.assertEqual(invitation.statut, 'en_attente')
		self.assertFalse(ProjectCollaborator.objects.filter(
			projet=projet,
			utilisateur=ami,
			statut='acceptee',
		).exists())
		self.assertTrue(Notification.objects.filter(destinataire=ami, type_notification='projet').exists())

		self.client.force_login(ami)
		dashboard = self.client.get(reverse('tableau_bord'))
		self.assertEqual(dashboard.status_code, 200)
		self.assertIn(invitation, dashboard.context['invitations_projet'])
		self.assertNotIn(projet, dashboard.context['projets'])
		galerie = self.client.get(reverse('galerie_projets'))
		self.assertNotIn(projet, galerie.context['projets'])

		response = self.client.post(reverse('projet_invitation_action', args=[invitation.pk, 'accepter']))
		self.assertEqual(response.status_code, 302)
		invitation.refresh_from_db()
		self.assertEqual(invitation.statut, 'acceptee')
		self.assertTrue(ProjectCollaborator.objects.filter(
			projet=projet,
			utilisateur=ami,
			statut='acceptee',
		).exists())
		self.assertIn(projet, self.client.get(reverse('tableau_bord')).context['projets'])

		projet.statut = 'publie'
		projet.save(update_fields=['statut'])
		self.assertContains(self.client.get(reverse('galerie_projets')), 'Mariam Kone')

	def test_project_collaboration_rejects_non_friends_and_private_responses(self):
		projet = ProjectSubmission.objects.create(
			auteur=self.user,
			titre='Projet réservé',
			description='Projet en cours de validation.',
		)
		intrus = User.objects.create_user(username='intrus-projet', password='Strong!Passphrase2026')
		with self.assertRaises(ValidationError):
			invite_project_collaborators(projet.pk, [intrus], actor=self.user)

		ami = User.objects.create_user(username='ami-projet', password='Strong!Passphrase2026')
		Friendship.objects.create(
			person_one=self.user,
			person_two=ami,
			requested_by=self.user,
			status=Friendship.ACCEPTED,
		)
		invite_project_collaborators(projet.pk, [ami], actor=self.user)
		invitation = ProjectCollaborator.objects.get(projet=projet, utilisateur=ami)
		with self.assertRaises(PermissionDenied):
			respond_to_project_invitation(invitation.pk, statut='acceptee', actor=intrus)
		self.client.force_login(intrus)
		response = self.client.post(reverse('projet_invitation_action', args=[invitation.pk, 'accepter']))
		self.assertEqual(response.status_code, 403)
		invitation.refresh_from_db()
		self.assertEqual(invitation.statut, 'en_attente')

	def test_accepted_project_collaborator_can_edit_and_must_resubmit_for_review(self):
		ami = User.objects.create_user(username='coequipier', password='Strong!Passphrase2026')
		projet = ProjectSubmission.objects.create(
			auteur=self.user,
			titre='Projet publié',
			description='Version initialement validée.',
			statut='publie',
		)
		ProjectCollaborator.objects.create(
			projet=projet,
			utilisateur=ami,
			invite_par=self.user,
			statut='acceptee',
			date_decision=timezone.now(),
		)
		intrus = User.objects.create_user(username='visiteur-projet', password='Strong!Passphrase2026')
		self.client.force_login(intrus)
		self.assertEqual(self.client.get(reverse('projet_modifier', args=[projet.pk])).status_code, 404)

		self.client.force_login(ami)
		page = self.client.get(reverse('projet_modifier', args=[projet.pk]))
		self.assertEqual(page.status_code, 200)
		self.assertNotIn('collaborateurs', page.context['form'].fields)
		response = self.client.post(reverse('projet_modifier', args=[projet.pk]), {
			'titre': 'Projet amélioré en équipe',
			'description': 'Une nouvelle version réalisée ensemble.',
			'competences': 'Django, conception',
			'formation': '',
			'url_demo': '',
			'url_code': '',
		})
		self.assertEqual(response.status_code, 302)
		projet.refresh_from_db()
		self.assertEqual(projet.titre, 'Projet amélioré en équipe')
		self.assertEqual(projet.statut, 'a_valider')
		self.assertTrue(AuditLog.objects.filter(action='projet.modifie_soumis_validation').exists())
		self.assertNotIn(projet, self.client.get(reverse('galerie_projets')).context['projets'])

	def test_learning_goals_are_private_editable_and_track_completion(self):
		self.client.force_login(self.user)
		date_cible = (timezone.localdate() + timedelta(days=14)).isoformat()
		response = self.client.post(reverse('objectif_creer'), {
			'titre': 'Terminer mon cours Python',
			'description': 'Étudier une leçon chaque semaine.',
			'date_cible': date_cible,
		})
		self.assertEqual(response.status_code, 302)
		objectif = LearningGoal.objects.get(user=self.user)
		self.assertContains(self.client.get(reverse('tableau_bord')), objectif.titre)

		other_user = User.objects.create_user(username='autre-apprenant', password='Strong!Passphrase2026')
		self.client.force_login(other_user)
		self.assertEqual(self.client.get(reverse('objectif_modifier', args=[objectif.pk])).status_code, 404)
		self.assertNotContains(self.client.get(reverse('tableau_bord')), objectif.titre)

		self.client.force_login(self.user)
		response = self.client.post(reverse('objectif_action', args=[objectif.pk, 'atteindre']))
		self.assertEqual(response.status_code, 302)
		objectif.refresh_from_db()
		self.assertEqual(objectif.statut, 'atteint')
		self.assertIsNotNone(objectif.date_atteinte)

		response = self.client.post(reverse('objectif_modifier', args=[objectif.pk]), {
			'titre': 'Terminer mon parcours Python',
			'description': 'Réviser et construire une application.',
			'date_cible': date_cible,
		})
		self.assertEqual(response.status_code, 302)
		objectif.refresh_from_db()
		self.assertEqual(objectif.titre, 'Terminer mon parcours Python')

		self.client.post(reverse('objectif_action', args=[objectif.pk, 'reprendre']))
		objectif.refresh_from_db()
		self.assertEqual(objectif.statut, 'en_cours')
		self.assertIsNone(objectif.date_atteinte)
		self.client.post(reverse('objectif_action', args=[objectif.pk, 'supprimer']))
		self.assertFalse(LearningGoal.objects.filter(pk=objectif.pk).exists())

	def test_learning_goal_rejects_a_past_target_date(self):
		self.client.force_login(self.user)
		response = self.client.post(reverse('objectif_creer'), {
			'titre': 'Objectif avec date passée',
			'description': '',
			'date_cible': (timezone.localdate() - timedelta(days=1)).isoformat(),
		})
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'La date cible ne peut pas être dans le passé.')
		self.assertFalse(LearningGoal.objects.filter(user=self.user).exists())

	def test_authentication_and_password_reset_templates_render(self):
		from django.contrib.auth.tokens import default_token_generator
		from django.utils.encoding import force_bytes
		from django.utils.http import urlsafe_base64_encode

		uid = urlsafe_base64_encode(force_bytes(self.user.pk))
		token = default_token_generator.make_token(self.user)
		confirm_path = reverse('password_reset_confirm', args=[uid, token])
		for path in (
			reverse('inscription'),
			reverse('connexion'),
			reverse('password_reset'),
			reverse('password_reset_done'),
			reverse('password_reset_complete'),
		):
			with self.subTest(path=path):
				self.assertEqual(self.client.get(path).status_code, 200)

		confirmation = self.client.get(confirm_path, follow=True)
		self.assertEqual(confirmation.status_code, 200)
		self.assertTrue(confirmation.context['validlink'])

		self.client.force_login(self.user)
		logout_response = self.client.post(reverse('deconnexion'))
		self.assertRedirects(logout_response, reverse('home'))
		self.assertNotIn('_auth_user_id', self.client.session)

	def test_login_social_buttons_are_outside_the_login_form_and_card(self):
		response = self.client.get(reverse('connexion'))
		self.assertEqual(response.status_code, 200)
		content = response.content.decode()
		self.assertIn('>Google<', content)
		self.assertIn('>Microsoft<', content)
		self.assertIn('disabled', content)
		self.assertNotIn('footer sm:footer-horizontal', content)
		self.assertIn('alt="Dunia"', content)
		self.assertIn('dunia-logo-auth.png', content)
		self.assertLess(content.index('</form>'), content.index('aria-label="Autres moyens de connexion"'))

	def test_registration_has_provider_buttons_outside_its_form(self):
		for response in (
			self.client.get(reverse('inscription')),
		):
			content = response.content.decode()
			self.assertContains(response, 'alt="Dunia"')
			self.assertContains(response, 'dunia-logo-auth.png')
			self.assertContains(response, '>Google<')
			self.assertContains(response, '>Microsoft<')
			self.assertLess(content.index('</form>'), content.index('aria-label="Autres moyens de connexion"'))
			self.assertNotContains(response, 'footer sm:footer-horizontal')

	def test_login_accepts_registered_email_address(self):
		response = self.client.post(reverse('connexion'), {
			'username': self.user.email,
			'password': 'Strong!Passphrase2026',
		})
		self.assertRedirects(response, reverse('tableau_bord'))

	def test_direct_messages_are_private_and_create_notifications(self):
		interlocuteur = User.objects.create_user(username='samuel', password='Strong!Passphrase2026')
		autre = User.objects.create_user(username='autre', password='Strong!Passphrase2026')
		self.client.force_login(self.user)
		start = self.client.get(reverse('conversation_demarrer', args=[interlocuteur.username]))
		self.assertEqual(start.status_code, 302)
		conversation = Conversation.objects.get()
		conversation_url = reverse('conversation_detail', args=[conversation.pk])

		page = self.client.get(conversation_url)
		self.assertEqual(page.status_code, 200)
		self.assertContains(page, 'aria-label="Ouvrir le menu principal"')
		self.assertContains(page, 'data-navigation-skeleton="conversation"')
		self.assertNotContains(page, 'class="footer sm:footer-horizontal')
		posted = self.client.post(conversation_url, {'content': 'Bonjour, échangeons sur le projet.'})
		self.assertEqual(posted.status_code, 302)
		self.assertEqual(Message.objects.filter(conversation=conversation, sender=self.user).count(), 1)
		self.assertTrue(Notification.objects.filter(destinataire=interlocuteur, type_notification='message').exists())

		self.client.force_login(autre)
		self.assertEqual(self.client.get(conversation_url).status_code, 404)

	def test_notifications_can_be_marked_read_and_badge_is_counted(self):
		notification = Notification.objects.create(
			destinataire=self.user,
			titre='Bienvenue',
			message='Votre espace Dunia est prêt.',
		)
		self.client.force_login(self.user)
		response = self.client.get(reverse('tableau_bord'))
		self.assertEqual(response.context['unread_notifications_count'], 1)
		marked = self.client.post(reverse('notification_mark_read', args=[notification.pk]), {
			'next': reverse('tableau_bord'),
		})
		self.assertRedirects(marked, reverse('tableau_bord'))
		notification.refresh_from_db()
		self.assertTrue(notification.lue)

	def test_company_can_submit_job_for_review(self):
		self.client.force_login(self.entreprise_user)
		self.assertEqual(self.client.get(reverse('offre_creer', args=[self.entreprise.pk])).status_code, 200)
		response = self.client.post(reverse('offre_creer', args=[self.entreprise.pk]), {
			'titre': 'Designer UX junior',
			'description': 'Contribuez à la conception de produits accessibles.',
			'type_offre': 'stage',
			'domaine': 'design',
			'lieu': 'Abidjan',
			'format_emploi': 'hybride',
			'date_limite': '',
		})

		self.assertEqual(response.status_code, 302)
		self.assertTrue(JobPosting.objects.filter(titre='Designer UX junior', statut='a_valider').exists())


class BusinessRuleServiceTests(TestCase):
	def setUp(self):
		self.member = User.objects.create_user(username='membre-metier', password='Strong!Passphrase2026')
		self.admin = User.objects.create_superuser(
			username='admin-metier',
			password='Strong!Passphrase2026',
			email='admin@example.com',
		)
		self.formation = Information.objects.create(
			module=1,
			heures=24,
			lieu='Abidjan',
			titre='Formation métier',
			contenue='Contenu de formation.',
			status=1,
		)

	def test_role_request_requires_team_decision_and_updates_trainer_profile(self):
		profile = TrainerProfile.objects.create(user=self.member, status=0)
		demande = request_role(self.member, 'formateur')
		self.assertFalse(has_approved_role(self.member, 'formateur'))
		with self.assertRaises(PermissionDenied):
			review_role_request(demande.pk, statut='approuve', actor=self.member)

		review_role_request(demande.pk, statut='approuve', actor=self.admin)
		demande.refresh_from_db()
		profile.refresh_from_db()
		self.assertEqual(demande.statut, 'approuve')
		self.assertEqual(profile.status, 1)
		self.assertTrue(has_approved_role(self.member, 'formateur'))
		self.assertTrue(AuditLog.objects.filter(action='role.decision', actor=self.admin).exists())

	def test_candidature_transition_reserves_and_releases_a_cohort_place_once(self):
		date_debut = timezone.localdate() + timedelta(days=30)
		session = TrainingSession.objects.create(
			formation=self.formation,
			titre='Cohorte limitée',
			type_session='cohorte',
			date_debut=date_debut,
			date_fin=date_debut + timedelta(days=14),
			places_totales=1,
			places_restantes=1,
			status=1,
		)
		candidature = Candidature.objects.create(
			formation=self.formation,
			nom='Kone',
			prenom='Mariam',
			email='mariam@example.com',
			telephone='+22501020304',
			motivation='Je souhaite suivre cette formation.',
		)
		with self.assertRaises(PermissionDenied):
			transition_candidature(candidature.pk, statut='test', actor=self.member)

		transition_candidature(
			candidature.pk,
			statut='confirmee',
			session_id=session.pk,
			actor=self.admin,
		)
		session.refresh_from_db()
		candidature.refresh_from_db()
		self.assertEqual(session.places_restantes, 0)
		self.assertTrue(candidature.place_retenue)

		transition_candidature(candidature.pk, statut='decision', actor=self.admin)
		session.refresh_from_db()
		candidature.refresh_from_db()
		self.assertEqual(session.places_restantes, 1)
		self.assertFalse(candidature.place_retenue)

		transition_candidature(candidature.pk, statut='refusee', actor=self.admin)
		with self.assertRaises(PermissionDenied):
			transition_candidature(candidature.pk, statut='test', actor=self.member)
		self.assertEqual(AuditLog.objects.filter(action='candidature.statut').count(), 3)

	def test_payment_attempts_can_be_retried_without_erasing_decisions(self):
		challenge = Challenge.objects.create(
			titre='Défi paiement versionné',
			description='Défi de test.',
			prix='2500',
			status=1,
		)
		participation = ChallengeParticipation.objects.create(
			challenge=challenge,
			participant=self.member,
			paiement_statut='en_attente',
		)
		premiere = submit_challenge_payment(participation.pk, reference='REF-001', actor=self.member)
		with self.assertRaises(ValidationError):
			submit_challenge_payment(participation.pk, reference='REF-002', actor=self.member)
		review_challenge_payment(premiere.pk, statut='refuse', actor=self.admin, commentaire='Référence non trouvée.')

		seconde = submit_challenge_payment(participation.pk, reference='REF-003', actor=self.member)
		review_challenge_payment(seconde.pk, statut='confirme', actor=self.admin, commentaire='Paiement vérifié.')
		participation.refresh_from_db()
		self.assertEqual(participation.paiement_statut, 'confirme')
		self.assertEqual(participation.reference_paiement, 'REF-003')
		self.assertEqual(participation.tentatives_paiement.count(), 2)
		self.assertEqual(
			list(participation.tentatives_paiement.order_by('pk').values_list('statut', flat=True)),
			['refuse', 'confirme'],
		)

	def test_challenge_work_submissions_keep_each_version_and_review(self):
		challenge = Challenge.objects.create(
			titre='Défi remise versionnée',
			description='Défi de test.',
			status=1,
		)
		participation = ChallengeParticipation.objects.create(
			challenge=challenge,
			participant=self.member,
		)
		premiere = submit_challenge_work(participation.pk, travail='Version initiale', actor=self.member)
		review_challenge_work(
			premiere.pk,
			statut='a_corriger',
			retour='Ajoutez une démonstration.',
			actor=self.admin,
		)
		seconde = submit_challenge_work(participation.pk, travail='Version corrigée', actor=self.member)
		premiere.refresh_from_db()
		self.assertEqual(seconde.version, 2)
		self.assertEqual(participation.soumissions_travail.count(), 2)
		self.assertEqual(premiere.travail, 'Version initiale')
		self.assertEqual(premiere.retour, 'Ajoutez une démonstration.')
		with self.assertRaises(ValidationError):
			submit_challenge_work(participation.pk, travail='Version prématurée', actor=self.member)

	def test_company_profile_change_resets_verification_and_requeues_published_offers(self):
		entreprise_user = User.objects.create_user(username='entreprise-metier')
		entreprise = BusinessProfile.objects.create(
			user=entreprise_user,
			nom='Entreprise vérifiée',
			description='Organisation.',
			email='contact@entreprise.example',
			verifiee=True,
		)
		RoleRequest.objects.create(user=entreprise_user, role='entreprise', statut='approuve')
		offre = JobPosting.objects.create(
			entreprise=entreprise,
			titre='Poste déjà publié',
			description='Offre existante.',
			statut='publiee',
		)

		update_business_profile(
			entreprise.pk,
			actor=entreprise_user,
			changes={'nom': 'Entreprise mise à jour'},
		)
		entreprise.refresh_from_db()
		offre.refresh_from_db()
		self.assertFalse(entreprise.verifiee)
		self.assertEqual(offre.statut, 'a_valider')
		self.assertTrue(AuditLog.objects.filter(action='entreprise.profil_modifie').exists())

		set_business_profile_verification(entreprise.pk, verifiee=True, actor=self.admin)
		entreprise.refresh_from_db()
		self.assertTrue(entreprise.verifiee)
		self.assertEqual(offre.statut, 'a_valider')

	def test_admin_company_profile_change_resets_verification_and_requeues_offers(self):
		entreprise = BusinessProfile.objects.create(
			user=self.member,
			nom='Entreprise à réviser',
			description='Profil initial.',
			email='contact@revision.example',
			verifiee=True,
		)
		offre = JobPosting.objects.create(
			entreprise=entreprise,
			titre='Offre existante',
			description='Offre déjà publiée.',
			statut='publiee',
		)
		request = RequestFactory().post('/admin/dunia_app/businessprofile/')
		request.user = self.admin
		request._messages = SimpleNamespace(add=lambda *args, **kwargs: None)
		entreprise.description = 'Profil modifié depuis l’administration.'

		BusinessProfileAdmin(BusinessProfile, AdminSite()).save_model(
			request,
			entreprise,
			SimpleNamespace(changed_data=['description']),
			change=True,
		)

		entreprise.refresh_from_db()
		offre.refresh_from_db()
		self.assertFalse(entreprise.verifiee)
		self.assertEqual(offre.statut, 'a_valider')
		self.assertTrue(AuditLog.objects.filter(action='entreprise.profil_modifie_admin').exists())

	def test_course_requires_admin_approval_before_publication(self):
		with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
			cours = Cours.objects.create(
				formateur=self.member,
				titre='Cours en attente',
				description='Contenu de cours.',
				type_contenu='video',
				video=SimpleUploadedFile('cours.mp4', b'test video bytes', content_type='video/mp4'),
				workflow_status='a_valider',
				status=0,
			)
			with self.assertRaises(PermissionDenied):
				set_course_workflow_status(cours.pk, statut='publie', actor=self.member)
			set_course_workflow_status(cours.pk, statut='publie', actor=self.admin)
			cours.refresh_from_db()
			self.assertEqual(cours.workflow_status, 'publie')
			self.assertEqual(cours.status, 1)
		self.assertTrue(AuditLog.objects.filter(action='cours.statut').exists())

	def test_unapproved_business_role_cannot_publish_or_expose_jobs(self):
		entreprise_user = User.objects.create_user(username='entreprise-sans-role')
		entreprise = BusinessProfile.objects.create(
			user=entreprise_user,
			nom='Entreprise sans rôle',
			description='Organisation en attente.',
			email='contact@sans-role.example',
			verifiee=True,
		)
		offre = JobPosting.objects.create(
			entreprise=entreprise,
			titre='Offre à ne pas exposer',
			description='Offre nécessitant une approbation.',
			statut='a_valider',
		)
		with self.assertRaises(ValidationError):
			set_job_posting_status(offre.pk, statut='publiee', actor=self.admin)
		self.client.force_login(entreprise_user)
		self.assertEqual(self.client.get(reverse('offre_creer', args=[entreprise.pk])).status_code, 403)
		self.assertEqual(self.client.get(reverse('offres_emploi')).status_code, 200)
		self.assertNotContains(self.client.get(reverse('offres_emploi')), offre.titre)

	def test_training_application_document_is_only_downloadable_by_owner_or_admin(self):
		with tempfile.TemporaryDirectory() as private_root, override_settings(PRIVATE_MEDIA_ROOT=private_root):
			candidature = Candidature.objects.create(
				formation=self.formation,
				utilisateur=self.member,
				nom='Membre',
				prenom='Test',
				email='membre@example.com',
				telephone='+22501020304',
				motivation='Ma candidature.',
				document=SimpleUploadedFile('justificatif.pdf', b'%PDF-1.4 document priv\xc3\xa9', content_type='application/pdf'),
			)
			with self.assertRaises(ValueError):
				candidature.document.url

			self.client.force_login(self.member)
			owner_response = self.client.get(reverse('candidature_document_download', args=[candidature.pk]))
			self.assertEqual(owner_response.status_code, 200)
			self.assertEqual(owner_response['Cache-Control'], 'private, no-store')
			owner_response.close()

			self.client.force_login(User.objects.create_user(username='autre-candidat'))
			self.assertEqual(self.client.get(reverse('candidature_document_download', args=[candidature.pk])).status_code, 404)

			self.client.force_login(self.admin)
			admin_response = self.client.get(reverse('candidature_document_download', args=[candidature.pk]))
			self.assertEqual(admin_response.status_code, 200)
			admin_response.close()


class RequestThrottlingTests(TestCase):
	@override_settings(CACHES={
		'default': {
			'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
			'LOCATION': 'dunia-rate-limit-test-cache',
		},
	})
	def test_contact_form_is_throttled(self):
		cache.clear()
		responses = [self.client.post(reverse('contact_create'), {}) for _ in range(6)]

		self.assertTrue(all(response.status_code == 302 for response in responses[:5]))
		self.assertEqual(responses[5].status_code, 429)
		self.assertEqual(responses[5]['Retry-After'], '3600')
		self.assertFalse(Contact.objects.exists())


class WorkflowDataMigrationTests(TransactionTestCase):
	reset_sequences = True

	def setUp(self):
		super().setUp()
		self.migrate_from = ('dunia_app', '0026_alter_challenge_prix')
		self.migrate_to = ('dunia_app', '0029_demandeaidefinanciere_reference_and_more')
		self.latest_migrations = MigrationExecutor(connection).loader.graph.leaf_nodes()
		self._restore_latest_schema = False
		try:
			MigrationExecutor(connection).migrate([self.migrate_from])
			old_apps = MigrationExecutor(connection).loader.project_state([self.migrate_from]).apps
			self._create_legacy_records(old_apps)
			MigrationExecutor(connection).migrate([self.migrate_to])
			self._restore_latest_schema = True
			self.migrated_apps = MigrationExecutor(connection).loader.project_state([self.migrate_to]).apps
		except Exception:
			MigrationExecutor(connection).migrate(self.latest_migrations)
			self._restore_latest_schema = True
			raise

	def _create_legacy_records(self, apps):
		UserModel = apps.get_model('auth', 'User')
		InformationModel = apps.get_model('dunia_app', 'Information')
		TrainingSessionModel = apps.get_model('dunia_app', 'TrainingSession')
		CandidatureModel = apps.get_model('dunia_app', 'Candidature')
		CourseModel = apps.get_model('dunia_app', 'Cours')
		TrainerProfileModel = apps.get_model('dunia_app', 'TrainerProfile')
		BusinessProfileModel = apps.get_model('dunia_app', 'BusinessProfile')
		ChallengeModel = apps.get_model('dunia_app', 'Challenge')
		ChallengeParticipationModel = apps.get_model('dunia_app', 'ChallengeParticipation')
		DemandeAideFinanciereModel = apps.get_model('dunia_app', 'DemandeAideFinanciere')

		self.legacy_user = UserModel.objects.create(username='compte-migration')
		self.legacy_trainer = UserModel.objects.create(username='formateur-migration')
		self.legacy_business = UserModel.objects.create(username='entreprise-migration')
		formation = InformationModel.objects.create(
			module=1,
			heures=20,
			lieu='Abidjan',
			titre='Formation conservée',
			contenue='Contenu historique.',
			status=1,
			slug='formation-conservee',
		)
		self.legacy_aid_request_ids = []
		for email in ('legacy-aide-one@example.com', 'legacy-aide-two@example.com'):
			demande = DemandeAideFinanciereModel.objects.create(
				formation=formation,
				nom='Test',
				prenom='Legacy',
				email=email,
				telephone='+22501020304',
				situation='Demande d’aide historique.',
			)
			self.legacy_aid_request_ids.append(demande.pk)
		session_start = timezone.localdate() + timedelta(days=40)
		session = TrainingSessionModel.objects.create(
			formation=formation,
			titre='Cohorte conservée',
			date_debut=session_start,
			places_totales=5,
			places_restantes=3,
			status=1,
		)
		self.legacy_candidature = CandidatureModel.objects.create(
			formation=formation,
			session=session,
			utilisateur=self.legacy_user,
			nom='Test',
			prenom='Legacy',
			email='legacy@example.com',
			telephone='+22501020304',
			motivation='Candidature historique.',
			statut='confirmee',
		)
		self.legacy_course = CourseModel.objects.create(
			formateur=self.legacy_trainer,
			titre='Cours déjà public',
			description='Contenu existant.',
			type_contenu='video',
			status=1,
			slug='cours-deja-public',
		)
		TrainerProfileModel.objects.create(user=self.legacy_trainer, status=1)
		BusinessProfileModel.objects.create(
			user=self.legacy_business,
			nom='Entreprise déjà vérifiée',
			slug='entreprise-deja-verifiee',
			description='Organisation historique.',
			email='legacy-company@example.com',
			verifiee=True,
		)
		challenge = ChallengeModel.objects.create(
			titre='Défi historique',
			slug='defi-historique',
			description='Défi déjà en cours.',
			status=1,
		)
		self.legacy_payment_reference = 'LEGACY-PAY-321'
		self.legacy_work_date = timezone.now() - timedelta(days=3)
		self.legacy_participation = ChallengeParticipationModel.objects.create(
			challenge=challenge,
			participant=self.legacy_user,
			paiement_statut='confirme',
			reference_paiement=self.legacy_payment_reference,
			travail='https://example.test/ancien-travail',
			travail_statut='a_corriger',
			date_soumission=self.legacy_work_date,
		)

	def tearDown(self):
		if self._restore_latest_schema:
			MigrationExecutor(connection).migrate(self.latest_migrations)
		super().tearDown()

	def test_backfill_preserves_publication_roles_slots_and_challenge_history(self):
		Cours = self.migrated_apps.get_model('dunia_app', 'Cours')
		Candidature = self.migrated_apps.get_model('dunia_app', 'Candidature')
		TrainingSession = self.migrated_apps.get_model('dunia_app', 'TrainingSession')
		RoleRequest = self.migrated_apps.get_model('dunia_app', 'RoleRequest')
		ChallengePaymentAttempt = self.migrated_apps.get_model('dunia_app', 'ChallengePaymentAttempt')
		ChallengeWorkSubmission = self.migrated_apps.get_model('dunia_app', 'ChallengeWorkSubmission')
		ChallengeParticipation = self.migrated_apps.get_model('dunia_app', 'ChallengeParticipation')
		DemandeAideFinanciere = self.migrated_apps.get_model('dunia_app', 'DemandeAideFinanciere')

		self.assertEqual(Cours.objects.get(pk=self.legacy_course.pk).workflow_status, 'publie')
		self.assertTrue(Candidature.objects.get(pk=self.legacy_candidature.pk).place_retenue)
		self.assertEqual(
			TrainingSession.objects.get(pk=self.legacy_candidature.session_id).places_restantes,
			3,
		)
		self.assertEqual(
			RoleRequest.objects.get(user_id=self.legacy_trainer.pk, role='formateur').statut,
			'approuve',
		)
		self.assertEqual(
			RoleRequest.objects.get(user_id=self.legacy_business.pk, role='entreprise').statut,
			'approuve',
		)
		payment = ChallengePaymentAttempt.objects.get(participation_id=self.legacy_participation.pk)
		self.assertEqual(payment.reference, self.legacy_payment_reference)
		self.assertEqual(payment.statut, 'confirme')
		self.assertIsNone(payment.montant)
		self.assertTrue(payment.historique_importe)
		submission = ChallengeWorkSubmission.objects.get(participation_id=self.legacy_participation.pk)
		self.assertEqual(submission.version, 1)
		self.assertEqual(submission.travail, 'https://example.test/ancien-travail')
		self.assertEqual(submission.statut, 'a_corriger')
		self.assertEqual(submission.date_soumission, self.legacy_work_date)
		self.assertTrue(submission.historique_importe)
		self.assertEqual(
			ChallengeParticipation.objects.get(pk=self.legacy_participation.pk).travail,
			'https://example.test/ancien-travail',
		)
		references_aide = [
			DemandeAideFinanciere.objects.get(pk=demande_id).reference
			for demande_id in self.legacy_aid_request_ids
		]
		self.assertTrue(all(references_aide))
		self.assertEqual(len(references_aide), len(set(references_aide)))


class UrlRoutingSmokeTests(TestCase):
	def test_every_named_application_route_resolves_and_gets_no_server_error(self):
		from .urls import urlpatterns as app_urlpatterns

		named_routes = [
			route for route in app_urlpatterns
			if isinstance(route, URLPattern) and route.name
		]
		self.assertTrue(named_routes)

		for route in named_routes:
			kwargs = {
					name: (
						uuid.uuid4()
						if converter.__class__.__name__ == 'UUIDConverter'
						else 1 if converter.regex == '[0-9]+' else 'smoke-test'
					)
				for name, converter in route.pattern.converters.items()
			}
			path = reverse(route.name, kwargs=kwargs)
			with self.subTest(url_name=route.name, path=path):
				self.assertEqual(resolve(path).url_name, route.name)
				response = self.client.get(path)
				self.assertLess(response.status_code, 500)

	def test_admin_entry_and_login_page_are_reachable(self):
		admin_home = self.client.get('/admin/')
		self.assertEqual(admin_home.status_code, 302)
		self.assertIn(reverse('admin:login'), admin_home.url)
		self.assertEqual(self.client.get(reverse('admin:login')).status_code, 200)
