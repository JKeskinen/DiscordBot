import os
from datetime import timedelta

# Basic tokens / channel ids
# You can override these by editing this file or via environment variables.
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN', '')
TEST_CHANNEL_ID = os.environ.get('DISCORD_TEST_CHANNEL_ID', '1456702993377267905')
DISCORD_CHANNEL_ID = int(os.environ.get('DISCORD_CHANNEL_ID', TEST_CHANNEL_ID))
DISCORD_THREAD_ID = int(os.environ.get('DISCORD_THREAD_ID', TEST_CHANNEL_ID))
DISCORD_WEEKLY_THREAD_ID = int(os.environ.get('DISCORD_WEEKLY_THREAD_ID', TEST_CHANNEL_ID))
DISCORD_DISCS_THREAD_ID = os.environ.get('DISCORD_DISCS_THREAD', TEST_CHANNEL_ID)
DISCORD_PDGA_THREAD = int(os.environ.get('DISCORD_PDGA_THREAD', TEST_CHANNEL_ID))
# Backwards-compatible aliases
DISCORD_PDGA_THREAD_ID = DISCORD_PDGA_THREAD
DISCORD_WEEKLY_THREAD = DISCORD_WEEKLY_THREAD_ID
DISCORD_DISCS_THREAD = DISCORD_DISCS_THREAD_ID

# File paths / caches
WEEKLY_JSON = os.environ.get('WEEKLY_JSON', 'weekly_pair.json')
CACHE_FILE = os.environ.get('CACHE_FILE', 'known_pdga_competitions.json')
REG_CHECK_FILE = os.environ.get('REG_CHECK_FILE', 'pending_registration.json')
KNOWN_WEEKLY_FILE = os.environ.get('KNOWN_WEEKLY_FILE', 'known_weekly_competitions.json')
KNOWN_DOUBLES_FILE = os.environ.get('KNOWN_DOUBLES_FILE', 'known_doubles_competitions.json')
KNOWN_PDGA_DISCS_FILE = os.environ.get('KNOWN_PDGA_DISCS_FILE', 'known_pdga_discs_specs.json')

# Location / search defaults
WEEKLY_LOCATION = os.environ.get('WEEKLY_LOCATION', 'Etelä-Pohjanmaa')
WEEKLY_RADIUS_KM = int(os.environ.get('WEEKLY_RADIUS_KM', '100'))
WEEKLY_SEARCH_URL = os.environ.get('WEEKLY_SEARCH_URL', '')
METRIX_URL = os.environ.get('METRIX_URL', '')

# Intervals and scheduling (seconds unless noted)
AUTO_LIST_INTERVAL = int(os.environ.get('AUTO_LIST_INTERVAL', '86400'))
CHECK_INTERVAL = int(os.environ.get('CHECK_INTERVAL', '600'))
CHECK_REGISTRATION_INTERVAL = int(os.environ.get('CHECK_REGISTRATION_INTERVAL', '3600'))
CAPACITY_CHECK_INTERVAL = int(os.environ.get('CAPACITY_CHECK_INTERVAL', '1800'))
DISCS_CHECK_INTERVAL = int(os.environ.get('DISCS_CHECK_INTERVAL', '86400'))

# Daily digest time (24h)
DAILY_DIGEST_HOUR = int(os.environ.get('DAILY_DIGEST_HOUR', '4'))
DAILY_DIGEST_MINUTE = int(os.environ.get('DAILY_DIGEST_MINUTE', '0'))

# Behavior toggles
AUTO_RUN_ON_STARTUP = os.environ.get('AUTO_RUN_ON_STARTUP', '1')  # '1' or '0'
RUN_DIGEST_ON_PRESENCE = os.environ.get('RUN_DIGEST_ON_PRESENCE', '1')  # '1' or '0'

# Discord formatting
DISCORD_SHOW_DATE = os.environ.get('DISCORD_SHOW_DATE', '1')
DISCORD_DATE_FORMAT = os.environ.get('DISCORD_DATE_FORMAT', 'DD.MM.YYYY')
DISCORD_SHOW_ID = os.environ.get('DISCORD_SHOW_ID', '0')
DISCORD_SHOW_LOCATION = os.environ.get('DISCORD_SHOW_LOCATION', '0')
DISCORD_LINE_SPACING = int(os.environ.get('DISCORD_LINE_SPACING', '1'))

# Message templates / info texts
STARTUP_GREETING = (
    "Terve kaikki! LakeusBotti on livenä ja on aika muutamalle ilmoitukselle. "
    "Ilmoitan pian muun muassa eilisen jälkeen julkaistut kisat sekä PDGA:ssa että viikkarimuodossa. "
    "Kerron myös uudet julkaisut PDGA:n puolelta ja tottakai tuoreimmat tulokset."
)
STARTUP_PROMPT = "Jos haluatte kysyä enemmän, laitan ohjeet tulemaan tiedotusten jälkeen (komento: !ohje)."
STARTUP_ORDER = [
    "viikkokisat",
    "parikisat",
    "pdga_kisat",
    "low_spots_warning",
    "tulokset",
    "pdga_uutiset",
]
LOW_SPOTS_WARNING = "VÄHIIN KÄY PAIKAT NÄISSÄ KISOISSA! Katso lisätiedot komennolla: !paikat"
NO_PDGANEWS_TEXT = "Ei uusia julkaisuja PDGA:lta, tarkistetaan huomenna uudestaan."

# Presentation options
PDGA_SHOW_TIER = True
PDGA_OMIT_TIME = True  # Remove specific time from PDGA listings (show only date)

# Misc
DEFAULT_MAX_PDGA_LIST = 40
DEFAULT_MAX_WEEKLY_LIST = 40

# Export these names for convenience
__all__ = [
    'DISCORD_TOKEN', 'TEST_CHANNEL_ID', 'DISCORD_CHANNEL_ID', 'DISCORD_THREAD_ID', 'DISCORD_WEEKLY_THREAD_ID',
    'DISCORD_DISCS_THREAD_ID', 'WEEKLY_JSON', 'CACHE_FILE', 'REG_CHECK_FILE', 'KNOWN_WEEKLY_FILE',
    'KNOWN_DOUBLES_FILE', 'KNOWN_PDGA_DISCS_FILE', 'WEEKLY_LOCATION', 'WEEKLY_RADIUS_KM',
    'WEEKLY_SEARCH_URL', 'METRIX_URL', 'AUTO_LIST_INTERVAL', 'CHECK_INTERVAL', 'CHECK_REGISTRATION_INTERVAL',
    'CAPACITY_CHECK_INTERVAL', 'DISCS_CHECK_INTERVAL', 'DAILY_DIGEST_HOUR', 'DAILY_DIGEST_MINUTE',
    'AUTO_RUN_ON_STARTUP', 'RUN_DIGEST_ON_PRESENCE', 'DISCORD_SHOW_DATE', 'DISCORD_DATE_FORMAT',
    'DISCORD_SHOW_ID', 'DISCORD_SHOW_LOCATION', 'DISCORD_LINE_SPACING', 'STARTUP_GREETING', 'STARTUP_PROMPT',
    'STARTUP_ORDER', 'LOW_SPOTS_WARNING', 'NO_PDGANEWS_TEXT', 'PDGA_SHOW_TIER', 'PDGA_OMIT_TIME',
]
