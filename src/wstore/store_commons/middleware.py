# -*- coding: utf-8 -*-

# Copyright (c) 2013 - 2016 CoNWeT Lab., Universidad Politécnica de Madrid
# Copyright (c) 2021 Future Internet Consulting and Development Solutions S.L.

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

from logging import getLogger

from django.utils.functional import SimpleLazyObject


logger = getLogger("wstore.default_logger")

class AuthenticationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def _get_api_user(self, request):
        from django.conf import settings
        from django.contrib.auth.models import AnonymousUser
        from wstore.models import Organization, User

        # Get User information from the request
        token_info = ["bearer", "token"]
        try:
            if settings.PROPAGATE_TOKEN:
                token_info = request.META["HTTP_AUTHORIZATION"].split(" ")

            actor_id = request.META["HTTP_X_ACTOR_ID"]
            user_id = request.META["HTTP_X_USER_ID"]

            display_name = request.META["HTTP_X_DISPLAY_NAME"]
            email = request.META["HTTP_X_EMAIL"]
            roles = request.META["HTTP_X_ROLES"].split(",")

            idp = request.META["HTTP_X_IDP_ID"]

            party_id = request.META["HTTP_X_PARTY_ID"]
            user_party_id = request.META["HTTP_X_USER_PARTY_ID"]

            if "HTTP_X_ISSUER_DID" in request.META:
                issuerDid = request.META["HTTP_X_ISSUER_DID"]
            else:
                issuerDid = "none"
        except Exception as e:
            logger.info("Anonymous request due to missing header")
            logger.debug("Error: " + str(e))
            return AnonymousUser()

        if len(token_info) != 2 and token_info[0].lower() != "bearer":
            logger.info("Anonymous request due to invalid token header")
            return AnonymousUser()

        # Check if the user already exist
        try:
            user = User.objects.get(username=user_id)
        except:
            user = User.objects.create(username=user_id)

        if actor_id == user_id:
            # Update user info
            user.email = email
            user.userprofile.complete_name = display_name
            user.is_staff = settings.ADMIN_ROLE.lower() in roles
            user.save()

        user_roles = []

        if settings.PROVIDER_ROLE in roles:
            user_roles.append("provider")

        if settings.CUSTOMER_ROLE in roles:
            user_roles.append("customer")

        # Get or create current organization
        try:
            org = Organization.objects.get(name=actor_id)
        except:
            org = Organization.objects.create(name=actor_id)

        org.private = actor_id == user_id
        org.idp = idp
        org.issuerDid = issuerDid
        org.actor_id = party_id
        org.save()

        user.userprofile.current_roles = user_roles
        user.userprofile.current_organization = org
        user.userprofile.access_token = token_info[1]
        user.userprofile.actor_id = user_party_id

        # change user.userprofile.current_organization
        user.userprofile.save()

        logger.debug(f"Current Actor: {actor_id}")
        logger.debug(f"Current User: {user_id}")
        logger.debug(f"Current Party ID: {party_id}")
        logger.debug(f"Current User Party ID: {user_party_id}")
        logger.debug(f"Current token: {token_info[1]}")

        return user

    def __call__(self, request):
        request.user = SimpleLazyObject(lambda: self._get_api_user(request))

        response = self.get_response(request)
        return response
