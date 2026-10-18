/* COUNTRY FLAGS FOR SVG GRAPHS -- high-fidelity vector flags.
 *
 * Self-contained, pure SVG vector flags clipped to circular nodes.
 * Used by the Partnerships Region graph (and anywhere country badges appear)
 * without depending on external CDNs or operating system emoji glyphs
 * (which fail on Windows).
 */

const f1 = (x) => (Math.round(x * 10) / 10).toString();

// Canonical country key mapping
/* Country-name spellings -> ISO 3166 alpha-2, for the patent office column. A neutral lookup, no records. */
export const COUNTRY_ISO2_ALIAS = {
  INDIA: "IN",
  USA: "US",
  "UNITED STATES": "US",
  "U.S.": "US",
  "U.S.A.": "US",
  UK: "GB",
  "UNITED KINGDOM": "GB",
  KOREA: "KR",
  "SOUTH KOREA": "KR",
  "REPUBLIC OF KOREA": "KR",
  GERMANY: "DE",
  FRANCE: "FR",
  SPAIN: "ES",
  ISRAEL: "IL",
  AUSTRALIA: "AU",
  CANADA: "CA",
  JAPAN: "JP",
  CHINA: "CN",
};


export const COUNTRY_KEY_MAP = {
  // USA
  usa: "usa",
  us: "usa",
  "u.s.": "usa",
  "united states": "usa",
  "united states of america": "usa",

  // UK
  uk: "uk",
  "u.k.": "uk",
  "united kingdom": "uk",
  britain: "uk",
  "great britain": "uk",

  // Israel
  israel: "israel",

  // India
  india: "india",

  // France
  france: "france",

  // Germany
  germany: "germany",

  // South Africa
  "south africa": "south_africa",
  za: "south_africa",

  // Australia
  australia: "australia",

  // Brazil
  brazil: "brazil",

  // Canada
  canada: "canada",

  // Croatia
  croatia: "croatia",
  croatian: "croatia",

  // Czech Republic
  "czech republic": "czech_republic",
  czechia: "czech_republic",

  // Denmark
  denmark: "denmark",

  // Estonia
  estonia: "estonia",

  // Ethiopia
  ethiopia: "ethiopia",

  // Greece
  greece: "greece",

  // Indonesia
  indonesia: "indonesia",

  // Italy
  italy: "italy",

  // Japan
  japan: "japan",

  // South Korea
  korea: "south_korea",
  "south korea": "south_korea",
  "republic of korea": "south_korea",

  // Malaysia
  malaysia: "malaysia",

  // Netherlands
  netherlands: "netherlands",
  "the netherlands": "netherlands",

  // Norway
  norway: "norway",

  // Poland
  poland: "poland",

  // Russia
  russia: "russia",
  "russian federation": "russia",

  // Saudi Arabia
  "saudi arabia": "saudi_arabia",
  ksa: "saudi_arabia",

  // Singapore
  singapore: "singapore",

  // Spain
  spain: "spain",

  // Sweden
  sweden: "sweden",

  // Switzerland
  switzerland: "switzerland",
  swiss: "switzerland",

  // Thailand
  thailand: "thailand",

  // Turkey
  turkey: "turkey",
  türkiye: "turkey",

  // UAE
  uae: "uae",
  "united arab emirates": "uae",

  // Ukraine
  ukraine: "ukraine",

  // Armenia
  armenia: "armenia",

  // Austria
  austria: "austria",

  // Belgium
  belgium: "belgium",

  // Finland
  finland: "finland",

  // Morocco
  morocco: "morocco",
  maroko: "morocco",
  fas: "morocco",
  marruecos: "morocco",

  // Philippines
  philippines: "philippines",
  filipinas: "philippines",

  // Romania
  romania: "romania",
  roumanie: "romania",
  "rumanía": "romania",
  romanya: "romania",

  // Serbia
  serbia: "serbia",

  // Egypt
  egypt: "egypt",
  "mısır": "egypt",

  // Qatar
  qatar: "qatar",
  katar: "qatar",

  // Oman
  oman: "oman",
  "sultanate of oman": "oman",

  // Bahrain
  bahrain: "bahrain",
  bahreyn: "bahrain",

  // Chile
  chile: "chile",

  // Portugal
  portugal: "portugal",

  // Hungary
  hungary: "hungary",
  "węgry": "hungary",
  ungarn: "hungary",

  // New Zealand
  "new zealand": "new_zealand",

  // Taiwan
  taiwan: "taiwan",

  // Multilingual aliases for existing countries
  deutschland: "germany",
  alemania: "germany",
  almanya: "germany",
  "njemačka": "germany",
  "reino unido": "uk",
  "großbritannien": "uk",
  "wielka brytania": "uk",
  "regno unito": "uk",
  england: "uk",
  scotland: "uk",
  "u.k": "uk",
  "ee.uu.": "usa",
  "stany zjednoczone": "usa",
  francja: "france",
  polonia: "poland",
  polen: "poland",
  "polônia": "poland",
  polonya: "poland",
  dinamarca: "denmark",
  danimarka: "denmark",
  "дания": "denmark",
  "emiratos árabes unidos": "uae",
  eau: "uae",
  "emirati arabi uniti": "uae",
  "vereinigte arabische emirate": "uae",
  "i̇srail": "israel",
  "israël": "israel",
  israil: "israel",
  italia: "italy",
  italie: "italy",
  italya: "italy",
  norvegia: "norway",
  noruega: "norway",
  "norveç": "norway",
  malasia: "malaysia",
  "malásia": "malaysia",
  "corée du sud": "south_korea",
  "대한민국": "south_korea",
  brasil: "brazil",
  schweiz: "switzerland",
  suisse: "switzerland",
  avustralya: "australia",
  ucrania: "ukraine",
  ucraina: "ukraine",
  ukrayna: "ukraine",
  "ucrânia": "ukraine",
};

/** Normalise any country string or alias to a known canonical flag key */
export function normCountryKey(countryName) {
  if (!countryName) return "unknown";
  const clean = String(countryName).trim().toLowerCase();
  return COUNTRY_KEY_MAP[clean] || "unknown";
}

/** 5-point star polygon helper */
function starPoints(cx, cy, rOuter, rInner, points = 5, startAngle = -Math.PI / 2) {
  const pts = [];
  for (let i = 0; i < points * 2; i++) {
    const r = i % 2 === 0 ? rOuter : rInner;
    const a = startAngle + (i * Math.PI) / points;
    pts.push(`${f1(cx + r * Math.cos(a))},${f1(cy + r * Math.sin(a))}`);
  }
  return pts.join(" ");
}

/** Render raw flag vector content within a bounding box centered at (cx, cy) with radius r */
export function renderFlagContent(key, cx, cy, r) {
  const x0 = cx - r;
  const y0 = cy - r;
  const w = 2 * r;
  const h = 2 * r;

  switch (key) {
    case "india": {
      const cr = r * 0.25;
      let spokes = "";
      for (let s = 0; s < 12; s++) {
        const a = (s * Math.PI) / 12;
        const x1 = cx - cr * Math.cos(a);
        const y1 = cy - cr * Math.sin(a);
        const x2 = cx + cr * Math.cos(a);
        const y2 = cy + cr * Math.sin(a);
        spokes += `<line x1="${f1(x1)}" y1="${f1(y1)}" x2="${f1(x2)}" y2="${f1(y2)}" stroke="#000080" stroke-width="0.9" />`;
      }
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h / 3)}" fill="#ff9933"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + h / 3)}" width="${f1(w)}" height="${f1(h / 3)}" fill="#ffffff"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + 2 * h / 3)}" width="${f1(w)}" height="${f1(h / 3 + 0.5)}" fill="#138808"/>` +
        `<circle cx="${f1(cx)}" cy="${f1(cy)}" r="${f1(cr)}" fill="none" stroke="#000080" stroke-width="1.5"/>` +
        `<circle cx="${f1(cx)}" cy="${f1(cy)}" r="${f1(cr * 0.22)}" fill="#000080"/>` +
        spokes
      );
    }

    case "israel": {
      const sr = r * 0.42;
      const p1 = [cx, cy - sr];
      const p2 = [cx + sr * 0.866, cy + sr * 0.5];
      const p3 = [cx - sr * 0.866, cy + sr * 0.5];
      const q1 = [cx, cy + sr];
      const q2 = [cx + sr * 0.866, cy - sr * 0.5];
      const q3 = [cx - sr * 0.866, cy - sr * 0.5];
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h)}" fill="#ffffff"/>` +
        `<rect x="${f1(x0)}" y="${f1(cy - r * 0.72)}" width="${f1(w)}" height="${f1(r * 0.26)}" fill="#0038b8"/>` +
        `<rect x="${f1(x0)}" y="${f1(cy + r * 0.46)}" width="${f1(w)}" height="${f1(r * 0.26)}" fill="#0038b8"/>` +
        `<polygon points="${f1(p1[0])},${f1(p1[1])} ${f1(p2[0])},${f1(p2[1])} ${f1(p3[0])},${f1(p3[1])}" fill="none" stroke="#0038b8" stroke-width="2.2" stroke-linejoin="round"/>` +
        `<polygon points="${f1(q1[0])},${f1(q1[1])} ${f1(q2[0])},${f1(q2[1])} ${f1(q3[0])},${f1(q3[1])}" fill="none" stroke="#0038b8" stroke-width="2.2" stroke-linejoin="round"/>`
      );
    }

    case "usa": {
      const sh = h / 13;
      let stripes = "";
      for (let s = 0; s < 13; s++) {
        stripes += `<rect x="${f1(x0)}" y="${f1(y0 + s * sh)}" width="${f1(w)}" height="${f1(sh + 0.5)}" fill="${s % 2 === 0 ? "#b22234" : "#ffffff"}"/>`;
      }
      const cw = w * 0.46;
      const ch = sh * 7;
      let stars = "";
      for (let row = 0; row < 5; row++) {
        const cols = row % 2 === 0 ? 5 : 4;
        const offX = row % 2 === 0 ? cw * 0.12 : cw * 0.22;
        const sy = y0 + (row + 1) * (ch / 6);
        for (let col = 0; col < cols; col++) {
          const sx = x0 + offX + col * (cw * 0.19);
          stars += `<circle cx="${f1(sx)}" cy="${f1(sy)}" r="1" fill="#ffffff"/>`;
        }
      }
      return (
        stripes +
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(cw)}" height="${f1(ch)}" fill="#3c3b6e"/>` +
        stars
      );
    }

    case "uk": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h)}" fill="#012169"/>` +
        `<line x1="${f1(x0)}" y1="${f1(y0)}" x2="${f1(x0 + w)}" y2="${f1(y0 + h)}" stroke="#ffffff" stroke-width="${f1(r * 0.36)}"/>` +
        `<line x1="${f1(x0)}" y1="${f1(y0 + h)}" x2="${f1(x0 + w)}" y2="${f1(y0)}" stroke="#ffffff" stroke-width="${f1(r * 0.36)}"/>` +
        `<line x1="${f1(x0)}" y1="${f1(y0)}" x2="${f1(x0 + w)}" y2="${f1(y0 + h)}" stroke="#c8102e" stroke-width="${f1(r * 0.18)}"/>` +
        `<line x1="${f1(x0)}" y1="${f1(y0 + h)}" x2="${f1(x0 + w)}" y2="${f1(y0)}" stroke="#c8102e" stroke-width="${f1(r * 0.18)}"/>` +
        `<rect x="${f1(cx - r * 0.28)}" y="${f1(y0)}" width="${f1(r * 0.56)}" height="${f1(h)}" fill="#ffffff"/>` +
        `<rect x="${f1(x0)}" y="${f1(cy - r * 0.28)}" width="${f1(w)}" height="${f1(r * 0.56)}" fill="#ffffff"/>` +
        `<rect x="${f1(cx - r * 0.16)}" y="${f1(y0)}" width="${f1(r * 0.32)}" height="${f1(h)}" fill="#c8102e"/>` +
        `<rect x="${f1(x0)}" y="${f1(cy - r * 0.16)}" width="${f1(w)}" height="${f1(r * 0.32)}" fill="#c8102e"/>`
      );
    }

    case "france": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w / 3)}" height="${f1(h)}" fill="#002654"/>` +
        `<rect x="${f1(x0 + w / 3)}" y="${f1(y0)}" width="${f1(w / 3)}" height="${f1(h)}" fill="#ffffff"/>` +
        `<rect x="${f1(x0 + 2 * w / 3)}" y="${f1(y0)}" width="${f1(w / 3 + 0.5)}" height="${f1(h)}" fill="#ed2939"/>`
      );
    }

    case "germany": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h / 3)}" fill="#000000"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + h / 3)}" width="${f1(w)}" height="${f1(h / 3)}" fill="#dd0000"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + 2 * h / 3)}" width="${f1(w)}" height="${f1(h / 3 + 0.5)}" fill="#ffce00"/>`
      );
    }

    case "south_africa": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h / 2)}" fill="#e03c31"/>` +
        `<rect x="${f1(x0)}" y="${f1(cy)}" width="${f1(w)}" height="${f1(h / 2 + 0.5)}" fill="#001489"/>` +
        `<polygon points="${f1(x0)},${f1(y0)} ${f1(cx - r * 0.05)},${f1(cy - r * 0.32)} ${f1(x0 + w)},${f1(cy - r * 0.32)} ${f1(x0 + w)},${f1(cy + r * 0.32)} ${f1(cx - r * 0.05)},${f1(cy + r * 0.32)} ${f1(x0)},${f1(y0 + h)}" fill="#ffffff"/>` +
        `<polygon points="${f1(x0)},${f1(y0 + r * 0.22)} ${f1(cx - r * 0.16)},${f1(cy - r * 0.18)} ${f1(x0 + w)},${f1(cy - r * 0.18)} ${f1(x0 + w)},${f1(cy + r * 0.18)} ${f1(cx - r * 0.16)},${f1(cy + r * 0.18)} ${f1(x0)},${f1(y0 + h - r * 0.22)}" fill="#007749"/>` +
        `<polygon points="${f1(x0)},${f1(y0 + r * 0.35)} ${f1(cx - r * 0.25)},${f1(cy)} ${f1(x0)},${f1(y0 + h - r * 0.35)}" fill="#ffb612"/>` +
        `<polygon points="${f1(x0)},${f1(y0 + r * 0.52)} ${f1(cx - r * 0.44)},${f1(cy)} ${f1(x0)},${f1(y0 + h - r * 0.52)}" fill="#000000"/>`
      );
    }

    case "sweden": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h)}" fill="#006aa7"/>` +
        `<rect x="${f1(x0)}" y="${f1(cy - r * 0.18)}" width="${f1(w)}" height="${f1(r * 0.36)}" fill="#fecc00"/>` +
        `<rect x="${f1(cx - r * 0.25)}" y="${f1(y0)}" width="${f1(r * 0.36)}" height="${f1(h)}" fill="#fecc00"/>`
      );
    }

    case "norway": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h)}" fill="#ba0c2f"/>` +
        `<rect x="${f1(x0)}" y="${f1(cy - r * 0.24)}" width="${f1(w)}" height="${f1(r * 0.48)}" fill="#ffffff"/>` +
        `<rect x="${f1(cx - r * 0.28)}" y="${f1(y0)}" width="${f1(r * 0.48)}" height="${f1(h)}" fill="#ffffff"/>` +
        `<rect x="${f1(x0)}" y="${f1(cy - r * 0.12)}" width="${f1(w)}" height="${f1(r * 0.24)}" fill="#00205b"/>` +
        `<rect x="${f1(cx - r * 0.16)}" y="${f1(y0)}" width="${f1(r * 0.24)}" height="${f1(h)}" fill="#00205b"/>`
      );
    }

    case "denmark": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h)}" fill="#c60c30"/>` +
        `<rect x="${f1(x0)}" y="${f1(cy - r * 0.16)}" width="${f1(w)}" height="${f1(r * 0.32)}" fill="#ffffff"/>` +
        `<rect x="${f1(cx - r * 0.25)}" y="${f1(y0)}" width="${f1(r * 0.32)}" height="${f1(h)}" fill="#ffffff"/>`
      );
    }

    case "finland": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h)}" fill="#ffffff"/>` +
        `<rect x="${f1(x0)}" y="${f1(cy - r * 0.18)}" width="${f1(w)}" height="${f1(r * 0.36)}" fill="#002f6c"/>` +
        `<rect x="${f1(cx - r * 0.25)}" y="${f1(y0)}" width="${f1(r * 0.36)}" height="${f1(h)}" fill="#002f6c"/>`
      );
    }

    case "italy": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w / 3)}" height="${f1(h)}" fill="#008d46"/>` +
        `<rect x="${f1(x0 + w / 3)}" y="${f1(y0)}" width="${f1(w / 3)}" height="${f1(h)}" fill="#ffffff"/>` +
        `<rect x="${f1(x0 + 2 * w / 3)}" y="${f1(y0)}" width="${f1(w / 3 + 0.5)}" height="${f1(h)}" fill="#d12640"/>`
      );
    }

    case "japan": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h)}" fill="#ffffff"/>` +
        `<circle cx="${f1(cx)}" cy="${f1(cy)}" r="${f1(r * 0.58)}" fill="#bc002d"/>`
      );
    }

    case "south_korea": {
      const tr = r * 0.46;
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h)}" fill="#ffffff"/>` +
        `<circle cx="${f1(cx)}" cy="${f1(cy)}" r="${f1(tr)}" fill="#c60c30"/>` +
        `<path d="M ${f1(cx - tr)} ${f1(cy)} A ${f1(tr)} ${f1(tr)} 0 0 0 ${f1(cx + tr)} ${f1(cy)} A ${f1(tr / 2)} ${f1(tr / 2)} 0 0 1 ${f1(cx)} ${f1(cy)} A ${f1(tr / 2)} ${f1(tr / 2)} 0 0 0 ${f1(cx - tr)} ${f1(cy)} Z" fill="#003478"/>` +
        `<circle cx="${f1(cx - tr / 2)}" cy="${f1(cy)}" r="${f1(tr / 2)}" fill="#c60c30"/>` +
        `<circle cx="${f1(cx + tr / 2)}" cy="${f1(cy)}" r="${f1(tr / 2)}" fill="#003478"/>` +
        // trigram bars in 4 corners
        `<line x1="${f1(cx - r * 0.75)}" y1="${f1(cy - r * 0.62)}" x2="${f1(cx - r * 0.52)}" y2="${f1(cy - r * 0.78)}" stroke="#000000" stroke-width="1.8"/>` +
        `<line x1="${f1(cx + r * 0.52)}" y1="${f1(cy - r * 0.78)}" x2="${f1(cx + r * 0.75)}" y2="${f1(cy - r * 0.62)}" stroke="#000000" stroke-width="1.8"/>` +
        `<line x1="${f1(cx - r * 0.75)}" y1="${f1(cy + r * 0.62)}" x2="${f1(cx - r * 0.52)}" y2="${f1(cy + r * 0.78)}" stroke="#000000" stroke-width="1.8"/>` +
        `<line x1="${f1(cx + r * 0.52)}" y1="${f1(cy + r * 0.78)}" x2="${f1(cx + r * 0.75)}" y2="${f1(cy + r * 0.62)}" stroke="#000000" stroke-width="1.8"/>`
      );
    }

    case "australia": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h)}" fill="#00008b"/>` +
        // mini Union Jack in canton
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w / 2)}" height="${f1(h / 2)}" fill="#012169"/>` +
        `<line x1="${f1(x0)}" y1="${f1(y0)}" x2="${f1(cx)}" y2="${f1(cy)}" stroke="#ffffff" stroke-width="${f1(r * 0.18)}"/>` +
        `<line x1="${f1(x0)}" y1="${f1(cy)}" x2="${f1(cx)}" y2="${f1(y0)}" stroke="#ffffff" stroke-width="${f1(r * 0.18)}"/>` +
        `<line x1="${f1(x0)}" y1="${f1(y0)}" x2="${f1(cx)}" y2="${f1(cy)}" stroke="#c8102e" stroke-width="${f1(r * 0.09)}"/>` +
        `<line x1="${f1(x0)}" y1="${f1(cy)}" x2="${f1(cx)}" y2="${f1(y0)}" stroke="#c8102e" stroke-width="${f1(r * 0.09)}"/>` +
        `<rect x="${f1(x0 + w * 0.21)}" y="${f1(y0)}" width="${f1(r * 0.2)}" height="${f1(h / 2)}" fill="#ffffff"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + h * 0.21)}" width="${f1(w / 2)}" height="${f1(r * 0.2)}" fill="#ffffff"/>` +
        `<rect x="${f1(x0 + w * 0.23)}" y="${f1(y0)}" width="${f1(r * 0.12)}" height="${f1(h / 2)}" fill="#c8102e"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + h * 0.23)}" width="${f1(w / 2)}" height="${f1(r * 0.12)}" fill="#c8102e"/>` +
        // Commonwealth star (bottom-left)
        `<polygon points="${starPoints(cx - r * 0.45, cy + r * 0.48, r * 0.24, r * 0.1, 7)}" fill="#ffffff"/>` +
        // Southern cross stars (right)
        `<circle cx="${f1(cx + r * 0.52)}" cy="${f1(cy - r * 0.55)}" r="1.5" fill="#ffffff"/>` +
        `<circle cx="${f1(cx + r * 0.32)}" cy="${f1(cy - r * 0.12)}" r="1.5" fill="#ffffff"/>` +
        `<circle cx="${f1(cx + r * 0.72)}" cy="${f1(cy - r * 0.12)}" r="1.5" fill="#ffffff"/>` +
        `<circle cx="${f1(cx + r * 0.52)}" cy="${f1(cy + r * 0.45)}" r="1.8" fill="#ffffff"/>` +
        `<circle cx="${f1(cx + r * 0.62)}" cy="${f1(cy + r * 0.15)}" r="1.1" fill="#ffffff"/>`
      );
    }

    case "brazil": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h)}" fill="#009739"/>` +
        `<polygon points="${f1(cx)},${f1(cy - r * 0.74)} ${f1(cx + r * 0.85)},${f1(cy)} ${f1(cx)},${f1(cy + r * 0.74)} ${f1(cx - r * 0.85)},${f1(cy)}" fill="#fed100"/>` +
        `<circle cx="${f1(cx)}" cy="${f1(cy)}" r="${f1(r * 0.42)}" fill="#002776"/>` +
        `<path d="M ${f1(cx - r * 0.4)} ${f1(cy + r * 0.08)} Q ${f1(cx)} ${f1(cy - r * 0.12)} ${f1(cx + r * 0.4)} ${f1(cy - r * 0.05)}" fill="none" stroke="#ffffff" stroke-width="1.8"/>`
      );
    }

    case "canada": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w * 0.25)}" height="${f1(h)}" fill="#ff0000"/>` +
        `<rect x="${f1(x0 + w * 0.25)}" y="${f1(y0)}" width="${f1(w * 0.5)}" height="${f1(h)}" fill="#ffffff"/>` +
        `<rect x="${f1(x0 + w * 0.75)}" y="${f1(y0)}" width="${f1(w * 0.25 + 0.5)}" height="${f1(h)}" fill="#ff0000"/>` +
        `<path d="M ${f1(cx)} ${f1(cy - r * 0.56)} L ${f1(cx + r * 0.12)} ${f1(cy - r * 0.32)} L ${f1(cx + r * 0.34)} ${f1(cy - r * 0.36)} L ${f1(cx + r * 0.24)} ${f1(cy - r * 0.12)} L ${f1(cx + r * 0.48)} ${f1(cy + r * 0.04)} L ${f1(cx + r * 0.24)} ${f1(cy + r * 0.16)} L ${f1(cx + r * 0.32)} ${f1(cy + r * 0.36)} L ${f1(cx + r * 0.12)} ${f1(cy + r * 0.26)} L ${f1(cx + r * 0.04)} ${f1(cy + r * 0.48)} L ${f1(cx - r * 0.04)} ${f1(cy + r * 0.48)} L ${f1(cx - r * 0.12)} ${f1(cy + r * 0.26)} L ${f1(cx - r * 0.32)} ${f1(cy + r * 0.36)} L ${f1(cx - r * 0.24)} ${f1(cy + r * 0.16)} L ${f1(cx - r * 0.48)} ${f1(cy + r * 0.04)} L ${f1(cx - r * 0.24)} ${f1(cy - r * 0.12)} L ${f1(cx - r * 0.34)} ${f1(cy - r * 0.36)} L ${f1(cx - r * 0.12)} ${f1(cy - r * 0.32)} Z" fill="#ff0000"/>` +
        `<rect x="${f1(cx - r * 0.04)}" y="${f1(cy + r * 0.4)}" width="${f1(r * 0.08)}" height="${f1(r * 0.2)}" fill="#ff0000"/>`
      );
    }

    case "netherlands": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h / 3)}" fill="#ae1c28"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + h / 3)}" width="${f1(w)}" height="${f1(h / 3)}" fill="#ffffff"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + 2 * h / 3)}" width="${f1(w)}" height="${f1(h / 3 + 0.5)}" fill="#21468b"/>`
      );
    }

    case "poland": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h / 2)}" fill="#ffffff"/>` +
        `<rect x="${f1(x0)}" y="${f1(cy)}" width="${f1(w)}" height="${f1(h / 2 + 0.5)}" fill="#dc143c"/>`
      );
    }

    case "ukraine": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h / 2)}" fill="#0057b7"/>` +
        `<rect x="${f1(x0)}" y="${f1(cy)}" width="${f1(w)}" height="${f1(h / 2 + 0.5)}" fill="#ffd700"/>`
      );
    }

    case "russia": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h / 3)}" fill="#ffffff"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + h / 3)}" width="${f1(w)}" height="${f1(h / 3)}" fill="#0039a6"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + 2 * h / 3)}" width="${f1(w)}" height="${f1(h / 3 + 0.5)}" fill="#d52b1e"/>`
      );
    }

    case "spain": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h * 0.25)}" fill="#aa151b"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + h * 0.25)}" width="${f1(w)}" height="${f1(h * 0.5)}" fill="#f1bf00"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + h * 0.75)}" width="${f1(w)}" height="${f1(h * 0.25 + 0.5)}" fill="#aa151b"/>` +
        // Spanish coat of arms crest
        `<rect x="${f1(cx - r * 0.52)}" y="${f1(cy - r * 0.24)}" width="${f1(r * 0.36)}" height="${f1(r * 0.5)}" rx="3" fill="#c60b1e" stroke="#f1bf00" stroke-width="1"/>` +
        `<circle cx="${f1(cx - r * 0.34)}" cy="${f1(cy - r * 0.05)}" r="${f1(r * 0.08)}" fill="#f1bf00"/>`
      );
    }

    case "turkey": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h)}" fill="#e30a17"/>` +
        `<circle cx="${f1(cx - r * 0.12)}" cy="${f1(cy)}" r="${f1(r * 0.44)}" fill="#ffffff"/>` +
        `<circle cx="${f1(cx - r * 0.02)}" cy="${f1(cy)}" r="${f1(r * 0.35)}" fill="#e30a17"/>` +
        `<polygon points="${starPoints(cx + r * 0.28, cy, r * 0.16, r * 0.07, 5, -Math.PI / 2)}" fill="#ffffff"/>`
      );
    }

    case "uae": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w * 0.3)}" height="${f1(h)}" fill="#ff0000"/>` +
        `<rect x="${f1(x0 + w * 0.3)}" y="${f1(y0)}" width="${f1(w * 0.7 + 0.5)}" height="${f1(h / 3)}" fill="#00732f"/>` +
        `<rect x="${f1(x0 + w * 0.3)}" y="${f1(y0 + h / 3)}" width="${f1(w * 0.7 + 0.5)}" height="${f1(h / 3)}" fill="#ffffff"/>` +
        `<rect x="${f1(x0 + w * 0.3)}" y="${f1(y0 + 2 * h / 3)}" width="${f1(w * 0.7 + 0.5)}" height="${f1(h / 3 + 0.5)}" fill="#000000"/>`
      );
    }

    case "switzerland": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h)}" fill="#da291c"/>` +
        `<rect x="${f1(cx - r * 0.2)}" y="${f1(cy - r * 0.6)}" width="${f1(r * 0.4)}" height="${f1(r * 1.2)}" fill="#ffffff"/>` +
        `<rect x="${f1(cx - r * 0.6)}" y="${f1(cy - r * 0.2)}" width="${f1(r * 1.2)}" height="${f1(r * 0.4)}" fill="#ffffff"/>`
      );
    }

    case "czech_republic": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h / 2)}" fill="#ffffff"/>` +
        `<rect x="${f1(x0)}" y="${f1(cy)}" width="${f1(w)}" height="${f1(h / 2 + 0.5)}" fill="#d7141a"/>` +
        `<polygon points="${f1(x0)},${f1(y0)} ${f1(cx + r * 0.08)},${f1(cy)} ${f1(x0)},${f1(y0 + h)}" fill="#11457e"/>`
      );
    }

    case "croatia": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h / 3)}" fill="#ff0000"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + h / 3)}" width="${f1(w)}" height="${f1(h / 3)}" fill="#ffffff"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + 2 * h / 3)}" width="${f1(w)}" height="${f1(h / 3 + 0.5)}" fill="#0000ff"/>` +
        // checkerboard shield
        `<rect x="${f1(cx - r * 0.26)}" y="${f1(cy - r * 0.32)}" width="${f1(r * 0.52)}" height="${f1(r * 0.6)}" rx="2" fill="#ff0000" stroke="#ffffff" stroke-width="1"/>` +
        `<rect x="${f1(cx - r * 0.13)}" y="${f1(cy - r * 0.16)}" width="${f1(r * 0.26)}" height="${f1(r * 0.3)}" fill="#ffffff"/>`
      );
    }

    case "greece": {
      const sh = h / 9;
      let stripes = "";
      for (let s = 0; s < 9; s++) {
        stripes += `<rect x="${f1(x0)}" y="${f1(y0 + s * sh)}" width="${f1(w)}" height="${f1(sh + 0.5)}" fill="${s % 2 === 0 ? "#0d5eaf" : "#ffffff"}"/>`;
      }
      return (
        stripes +
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w * 0.44)}" height="${f1(sh * 5)}" fill="#0d5eaf"/>` +
        `<rect x="${f1(x0 + w * 0.17)}" y="${f1(y0)}" width="${f1(w * 0.1)}" height="${f1(sh * 5)}" fill="#ffffff"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + sh * 2)}" width="${f1(w * 0.44)}" height="${f1(sh)}" fill="#ffffff"/>`
      );
    }

    case "singapore": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h / 2)}" fill="#ee2536"/>` +
        `<rect x="${f1(x0)}" y="${f1(cy)}" width="${f1(w)}" height="${f1(h / 2 + 0.5)}" fill="#ffffff"/>` +
        `<circle cx="${f1(cx - r * 0.45)}" cy="${f1(cy - r * 0.45)}" r="${f1(r * 0.25)}" fill="#ffffff"/>` +
        `<circle cx="${f1(cx - r * 0.36)}" cy="${f1(cy - r * 0.45)}" r="${f1(r * 0.22)}" fill="#ee2536"/>` +
        `<circle cx="${f1(cx - r * 0.22)}" cy="${f1(cy - r * 0.45)}" r="1.3" fill="#ffffff"/>` +
        `<circle cx="${f1(cx - r * 0.27)}" cy="${f1(cy - r * 0.6)}" r="1.3" fill="#ffffff"/>` +
        `<circle cx="${f1(cx - r * 0.27)}" cy="${f1(cy - r * 0.3)}" r="1.3" fill="#ffffff"/>`
      );
    }

    case "saudi_arabia": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h)}" fill="#006c35"/>` +
        `<rect x="${f1(cx - r * 0.52)}" y="${f1(cy + r * 0.18)}" width="${f1(r * 1.04)}" height="2" fill="#ffffff"/>` +
        `<path d="M ${f1(cx - r * 0.56)} ${f1(cy + r * 0.14)} L ${f1(cx - r * 0.5)} ${f1(cy + r * 0.19)} L ${f1(cx - r * 0.56)} ${f1(cy + r * 0.24)} Z" fill="#ffffff"/>` +
        `<text x="${f1(cx)}" y="${f1(cy + r * 0.04)}" text-anchor="middle" font-size="9" fill="#ffffff" font-weight="700" font-family="sans-serif">KSA</text>`
      );
    }

    case "thailand": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h / 6)}" fill="#a51931"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + h / 6)}" width="${f1(w)}" height="${f1(h / 6)}" fill="#ffffff"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + h / 3)}" width="${f1(w)}" height="${f1(h / 3)}" fill="#2d2a4a"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + 2 * h / 3)}" width="${f1(w)}" height="${f1(h / 6)}" fill="#ffffff"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + 5 * h / 6)}" width="${f1(w)}" height="${f1(h / 6 + 0.5)}" fill="#a51931"/>`
      );
    }

    case "malaysia": {
      const sh = h / 14;
      let stripes = "";
      for (let s = 0; s < 14; s++) {
        stripes += `<rect x="${f1(x0)}" y="${f1(y0 + s * sh)}" width="${f1(w)}" height="${f1(sh + 0.5)}" fill="${s % 2 === 0 ? "#cc0000" : "#ffffff"}"/>`;
      }
      return (
        stripes +
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w * 0.5)}" height="${f1(sh * 8)}" fill="#000066"/>` +
        `<circle cx="${f1(cx - r * 0.52)}" cy="${f1(cy - r * 0.44)}" r="${f1(r * 0.24)}" fill="#ffcc00"/>` +
        `<circle cx="${f1(cx - r * 0.44)}" cy="${f1(cy - r * 0.44)}" r="${f1(r * 0.2)}" fill="#000066"/>` +
        `<polygon points="${starPoints(cx - r * 0.24, cy - r * 0.44, r * 0.16, r * 0.08, 14)}" fill="#ffcc00"/>`
      );
    }

    case "indonesia": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h / 2)}" fill="#ff0000"/>` +
        `<rect x="${f1(x0)}" y="${f1(cy)}" width="${f1(w)}" height="${f1(h / 2 + 0.5)}" fill="#ffffff"/>`
      );
    }

    case "estonia": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h / 3)}" fill="#0072ce"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + h / 3)}" width="${f1(w)}" height="${f1(h / 3)}" fill="#000000"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + 2 * h / 3)}" width="${f1(w)}" height="${f1(h / 3 + 0.5)}" fill="#ffffff"/>`
      );
    }

    case "ethiopia": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h / 3)}" fill="#009a44"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + h / 3)}" width="${f1(w)}" height="${f1(h / 3)}" fill="#fed100"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + 2 * h / 3)}" width="${f1(w)}" height="${f1(h / 3 + 0.5)}" fill="#ef3340"/>` +
        `<circle cx="${f1(cx)}" cy="${f1(cy)}" r="${f1(r * 0.38)}" fill="#003882"/>` +
        `<polygon points="${starPoints(cx, cy, r * 0.26, r * 0.11, 5, -Math.PI / 2)}" fill="#fed100"/>`
      );
    }

    case "armenia": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h / 3)}" fill="#d90012"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + h / 3)}" width="${f1(w)}" height="${f1(h / 3)}" fill="#0033a0"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + 2 * h / 3)}" width="${f1(w)}" height="${f1(h / 3 + 0.5)}" fill="#f2a800"/>`
      );
    }

    case "austria": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h / 3)}" fill="#ed2939"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + h / 3)}" width="${f1(w)}" height="${f1(h / 3)}" fill="#ffffff"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + 2 * h / 3)}" width="${f1(w)}" height="${f1(h / 3 + 0.5)}" fill="#ed2939"/>`
      );
    }

    case "belgium": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w / 3)}" height="${f1(h)}" fill="#000000"/>` +
        `<rect x="${f1(x0 + w / 3)}" y="${f1(y0)}" width="${f1(w / 3)}" height="${f1(h)}" fill="#fdda24"/>` +
        `<rect x="${f1(x0 + 2 * w / 3)}" y="${f1(y0)}" width="${f1(w / 3 + 0.5)}" height="${f1(h)}" fill="#ef3340"/>`
      );
    }

    case "morocco": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h)}" fill="#c1272d"/>` +
        `<polygon points="${starPoints(cx, cy, r * 0.44, r * 0.17, 5, -Math.PI / 2)}" fill="none" stroke="#006233" stroke-width="2.5" stroke-linejoin="round"/>`
      );
    }

    case "philippines": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h / 2)}" fill="#0038a8"/>` +
        `<rect x="${f1(x0)}" y="${f1(cy)}" width="${f1(w)}" height="${f1(h / 2 + 0.5)}" fill="#ce1126"/>` +
        `<polygon points="${f1(x0)},${f1(y0)} ${f1(cx + r * 0.08)},${f1(cy)} ${f1(x0)},${f1(y0 + h)}" fill="#ffffff"/>` +
        `<circle cx="${f1(cx - r * 0.44)}" cy="${f1(cy)}" r="${f1(r * 0.16)}" fill="#fcd116"/>` +
        `<polygon points="${starPoints(cx - r * 0.72, cy - r * 0.5, r * 0.07, r * 0.03, 5)}" fill="#fcd116"/>` +
        `<polygon points="${starPoints(cx - r * 0.72, cy + r * 0.5, r * 0.07, r * 0.03, 5)}" fill="#fcd116"/>` +
        `<polygon points="${starPoints(cx - r * 0.12, cy, r * 0.07, r * 0.03, 5)}" fill="#fcd116"/>`
      );
    }

    case "romania": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w / 3)}" height="${f1(h)}" fill="#002b7f"/>` +
        `<rect x="${f1(x0 + w / 3)}" y="${f1(y0)}" width="${f1(w / 3)}" height="${f1(h)}" fill="#fcd116"/>` +
        `<rect x="${f1(x0 + 2 * w / 3)}" y="${f1(y0)}" width="${f1(w / 3 + 0.5)}" height="${f1(h)}" fill="#ce1126"/>`
      );
    }

    case "serbia": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h / 3)}" fill="#c6363c"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + h / 3)}" width="${f1(w)}" height="${f1(h / 3)}" fill="#0c4076"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + 2 * h / 3)}" width="${f1(w)}" height="${f1(h / 3 + 0.5)}" fill="#ffffff"/>` +
        `<circle cx="${f1(cx - r * 0.28)}" cy="${f1(cy)}" r="${f1(r * 0.26)}" fill="#c6363c" stroke="#ffffff" stroke-width="1"/>`
      );
    }

    case "egypt": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h / 3)}" fill="#ce1126"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + h / 3)}" width="${f1(w)}" height="${f1(h / 3)}" fill="#ffffff"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + 2 * h / 3)}" width="${f1(w)}" height="${f1(h / 3 + 0.5)}" fill="#000000"/>` +
        `<circle cx="${f1(cx)}" cy="${f1(cy)}" r="${f1(r * 0.16)}" fill="#c0932b"/>`
      );
    }

    case "qatar": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w * 0.35)}" height="${f1(h)}" fill="#ffffff"/>` +
        `<rect x="${f1(x0 + w * 0.35)}" y="${f1(y0)}" width="${f1(w * 0.65 + 0.5)}" height="${f1(h)}" fill="#8a1538"/>` +
        `<polygon points="${f1(x0 + w * 0.35)},${f1(y0)} ${f1(cx - r * 0.15)},${f1(cy - r * 0.5)} ${f1(x0 + w * 0.35)},${f1(cy)} ${f1(cx - r * 0.15)},${f1(cy + r * 0.5)} ${f1(x0 + w * 0.35)},${f1(y0 + h)}" fill="#ffffff"/>`
      );
    }

    case "oman": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w * 0.28)}" height="${f1(h)}" fill="#db161d"/>` +
        `<rect x="${f1(x0 + w * 0.28)}" y="${f1(y0)}" width="${f1(w * 0.72 + 0.5)}" height="${f1(h / 3)}" fill="#ffffff"/>` +
        `<rect x="${f1(x0 + w * 0.28)}" y="${f1(y0 + h / 3)}" width="${f1(w * 0.72 + 0.5)}" height="${f1(h / 3)}" fill="#db161d"/>` +
        `<rect x="${f1(x0 + w * 0.28)}" y="${f1(y0 + 2 * h / 3)}" width="${f1(w * 0.72 + 0.5)}" height="${f1(h / 3 + 0.5)}" fill="#008000"/>`
      );
    }

    case "bahrain": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w * 0.32)}" height="${f1(h)}" fill="#ffffff"/>` +
        `<rect x="${f1(x0 + w * 0.32)}" y="${f1(y0)}" width="${f1(w * 0.68 + 0.5)}" height="${f1(h)}" fill="#ce1126"/>`
      );
    }

    case "chile": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h / 2)}" fill="#ffffff"/>` +
        `<rect x="${f1(x0)}" y="${f1(cy)}" width="${f1(w)}" height="${f1(h / 2 + 0.5)}" fill="#d52b1e"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w * 0.44)}" height="${f1(h / 2)}" fill="#0039a6"/>` +
        `<polygon points="${starPoints(x0 + w * 0.22, y0 + h * 0.25, r * 0.16, r * 0.07, 5)}" fill="#ffffff"/>`
      );
    }

    case "portugal": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w * 0.4)}" height="${f1(h)}" fill="#046a38"/>` +
        `<rect x="${f1(x0 + w * 0.4)}" y="${f1(y0)}" width="${f1(w * 0.6 + 0.5)}" height="${f1(h)}" fill="#da291c"/>` +
        `<circle cx="${f1(x0 + w * 0.4)}" cy="${f1(cy)}" r="${f1(r * 0.3)}" fill="#ffdd00"/>` +
        `<circle cx="${f1(x0 + w * 0.4)}" cy="${f1(cy)}" r="${f1(r * 0.2)}" fill="#ffffff"/>`
      );
    }

    case "hungary": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h / 3)}" fill="#ce2939"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + h / 3)}" width="${f1(w)}" height="${f1(h / 3)}" fill="#ffffff"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0 + 2 * h / 3)}" width="${f1(w)}" height="${f1(h / 3 + 0.5)}" fill="#477050"/>`
      );
    }

    case "new_zealand": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h)}" fill="#00247d"/>` +
        `<circle cx="${f1(cx + r * 0.45)}" cy="${f1(cy - r * 0.4)}" r="2" fill="#cc142b" stroke="#ffffff" stroke-width="0.8"/>` +
        `<circle cx="${f1(cx + r * 0.65)}" cy="${f1(cy)}" r="2" fill="#cc142b" stroke="#ffffff" stroke-width="0.8"/>` +
        `<circle cx="${f1(cx + r * 0.45)}" cy="${f1(cy + r * 0.4)}" r="2" fill="#cc142b" stroke="#ffffff" stroke-width="0.8"/>` +
        `<circle cx="${f1(cx + r * 0.25)}" cy="${f1(cy)}" r="1.7" fill="#cc142b" stroke="#ffffff" stroke-width="0.8"/>`
      );
    }

    case "taiwan": {
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h)}" fill="#fe0000"/>` +
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w * 0.5)}" height="${f1(h / 2)}" fill="#000095"/>` +
        `<circle cx="${f1(x0 + w * 0.25)}" cy="${f1(y0 + h * 0.25)}" r="${f1(r * 0.16)}" fill="#ffffff"/>`
      );
    }

    default: {
      // Stylized global sphere / coordinates disc for unknown or international
      return (
        `<rect x="${f1(x0)}" y="${f1(y0)}" width="${f1(w)}" height="${f1(h)}" fill="#1d2b3a"/>` +
        `<circle cx="${f1(cx)}" cy="${f1(cy)}" r="${f1(r * 0.62)}" fill="none" stroke="#7fa8c9" stroke-width="1.2" stroke-dasharray="3,2"/>` +
        `<ellipse cx="${f1(cx)}" cy="${f1(cy)}" rx="${f1(r * 0.32)}" ry="${f1(r * 0.62)}" fill="none" stroke="#7fa8c9" stroke-width="1.2"/>` +
        `<line x1="${f1(cx - r * 0.62)}" y1="${f1(cy)}" x2="${f1(cx + r * 0.62)}" y2="${f1(cy)}" stroke="#7fa8c9" stroke-width="1.2"/>` +
        `<line x1="${f1(cx)}" y1="${f1(cy - r * 0.62)}" x2="${f1(cx)}" y2="${f1(cy + r * 0.62)}" stroke="#7fa8c9" stroke-width="1.2"/>` +
        `<text x="${f1(cx)}" y="${f1(cy + 3.5)}" text-anchor="middle" font-size="8" fill="#9dbcd6" font-weight="700" font-family="monospace">GLOBAL</text>`
      );
    }
  }
}

/**
 * Returns a complete SVG node element representing a circular country flag:
 * includes outer glow halo, clipPath, flag graphic, coin rim, and active/focus ring.
 */
export function countryFlagDisc(countryName, cx, cy, r, ringColor, extraAttr, clipId) {
  const normKey = normCountryKey(countryName);
  const flagContent = renderFlagContent(normKey, cx, cy, r);

  return (
    `<defs>` +
    `<clipPath id="${clipId}">` +
    `<circle cx="${f1(cx)}" cy="${f1(cy)}" r="${f1(r)}" />` +
    `</clipPath>` +
    `</defs>` +
    // outer halo
    `<circle class="halo" cx="${f1(cx)}" cy="${f1(cy)}" r="${f1(r + 7)}" style="fill:none;stroke:${ringColor || "#7fa8c9"}" stroke-width="1.3" opacity="0.35" />` +
    // clipped flag graphics
    `<g class="pg-flag" clip-path="url(#${clipId})">` +
    flagContent +
    // inner dark rim / vignette for depth
    `<circle cx="${f1(cx)}" cy="${f1(cy)}" r="${f1(r)}" fill="none" stroke="rgba(0,0,0,0.25)" stroke-width="2" />` +
    `</g>` +
    // subtle inner rim highlight
    `<circle cx="${f1(cx)}" cy="${f1(cy)}" r="${f1(r - 0.75)}" style="fill:none;stroke:rgba(255,255,255,0.28)" stroke-width="1" />` +
    // outer border ring
    `<circle class="net-circle" cx="${f1(cx)}" cy="${f1(cy)}" r="${f1(r)}" style="fill:none;stroke:${ringColor || "#7fa8c9"}" stroke-width="2" ${extraAttr || ""} />`
  );
}
