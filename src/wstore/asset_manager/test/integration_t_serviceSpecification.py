import json
from copy import deepcopy
from datetime import datetime
from importlib import reload

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from parameterized import parameterized

from wstore.asset_manager import service_specification_imp
#from wstore.charging_engine.accounting.errors import UsageError

#./manage.py test wstore.asset_manager.test.integration_t_serviceSpecification
#Revisar porque ao mellor teño que cambiarlle o nombre a serviceSpecificationClient

EMPTY_SERVICE_SPECIFICATION = {
    "name" : "test"
}


class ServiceSpecificationClientTestCase(TestCase):
    tags = ("service-specification-client",)

    def setUp(self):
        service_specification_imp.settings.SERVICE_CATALOG = "http://host.docker.internal:8638"

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

    @parameterized.expand(
        [
            ("empty service specification", EMPTY_SERVICE_SPECIFICATION, EMPTY_SERVICE_SPECIFICATION)
        ]
    )

    def test_create_service_specification(self, name, response, exp_resp):
        
        client = service_specification_imp.ServiceSpecification()
        created_service_specification= client.create_service_specification(response)
        exp_resp["lastUpdate"] = created_service_specification["lastUpdate"]
        exp_resp["lifecycleStatus"] = created_service_specification["lifecycleStatus"]
        exp_resp["isBundle"] = created_service_specification["isBundle"]
        self._addIdHref(exp_resp, created_service_specification)
        self.assertEquals(exp_resp, created_service_specification)
        self._delete_all_service_specification()


    @parameterized.expand(
        [
            ("empty service specification", EMPTY_SERVICE_SPECIFICATION, EMPTY_SERVICE_SPECIFICATION)
        ]
    )

    def test_update_service_specification(self, name, response, exp_resp):
    
        client = service_specification_imp.ServiceSpecification()
        created_service_specification = client.create_service_specification(response)

        name = "prueba"
        expected_json = {"name": name}
        client.update_service_specification(created_service_specification['id'], expected_json)
        self._delete_all_service_specification()

        #The update works, but it does not return anything so no 

    @parameterized.expand(
        [
            ("empty service specification", EMPTY_SERVICE_SPECIFICATION, EMPTY_SERVICE_SPECIFICATION)
        ]
    )

    def test_get_delete_service_specification(self, name, response, exp_resp):

        client = service_specification_imp.ServiceSpecification()
        created_service_specification = client.create_service_specification(response)
        got_service_specification = client.get_service_specification(created_service_specification['name'])
        print(created_service_specification)
        print(got_service_specification[0])
        self.assertEquals(created_service_specification, got_service_specification[0])

        client.delete_service_specification(got_service_specification[0]['id'])
        got_service_specification = client.get_service_specification()
        self.assertEquals([], got_service_specification)
        self._delete_all_service_specification()