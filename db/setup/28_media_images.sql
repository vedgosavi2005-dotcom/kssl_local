-- Article images stored in the database (2026-10-22, owner: "fetch the image from the article and store it in the database, not only the
-- image path"). backend/media_images.py fills them; GET /api/image/<image_id> serves them (both the live and the review API read this
-- schema of the STAGING database: images are an asset cache, not reviewed content, so they sit outside the staging -> serving tables).
-- Idempotent; run on the staging DB only.
CREATE SCHEMA IF NOT EXISTS media;

CREATE TABLE IF NOT EXISTS media.image (
    image_id      uuid PRIMARY KEY,                -- uuid5(URL, source_url)
    source_url    text NOT NULL UNIQUE,            -- where the picture came from (the article's og:image, or the card's own link)
    content_type  varchar(40) NOT NULL,
    bytes         bytea NOT NULL,
    byte_len      integer NOT NULL,
    width         integer,
    height        integer,
    sha256        char(64) NOT NULL,
    fetched_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS media.page_image (
    page_url    text PRIMARY KEY,                  -- the article / source page a card points at
    image_id    uuid REFERENCES media.image(image_id),
    how         varchar(20),                       -- card_link | og_image | twitter_image | link_image_src | article_img
    status      varchar(20) NOT NULL,              -- ok | no_image | page_failed | image_failed | too_small | not_image
    error       text,
    checked_at  timestamptz NOT NULL DEFAULT now()
);

COMMENT ON SCHEMA media IS 'images of the articles behind the cards, stored as bytes (backend/media_images.py); served by GET /api/image/<id>';
