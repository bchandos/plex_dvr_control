import json
import pathlib


class JSONSettings():
    def __init__(self, settings_file, settings_template=None):
        self.settings_file = settings_file
        settings_path = pathlib.Path(self.settings_file)
        if settings_path.exists():
            self.get_settings(self.settings_file)
        elif settings_template and pathlib.Path(settings_template).exists():
            self.get_settings(settings_template)
            self.write_settings()

    def get_settings(self, settings_file):
        with open(settings_file) as json_settings_file:
            self.settings = json.load(json_settings_file)

    def write_settings(self):
        # destructive writing
        with open(self.settings_file, 'w') as json_settings_file:
            json.dump(self.settings, json_settings_file)
        self.get_settings(self.settings_file)

    def add_setting(self, category, setting_name, setting_value):
        self.settings[category][setting_name] = setting_value
        self.write_settings()

    def edit_setting(self, category, setting_name, setting_value):
        self.add_setting(category, setting_name, setting_value)

    def delete_setting(self, category, setting_name):
        self.settings[category].pop('setting_name', None)
        self.write_settings()

    def get_setting(self, category, setting_name):
        try:
            return self.settings[category][setting_name]
        except KeyError:
            return None
