
def set_override_long(config_obj, section, key):
    if (config_obj.data["main"]["override_latitude"] is not None) \
            and (config_obj.data["main"]["override_longitude"] is not None):
        config_obj.data["main"]["mock_location"] = {
            "latitude": config_obj.data["main"]["override_latitude"],
            "longitude": config_obj.data["main"]["override_longitude"]
        }
