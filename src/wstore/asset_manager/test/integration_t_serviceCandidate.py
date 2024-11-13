import json
from copy import deepcopy
from datetime import datetime
from importlib import reload

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from parameterized import parameterized

from wstore.asset_manager import service_candidate_imp
#from wstore.charging_engine.accounting.errors import UsageError

#./manage.py test wstore.asset_manager.test.integration_t_serviceCandidate
#Revisar porque ao mellor teño que cambiarlle o nombre a serviceCandidateClient

EMPTY_SERVICE_CANDIDATE = {
    "name" : "test"
}


class ServiceCandidateClientTestCase(TestCase):
    tags = ("service-catalog-client",)

    def setUp(self):
        service_candidate_imp.settings.SERVICE = "http://host.docker.internal:8638"

    def _addIdHref(self, gson, returned):
        print(returned['id'])

        gson["id"] = returned['id']
        gson["href"] = returned['href']

    def _delete_all_service_candidate(self):

        client = service_candidate_imp.ServiceCandidate()
        services_c = client.get_service_candidate()
        while len(services_c) > 0 :
            client.delete_service_candidate(services_c[0]['id'])
            services_c = client.get_service_candidate()

        self.assertEquals([], client.get_service_candidate())

    @parameterized.expand(
        [
            ("empty service candidate", EMPTY_SERVICE_CANDIDATE, EMPTY_SERVICE_CANDIDATE)
        ]
    )

    def test_create_service_candidate(self, name, response, exp_resp):
        
        client = service_candidate_imp.ServiceCandidate()
        created_service_candidate= client.create_service_candidate(response)
        exp_resp["lastUpdate"] = created_service_candidate["lastUpdate"]
        self._addIdHref(exp_resp, created_service_candidate)
        self.assertEquals(exp_resp, created_service_candidate)
        self._delete_all_service_candidate()


    @parameterized.expand(
        [
            ("empty service candidate", EMPTY_SERVICE_CANDIDATE, EMPTY_SERVICE_CANDIDATE)
        ]
    )

    def test_update_service_candidate(self, name, response, exp_resp):
    
        client = service_candidate_imp.ServiceCandidate()
        created_service_candidate = client.create_service_candidate(response)

        name = "prueba"
        expected_json = {"name": name}
        client.update_service_candidate(created_service_candidate['id'], expected_json)
        self._delete_all_service_candidate()

        #The update works, but it does not return anything so no 

    @parameterized.expand(
        [
            ("empty service candidate", EMPTY_SERVICE_CANDIDATE, EMPTY_SERVICE_CANDIDATE)
        ]
    )

    def test_get_delete_service_candidate(self, name, response, exp_resp):

        client = service_candidate_imp.ServiceCandidate()
        created_service_candidate = client.create_service_candidate(response)
        got_service_candidate = client.get_service_candidate(created_service_candidate['name'])
        print(created_service_candidate)
        print(got_service_candidate[0])
        self.assertEquals(created_service_candidate, got_service_candidate[0])

        client.delete_service_candidate(got_service_candidate[0]['id'])
        got_service_candidate = client.get_service_candidate()
        self.assertEquals([], got_service_candidate)
        self._delete_all_service_candidate()


        

