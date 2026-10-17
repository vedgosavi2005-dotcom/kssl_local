import { clientShort } from "../../lib/client.js";
import { useEffect, useMemo, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { companyOrigin } from "../../lib/countryFacet.js";
/* The country table, the plot plan and the head-office rule moved to lib/geoCountries.js
   so a node test can import them instead of slicing this file's text. Re-exported below
   because pages/competitive/Geo.jsx and test_geo_map.mjs read them from here. */
import {
  geoCountryCoords,
  geoPlotPlan,
  isHeadOffice,
} from "../../lib/geoCountries.js";
/* The tooltip's wording, as data: lib/geoBadge.js. See the comments there for the three
   faults it exists to prevent -- the badge that parroted the client's own name, the
   estimate drawn as a measurement, and the head office that never matched. */
import {
  companyRole,
  presenceBadge,
} from "../../lib/geoBadge.js";

export { geoCountryCoords, geoPlotPlan };

// Emptied deliberately. This map held hand-researched export/import strings per company --
// data, living in code, that no source in the corpus supports. The pipeline now supplies
// everything the map draws, and a company with nothing recorded shows nothing rather than
// showing a sentence somebody typed in 2026.
const COMPANY_MATERIALS = {};

/* The plotted list comes from the SERVED footprint rows — geoCountries is a
   vocabulary that at most orders them. An empty geoData plots an empty map. */
export function servedGeoCountries(data) {
  const served = new Set();
  Object.values(data.geoData || {}).forEach((byCountry) =>
    Object.keys(byCountry || {}).forEach((ct) => served.add(ct)),
  );
  const order = data.geoCountries || [];
  return [...served].sort((a, b) => {
    const ia = order.indexOf(a);
    const ib = order.indexOf(b);
    return (ia < 0 ? 1 : 0) - (ib < 0 ? 1 : 0) || ia - ib || a.localeCompare(b);
  });
}

/* Basemap tiles.

   CARTO's dark_all served this map keylessly for years and now returns a tile
   stamped "API KEY REQUIRED · carto.com/basemaps/apikey" instead of the map — a 200
   with a watermark, not an error, which is why the map went on rendering markers over
   an unreadable ground rather than failing loudly.

   The default below is Esri's World Dark Gray Canvas: a dark basemap that needs no key
   and no account. If a CARTO (or Stadia, or MapTiler) key is ever bought, set both
   VITE_MAP_TILE_URL and VITE_MAP_TILE_ATTR at BUILD time — Vite inlines them, so they
   must be present when the image is built, not when the container starts. e.g.
     VITE_MAP_TILE_URL="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png?api_key=KEY"
   Attribution is a licence condition on every one of these providers, so the URL and
   the credit move together. */
const TILE_URL =
  import.meta.env.VITE_MAP_TILE_URL ||
  "https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}";
const TILE_ATTR =
  import.meta.env.VITE_MAP_TILE_ATTR ||
  '&copy; <a href="https://www.esri.com/">Esri</a> &copy; OpenStreetMap contributors';


export default function GeoMap({ data, geo, selectedCountry, onSelectCountry }) {
  const mapContainerRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const countries = useMemo(() => servedGeoCountries(data), [data]);
  /* the parent passes a new function each render; reading it through a ref keeps the markers (and their
     tooltips) from being torn down and rebuilt on every parent render */
  const onSelectRef = useRef(onSelectCountry);
  onSelectRef.current = onSelectCountry;

  useEffect(() => {
    if (!mapContainerRef.current) return;

    if (!mapInstanceRef.current) {
      const map = L.map(mapContainerRef.current, {
        center: [18, 10],
        zoom: 2.6,
        minZoom: 2.5,
        maxZoom: 8,
        /* ZOOM FEEL. Leaflet's own wheel zoom ignores every wheel event that arrives while a zoom animation is
           still running, so a scroll gesture only moved the map one animation step per ~250ms: about 0.2 of a
           zoom level per notch, in jerks. It is switched off here and replaced by the continuous, eased wheel
           handler below, which accepts every event. zoomSnap 0 lets the zoom sit between levels while it moves. */
        scrollWheelZoom: false,
        zoomSnap: 0,
        zoomDelta: 1,
        /* a handful of markers: one canvas is cheaper to scale than an SVG layer, and the markers do not
           animate on their own */
        preferCanvas: true,
        markerZoomAnimation: false,
        zoomControl: true,
        dragging: true,
        touchZoom: true,
        doubleClickZoom: true,
        boxZoom: true,
        keyboard: true,
        worldCopyJump: false,
        maxBounds: [
          [-85, -180],
          [85, 180],
        ],
        maxBoundsViscosity: 1.0,
      });

      L.tileLayer(TILE_URL, {
        attribution: TILE_ATTR,
        subdomains: "abcd",
        maxZoom: 19,
        /* no tile requests while the zoom animation runs (they were fetched, then scaled away a few frames
           later), a larger kept border so the view behind a zoom is already there, and a gentler refresh */
        updateWhenZooming: false,
        keepBuffer: 4,
        updateInterval: 250,
        noWrap: true,
        bounds: [
          [-85, -180],
          [85, 180],
        ],
      }).addTo(map);

      /* Continuous wheel zoom: each wheel event moves a TARGET zoom, and one animation frame at a time the map
         eases toward it around the pointer, with no per-step CSS animation. Nothing is dropped, so the speed is
         set by how far the wheel turns, and a trackpad's stream of small deltas feels like the large ones. */
      const wheel = { target: null, raf: 0, pt: null };
      const wheelStep = () => {
        wheel.raf = 0;
        const z = map.getZoom();
        const diff = wheel.target - z;
        if (Math.abs(diff) < 0.005) {
          map.setZoomAround(wheel.pt, wheel.target, { animate: false });
          wheel.target = null;
          return;
        }
        map.setZoomAround(wheel.pt, z + diff * 0.3, { animate: false });
        wheel.raf = requestAnimationFrame(wheelStep);
      };
      map.getContainer().addEventListener(
        "wheel",
        (e) => {
          e.preventDefault();
          const px = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaMode === 2 ? e.deltaY * 400 : e.deltaY;
          // a pinch on a trackpad arrives as a ctrl+wheel with small deltas: scale it up
          const perPx = e.ctrlKey ? 0.01 : 0.005;
          const from = wheel.target == null ? map.getZoom() : wheel.target;
          wheel.target = Math.max(map.getMinZoom(), Math.min(map.getMaxZoom(), from - px * perPx));
          wheel.pt = map.mouseEventToContainerPoint(e);
          if (!wheel.raf) wheel.raf = requestAnimationFrame(wheelStep);
        },
        { passive: false },
      );

      /* the tooltip is a large card with a blurred shadow that follows the pointer; while a zoom runs it was
         being re-laid-out on every frame under the cursor (the green dot is exactly where people zoom).
         Hide it for the gesture; it returns on the next mouse move. */
      map.on("zoomstart", () => map.getContainer().classList.add("geo-zooming"));
      map.on("zoomend", () => map.getContainer().classList.remove("geo-zooming"));

      mapInstanceRef.current = map;
    }

    const map = mapInstanceRef.current;

    map.eachLayer((layer) => {
      if (layer instanceof L.CircleMarker) {
        map.removeLayer(layer);
      }
    });

    const plan = geoPlotPlan(countries);
    plan.plotted.forEach(({ ct, coords }) => {
      const comps = geo.compsInCountry(ct);
      const rivals = comps.filter((c) => !c.isBf);
      /* The client's footprint is keyed by its COMPANY ID, not by its display short
         name. Looking it up as data.geoData["KSSL"] worked only while the archive
         wrote uppercase codes; the pipeline writes slugs, so the UAE pin listed a
         sourced KSSL supply row under the badge "No activity on file". Find the
         client the way the rest of the map does — the company flagged isBf. */
      const clientRow = (data.geoComps || []).find((c) => c.isBf);
      const ownData =
        (data.geoData &&
          (data.geoData[clientRow?.id] || data.geoData[clientShort()])) ||
        {};
      const isKoelPresent = !!ownData[ct];
      const isSelected = selectedCountry === ct;

      const clientLabel = clientShort();
      /* "Contested" requires an actual rival presence row here — a country with no
         activity on file is reported as exactly that, not as a contested market.

         The wording is built in lib/geoBadge.js, as data, so it can be asserted without
         a map. Two faults live in there rather than here: the badge used to append the
         LABELS of the client's own rows, and actLabel.bf is "KSSL present", so India
         rendered "KSSL Present · KSSL present / Local production"; and it never read
         src, so an analytical estimate (a client row with src='syn') drew exactly like a sourced presence. */
      const badge = presenceBadge({
        clientLabel,
        rows: ownData[ct] || [],
        rivalCount: rivals.length,
        actLabel: data.actLabel,
      });
      /* A presence that rests only on estimates is drawn hollow, not solid green. The
         tooltip alone would not do: a reader scanning the map sees dots, and a dot is
         the assertion. Same rule as the badge's wording, same input (row.src). */
      const estimateOnly = badge.cls.includes("est");
      const color = isKoelPresent ? "#3fa86a" : rivals.length > 0 ? "#f0593c" : "#e0a020";
      const radius = isSelected ? 11 : isKoelPresent ? 8 : 6;

      let compRowsHtml = "";
      comps.slice(0, 5).forEach((c) => {
        // Trade lines render only when a real entry exists — no fabricated fallback.
        const matInfo = COMPANY_MATERIALS[c.name];
        /* What the company DOES here, read from this country's own rows. The label
           used to be `isBf ? "KSSL HQ / Direct" : "Competitor"`, and isBf means "this
           company is the client" — not "this country is its head office" — so every
           pin the client appeared on was captioned as its HQ, the UAE included.

           The head-office test used to be a raw full-string equality between geo_comp.hq
           and the country name. The archived reference rows store a bare "Germany" and
           matched; every pipeline row stores a chain ("Ahmedabad, Gujarat, India") and
           never could, so the badge had silently stopped firing for the whole live
           roster. isHeadOffice asks the stated origin column first and falls back to the
           tidied hq — one rule, shared with the Profile page. */
        const rowsHere = (data.geoData && data.geoData[c.id] && data.geoData[c.id][ct]) || [];
        const role = companyRole({
          comp: c,
          rows: rowsHere,
          actLabel: data.actLabel,
          clientLabel,
          isHq: isHeadOffice(ct, { origin: companyOrigin(data, c.id), hq: c.hq }),
        });
        compRowsHtml += `
          <div class="gm-comp-row">
            <div class="gm-comp-head">
              <span class="gm-comp-name">${c.name}</span>
              <span class="gm-comp-role">${role}</span>
            </div>
            ${matInfo ? `<div class="gm-mat-line"><b>Exports:</b> ${matInfo.exports}</div>
            <div class="gm-mat-line"><b>Imports:</b> ${matInfo.imports}</div>` : ""}
          </div>
        `;
      });

      // the card lists five; say so when there are more instead of dropping the rest silently
      if (comps.length > 5) compRowsHtml += `<div class="gm-more">+${comps.length - 5} more ${comps.length - 5 === 1 ? "company" : "companies"}: click the point to see all</div>`;

      const tooltipContent = `
        <div class="gm-tooltip">
          <div class="gm-header">
            <span class="gm-country-name">${ct}</span>
            <span class="gm-koel-badge ${badge.cls}">${badge.text}</span>
          </div>
          ${badge.note ? `<div class="gm-evidence-note">${badge.note}</div>` : ""}
          <div class="gm-section-title">Active Companies & Material Trade</div>
          <div class="gm-comp-list">
            ${compRowsHtml}
          </div>
          <div class="gm-click-hint">Click point to open market product details ↗</div>
        </div>
      `;

      // Plot single marker on static map
      const marker = L.circleMarker(coords, {
        radius,
        fillColor: color,
        color: isSelected ? "#ffffff" : color,
        weight: isSelected ? 3 : 1.5,
        opacity: 0.95,
        // hollow + dashed where the presence is an estimate; solid where it is sourced
        fillOpacity: estimateOnly ? 0.12 : 0.85,
        dashArray: estimateOnly ? "3 3" : null,
      }).addTo(map);

      marker.bindTooltip(tooltipContent, {
        direction: "top",
        sticky: true,
        className: "geo-leaflet-tooltip",
      });

      /* KEEP THE CARD INSIDE THE MAP.
         The tooltip is pinned `direction: "top"`, and Leaflet renders it inside
         .leaflet-container, which sets overflow:hidden. So a country in the top band of
         the viewport got a card drawn above the cursor and clipped by the container edge
         -- the reader saw a half card, and the taller the country's material list the
         more of it was missing. The same happens sideways for a country near either edge,
         because the card is up to 340px wide and centred on the point.

         Leaflet has no flip of its own (`direction: "auto"` only chooses left or right,
         and only at bind time), but the tooltip IS sticky, so it is already being
         repositioned on every mousemove -- which is the moment to pick a side. The
         element's own measured height and width are used rather than a guess, so a short
         card near the top still gets to stay above the cursor.

         Vertical is decided first: a card that does not fit above goes below, and only
         then is the horizontal overflow considered. Setting the option and calling
         update() is the whole of it; if nothing would change, nothing is touched, so this
         does not re-render the tooltip on every pixel of movement. */
      let raf = 0;
      marker.on("mousemove", (e) => {
        // once per frame, and not at all while zooming: the handler reads element sizes, which forces layout
        if (raf || map.getContainer().classList.contains("geo-zooming")) return;
        const pt = e.containerPoint;
        raf = requestAnimationFrame(() => {
          raf = 0;
          placeTooltip(pt);
        });
      });
      const placeTooltip = (p) => {
        const tip = marker.getTooltip();
        if (!tip) return;
        const el = tip.getElement();
        if (!el) return;
        const size = map.getSize();
        const h = el.offsetHeight || 0;
        const w = el.offsetWidth || 0;
        const GAP = 16; // leaflet's own offset plus the arrow
        /* Vertical by DIRECTION, horizontal by OFFSET -- not by direction on both axes.
           Flipping to "left"/"right" near a side edge would re-centre the card
           vertically on the point, so in a corner it stops being clipped sideways and
           starts being clipped at the top instead. Nudging it horizontally keeps the
           chosen vertical side and slides the card back inside, which handles an edge
           and a corner with the same two numbers. */
        const dir = p.y - h - GAP < 0 ? "bottom" : "top";
        const half = w / 2;
        let dx = 0;
        if (p.x + half + GAP > size.x) dx = size.x - GAP - (p.x + half);
        else if (p.x - half - GAP < 0) dx = GAP - (p.x - half);
        const cur = tip.options.offset;
        if (tip.options.direction !== dir || !cur || cur.x !== dx) {
          tip.options.direction = dir;
          tip.options.offset = L.point(dx, 0);
          tip.update();
        }
      };

      marker.on("click", () => {
        onSelectRef.current(ct);
      });
    });

    setTimeout(() => {
      map.invalidateSize();
    }, 150);
  }, [data, geo, countries, selectedCountry]);

  return (
    <div className="geo-map-wrapper" style={{ position: "relative" }}>
      <div className="geo-map-container" ref={mapContainerRef} />
      {!countries.length ? (
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            pointerEvents: "none",
            zIndex: 500,
          }}
        >
          <div
            style={{
              background: "rgba(20,20,24,0.85)",
              color: "#c9c9cf",
              fontFamily: "var(--mono)",
              fontSize: "12px",
              padding: "10px 16px",
              borderRadius: "4px",
              border: "1px solid #2a2a2f",
            }}
          >
            No geographic activity on file yet - the map plots only served footprint data.
          </div>
        </div>
      ) : null}
    </div>
  );
}
