"""Competitor order for the Competitive Overview data flood (Lane A): KSSL-relevance first."""
PRIORITY = [
    # Indian artillery / ammunition rivals first
    "Adani Defence & Aerospace", "Larsen & Toubro", "Tata Advanced Systems", "Bharat Dynamics Ltd (BDL)", "Munitions India Ltd (MIL)",
    # then the foreign artillery / armour / ammunition rivals
    "Hanwha Aerospace", "KNDS Germany", "Nexter (KNDS France)", "Rheinmetall", "Elbit Systems", "NORINCO",
    # other Indian
    "BrahMos Aerospace", "Mahindra Defence", "AWEIL", "PLR Systems (IWI+Adani)", "Solar Industries", "SSS Defence", "Premier Explosives",
    # artillery / ammunition / vehicles abroad
    "BAE Systems", "Nammo", "Poongsan", "Huta Stalowa Wola (HSW)", "Patria", "Otokar", "Oshkosh Defense", "General Dynamics", "Paramount Group",
    "Diehl Defence", "IDV (Iveco Defence)", "Kalashnikov Concern", "SIG Sauer", "Roshel", "Supacat", "Leonardo", "SAAB", "KONGSBERG",
    "Rafael Advanced Defense Systems", "Israel Aerospace Industries (IAI)", "MBDA", "UVision Air",
    "Lockheed Martin", "Northrop Grumman", "RTX (Raytheon)", "L3Harris", "Anduril", "AeroVironment", "Babcock", "Naval Group",
    "Thyssenkrupp Marine Systems", "Huntington Ingalls Industries",
]


def order_index(name: str) -> int:
    return PRIORITY.index(name) if name in PRIORITY else len(PRIORITY)
