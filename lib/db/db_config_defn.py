import json

from lib.db.db import DB


class DBConfigDefn(DB):

    def get_area_dict(self, _where):
        return self.get_dict('area', (_where,))[0]

    def get_area_json(self, _where):
        return json.dumps(self.get_dict('area', (_where,))[0])

    def get_sections_dict(self, _where):
        rows_dict = {}
        rows = self.get_dict('section', (_where,))
        for row in rows:
            settings = json.loads(row['settings'])
            row['settings'] = settings
            rows_dict[row['name']] = row
        return rows_dict

    def get_areas(self):
        """ returns an array of the area names in id order
        """
        area_tuple = self.get('area_keys')
        areas = [area[0] for area in area_tuple]
        return areas
