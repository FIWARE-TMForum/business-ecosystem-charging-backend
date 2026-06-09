# -*- coding: utf-8 -*-

# Copyright (c) 2026 Future Internet Consulting and Development Solutions S.L.
#
# This file belongs to the business-charging-backend
# of the Business API Ecosystem.
#
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

import base64
import json

from django.conf import settings

from wstore.store_commons.utils.url import get_service_url
from wstore.store_commons.utils.url import is_valid_url


FEDERATION_REF_PREFIX = "federationRef::"


def resolve_federation_ref(entity_id):
    if not isinstance(entity_id, str) or len(entity_id) == 0:
        raise ValueError("The entity id must be a non-empty string")

    if not settings.FEDERATION_ENABLED or not entity_id.startswith(FEDERATION_REF_PREFIX):
        return {"id": entity_id, "source_endpoint": None}

    payload = entity_id[len(FEDERATION_REF_PREFIX):]
    if len(payload) == 0:
        raise ValueError("Invalid federation reference: missing payload")

    padding = "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(f"{payload}{padding}".encode("ascii"))
        ref_data = json.loads(decoded.decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("Invalid federation reference payload")

    source_endpoint = ref_data.get("sourceEndpoint")
    resolved_id = ref_data.get("id")

    if not isinstance(source_endpoint, str) or not is_valid_url(source_endpoint):
        raise ValueError("Invalid federation reference sourceEndpoint")

    if not isinstance(resolved_id, str) or len(resolved_id) == 0:
        raise ValueError("Invalid federation reference id")

    return {"id": resolved_id, "source_endpoint": source_endpoint}


def get_service_url_from_ref(api, collection_path, entity_id):
    resolved_ref = resolve_federation_ref(entity_id)

    federation_context = None
    if resolved_ref["source_endpoint"] is not None:
        federation_context = {"source_endpoint": resolved_ref["source_endpoint"]}

    normalized_path = collection_path.rstrip("/")
    return get_service_url(
        api,
        f"{normalized_path}/{resolved_ref['id']}",
        federation_context=federation_context,
    )


def resolve_party_ref(party_id):
    resolved_ref = resolve_federation_ref(party_id)
    resolved_party_id = resolved_ref["id"]

    party_parts = resolved_party_id.rsplit(sep=":")
    if len(party_parts) < 3:
        raise ValueError(f"Invalid party id: {resolved_party_id}")

    user_type = party_parts[2]
    if user_type not in ("individual", "organization"):
        raise ValueError(f"Invalid user type: {user_type}")

    federation_context = None
    if resolved_ref["source_endpoint"] is not None:
        federation_context = {"source_endpoint": resolved_ref["source_endpoint"]}

    return {
        "id": resolved_party_id,
        "source_endpoint": resolved_ref["source_endpoint"],
        "user_type": user_type,
        "url": get_service_url(
            "party",
            f"/{user_type}/{resolved_party_id}",
            federation_context=federation_context,
        ),
    }
