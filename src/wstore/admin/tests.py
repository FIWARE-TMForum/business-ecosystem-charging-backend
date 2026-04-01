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

from mock import MagicMock
from django.conf import settings
from django.test import TestCase

from wstore.admin import views


class AdminViewTestCase(TestCase):
    tags = ("notifications",)

    def setUp(self):
        views.requests = MagicMock()
        views.build_response = MagicMock()
        self._old_notification_recipient_email = settings.NOTIFICATION_RECIPIENT_EMAIL
        settings.NOTIFICATION_RECIPIENT_EMAIL = None

        self._email_instance = MagicMock()
        views.NotificationsHandler = MagicMock()
        views.NotificationsHandler.return_value = self._email_instance

    def tearDown(self):
        settings.NOTIFICATION_RECIPIENT_EMAIL = self._old_notification_recipient_email

    def _mock_request(self, body):
        request = MagicMock()
        request.method = "POST"
        request.user.is_anonymous = False
        request.META = {"CONTENT_TYPE": "application/json"}
        request.body = json.dumps(body)
        return request

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
        settings.NOTIFICATION_RECIPIENT_EMAIL = "configured@email.com"
        request = self._mock_request({
            "message": "Test message",
            "subject": "Test subject"
        })

        api = views.ConfiguredNotificationCollection(permitted_methods=("POST",))
        api.create(request)

        self._email_instance.send_custom_email.assert_called_once_with(
            "configured@email.com", "Test subject", "Test message"
        )
        views.build_response.assert_called_once_with(request, 200, "Notification sent successfully")

    def test_configured_notifications_api_invalid_body(self):
        request = self._mock_request({})

        api = views.ConfiguredNotificationCollection(permitted_methods=("POST",))
        api.create(request)

        views.build_response.assert_called_once_with(request, 400, "The provided data is not a valid JSON object")

    def test_configured_notifications_api_missing_recipient(self):
        request = self._mock_request({
            "message": "Test message",
            "subject": "Test subject"
        })

        api = views.ConfiguredNotificationCollection(permitted_methods=("POST",))
        api.create(request)

        self._email_instance.send_custom_email.assert_not_called()
        views.build_response.assert_called_once_with(request, 500, "Configured notification recipient email is not set")

    def test_configured_notifications_api_email_error(self):
        settings.NOTIFICATION_RECIPIENT_EMAIL = "configured@email.com"
        request = self._mock_request({
            "message": "Test message",
            "subject": "Test subject"
        })

        self._email_instance.send_custom_email.side_effect = Exception("Email service error")

        api = views.ConfiguredNotificationCollection(permitted_methods=("POST",))
        api.create(request)

        self._email_instance.send_custom_email.assert_called_once_with(
            "configured@email.com", "Test subject", "Test message"
        )
        views.build_response.assert_called_once_with(request, 500, "Error sending notification email")
