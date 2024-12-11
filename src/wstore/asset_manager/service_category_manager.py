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


class ServiceCategoryManager:
    def __init__(self):
        pass

    def create_service_cat(self, plugin_model, rb_log=None):

        ############
        # Marcos


        logger.debug("Serializar el json")
        #sc_json = {
        #    "name" : plugin_model.name,
        #    "version" : plugin_model.version
        #}
        logger.debug("Tras serializar")
        sc_client = service_category_imp.ServiceCategory()
        return sc_client.create_service_category(plugin_model)
        ############

    def update_service_cat(self, category_id, plugin_model):

        ############
        # Marcos
        # Preguntar sobre el related party
        # Falta related party, pero non sei se hai que telo en conta
        # El provider puede ser el un EntitySpecifcicationRelationship
        # Non sei cales son os characteristic que necesito

        sc_json = {
            "name" : plugin_model.name,
            "version" : plugin_model.version
        }

        sc_client = service_category_imp.ServiceCategory()
        sc_client.update_service_category(category_id ,sc_json)
        ############

    def remove_service_cat(self, category_id):

        ############
        # Marcos
        # Preguntar sobre el related party
        # Falta related party, pero non sei se hai que telo en conta
        # El provider puede ser el un EntitySpecifcicationRelationship
        # Non sei cales son os characteristic que necesito

        sc_client = service_category_imp.ServiceCategory()
        sc_client.delete_service_category(category_id)
        ############