# Esta clase se conectará con el asset manager o se llamará al mismo
# tiempo que esta

# Cosas que necesito:
# Tener related party, no se puede crear un service specification sin related party
# En principio estos serían service specifications, pero no hay relación entre
# service specification y service category

import base64
import json
import os
import threading
from logging import getLogger
from urllib.parse import urljoin

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

from wstore.models import Resource, ResourcePlugin, ResourceVersion
from wstore.store_commons.database import DocumentLock
from wstore.store_commons.errors import ConflictError
from wstore.store_commons.rollback import downgrade_asset, downgrade_asset_pa, rollback
from wstore.store_commons.utils.name import is_valid_file
from wstore.store_commons.utils.url import is_valid_url, url_fix
from wstore.asset_manager import service_specification_imp, service_candidate_imp, service_category_imp

logger = getLogger("wstore.default_logger")

# Espero recibir el json bien montado


class ServiceSpecificationManager:
    def __init__(self):
        pass

    def create_service_spec_cand(self, service_json):

        ############
        # Marcos
        # Preguntar sobre el related party
        # Falta related party, pero non sei se hai que telo en conta

        #plugin_name = resource.resource_type
        #category = cat_service.get_service_category(plugin_name)
        #cat_service = service_category_imp.ServiceCategory()
        #resource_id = resource.get_id()

        #service_json = {
        #    "name" : "",
        #    "description" : "",
        #    "version" : resource.version,
        #    "specCharacteristic" : [{
        #        "name" : str(resource_id)
        #    }]
        #}
        sp_service = service_specification_imp.ServiceSpecification()
        created_specification = sp_service.create_service_specification(service_json)
        
        # Para o candiate json necesito a referencia ao service e ao category
        # Hai que comprobar si mete los elementos que tocan
        candidate_json = {
            "version" : created_specification['version'],
            "serviceSpecification" : created_specification,
            "category" : service_json.category
        }
        cand_service = service_candidate_imp.ServiceCandidate()
        cand_service.create_service_candidate(candidate_json)
        ############


    def update_service_spec_cand(self, plugin_name,service_json):

        ############
        # Marcos
        # Preguntar sobre el related party
        # Falta related party, pero non sei se hai que telo en conta
        # El provider puede ser el un EntitySpecifcicationRelationship
        # Non sei cales son os characteristic que necesito

        cat_service = service_category_imp.ServiceCategory()
        category = cat_service.get_service_category(plugin_name)

        #service_json = {
        #    "name" : "",
        #    "description" : "",
        #    "version" : resource.version,
        #    "specCharacteristic" :{
        #        "name" : str(resource_id)
        #    }
        #}
        sp_service = service_specification_imp.ServiceSpecification()
        updated_specification = sp_service.update_service_specification(category.service_id, service_json)
        ############
