# -*- coding: utf-8 -*-

# Copyright (c) 2026 Future Internet Consulting and Development Solutions S.L.

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

from django.conf import settings

from wstore.models import EmailConfig


def get_email_config():
    """Persist the environment-backed defaults on first use, preserving admin changes."""
    config = EmailConfig.objects.first()
    if config is not None:
        return config

    if not all((settings.WSTOREMAILUSER, settings.WSTOREMAILPASS, settings.WSTOREMAIL, settings.SMTPSERVER)):
        return None

    config, _ = EmailConfig.objects.get_or_create(defaults={
        "email_user": settings.WSTOREMAILUSER,
        "email_password": settings.WSTOREMAILPASS,
        "email": settings.WSTOREMAIL,
        "smtp_server": settings.SMTPSERVER,
        "smtp_port": int(settings.SMTPPORT),
        "contact_us_general": (
            settings.NOTIFICATION_RECIPIENT_EMAIL_GENERAL or settings.NOTIFICATION_RECIPIENT_EMAIL or ""
        ),
        "contact_us_technical": (
            settings.NOTIFICATION_RECIPIENT_EMAIL_TECHNICAL or settings.NOTIFICATION_RECIPIENT_EMAIL or ""
        ),
        "contact_us_onboarding": (
            settings.NOTIFICATION_RECIPIENT_EMAIL_ONBOARDING or settings.NOTIFICATION_RECIPIENT_EMAIL or ""
        ),
        "contact_us_legal": (
            settings.NOTIFICATION_RECIPIENT_EMAIL_LEGAL or settings.NOTIFICATION_RECIPIENT_EMAIL or ""
        ),
    })
    return config
