# -*- coding: utf-8 -*-

# Copyright (c) 2013 - 2017 CoNWeT Lab., Universidad Politécnica de Madrid

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
import smtplib
import ssl
import requests

from logging import getLogger
from django.core.exceptions import ImproperlyConfigured

from wstore.store_commons.database import get_database_connection
from wstore.store_commons.resource import Resource
from wstore.store_commons.utils.http import JsonResponse, authentication_required, build_response, supported_request_mime_types
from wstore.store_commons.utils.units import ChargePeriod, CurrencyCode
from wstore.store_commons.utils.url import get_service_url

from wstore.admin.users.notification_handler import NotificationsHandler
from wstore.admin.users.email_config import get_email_config
from wstore.models import EmailConfig


logger = getLogger("wstore.default_logger")

SUPPORTED_CONTACT_US_TYPES = ("general", "technical", "onboarding", "legal")


def _get_contact_us_destinations(email_config):
    return {
        "general": getattr(email_config, "contact_us_general", ""),
        "technical": getattr(email_config, "contact_us_technical", ""),
        "onboarding": getattr(email_config, "contact_us_onboarding", ""),
        "legal": getattr(email_config, "contact_us_legal", ""),
    }


def _parse_contact_us_destinations(data):
    contact_us_destinations = data.get("contactUsDestinations", {})
    if not isinstance(contact_us_destinations, dict):
        raise ValueError("contactUsDestinations must be an object")

    if any(key not in SUPPORTED_CONTACT_US_TYPES for key in contact_us_destinations):
        raise ValueError("Unsupported contact-us destination")

    if any(not isinstance(value, str) or len(value) > 100 for value in contact_us_destinations.values()):
        raise ValueError("Contact-us destinations must be strings of at most 100 characters")

    return contact_us_destinations


class ChargePeriodCollection(Resource):
    def read(self, request):
        return JsonResponse(200, ChargePeriod.to_json())


class CurrencyCodeCollection(Resource):
    def read(self, request):
        return JsonResponse(200, CurrencyCode.to_json())


class HealthCollection(Resource):
    def read(self, request):
        try:
            db = get_database_connection()
            db.command("ping")
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return build_response(request, 503, "database unavailable")

        return JsonResponse(200, {"status": "ok"})


class NotificationConfigCollection(Resource):

    @authentication_required
    def read(self, request):
        if not request.user.is_staff:
            return build_response(request, 403, "Only administrators can access this resource")

        email_config = get_email_config()
        if email_config is None:
            return build_response(request, 404, "No notification configuration found")

        config_data = {
            "smtpServer": email_config.smtp_server,
            "smtpPort": str(email_config.smtp_port),
            "email": email_config.email,
            "emailUser": email_config.email_user,
            "hasPassword": bool(email_config.email_password),
            "contactUsDestinations": _get_contact_us_destinations(email_config),
        }

        return JsonResponse(200, config_data)

    def _create_email_config(self, updates):
        mandatory = ('smtp_server', 'smtp_port', 'email', 'email_user')
        if any(field not in updates for field in mandatory):
            raise ValueError(
                "smtpServer, smtpPort, email and emailUser are required when creating a configuration"
            )

        if not 'email_password' in updates:
            raise ValueError("emailPassword is required when creating a configuration")

        email_config = EmailConfig(**updates)
        email_config.save()

    def _update_email_config(self, updates, email_config):
        if not 'email_password' in updates and not email_config.email_password:
            raise ValueError("emailPassword is required when no password is configured")

        for attribute, value in updates.items():
            setattr(email_config, attribute, value)
        email_config.save()

    @supported_request_mime_types(("application/json",))
    @authentication_required
    def create(self, request):
        if not request.user.is_staff:
            return build_response(request, 403, "Only administrators can access this resource")

        try:
            data = json.loads(request.body)

            if not isinstance(data, dict):
                raise ValueError("The provided data must be a JSON object")

            contact_us_destinations = _parse_contact_us_destinations(data)

            string_error = lambda x: not isinstance(x, str) or not x.strip() or len(x) > 100
            string_names = {
                "smtpServer": "smtp_server",
                "email": "email",
                "emailUser": "email_user"
            }
            updates = {}
            for field, attribute in string_names.items():
                if field not in data:
                    continue

                value = data[field]
                if string_error(value):
                    raise ValueError(f"{field} must be a nonempty string of at most 100 characters")

                updates[attribute] = value

            if "smtpPort" in data:
                smtp_port = data.get("smtpPort", "")

                if isinstance(smtp_port, bool) or not isinstance(smtp_port, (str, int)) :
                    raise ValueError("smtpPort must be a number between 1 and 65535")

                port = int(smtp_port)

                if port < 1 or port > 65535:
                    raise ValueError("smtpPort must be a number between 1 and 65535")

                updates["smtp_port"] = port

            password = data.get("emailPassword", "")
            if not isinstance(password, str) or len(password) > 100:
                raise ValueError("emailPassword must be a string of at most 100 characters")

            if password:
                updates["email_password"] = password

            for support_type, address in contact_us_destinations.items():
                updates["contact_us_" + support_type] = address

            email_config = EmailConfig.objects.first()
            if email_config is None:
                self._create_email_config(updates)
            else:
                self._update_email_config(updates, email_config)

        except (TypeError, ValueError):
            return build_response(request, 400, "Invalid email configuration")

        return build_response(request, 201, "Notification configuration created/updated successfully")


class NotificationConfigConnectionTest(Resource):
    @authentication_required
    def create(self, request):
        if not request.user.is_staff:
            return build_response(request, 403, "Only administrators can access this resource")

        try:
            NotificationsHandler().test_connection()
        except (ImproperlyConfigured, TypeError, ValueError):
            return build_response(request, 400, "Email configuration is missing or invalid")
        except TimeoutError:
            return build_response(request, 504, "SMTP connection timed out")
        except smtplib.SMTPAuthenticationError:
            return build_response(request, 502, "SMTP authentication failed")
        except smtplib.SMTPNotSupportedError:
            return build_response(request, 502, "SMTP server does not support required TLS or authentication")
        except ssl.SSLError:
            return build_response(request, 502, "SMTP TLS negotiation failed")
        except (smtplib.SMTPException, OSError):
            return build_response(request, 502, "Could not connect to the SMTP server")

        return build_response(request, 200, "SMTP connection and authentication succeeded")


class NotificationCollection(Resource):

    def _get_notification_data(self, request):
        try:
            data = json.loads(request.body)

            return {
                "message": data["message"],
                "subject": data.get("subject", "Notification from Marketplace"),
                "sender": data.get("sender", ""),
                "recipient": data.get("recipient"),
            }
        except (TypeError, ValueError, KeyError):
            raise ValueError("The provided data is not a valid JSON object")

    def get_party(self, party_id):
        """
        Get the party information from the party service.
        """
        try:
            party_url = get_service_url('party', f"/organization/{party_id}")
            response = requests.get(party_url)
            response.raise_for_status()

            return response.json()
        except:
            raise ValueError(f"Error fetching party information")

    def _send_notification_email(self, request, recipient_email, subject, message):
        try:
            notif = NotificationsHandler()
            notif.send_custom_email(recipient_email, subject, message)
        except Exception as e:
            logger.error(f"Error sending notification email: {str(e)}")
            return build_response(request, 500, "Error sending notification email")

        return build_response(request, 200, "Notification sent successfully")

    @supported_request_mime_types(("application/json",))
    def create(self, request):
        try:
            data = self._get_notification_data(request)
            message = data["message"]
            subject = data["subject"]
            sender_id = data["sender"]
            recipient_id = data["recipient"]
        except ValueError:
            return build_response(request, 400, "The provided data is not a valid JSON object")

        try:
            recipient = self.get_party(recipient_id)
        except:
            return build_response(request, 400, "Error fetching party information")

        # Get organization email from the party
        party_email = None
        if "contactMedium" in recipient:
            for medium in recipient["contactMedium"]:
                if medium["mediumType"].lower() == "email":
                    party_email = medium["characteristic"]["emailAddress"]

        if party_email is None:
            return build_response(request, 400, "The recipient does not have a valid email address")

        return self._send_notification_email(request, party_email, subject, message)


class ConfiguredNotificationCollection(NotificationCollection):
    def _get_configured_notification_data(self, request):
        try:
            data = self._get_notification_data(request)
            logger.info(f"Support type: request.body: {request.body}")

            support_type = json.loads(request.body)["supportType"]
        except (TypeError, ValueError, KeyError):
            raise ValueError("The provided data is not a valid JSON object")

        if support_type not in SUPPORTED_CONTACT_US_TYPES:
            raise ValueError("Unsupported support type")

        data["supportType"] = support_type
        return data

    @supported_request_mime_types(("application/json",))
    def create(self, request):
        try:
            data = self._get_configured_notification_data(request)
            message = data["message"]
            subject = data["subject"]
            support_type = data["supportType"]
        except ValueError:
            return build_response(request, 400, "The provided data is not a valid JSON object")

        email_config = get_email_config()
        if email_config is None:
            logger.error("Contact-us notification configuration is not set")
            return build_response(request, 500, "Contact-us notification configuration is not set")

        recipient_email = _get_contact_us_destinations(email_config)[support_type]

        if recipient_email == "":
            logger.error("Configured notification recipient email is not set")
            return build_response(request, 500, "Configured notification recipient email is not set")

        return self._send_notification_email(request, recipient_email, subject, message)
