
from logging import getLogger

logger = getLogger("wstore.charging_engine.cb_listener")

class Cb_listener:
    def __init__(self, customer_bill):
        self.cb = customer_bill

    def listen(self):
        logger.debug(f"start listening to {self.cb}")