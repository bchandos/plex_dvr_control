DROP TABLE IF EXISTS shows;
CREATE TABLE "shows" (  `id` INTEGER PRIMARY KEY AUTOINCREMENT,
                        `show_title` TEXT,
                        `gracenote_id` NUMERIC,
                        `date_added` REAL,
                        `plex_key` INTEGER )

DROP TABLE IF EXISTS episodes;
CREATE TABLE "episodes" (   `id` INTEGER PRIMARY KEY AUTOINCREMENT,
                            `show_id` INTEGER,
                            `season` INTEGER,
                            `episode` INTEGER,
                            `name` INTEGER,
                            `season_gracenote_id` NUMERIC,
                            `episode_gracenote_id` NUMERIC,
                            `season_plex_key` INTEGER,
                            `episode_plex_key` INTEGER UNIQUE,
                            FOREIGN KEY(`show_id`) REFERENCES `shows`(`id`) )