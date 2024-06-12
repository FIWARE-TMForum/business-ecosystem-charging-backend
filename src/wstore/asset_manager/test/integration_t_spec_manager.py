# Orde de creación de cosas:
#   Necesito crear un plugin y después crear el service specification

import json
from copy import deepcopy
from datetime import datetime
from importlib import reload

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from parameterized import parameterized
from wstore.asset_manager import service_specification_manager, service_category_imp, service_candidate_imp, service_specification_imp
from wstore.models import Resource, ResourcePlugin, ResourceVersion

#./manage.py test wstore.asset_manager.test.integration_t_spec_manager
# No hay assertequals, solo ver que se crean bien los elementos


class ServiceSpecificationManagerTest(TestCase):

    tags = ("service-specification-manager",)

    def _addIdHref(self, gson, returned):
        print(returned['id'])

        gson["id"] = returned['id']
        gson["href"] = returned['href']

    def _delete_all_service_specification(self):

        client = service_specification_imp.ServiceSpecification()
        services_c = client.get_service_specification()
        while len(services_c) > 0 :
            client.delete_service_specification(services_c[0]['id'])
            services_c = client.get_service_specification()

        self.assertEquals([], client.get_service_specification())

    def _delete_all_service_category(self):

        client = service_category_imp.ServiceCategory()
        services_c = client.get_service_category()
        while len(services_c) > 0 :
            client.delete_service_category(services_c[0]['id'])
            services_c = client.get_service_category()

        self.assertEquals([], client.get_service_category())

    def _delete_all_service_candidate(self):

        client = service_candidate_imp.ServiceCandidate()
        services_c = client.get_service_candidate()
        while len(services_c) > 0 :
            client.delete_service_candidate(services_c[0]['id'])
            services_c = client.get_service_candidate()

        self.assertEquals([], client.get_service_candidate())

    def test_create_service_spec_from_asset(self):

        sp = service_specification_manager.ServiceSpecificationManager()

        resource = Resource.objects.create(
            provider=None,
            version="0.1",
            download_link="link",
            resource_path="path",
            content_type="content type",
            resource_type="plugin",
            state="state",
            is_public=False
        )

        resource_json = {
            "name" : "plugin"
        }

        category = service_category_imp.ServiceCategory()
        category.create_service_category(resource_json)

        sp.create_service_spec_cand(resource)

        self._delete_all_service_candidate()
        self._delete_all_service_category()
        self._delete_all_service_specification()

