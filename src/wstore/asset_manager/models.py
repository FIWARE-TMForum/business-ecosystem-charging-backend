# -*- coding: utf-8 -*-

# Copyright (c) 2013 - 2017 CoNWeT Lab., Universidad Politécnica de Madrid
# Copyright (c) 2021 Future Internet Consulting and Development Solutions S. L.

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

from urllib.parse import urljoin

from django.conf import settings
from djongo import models
from djongo.models.fields import JSONField

from wstore.models import Organization


# This embedded class is used to save old versions
# of resources to allow downgrades
class ResourceVersion(models.Model):
    _id = models.ObjectIdField()
    version = models.CharField(max_length=20)
    resource_path = models.CharField(max_length=100)
    download_link = models.URLField()
    content_type = models.CharField(max_length=100)
    meta_info = models.JSONField()

    class Meta:
        managed = False

    def __getitem__(self, name):
        return getattr(self, name)


class Resource(models.Model):
    _id = models.ObjectIdField() # necesita ser accesible, pode poser un método get_id
    #product_id = models.CharField(max_length=100, blank=True, null=True)
    service_spec_id = models.CharField(max_length=100, blank=True, null=True) #este es el id del service spec del api
    version = models.CharField(max_length=20)  # This field maps the Product Spec version
    provider = models.ForeignKey(Organization, on_delete=models.DO_NOTHING)
    content_type = models.CharField(max_length=100)
    download_link = models.URLField()
    resource_path = models.CharField(max_length=100)
    old_versions = models.ArrayField(model_container=ResourceVersion)
    state = models.CharField(max_length=20)
    resource_type = models.CharField(max_length=100, blank=True, null=True)
    is_public = models.BooleanField(default=False)
    has_terms = models.BooleanField(default=False)

    bundled_assets = models.JSONField(default=[])  # List
    meta_info = models.JSONField(default={})  # Dict

    def get_url(self):
        return self.download_link

    def get_uri(self):
        base_uri = settings.SITE

        return urljoin(base_uri, "charging/api/assetManagement/assets/" + str(self.pk))

    #def get_id(self):
    #    return self._id

    class Meta:
        app_label = "wstore"


class ResourcePlugin(models.Model):
    _id = models.ObjectIdField()
    plugin_id = models.CharField(max_length=100) # Plugin name
    category_id = models.CharField(max_length=100) # Id del category en el API
    name = models.CharField(max_length=100)
    version = models.CharField(max_length=50)
    version_history = models.JSONField(default=[])
    author = models.CharField(max_length=100)
    form_order = models.JSONField(default=[])  # String List
    module = models.CharField(max_length=200)
    media_types = models.JSONField(default=[])  # String List
    formats = models.JSONField(default=[])  # String List
    overrides = models.JSONField(default=[])  # String List
    options = models.JSONField(default={})  # Dict
    form = models.JSONField(default={})  # Dict

    # Whether the plugin must ask for accounting info
    pull_accounting = models.BooleanField(default=False)

    def __str__(self):
        return self.plugin_id

    class Meta:
        app_label = "wstore"
