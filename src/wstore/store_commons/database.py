# -*- coding: utf-8 -*-

# Copyright (c) 2015 - 2017 CoNWeT Lab., Universidad Politécnica de Madrid
# Copyright (c) 2023 Future Internet Consulting and Development Solutions S.L.

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


from logging import getLogger

from django.conf import settings
from pymongo import MongoClient

logger = getLogger("wstore.default_logger")


def get_database_connection():
    """
    Gets a raw database connection to MongoDB
    """
    logger.debug("Getting connection to MongoDB")

    # Get database info from settings
    database_info = settings.DATABASES["default"]

    # Create database connection
    client = None
    if 'CLIENT' in database_info:
        client_info = database_info['CLIENT']
        db_name = database_info['NAME']

        if "host" in client_info and "port" in client_info and "username" in client_info:
            client = MongoClient(
                client_info['host'],
                int(client_info['port']),
                username=client_info['username'],
                password=client_info['password'],
                authSource=db_name)

        elif "host" in client_info and "port" in client_info and "username" not in client_info:
            client = MongoClient(client_info["host"], int(client_info["port"]))

        elif "host" in client_info and "port" not in client_info and "username" in client_info:
            client = MongoClient(
                client_info['host'],
                username=client_info['username'],
                password=client_info['password'],
                authSource=db_name)

        elif "host" in client_info and "port" not in client_info and "username" not in client_info:
            client = MongoClient(client_info["host"])

        elif "host" not in client_info and "port" in client_info and "username" in client_info:
            client = MongoClient(
                'localhost',
                int(client_info['port']),
                username=client_info['username'],
                password=client_info['password'],
                authSource=db_name)

        elif "host" not in client_info and "port" in client_info and "username" not in client_info:
            client = MongoClient("localhost", int(client_info["port"]))

        else:
            client = MongoClient()
    else:
        client = MongoClient()

    db = client[db_name]

    logger.info(f"Connected to MongoDB: {db_name} OK")
    return db


class DocumentLock:
    def __init__(self, collection, doc_id, lock_id):
        self._collection = collection
        self._doc_id = doc_id
        self._lock_id = "_lock_{}".format(lock_id)
        self._db = get_database_connection()

    def lock_document(self):
        prev = self._db[self._collection].find_one_and_update({"_id": self._doc_id}, {"$set": {self._lock_id: True}})
        logger.debug(f"Locked document {self._lock_id}")
        return prev is not None and self._lock_id in prev and prev[self._lock_id]

    def wait_document(self):
        locked = self.lock_document()
        logger.debug(f"Waiting for document {self._lock_id}")

        while locked:
            locked = self.lock_document()

    def unlock_document(self):
        logger.debug(f"Unlocked document {self._lock_id}")
        self._db[self._collection].find_one_and_update({"_id": self._doc_id}, {"$set": {self._lock_id: False}})
