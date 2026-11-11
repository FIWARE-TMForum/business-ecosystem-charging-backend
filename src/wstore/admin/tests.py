# -*- coding: utf-8 -*-

# Copyright (c) 2025 Future Internet Consulting and Development Solutions S.L.

# This file belongs to the business-charging-backend
# of the Business API Ecosystem.

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import json

from mock import MagicMock, patch
from django.conf import settings
from django.test import TestCase, override_settings

from wstore.admin import views
from wstore.admin.users import email_config


class AdminViewTestCase(TestCase):
    tags = ("notifications",)

    def setUp(self):
        views.requests = MagicMock()
        views.build_response = MagicMock()
        views.JsonResponse = MagicMock()
        views.EmailConfig = MagicMock()
        self._config_patcher = patch.object(views, "get_email_config")
        self._get_email_config = self._config_patcher.start()
        self.addCleanup(self._config_patcher.stop)
        self._get_email_config.side_effect = lambda: views.EmailConfig.objects.first()
        self._old_notification_recipient_email = settings.NOTIFICATION_RECIPIENT_EMAIL
        settings.NOTIFICATION_RECIPIENT_EMAIL = None

        self._email_instance = MagicMock()
        views.NotificationsHandler = MagicMock()
        views.NotificationsHandler.return_value = self._email_instance

    def tearDown(self):
        settings.NOTIFICATION_RECIPIENT_EMAIL = self._old_notification_recipient_email

    def _mock_request(self, body, method="POST", is_staff=False):
        request = MagicMock()
        request.method = method
        request.user.is_anonymous = False
        request.user.is_staff = is_staff
        request.META = {"CONTENT_TYPE": "application/json"}
        request.body = json.dumps(body)
        request.path = "/charging/api/orderManagement/notify/configured"
        return request

    def _contact_us_destinations(self, **overrides):
        destinations = {
            "general": "general@example.org",
            "technical": "technical@example.org",
            "onboarding": "onboarding@example.org",
            "legal": "legal@example.org",
        }
        destinations.update(overrides)
        return destinations

    def test_notifications_api(self):
        request = self._mock_request({
            "message": "Test message",
            "subject": "Test subject",
            "sender": "",
            "recipient": "party_id"
        })

        response = MagicMock()
        response.json.return_value = {
            "contactMedium": [{
                "mediumType": "email",
                "characteristic": {
                    "emailAddress": "user@email.com"
                }
            }]
        }

        views.requests.get.return_value = response
        api = views.NotificationCollection(permitted_methods=("POST",))
        api.create(request)

        self._email_instance.send_custom_email.assert_called_once_with(
            "user@email.com", "Test subject", "Test message"
        )
        views.build_response.assert_called_once_with(request, 200, "Notification sent successfully")


    def test_notifications_api_invalid_body(self):
        request = self._mock_request({})

        api = views.NotificationCollection(permitted_methods=("POST",))
        api.create(request)

        views.build_response.assert_called_once_with(request, 400, "The provided data is not a valid JSON object")

    def test_notifications_api_party_not_found(self):
        request = self._mock_request({
            "message": "Test message",
            "subject": "Test subject",
            "sender": "",
            "recipient": "party_id"
        })

        response = MagicMock()
        response.raise_for_status.side_effect = ValueError("Party not found")

        views.requests.get.return_value = response

        api = views.NotificationCollection(permitted_methods=("POST",))
        api.create(request)

        views.build_response.assert_called_once_with(request, 400, "Error fetching party information")

    def test_notifications_api_party_no_email(self):
        request = self._mock_request({
            "message": "Test message",
            "subject": "Test subject",
            "sender": "",
            "recipient": "party_id"
        })

        response = MagicMock()
        response.json.return_value = {}

        views.requests.get.return_value = response
        api = views.NotificationCollection(permitted_methods=("POST",))
        api.create(request)

        views.build_response.assert_called_once_with(request, 400, "The recipient does not have a valid email address")

    def test_notifications_api_party_email_error(self):
        request = self._mock_request({
            "message": "Test message",
            "subject": "Test subject",
            "recipient": "party_id"
        })

        response = MagicMock()
        response.json.return_value = {
            "contactMedium": [{
                "mediumType": "email",
                "characteristic": {
                    "emailAddress": "user@email.com"
                }
            }]
        }

        views.requests.get.return_value = response

        self._email_instance.send_custom_email.side_effect = Exception("Email service error")

        api = views.NotificationCollection(permitted_methods=("POST",))
        api.create(request)

        self._email_instance.send_custom_email.assert_called_once_with(
            "user@email.com", "Test subject", "Test message"
        )
        views.build_response.assert_called_once_with(request, 500, "Error sending notification email")

    def test_configured_notifications_api(self):
        email_config = MagicMock()
        email_config.contact_us_general = "general@example.org"
        email_config.contact_us_technical = "technical@example.org"
        email_config.contact_us_onboarding = "onboarding@example.org"
        email_config.contact_us_legal = "legal@example.org"
        views.EmailConfig.objects.first.return_value = email_config
        request = self._mock_request({
            "message": "Test message",
            "subject": "Test subject",
            "supportType": "technical",
        })

        api = views.ConfiguredNotificationCollection(permitted_methods=("POST",))
        api.create(request)

        self._email_instance.send_custom_email.assert_called_once_with(
            "technical@example.org", "Test subject", "Test message"
        )
        views.build_response.assert_called_once_with(request, 200, "Notification sent successfully")

    def test_configured_notifications_api_invalid_body(self):
        request = self._mock_request({})

        api = views.ConfiguredNotificationCollection(permitted_methods=("POST",))
        api.create(request)

        views.build_response.assert_called_once_with(request, 400, "The provided data is not a valid JSON object")

    def test_configured_notifications_api_missing_recipient(self):
        email_config = MagicMock()
        email_config.contact_us_general = ""
        email_config.contact_us_technical = "technical@example.org"
        email_config.contact_us_onboarding = "onboarding@example.org"
        email_config.contact_us_legal = "legal@example.org"
        views.EmailConfig.objects.first.return_value = email_config
        request = self._mock_request({
            "message": "Test message",
            "subject": "Test subject",
            "supportType": "general",
        })

        api = views.ConfiguredNotificationCollection(permitted_methods=("POST",))
        api.create(request)

        self._email_instance.send_custom_email.assert_not_called()
        views.build_response.assert_called_once_with(request, 500, "Configured notification recipient email is not set")

    def test_configured_notifications_api_email_error(self):
        email_config = MagicMock()
        email_config.contact_us_general = "general@example.org"
        email_config.contact_us_technical = "technical@example.org"
        email_config.contact_us_onboarding = "onboarding@example.org"
        email_config.contact_us_legal = "legal@example.org"
        views.EmailConfig.objects.first.return_value = email_config
        request = self._mock_request({
            "message": "Test message",
            "subject": "Test subject",
            "supportType": "legal",
        })

        self._email_instance.send_custom_email.side_effect = Exception("Email service error")

        api = views.ConfiguredNotificationCollection(permitted_methods=("POST",))
        api.create(request)

        self._email_instance.send_custom_email.assert_called_once_with(
            "legal@example.org", "Test subject", "Test message"
        )
        views.build_response.assert_called_once_with(request, 500, "Error sending notification email")

    def test_configured_notifications_api_invalid_support_type(self):
        request = self._mock_request({
            "message": "Test message",
            "subject": "Test subject",
            "supportType": "sales",
        })

        api = views.ConfiguredNotificationCollection(permitted_methods=("POST",))
        api.create(request)

        self._email_instance.send_custom_email.assert_not_called()
        views.build_response.assert_called_once_with(request, 400, "The provided data is not a valid JSON object")

    def test_configured_notifications_api_missing_configuration(self):
        views.EmailConfig.objects.first.return_value = None
        request = self._mock_request({
            "message": "Test message",
            "subject": "Test subject",
            "supportType": "general",
        })

        api = views.ConfiguredNotificationCollection(permitted_methods=("POST",))
        api.create(request)

        self._email_instance.send_custom_email.assert_not_called()
        views.build_response.assert_called_once_with(request, 500, "Contact-us notification configuration is not set")

    def test_notification_config_read_includes_contact_us_destinations(self):
        email_config = MagicMock()
        email_config.smtp_server = "smtp.example.org"
        email_config.smtp_port = 587
        email_config.email = "source@example.org"
        email_config.email_user = "smtp-user"
        email_config.contact_us_general = "general@example.org"
        email_config.contact_us_technical = "technical@example.org"
        email_config.contact_us_onboarding = "onboarding@example.org"
        email_config.contact_us_legal = "legal@example.org"

        views.EmailConfig.objects.first.return_value = email_config

        request = self._mock_request({}, method="GET", is_staff=True)
        request.path = "/charging/api/orderManagement/notify/config"

        api = views.NotificationConfigCollection(permitted_methods=("GET",))
        api.read(request)

        views.JsonResponse.assert_called_once_with(200, {
            "smtpServer": "smtp.example.org",
            "smtpPort": "587",
            "email": "source@example.org",
            "emailUser": "smtp-user",
            "contactUsDestinations": self._contact_us_destinations(),
        })

    def test_notification_config_create_persists_contact_us_destinations(self):
        email_config = MagicMock()
        existing_configs = MagicMock()
        existing_configs.count.return_value = 1
        existing_configs.first.return_value = email_config
        views.EmailConfig.objects.all.return_value = existing_configs

        request = self._mock_request({
            "smtpServer": "smtp.example.org",
            "smtpPort": "587",
            "email": "source@example.org",
            "emailUser": "smtp-user",
            "emailPassword": "secret",
            "contactUsDestinations": self._contact_us_destinations(),
        }, is_staff=True)
        request.path = "/charging/api/orderManagement/notify/config"

        api = views.NotificationConfigCollection(permitted_methods=("POST",))
        api.create(request)

        self.assertEqual("smtp.example.org", email_config.smtp_server)
        self.assertEqual("587", email_config.smtp_port)
        self.assertEqual("source@example.org", email_config.email)
        self.assertEqual("smtp-user", email_config.email_user)
        self.assertEqual("secret", email_config.email_password)
        self.assertEqual("general@example.org", email_config.contact_us_general)
        self.assertEqual("technical@example.org", email_config.contact_us_technical)
        self.assertEqual("onboarding@example.org", email_config.contact_us_onboarding)
        self.assertEqual("legal@example.org", email_config.contact_us_legal)
        email_config.save.assert_called_once_with()
        views.build_response.assert_called_once_with(request, 201, "Notification configuration created/updated successfully")

    def test_notification_config_create_rejects_invalid_contact_us_destinations(self):
        views.EmailConfig.objects.all.return_value.count.return_value = 0
        request = self._mock_request({
            "smtpServer": "smtp.example.org",
            "smtpPort": "587",
            "email": "source@example.org",
            "emailUser": "smtp-user",
            "emailPassword": "secret",
            "contactUsDestinations": {
                "general": "general@example.org",
                "technical": "technical@example.org",
            },
        }, is_staff=True)
        request.path = "/charging/api/orderManagement/notify/config"

        api = views.NotificationConfigCollection(permitted_methods=("POST",))
        api.create(request)

        views.build_response.assert_called_once_with(request, 400, "The provided data is not a valid JSON object")

    @override_settings(
        WSTOREMAILUSER="env-user", WSTOREMAILPASS="env-password",
        WSTOREMAIL="env@example.org", SMTPSERVER="smtp.env.example.org", SMTPPORT="2525",
        NOTIFICATION_RECIPIENT_EMAIL="support@example.org",
        NOTIFICATION_RECIPIENT_EMAIL_GENERAL="general@example.org",
        NOTIFICATION_RECIPIENT_EMAIL_TECHNICAL="technical@example.org",
        NOTIFICATION_RECIPIENT_EMAIL_ONBOARDING="",
        NOTIFICATION_RECIPIENT_EMAIL_LEGAL="legal@example.org",
    )
    @patch.object(email_config, "EmailConfig")
    def test_notification_config_get_persists_and_returns_environment_defaults(self, model):
        model.objects.first.return_value = None
        defaults = {
            "email_user": "env-user", "email_password": "env-password",
            "email": "env@example.org", "smtp_server": "smtp.env.example.org", "smtp_port": 2525,
            "contact_us_general": "general@example.org",
            "contact_us_technical": "technical@example.org",
            "contact_us_onboarding": "support@example.org",
            "contact_us_legal": "legal@example.org",
        }
        config = MagicMock(**defaults)
        model.objects.get_or_create.return_value = (config, True)
        self._get_email_config.side_effect = email_config.get_email_config

        request = self._mock_request({}, method="GET", is_staff=True)
        views.NotificationConfigCollection(permitted_methods=("GET",)).read(request)

        model.objects.get_or_create.assert_called_once_with(defaults=defaults)
        views.JsonResponse.assert_called_once_with(200, {
            "smtpServer": "smtp.env.example.org", "smtpPort": "2525",
            "email": "env@example.org", "emailUser": "env-user",
            "contactUsDestinations": self._contact_us_destinations(onboarding="support@example.org"),
        })

    def test_notification_config_get_does_not_initialize_for_non_admin(self):
        request = self._mock_request({}, method="GET", is_staff=False)
        views.NotificationConfigCollection(permitted_methods=("GET",)).read(request)
        self._get_email_config.assert_not_called()
        views.build_response.assert_called_once_with(request, 403, "Only administrators can access this resource")
