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
            "hasPassword": True,
            "contactUsDestinations": self._contact_us_destinations(),
        })

    def test_notification_config_create_persists_contact_us_destinations(self):
        email_config = MagicMock()
        views.EmailConfig.objects.first.return_value = email_config

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
        self.assertEqual(587, email_config.smtp_port)
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
        views.EmailConfig.objects.first.return_value = None
        request = self._mock_request({
            "smtpServer": "smtp.example.org",
            "smtpPort": "587",
            "email": "source@example.org",
            "emailUser": "smtp-user",
            "emailPassword": "secret",
            "contactUsDestinations": {"general": None},
        }, is_staff=True)
        request.path = "/charging/api/orderManagement/notify/config"

        api = views.NotificationConfigCollection(permitted_methods=("POST",))
        api.create(request)

        views.build_response.assert_called_once_with(request, 400, "Invalid email configuration")

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
            "hasPassword": True,
            "contactUsDestinations": self._contact_us_destinations(onboarding="support@example.org"),
        })

    def test_notification_config_get_does_not_initialize_for_non_admin(self):
        request = self._mock_request({}, method="GET", is_staff=False)
        views.NotificationConfigCollection(permitted_methods=("GET",)).read(request)
        self._get_email_config.assert_not_called()
        views.build_response.assert_called_once_with(request, 403, "Only administrators can access this resource")

    def test_notification_config_partial_update_preserves_password_and_other_fields(self):
        for password_data in ({}, {"emailPassword": ""}):
            with self.subTest(password_data=password_data):
                config = MagicMock(
                    smtp_server="smtp.example.org", smtp_port=587,
                    email="source@example.org", email_user="smtp-user", email_password="secret",
                    contact_us_general="general@example.org", contact_us_technical="technical@example.org",
                )
                views.EmailConfig.objects.first.return_value = config
                request = self._mock_request(dict(password_data, email="new@example.org"), is_staff=True)
                views.build_response.reset_mock()

                views.NotificationConfigCollection(permitted_methods=("POST",)).create(request)

                self.assertEqual("new@example.org", config.email)
                self.assertEqual("secret", config.email_password)
                self.assertEqual("smtp.example.org", config.smtp_server)
                self.assertEqual(587, config.smtp_port)
                self.assertEqual("smtp-user", config.email_user)
                self.assertEqual("general@example.org", config.contact_us_general)
                self.assertEqual("technical@example.org", config.contact_us_technical)
                config.save.assert_called_once_with()
                views.build_response.assert_called_once_with(
                    request, 201, "Notification configuration created/updated successfully"
                )

    def test_notification_config_partial_contact_update_clears_only_explicit_empty_destination(self):
        config = MagicMock(
            email_password="secret", contact_us_general="general@example.org",
            contact_us_technical="technical@example.org", contact_us_onboarding="onboarding@example.org",
            contact_us_legal="legal@example.org",
        )
        views.EmailConfig.objects.first.return_value = config
        request = self._mock_request(
            {"contactUsDestinations": {"general": "", "technical": "new@example.org"}}, is_staff=True
        )

        views.NotificationConfigCollection(permitted_methods=("POST",)).create(request)

        self.assertEqual("", config.contact_us_general)
        self.assertEqual("new@example.org", config.contact_us_technical)
        self.assertEqual("onboarding@example.org", config.contact_us_onboarding)
        self.assertEqual("legal@example.org", config.contact_us_legal)
        self.assertEqual("secret", config.email_password)
        config.save.assert_called_once_with()

    def test_notification_config_replaces_password_when_provided(self):
        config = MagicMock(email_password="old-password")
        views.EmailConfig.objects.first.return_value = config
        request = self._mock_request({"emailPassword": "new-password"}, is_staff=True)

        views.NotificationConfigCollection(permitted_methods=("POST",)).create(request)

        self.assertEqual("new-password", config.email_password)
        config.save.assert_called_once_with()

    def test_notification_config_creation_accepts_optional_contact_destinations(self):
        for contact_data in ({}, {"contactUsDestinations": {}}, {"contactUsDestinations": {"general": ""}}):
            with self.subTest(contact_data=contact_data):
                views.EmailConfig.reset_mock()
                views.EmailConfig.objects.first.return_value = None
                data = dict(contact_data, smtpServer="smtp.example.org", smtpPort="587", email="source@example.org",
                            emailUser="smtp-user", emailPassword="secret")
                request = self._mock_request(data, is_staff=True)

                views.NotificationConfigCollection(permitted_methods=("POST",)).create(request)

                expected = dict(smtp_server="smtp.example.org", smtp_port=587, email="source@example.org",
                                email_user="smtp-user", email_password="secret")
                if contact_data.get("contactUsDestinations"):
                    expected["contact_us_general"] = ""
                views.EmailConfig.assert_called_once_with(**expected)
                views.EmailConfig.return_value.save.assert_called_once_with()

    def test_notification_config_creation_requires_password_and_smtp_fields(self):
        complete = dict(smtpServer="smtp.example.org", smtpPort=587, email="source@example.org",
                        emailUser="smtp-user", emailPassword="secret")
        for field in complete:
            for value in (None, ""):
                with self.subTest(field=field, value=value):
                    views.EmailConfig.reset_mock()
                    views.build_response.reset_mock()
                    views.EmailConfig.objects.first.return_value = None
                    data = complete.copy()
                    if value is None:
                        del data[field]
                    else:
                        data[field] = value
                    request = self._mock_request(data, is_staff=True)

                    views.NotificationConfigCollection(permitted_methods=("POST",)).create(request)

                    views.EmailConfig.assert_not_called()
                    views.build_response.assert_called_once_with(request, 400, "Invalid email configuration")

    def test_notification_config_invalid_updates_do_not_save_or_modify_existing_values(self):
        invalid_bodies = [
            [], None, {"emailPassword": None}, {"emailPassword": 123}, {"smtpServer": ""},
            {"smtpPort": 0}, {"smtpPort": 65536}, {"smtpPort": True}, {"smtpPort": 1.5},
            {"smtpPort": "invalid"}, {"contactUsDestinations": None}, {"contactUsDestinations": []},
            {"contactUsDestinations": {"general": None}}, {"contactUsDestinations": {"unknown": ""}},
            {"email": "new@example.org", "emailPassword": None},
        ]
        for body in invalid_bodies:
            with self.subTest(body=body):
                config = MagicMock(email="original@example.org", email_password="secret")
                views.EmailConfig.objects.first.return_value = config
                views.build_response.reset_mock()
                request = self._mock_request(body, is_staff=True)

                views.NotificationConfigCollection(permitted_methods=("POST",)).create(request)

                self.assertEqual("original@example.org", config.email)
                self.assertEqual("secret", config.email_password)
                config.save.assert_not_called()
                views.build_response.assert_called_once_with(request, 400, "Invalid email configuration")

    def test_notification_config_get_reports_missing_password_without_exposing_it(self):
        config = MagicMock(email_password="")
        views.EmailConfig.objects.first.return_value = config
        request = self._mock_request({}, method="GET", is_staff=True)

        views.NotificationConfigCollection(permitted_methods=("GET",)).read(request)

        data = views.JsonResponse.call_args[0][1]
        self.assertIs(False, data["hasPassword"])
        self.assertNotIn("emailPassword", data)

    def test_notification_config_update_requires_password_when_none_is_stored(self):
        config = MagicMock(email_password="")
        views.EmailConfig.objects.first.return_value = config
        request = self._mock_request({"email": "new@example.org"}, is_staff=True)

        views.NotificationConfigCollection(permitted_methods=("POST",)).create(request)

        config.save.assert_not_called()
        views.build_response.assert_called_once_with(request, 400, "Invalid email configuration")
