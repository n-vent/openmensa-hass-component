import logging
from datetime import timedelta, datetime
import unicodedata
from urllib.error import HTTPError

import voluptuous as vol
import holidays

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import CONF_CODE, CONF_REGION, STATE_UNAVAILABLE
from homeassistant.helpers.entity import Entity
import homeassistant.helpers.config_validation as cv
from homeassistant.util import Throttle

_LOGGER = logging.getLogger(__name__)

CONF_DEFAULT_MENSA = 828
CONF_DEFAULT_REGION = "RP"
MEAL_CATEGORY = "category"

MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=5)
CONST_NAME = "name"
CONST_MEALS = "meals"
STATE_ONLINE = "online"
STATE_NO_MEALS = "no_meals"

ICON = "mdi:hamburger"

VALID_REGIONS = [
    "BW", "BY", "BE", "BB", "HB", "HH", "HE", "MV",
    "NI", "NW", "RP", "SL", "SN", "ST", "SH", "TH",
]

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_CODE, default=CONF_DEFAULT_MENSA): cv.positive_int,
    vol.Optional(CONF_REGION, default=CONF_DEFAULT_REGION): vol.In(VALID_REGIONS),
})

def setup_platform(hass, config, add_entities, discovery_info=None):
    from openmensa import OpenMensa as om

    _LOGGER.debug("setup openmensa sensor")
    mensa = config.get(CONF_CODE)
    region = config.get(CONF_REGION)
    add_entities([OpenmensaSensor(om, mensa, region)], True)


class OpenmensaSensor(Entity):
    """Representation of a Sensor."""

    def __init__(self, om, mensa, region):
        """Initialize the sensor."""
        self._om = om
        self._mensa = mensa
        self._region = region
        self._state = STATE_UNAVAILABLE
        self._meals = None

    def meal_category_from_categories_list(self, categories, search_category):
        for category in categories:
            if category[CONST_NAME] == search_category:
                return category
        return None

    def get_meals_by_date(self, date_str):
        categories = []
        try:
            meals = self._om.get_meals_by_day(self._mensa, date_str)
            for meal in meals:
                meal_category = meal[MEAL_CATEGORY]
                category = self.meal_category_from_categories_list(
                    categories, meal_category
                )
                if category is None:
                    category = {CONST_NAME: meal[MEAL_CATEGORY], CONST_MEALS: []}
                    categories.append(category)
                category[CONST_MEALS].append({CONST_NAME: meal[CONST_NAME]})
        except HTTPError:
            self._state = STATE_NO_MEALS

        return categories

    def next_workday(self):
        de_holidays = holidays.Germany(subdiv=self._region)
        day = datetime.now() + timedelta(days=1)
        while day.weekday() >= 5 or day.date() in de_holidays:
            day += timedelta(days=1)
        return day.strftime("%Y-%m-%d")

    def get_meals(self):
        today_date_str = datetime.now().strftime("%Y-%m-%d")
        next_date_str = self.next_workday()
        meals = {"today": self.get_meals_by_date(today_date_str),
                 "next_workday": self.get_meals_by_date(next_date_str)}
        return meals

    def normalize_string(self, my_string):
        """
        Normalize a String with Umlauts and blanks to ascii, lowercase and _ instead of blanks.
        :param my_string:
        :return:
        """
        return (
            unicodedata.normalize("NFKD", my_string)
            .encode("ASCII", "ignore")
            .decode()
            .replace(" ", "_")
            .lower()
        )

    @property
    def name(self):
        return "Openmensa Sensor"

    @property
    def icon(self):
        return ICON

    @property
    def state(self):
        return self._state

    @property
    def state_attributes(self):
        if self._state == STATE_UNAVAILABLE:
            return {}
        attr = {}
        attr["meals"] = self._meals
        return attr

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        """Fetch new meals for the day
        """
        _LOGGER.debug("Updating meals of the day.")
        self._state = STATE_ONLINE
        self._meals = self.get_meals()
