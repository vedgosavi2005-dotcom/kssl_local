import { useEffect, useMemo, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
/* The plot plan and the head-office rule live in lib/geoCountries.js so a node test can import
   them instead of slicing this file's text; the coordinates are the served latitude/longitude
   of each competitive_geo_location. Re-exported because pages read them from here. */
import { geoCountryCoords, geoPlotPlan, isHeadOffice } from "../../lib/geoCountries.js";
import { companyRole } from "../../lib/geoBadge.js";

export { geoCountryCoords, geoPlotPlan };

/* The plotted list comes from the SERVED footprint rows: a country with no presence row is not
   plotted, and one with no coordinates is listed as unlocated instead. */
export function servedGeoCountries(data) {
  const served = new Set();
  Object.values(data.geoData || {}).forEach((byCountry) =>
    Object.keys(byCountry || {}).forEach((ct) => served.add(ct)),
  );
  return [...served].sort((a, b) => a.localeCompare(b));
}

/* Basemap tiles.

   CARTO's dark_all served this map keylessly for years and now returns a tile
   stamped "API KEY REQUIRED" instead of the map. The default below is Esri's World Dark Gray
   Canvas, which needs no key. If a key is bought, set both VITE_MAP_TILE_URL and
   VITE_MAP_TILE_ATTR at BUILD time (Vite inlines them). Attribution is a licence condition,
   so the URL and the credit move together. The tiles are an external, non-DB element. */
const TILE_URL =
  import.meta.env.VITE_MAP_TILE_URL ||
  "https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}";
const TILE_ATTR =
  import.meta.env.VITE_MAP_TILE_ATTR ||
  '&copy; <a href="https://www.esri.com/">Esri</a> &copy; OpenStreetMap contributors';

const escHtml = (v) => String(v == null ? "" : v).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

export default function GeoMap({ data, geo, selectedCountry, onSelectCountry }) {
  const mapContainerRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const countries = useMemo(() => servedGeoCountries(data), [data]);
  const unlocated = useMemo(() => geoPlotPlan(countries).unlocated, [countries]);

  useEffect(() => {
    if (!mapContainerRef.current) return;

    if (!mapInstanceRef.current) {
      const map = L.map(mapContainerRef.current, {
        center: [18, 10],
        zoom: 2.6,
        minZoom: 2.5,
        maxZoom: 8,
        zoomSnap: 0.1,
        zoomControl: true,
        dragging: true,
        touchZoom: true,
        doubleClickZoom: true,
        scrollWheelZoom: true,
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
        noWrap: true,
        bounds: [
          [-85, -180],
          [85, 180],
        ],
      }).addTo(map);

      mapInstanceRef.current = map;
    }

    const map = mapInstanceRef.current;

    map.eachLayer((layer) => {
      if (layer instanceof L.CircleMarker) {
        map.removeLayer(layer);
      }
    });

    const plan = geoPlotPlan(countries);
    const clientRow = (data.geoComps || []).find((c) => c.isBf);
    const clientKey = data.client?.id || clientRow?.id;
    const ownData = (clientKey && data.geoData && data.geoData[clientKey]) || {};
    const locationOf = {};
    (data.geoLocations || []).forEach((l) => {
      locationOf[l.name] = l;
    });
    plan.plotted.forEach(({ ct, coords }) => {
      const comps = geo.compsInCountry(ct);
      const rivals = comps.filter((c) => !c.isBf);
      const isKoelPresent = !!ownData[ct];
      const isSelected = selectedCountry === ct;
      const location = locationOf[ct] || {};
      const color = isKoelPresent ? "#3fa86a" : rivals.length > 0 ? "#f0593c" : "#e0a020";
      const radius = isSelected ? 11 : isKoelPresent ? 8 : 6;

      let compRowsHtml = "";
      comps.slice(0, 5).forEach((c) => {
        const role = companyRole({
          presences: geo.presencesFor(c.id, ct),
          rows: geo.productsFor(c.id, ct),
          isHq: isHeadOffice(ct, { origin: data.competitors?.[c.id]?.origin, hq: data.competitors?.[c.id]?.hq }),
        });
        compRowsHtml += `
          <div class="gm-comp-row">
            <div class="gm-comp-head">
              <span class="gm-comp-name">${escHtml(c.name)}</span>
              ${role ? `<span class="gm-comp-role">${escHtml(role)}</span>` : ""}
            </div>
          </div>
        `;
      });

      const tooltipContent = `
        <div class="gm-tooltip">
          <div class="gm-header">
            <span class="gm-country-name">${escHtml(ct)}</span>
            ${location.summary ? `<span class="gm-koel-badge${isKoelPresent ? " present" : ""}">${escHtml(location.summary)}</span>` : ""}
          </div>
          ${location.presenceTypes ? `<div class="gm-evidence-note">${escHtml(location.presenceTypes)}</div>` : ""}
          <div class="gm-section-title">Active companies</div>
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
        fillOpacity: 0.85,
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
      marker.on("mousemove", (e) => {
        const tip = marker.getTooltip();
        if (!tip) return;
        const el = tip.getElement();
        if (!el) return;
        const size = map.getSize();
        const p = e.containerPoint;
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
      });

      marker.on("click", (e) => {
        if (e && e.originalEvent) e.originalEvent.stopPropagation();
        onSelectCountry(ct);
      });

      marker.on("tooltipopen", () => {
        const tip = marker.getTooltip();
        if (tip && tip.getElement()) {
          tip.getElement().style.cursor = "pointer";
          tip.getElement().onclick = (e) => {
            e.stopPropagation();
            onSelectCountry(ct);
          };
        }
      });
    });

    setTimeout(() => {
      map.invalidateSize();
    }, 150);
  }, [data, geo, countries, selectedCountry, onSelectCountry]);

  return (
    <div className="geo-map-wrapper" style={{ position: "relative" }}>
      <div className="geo-map-container" ref={mapContainerRef} />
      {unlocated.length ? (
        <div
          style={{
            position: "absolute",
            left: 12,
            bottom: 12,
            zIndex: 500,
            background: "rgba(20,20,24,0.85)",
            color: "#c9c9cf",
            fontFamily: "var(--mono)",
            fontSize: "11px",
            padding: "6px 10px",
            borderRadius: "4px",
          }}
        >
          Not on the map (no coordinates stored): {unlocated.join(", ")}
        </div>
      ) : null}
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
            No geographic activity on file yet.
          </div>
        </div>
      ) : null}
    </div>
  );
}
