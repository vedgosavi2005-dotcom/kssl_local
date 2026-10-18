import { useState } from "react";

/* One article image, and one honest answer when there isn't one.

   Reported: "Images for Allen Control Systems and similarly affected entries are not
   displayed. Missing images should use a defined fallback rather than a broken or
   blank area."

   Two different faults were producing the same broken box, and only one of them is
   about missing data:

     1. NO URL. Five render sites wrote `<img src={item.image} />` with no guard, so a
        card with no image became `<img src={undefined}>` -- which every browser draws
        as its broken-image glyph. Measured on production: 123 of the 1,175 served
        signal cards carry no image at all, and Allen Control Systems is one of them
        (2 cards, 1 image).
     2. THE URL DOES NOT LOAD. A publisher that blocks hotlinking, or a link that has
        rotted, fails at fetch time. No site had an onError, so a perfectly well-formed
        record also ended as a broken box.

   partners.js already drew a neutral captioned tile for case 1. It was the only place
   that did. This component is that tile, made shared, and extended to case 2.

   `FAILED` is module-level on purpose: a URL that failed once must not be requested
   again when the card scrolls back into view or the panel remounts. That is the whole
   of the caching that can be done from here -- images are third-party origins, so the
   only durable cache is the browser's own HTTP cache, which the publisher's headers
   control. Serving them from our origin would need a proxy, which is a backend change
   and is NOT done here. */
const FAILED = new Set();

/* Pure, and exported, so the rule can be tested without React or a DOM. Only http(s):
   a `data:` or `javascript:` value is not something this app publishes, and an <img>
   is a place a stray value would otherwise be honoured silently. */
export function thumbUsable(src, failed = FAILED) {
  // http(s), or the image folders shipped with the app: /product-images/ (served) and product-images/,
  // news-images/ (beside the standalone HTML file)
  return typeof src === "string" && /^(https?:\/\/|\/?product-images\/[\w.-]+$|news-images\/[\w.-]+$)/i.test(src) && !failed.has(src);
}

export function thumbMarkFailed(src, failed = FAILED) {
  if (typeof src === "string" && src) failed.add(src);
  return failed;
}

/* Route the image through our own origin. Publishers block hotlinking (Referer/UA
   checks), so a good og:image 403s in a bare <img>; /api/img refetches it server-side
   with a browser UA and no referer and streams it back, so the browser loads it from
   us. Served by the backend on staging/prod and by the vite middleware in dev. The
   FAILED set stays keyed on the ORIGINAL url, so a genuinely dead image still falls
   back once and is not retried. */
export function proxied(src) {
  // the standalone HTML has no /api/img: its images are local files or the original address
  if (typeof window !== "undefined" && window.__EMBEDDED_DATASET__) return src;
  return typeof src === "string" && /^https?:\/\//i.test(src)
    ? `/api/img?u=${encodeURIComponent(src)}`
    : src;
}

/* THE WHOLE PICTURE, NOT THE MIDDLE OF IT -- decided here, once.
 *
 * All nine render sites wrote `object-fit: cover` into their own style, so a press photo
 * in a 105x82 thumb was centre-cropped to that box: a wide tank shot lost both ends, a
 * ribbon-cutting line-up lost the people on the outside, a product render on a wide
 * canvas came out an unreadable slab of the middle. Reported as "some of the img are
 * cut", and true wherever the article's aspect ratio was not the tile's -- which, across
 * 803 article images from 40-odd publishers, is most of them.
 *
 * `contain` fits the whole frame inside the box and leaves ground where the two ratios
 * disagree. That ground is PAINTED rather than left transparent, so the letterboxing
 * reads as the tile's own surface and not as a hole in the card.
 *
 * Spread FIRST, so a caller can still override deliberately -- this is a default, not a
 * lock. The point is that it is a default at all: the next image tile someone adds
 * inherits the rule instead of copying `cover` off the tile beside it. */
const FIT = { objectFit: "contain", background: "var(--d-bg-3)" };

export default function Thumb({ src, alt, className, style, caption }) {
  const usable = thumbUsable(src);
  const [broken, setBroken] = useState(false);

  if (!usable || broken) {
    return (
      <div className={`thumb-none ${className || ""}`} style={style}>
        <span className="thumb-none-label">
          {caption || "No image published with this article"}
        </span>
      </div>
    );
  }
  return (
    <img
      alt={alt || ""}
      className={className}
      decoding="async"
      loading="lazy"
      onError={() => {
        thumbMarkFailed(src);
        setBroken(true);
      }}
      src={proxied(src)}
      style={{ ...FIT, ...style }}
    />
  );
}
