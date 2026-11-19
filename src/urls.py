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

from django.conf.urls import url

import wstore.urls
from wstore.views import ServeMedia

urlpatterns = [
    url(
        # Retain legacy matches while admitting the expanded upload filenames.
        r"^charging/media/(?P<path>.+)/(?P<name>[\w -.]+|[^/\\#?%\x00-\x1f\x7f-\x9f]+)/?$",
        ServeMedia(permitted_methods=("GET",)),
    )
]

urlpatterns += wstore.urls.urlpatterns
