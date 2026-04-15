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

from contextvars import ContextVar


_CURRENT_PARTY_ID = ContextVar("current_party_id", default=None)


def set_current_party_id(party_id):
    return _CURRENT_PARTY_ID.set(party_id)


def get_current_party_id():
    return _CURRENT_PARTY_ID.get()


def reset_current_party_id(token):
    _CURRENT_PARTY_ID.reset(token)
