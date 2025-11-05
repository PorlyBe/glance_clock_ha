DOMAIN = "glance_clock"

# Glance Clock specific service UUID (from the docs)
GLANCE_SERVICE_UUID = "5075f606-1e0e-11e7-93ae-92361f002671"
GLANCE_CHARACTERISTIC_UUID = "5075fb2e-1e0e-11e7-93ae-92361f002671"

# Settings characteristic (same as GLANCE_CHARACTERISTIC_UUID but more explicit)
SETTINGS_CHARACTERISTIC_UUID = "5075fb2e-1e0e-11e7-93ae-92361f002671"

# Scene characteristics
SCENE_DATA_CHARACTERISTIC_UUID = "5075ffac-1e0e-11e7-93ae-92361f002671"
SCENE_STATE_DATA_CHARACTERISTIC_UUID = "5075fc78-1e0e-11e7-93ae-92361f002671"

# Notification constants (matching protobuf enums)
ANIMATIONS = {
    "none": 0,
    "pulse": 1,
    "wave": 2,
    "fire": 10,
    "wheel": 11,
    "flower": 12,
    "flower2": 13,
    "fan": 14,
    "sun": 15,
    "thunderstorm": 16,
    "cloud": 17,
    "weather_clear": 101,
    "weather_cloudy": 102,
    "weather_fog": 103,
    "weather_light_rain": 104,
    "weather_rain": 105,
    "weather_thunderstorm": 106,
    "weather_snow": 107,
    "weather_hail": 108,
    "weather_wind": 109,
    "weather_tornado": 110,
    "weather_hurricane": 111,
    "weather_snow_thunderstorm": 112,
}

SOUNDS = {
    "none": 0,
    "waves": 1,
    "rise": 2,
    "charging": 3,
    "steps": 4,
    "radar": 5,
    "bells": 6,
    "bye": 7,
    "hello": 8,
    "flowers": 9,
    "circles": 10,
    "complete": 11,
    "popcorn": 12,
    "break": 13,
    "opening": 14,
    "high": 15,
    "shine": 16,
    "extension": 17,
}

COLORS = {
    "black": 0,
    "dark_golden_rod": 1,
    "dark_orange": 2,
    "olive": 3,
    "orange_red": 4,
    "red": 5,
    "maroon": 6,
    "dark_magenta": 7,
    "medium_violet_red": 8,
    "brown": 9,
    "indigo": 10,
    "blue_violet": 11,
    "white": 12,
    "light_slate_blue": 13,
    "royal_blue": 14,
    "blue": 15,
    "cornflower_blue": 16,
    "sky_blue": 17,
    "turquoise": 18,
    "aqua": 19,
    "medium_spring_green": 20,
    "lime_green": 21,
    "dark_green": 22,
    "lime": 23,
    "lawn_green": 24,
}

PRIORITIES = {
    "low": 1,
    "medium": 16,
    "high": 48,
    "highest": 64,
    "critical": 80,
}

TEXT_MODIFIERS = {
    "none": 0,
    "repeat": 1,
    "rapid": 2,
    "delay": 3,
}
