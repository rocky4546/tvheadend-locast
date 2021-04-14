sql = {
    'config_defn_ct': ["""
    CREATE TABLE IF NOT EXISTS area (
        id integer,
        name text NOT NULL,
        icon text NOT NULL,
        label text NOT NULL,
        description text NOT NULL,
        PRIMARY KEY(id  AUTOINCREMENT),
        UNIQUE(name) on CONFLICT REPLACE
        )
    """,

    """
    CREATE TABLE IF NOT EXISTS section (
        id INTEGER NOT NULL,
        area TEXT NOT NULL,
        name TEXT NOT NULL,
        icon TEXT NOT NULL,
        label TEXT NOT NULL,
        description TEXT NOT NULL,
        settings TEXT NOT NULL,
        PRIMARY KEY(id AUTOINCREMENT),
        FOREIGN KEY(area) REFERENCES area(name),
        UNIQUE(area, name) on CONFLICT REPLACE
        )
    """],

    'config_defn_dt': ["""
    DROP TABLE IF EXISTS area
    """,
    """
    DROP TABLE IF EXISTS section
    """],

    'config_defn_area_add': """
    INSERT INTO area (
        name, icon, label, description
        ) VALUES ( ?, ?, ?, ? )
    """,

    'config_defn_section_add': """
    INSERT INTO section (
        area, name, icon, label, description, settings
        ) VALUES ( ?, ?, ?, ?, ?, ? )
    """,

    'config_defn_area_get':
    """
    SELECT * from area WHERE name = ? ORDER BY id
    """,

    'config_defn_section_get':
    """
    SELECT * from section WHERE area = ? ORDER BY id
    """,

    'config_defn_area_keys_get':
    """
    SELECT name from area ORDER BY id
    """

}
