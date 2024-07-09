import json
from copy import deepcopy
from datetime import datetime
from importlib import reload

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from parameterized import parameterized

from wstore.asset_manager import service_category_imp
#from wstore.charging_engine.accounting.errors import UsageError

#./manage.py test wstore.asset_manager.test.integration_t_serviceCategory
#Revisar porque ao mellor teño que cambiarlle o nombre a serviceCategoryClient

EMPTY_SERVICE_CATALOG = {
    "name" : "test"
}


class ServiceCategoryClientTestCase(TestCase):
    tags = ("service-catalog-client",)

    def setUp(self):
        service_category_imp.settings.SERVICE = "http://host.docker.internal:8638"

    def _addIdHref(self, gson, returned):
        print(returned['id'])

        gson["id"] = returned['id']
        gson["href"] = returned['href']

    def _delete_all_service_category(self):

        client = service_category_imp.ServiceCategory()
        services_c = client.get_service_category()
        while len(services_c) > 0 :
            client.delete_service_category(services_c[0]['id'])
            services_c = client.get_service_category()

        self.assertEquals([], client.get_service_category())

    @parameterized.expand(
        [
            ("empty service category", EMPTY_SERVICE_CATALOG, EMPTY_SERVICE_CATALOG)
        ]
    )

    def test_create_service_category(self, name, response, exp_resp):
        
        client = service_category_imp.ServiceCategory()
        created_service_category= client.create_service_category(response)
        exp_resp["lastUpdate"] = created_service_category["lastUpdate"]
        self._addIdHref(exp_resp, created_service_category)
        self.assertEquals(exp_resp, created_service_category)
        self._delete_all_service_category()


    @parameterized.expand(
        [
            ("empty service category", EMPTY_SERVICE_CATALOG, EMPTY_SERVICE_CATALOG)
        ]
    )

    def test_update_service_category(self, name, response, exp_resp):
    
        client = service_category_imp.ServiceCategory()
        created_service_category = client.create_service_category(response)

        name = "prueba"
        expected_json = {"name": name}
        client.update_service_category(created_service_category['id'], expected_json)
        self._delete_all_service_category()

        #The update works, but it does not return anything so no 

    @parameterized.expand(
        [
            ("empty service category", EMPTY_SERVICE_CATALOG, EMPTY_SERVICE_CATALOG)
        ]
    )

    def test_get_delete_service_category(self, name, response, exp_resp):

        client = service_category_imp.ServiceCategory()
        created_service_category = client.create_service_category(response)
        got_service_category = client.get_service_category(created_service_category['name'])
        print(created_service_category)
        print(got_service_category[0])
        self.assertEquals(created_service_category, got_service_category[0])

        client.delete_service_category(got_service_category[0]['id'])
        got_service_category = client.get_service_category()
        self.assertEquals([], got_service_category)


        

