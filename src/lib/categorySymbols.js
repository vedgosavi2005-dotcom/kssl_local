/* CATEGORY SYMBOLS FOR PARTNERSHIP GRAPH NODES
 *
 * Vector icons placed inside category node circles (e.g. Technology chip,
 * Supplier crate, Joint Venture handshake/alliance, MoU charter document,
 * Acquisition crosshairs target, Other network, plus the channel set:
 * distributor truck, dealer shopfront, packager stack, rental clock, OEM gear,
 * framework contract, localization factory, service spanner, key-account briefcase).
 */

const f1 = (x) => (Math.round(x * 10) / 10).toString();

/**
 * Returns SVG markup for a category's central symbol centered at (cx, cy)
 */
export function categorySymbolSvg(key, cx, cy, r, color, fill) {
  const c = color || "#ffffff";
  const bg = fill || "rgba(0,0,0,0.5)";

  switch (key) {
    case "tech": {
      // Microchip / CPU processor with silicon core and pin leads
      return (
        // Chip body
        `<rect x="${f1(cx - 9.5)}" y="${f1(cy - 9.5)}" width="19" height="19" rx="3" fill="${bg}" stroke="${c}" stroke-width="1.8" />` +
        // Inner core
        `<rect x="${f1(cx - 4.5)}" y="${f1(cy - 4.5)}" width="9" height="9" rx="1.5" fill="${c}" fill-opacity="0.3" stroke="${c}" stroke-width="1.2" />` +
        // Core center dot
        `<circle cx="${f1(cx)}" cy="${f1(cy)}" r="1.5" fill="${c}" />` +
        // Top pin leads
        `<line x1="${f1(cx - 5.5)}" y1="${f1(cy - 9.5)}" x2="${f1(cx - 5.5)}" y2="${f1(cy - 14.5)}" stroke="${c}" stroke-width="1.5" stroke-linecap="round" />` +
        `<line x1="${f1(cx)}" y1="${f1(cy - 9.5)}" x2="${f1(cx)}" y2="${f1(cy - 14.5)}" stroke="${c}" stroke-width="1.5" stroke-linecap="round" />` +
        `<line x1="${f1(cx + 5.5)}" y1="${f1(cy - 9.5)}" x2="${f1(cx + 5.5)}" y2="${f1(cy - 14.5)}" stroke="${c}" stroke-width="1.5" stroke-linecap="round" />` +
        // Bottom pin leads
        `<line x1="${f1(cx - 5.5)}" y1="${f1(cy + 9.5)}" x2="${f1(cx - 5.5)}" y2="${f1(cy + 14.5)}" stroke="${c}" stroke-width="1.5" stroke-linecap="round" />` +
        `<line x1="${f1(cx)}" y1="${f1(cy + 9.5)}" x2="${f1(cx)}" y2="${f1(cy + 14.5)}" stroke="${c}" stroke-width="1.5" stroke-linecap="round" />` +
        `<line x1="${f1(cx + 5.5)}" y1="${f1(cy + 9.5)}" x2="${f1(cx + 5.5)}" y2="${f1(cy + 14.5)}" stroke="${c}" stroke-width="1.5" stroke-linecap="round" />` +
        // Left pin leads
        `<line x1="${f1(cx - 9.5)}" y1="${f1(cy - 5.5)}" x2="${f1(cx - 14.5)}" y2="${f1(cy - 5.5)}" stroke="${c}" stroke-width="1.5" stroke-linecap="round" />` +
        `<line x1="${f1(cx - 9.5)}" y1="${f1(cy)}" x2="${f1(cx - 14.5)}" y2="${f1(cy)}" stroke="${c}" stroke-width="1.5" stroke-linecap="round" />` +
        `<line x1="${f1(cx - 9.5)}" y1="${f1(cy + 5.5)}" x2="${f1(cx - 14.5)}" y2="${f1(cy + 5.5)}" stroke="${c}" stroke-width="1.5" stroke-linecap="round" />` +
        // Right pin leads
        `<line x1="${f1(cx + 9.5)}" y1="${f1(cy - 5.5)}" x2="${f1(cx + 14.5)}" y2="${f1(cy - 5.5)}" stroke="${c}" stroke-width="1.5" stroke-linecap="round" />` +
        `<line x1="${f1(cx + 9.5)}" y1="${f1(cy)}" x2="${f1(cx + 14.5)}" y2="${f1(cy)}" stroke="${c}" stroke-width="1.5" stroke-linecap="round" />` +
        `<line x1="${f1(cx + 9.5)}" y1="${f1(cy + 5.5)}" x2="${f1(cx + 14.5)}" y2="${f1(cy + 5.5)}" stroke="${c}" stroke-width="1.5" stroke-linecap="round" />`
      );
    }

    case "supply": {
      // 3D Isometric Cargo Cube / Logistics delivery package
      return (
        // Top face
        `<polygon points="${f1(cx)},${f1(cy - 13.5)} ${f1(cx + 11.5)},${f1(cy - 6.5)} ${f1(cx)},${f1(cy)} ${f1(cx - 11.5)},${f1(cy - 6.5)}" fill="${c}" fill-opacity="0.32" stroke="${c}" stroke-width="1.6" stroke-linejoin="round" />` +
        // Left face
        `<polygon points="${f1(cx - 11.5)},${f1(cy - 6.5)} ${f1(cx)},${f1(cy)} ${f1(cx)},${f1(cy + 13.5)} ${f1(cx - 11.5)},${f1(cy + 6.5)}" fill="${c}" fill-opacity="0.16" stroke="${c}" stroke-width="1.6" stroke-linejoin="round" />` +
        // Right face
        `<polygon points="${f1(cx)},${f1(cy)} ${f1(cx + 11.5)},${f1(cy - 6.5)} ${f1(cx + 11.5)},${f1(cy + 6.5)} ${f1(cx)},${f1(cy + 13.5)}" fill="${c}" fill-opacity="0.24" stroke="${c}" stroke-width="1.6" stroke-linejoin="round" />` +
        // Vertical strapping band
        `<line x1="${f1(cx)}" y1="${f1(cy - 6.5)}" x2="${f1(cx)}" y2="${f1(cy + 13.5)}" stroke="#ffffff" stroke-opacity="0.8" stroke-width="1.3" />` +
        // Horizontal strapping band
        `<line x1="${f1(cx - 5.8)}" y1="${f1(cy - 3.2)}" x2="${f1(cx + 5.8)}" y2="${f1(cy - 3.2)}" stroke="#ffffff" stroke-opacity="0.8" stroke-width="1.3" />`
      );
    }

    case "jv": {
      // Interlocking Alliance Rings + Handshake clasp
      return (
        // Left partnership ring
        `<circle cx="${f1(cx - 5.5)}" cy="${f1(cy)}" r="8.5" fill="none" stroke="${c}" stroke-width="2.2" stroke-linecap="round" />` +
        // Right partnership ring
        `<circle cx="${f1(cx + 5.5)}" cy="${f1(cy)}" r="8.5" fill="none" stroke="${c}" stroke-width="2.2" stroke-linecap="round" />` +
        // Center alliance clasp
        `<path d="M ${f1(cx - 3.5)} ${f1(cy - 1.5)} L ${f1(cx)} ${f1(cy + 2.2)} L ${f1(cx + 3.5)} ${f1(cy - 1.5)}" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />`
      );
    }

    case "mou": {
      // Strategic Charter / Document with folded corner & official seal
      return (
        // Document page
        `<path d="M ${f1(cx - 7.5)} ${f1(cy - 12.5)} L ${f1(cx + 2.5)} ${f1(cy - 12.5)} L ${f1(cx + 8.5)} ${f1(cy - 6.5)} L ${f1(cx + 8.5)} ${f1(cy + 12.5)} L ${f1(cx - 7.5)} ${f1(cy + 12.5)} Z" fill="${c}" fill-opacity="0.18" stroke="${c}" stroke-width="1.8" stroke-linejoin="round" />` +
        // Folded top-right corner
        `<path d="M ${f1(cx + 2.5)} ${f1(cy - 12.5)} L ${f1(cx + 2.5)} ${f1(cy - 6.5)} L ${f1(cx + 8.5)} ${f1(cy - 6.5)}" fill="none" stroke="${c}" stroke-width="1.5" stroke-linejoin="round" />` +
        // Text lines
        `<line x1="${f1(cx - 4)}" y1="${f1(cy - 3)}" x2="${f1(cx + 4.5)}" y2="${f1(cy - 3)}" stroke="#ffffff" stroke-opacity="0.85" stroke-width="1.4" stroke-linecap="round" />` +
        `<line x1="${f1(cx - 4)}" y1="${f1(cy + 1.8)}" x2="${f1(cx + 4.5)}" y2="${f1(cy + 1.8)}" stroke="#ffffff" stroke-opacity="0.85" stroke-width="1.4" stroke-linecap="round" />` +
        `<line x1="${f1(cx - 4)}" y1="${f1(cy + 6.6)}" x2="${f1(cx + 1)}" y2="${f1(cy + 6.6)}" stroke="#ffffff" stroke-opacity="0.85" stroke-width="1.4" stroke-linecap="round" />` +
        // Wax seal
        `<circle cx="${f1(cx + 4.5)}" cy="${f1(cy + 7.5)}" r="2" fill="${c}" />`
      );
    }

    case "acq": {
      // Strategic Acquisition Target Crosshair Bullseye
      return (
        // Outer target circle
        `<circle cx="${f1(cx)}" cy="${f1(cy)}" r="10.5" fill="none" stroke="${c}" stroke-width="1.8" />` +
        // Inner bullseye ring
        `<circle cx="${f1(cx)}" cy="${f1(cy)}" r="5" fill="${c}" fill-opacity="0.25" stroke="${c}" stroke-width="1.5" />` +
        // Center target pip
        `<circle cx="${f1(cx)}" cy="${f1(cy)}" r="2" fill="#ffffff" />` +
        // 4 crosshair ticks
        `<line x1="${f1(cx - 13.5)}" y1="${f1(cy)}" x2="${f1(cx - 8.5)}" y2="${f1(cy)}" stroke="${c}" stroke-width="1.8" stroke-linecap="round" />` +
        `<line x1="${f1(cx + 8.5)}" y1="${f1(cy)}" x2="${f1(cx + 13.5)}" y2="${f1(cy)}" stroke="${c}" stroke-width="1.8" stroke-linecap="round" />` +
        `<line x1="${f1(cx)}" y1="${f1(cy - 13.5)}" x2="${f1(cx)}" y2="${f1(cy - 8.5)}" stroke="${c}" stroke-width="1.8" stroke-linecap="round" />` +
        `<line x1="${f1(cx)}" y1="${f1(cy + 8.5)}" x2="${f1(cx)}" y2="${f1(cy + 13.5)}" stroke="${c}" stroke-width="1.8" stroke-linecap="round" />`
      );
    }

    case "dist": {
      // Delivery truck: cargo box, cab and two wheels
      return (
        `<rect x="${f1(cx - 12)}" y="${f1(cy - 8)}" width="14" height="11" rx="1.5" fill="${c}" fill-opacity="0.25" stroke="${c}" stroke-width="1.6" />` +
        `<path d="M ${f1(cx + 2)} ${f1(cy - 4)} L ${f1(cx + 7)} ${f1(cy - 4)} L ${f1(cx + 11)} ${f1(cy)} L ${f1(cx + 11)} ${f1(cy + 3)} L ${f1(cx + 2)} ${f1(cy + 3)} Z" fill="${c}" fill-opacity="0.15" stroke="${c}" stroke-width="1.6" stroke-linejoin="round" />` +
        `<circle cx="${f1(cx - 6)}" cy="${f1(cy + 6)}" r="2.4" fill="#ffffff" stroke="${c}" stroke-width="1.4" />` +
        `<circle cx="${f1(cx + 6)}" cy="${f1(cy + 6)}" r="2.4" fill="#ffffff" stroke="${c}" stroke-width="1.4" />`
      );
    }

    case "dealer": {
      // Shopfront with awning
      return (
        `<path d="M ${f1(cx - 11)} ${f1(cy - 5)} L ${f1(cx - 8)} ${f1(cy - 11)} L ${f1(cx + 8)} ${f1(cy - 11)} L ${f1(cx + 11)} ${f1(cy - 5)} Z" fill="${c}" fill-opacity="0.3" stroke="${c}" stroke-width="1.6" stroke-linejoin="round" />` +
        `<rect x="${f1(cx - 9)}" y="${f1(cy - 5)}" width="18" height="15" fill="none" stroke="${c}" stroke-width="1.6" />` +
        `<rect x="${f1(cx - 3)}" y="${f1(cy + 1)}" width="6" height="9" fill="${c}" fill-opacity="0.5" />`
      );
    }

    case "packager": {
      // Stacked layers: parts assembled into one set
      return (
        `<rect x="${f1(cx - 10)}" y="${f1(cy + 3)}" width="20" height="7" rx="1.5" fill="${c}" fill-opacity="0.18" stroke="${c}" stroke-width="1.6" />` +
        `<rect x="${f1(cx - 10)}" y="${f1(cy - 4.5)}" width="20" height="7" rx="1.5" fill="${c}" fill-opacity="0.3" stroke="${c}" stroke-width="1.6" />` +
        `<rect x="${f1(cx - 10)}" y="${f1(cy - 12)}" width="20" height="7" rx="1.5" fill="${c}" fill-opacity="0.45" stroke="${c}" stroke-width="1.6" />`
      );
    }

    case "rental": {
      // Clock: equipment out on hire by the day
      return (
        `<circle cx="${f1(cx)}" cy="${f1(cy)}" r="11" fill="none" stroke="${c}" stroke-width="1.9" />` +
        `<line x1="${f1(cx)}" y1="${f1(cy)}" x2="${f1(cx)}" y2="${f1(cy - 7)}" stroke="#ffffff" stroke-width="1.8" stroke-linecap="round" />` +
        `<line x1="${f1(cx)}" y1="${f1(cy)}" x2="${f1(cx + 5.5)}" y2="${f1(cy + 3)}" stroke="#ffffff" stroke-width="1.8" stroke-linecap="round" />`
      );
    }

    case "oem": {
      // Gear: components built into another maker's product
      let teeth = "";
      for (let i = 0; i < 8; i++) {
        const a = (i * Math.PI) / 4;
        teeth += `<line x1="${f1(cx + 8 * Math.cos(a))}" y1="${f1(cy + 8 * Math.sin(a))}" x2="${f1(cx + 12.5 * Math.cos(a))}" y2="${f1(cy + 12.5 * Math.sin(a))}" stroke="${c}" stroke-width="3" stroke-linecap="round" />`;
      }
      return teeth + `<circle cx="${f1(cx)}" cy="${f1(cy)}" r="8" fill="${c}" fill-opacity="0.22" stroke="${c}" stroke-width="1.7" />` + `<circle cx="${f1(cx)}" cy="${f1(cy)}" r="3" fill="#ffffff" />`;
    }

    case "framework": {
      // Contract page with a tick: a committed volume
      return (
        `<rect x="${f1(cx - 8)}" y="${f1(cy - 12)}" width="16" height="24" rx="2" fill="${c}" fill-opacity="0.18" stroke="${c}" stroke-width="1.7" />` +
        `<line x1="${f1(cx - 4)}" y1="${f1(cy - 6)}" x2="${f1(cx + 4)}" y2="${f1(cy - 6)}" stroke="#ffffff" stroke-opacity="0.85" stroke-width="1.4" stroke-linecap="round" />` +
        `<path d="M ${f1(cx - 4)} ${f1(cy + 3)} L ${f1(cx - 1)} ${f1(cy + 6.5)} L ${f1(cx + 5)} ${f1(cy - 1)}" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />`
      );
    }

    case "local": {
      // Factory with sawtooth roof and chimney
      return (
        `<path d="M ${f1(cx - 11)} ${f1(cy + 10)} L ${f1(cx - 11)} ${f1(cy - 2)} L ${f1(cx - 4)} ${f1(cy - 7)} L ${f1(cx - 4)} ${f1(cy - 2)} L ${f1(cx + 3)} ${f1(cy - 7)} L ${f1(cx + 3)} ${f1(cy - 2)} L ${f1(cx + 11)} ${f1(cy - 2)} L ${f1(cx + 11)} ${f1(cy + 10)} Z" fill="${c}" fill-opacity="0.25" stroke="${c}" stroke-width="1.6" stroke-linejoin="round" />` +
        `<rect x="${f1(cx + 5)}" y="${f1(cy - 12)}" width="4" height="8" fill="${c}" fill-opacity="0.5" />`
      );
    }

    case "service": {
      // Spanner
      return (
        `<line x1="${f1(cx - 9)}" y1="${f1(cy + 9)}" x2="${f1(cx + 3)}" y2="${f1(cy - 3)}" stroke="${c}" stroke-width="4" stroke-linecap="round" />` +
        `<circle cx="${f1(cx + 5.5)}" cy="${f1(cy - 5.5)}" r="6" fill="none" stroke="${c}" stroke-width="2.4" />` +
        `<circle cx="${f1(cx + 8)}" cy="${f1(cy - 8)}" r="2.6" fill="${bg}" />`
      );
    }

    case "account": {
      // Briefcase: the buyer
      return (
        `<rect x="${f1(cx - 11)}" y="${f1(cy - 5)}" width="22" height="15" rx="2" fill="${c}" fill-opacity="0.25" stroke="${c}" stroke-width="1.7" />` +
        `<path d="M ${f1(cx - 4)} ${f1(cy - 5)} L ${f1(cx - 4)} ${f1(cy - 9)} L ${f1(cx + 4)} ${f1(cy - 9)} L ${f1(cx + 4)} ${f1(cy - 5)}" fill="none" stroke="${c}" stroke-width="1.7" stroke-linejoin="round" />` +
        `<line x1="${f1(cx - 11)}" y1="${f1(cy + 2)}" x2="${f1(cx + 11)}" y2="${f1(cy + 2)}" stroke="#ffffff" stroke-opacity="0.8" stroke-width="1.3" />`
      );
    }

    default: {
      // "other" -- Interconnected network constellation / ecosystem
      return (
        // 3 peripheral nodes
        `<circle cx="${f1(cx)}" cy="${f1(cy - 7)}" r="3" fill="${c}" />` +
        `<circle cx="${f1(cx - 6.5)}" cy="${f1(cy + 5.5)}" r="3" fill="${c}" />` +
        `<circle cx="${f1(cx + 6.5)}" cy="${f1(cy + 5.5)}" r="3" fill="${c}" />` +
        // connecting spoke lines
        `<line x1="${f1(cx)}" y1="${f1(cy - 7)}" x2="${f1(cx - 6.5)}" y2="${f1(cy + 5.5)}" stroke="${c}" stroke-width="1.5" />` +
        `<line x1="${f1(cx)}" y1="${f1(cy - 7)}" x2="${f1(cx + 6.5)}" y2="${f1(cy + 5.5)}" stroke="${c}" stroke-width="1.5" />` +
        `<line x1="${f1(cx - 6.5)}" y1="${f1(cy + 5.5)}" x2="${f1(cx + 6.5)}" y2="${f1(cy + 5.5)}" stroke="${c}" stroke-width="1.5" />` +
        // Central hub
        `<circle cx="${f1(cx)}" cy="${f1(cy + 0.5)}" r="1.6" fill="#ffffff" />`
      );
    }
  }
}

/**
 * Returns complete SVG node disc containing halo, background circle, inner rim,
 * and category vector icon.
 */
export function categoryDisc(key, cx, cy, r, fill, ringColor, extraAttr) {
  const symbol = categorySymbolSvg(key, cx, cy, r, ringColor, fill);

  return (
    // Outer glow halo
    `<circle class="halo" cx="${f1(cx)}" cy="${f1(cy)}" r="${f1(r + 7)}" style="fill:none;stroke:${ringColor}" stroke-width="1.3" opacity="0.35" />` +
    // Main colored disc
    `<circle class="net-circle" cx="${f1(cx)}" cy="${f1(cy)}" r="${f1(r)}" style="fill:${fill};stroke:${ringColor}" stroke-width="2" ${extraAttr || ""} />` +
    // Subtle inner rim highlight
    `<circle cx="${f1(cx)}" cy="${f1(cy)}" r="${f1(r - 1)}" style="fill:none;stroke:rgba(255,255,255,0.18)" stroke-width="1" />` +
    // Vector category symbol in center
    `<g class="pg-cat-symbol" pointer-events="none">${symbol}</g>`
  );
}
