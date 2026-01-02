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
import requests

from logging import getLogger

from wstore.store_commons.resource import Resource
from wstore.store_commons.utils.http import JsonResponse, authentication_required, build_response, supported_request_mime_types
from wstore.store_commons.utils.units import ChargePeriod, CurrencyCode
from wstore.store_commons.utils.url import get_service_url

from wstore.admin.users.notification_handler import NotificationsHandler
from wstore.models import EmailConfig


logger = getLogger("wstore.default_logger")


class ChargePeriodCollection(Resource):
    def read(self, request):
        return JsonResponse(200, ChargePeriod.to_json())


class CurrencyCodeCollection(Resource):
    def read(self, request):
        return JsonResponse(200, CurrencyCode.to_json())


class NotificationConfigCollection(Resource):

    @authentication_required
    def read(self, request):
        if not request.user.is_staff:
            return build_response(request, 403, "Only administrators can access this resource")

        existing_configs = EmailConfig.objects.all()

        if existing_configs.count() == 0:
            return build_response(request, 404, "No notification configuration found")

        email_config = existing_configs.first()

        config_data = {
            "smtpServer": email_config.smtp_server,
            "smtpPort": email_config.smtp_port,
            "email": email_config.email,
            "emailUser": email_config.email_user
        }

        return JsonResponse(200, config_data)

    @supported_request_mime_types(("application/json",))
    @authentication_required
    def create(self, request):
        if not request.user.is_staff:
            return build_response(request, 403, "Only administrators can access this resource")

        try:
            data = json.loads(request.body)
            smtp_server = data["smtpServer"]
            smtp_port = data["smtpPort"]
            email = data["email"]
            email_user = data["emailUser"]
            email_password = data["emailPassword"]
        except:
            logger.error(f"Invalid email config")
            return build_response(request, 400, "The provided data is not a valid JSON object")

        # Check if the config already exists
        existing_configs = EmailConfig.objects.all()

        if existing_configs.count() > 0:
            # Update the existing config
            email_config = existing_configs.first()
            email_config.smtp_server = smtp_server
            email_config.smtp_port = smtp_port
            email_config.email = email
            email_config.email_user = email_user
            email_config.email_password = email_password
            email_config.save()
        else:
            # Create a new config
            email_config = EmailConfig(
                smtp_server=smtp_server,
                smtp_port=smtp_port,
                email=email,
                email_user=email_user,
                email_password=email_password
            )
            email_config.save()

        return build_response(request, 201, "Notification configuration created/updated successfully")


class NotificationCollection(Resource):

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

    @supported_request_mime_types(("application/json",))
    def create(self, request):
        # Get request data
        try:
            data = json.loads(request.body)

            message = data["message"]
            subject = data.get("subject", "Notification from Marketplace")
            sender_id = data.get("sender", "")
            recipient_id = data.get("recipient")
        except:
            return build_response(request, 400, "The provided data is not a valid JSON object")

        try:
            sender = self.get_party(sender_id)
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

        # Call the notification service
        try:
            notif = NotificationsHandler()
            notif.send_custom_email(party_email, subject, message)
        except Exception as e:
            logger.error(f"Error sending notification email: {str(e)}")
            return build_response(request, 500, "Error sending notification email")

        return build_response(request, 200, "Notification sent successfully")
