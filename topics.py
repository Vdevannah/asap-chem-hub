"""
ASAP Chem Hub - research topic rules
====================================
Ten broad topics. Specific terms (Suzuki, JAK2, photoredox ...) are left to
the keyword search box; topics are for browsing.

How tagging works
-----------------
* Each topic has 'phrases' (case-insensitive) and 'acronyms' (case-sensitive,
  so "ALK" the kinase never matches "alk" in alkyl).
* A match in the TITLE scores 2, a match in the ABSTRACT scores 1.
  Each different rule counts once.
* An article gets the topic when the TITLE matches, or when the abstract alone
  scores >= 2 (two different matches). One passing mention is not enough.
  Computational needs 3 and Analytical 4 from the abstract alone, because most
  experimental papers mention DFT, NMR or crystallography in passing.
* An article can have several topics.

To tune: edit the lists below, then run  python tune_topics.py
"""

import re

D = r"[–—‐-]"  # any dash used by publishers

TOPICS = {
    # ---------------- Drug discovery ----------------
    "Targeted protein degradation": {
        "phrases": [
            r"\bPROTACs?\b", r"proteolysis[- ]targeting chimeras?",
            r"targeted protein degradation", r"\bdegraders?\b", r"molecular glues?",
            r"\bE3 (ubiquitin )?ligases?\b", r"\b(cereblon|VHL|von Hippel[- ]Lindau)\b",
            r"\bternary complex", r"\b(LYTAC|AUTAC|ATTEC|RIBOTAC)s?\b",
            r"\b(induced|targeted) (protein )?degradation\b",
        ],
        "acronyms": [r"\bCRBN\b", r"\bTPD\b"],
    },
    "Inhibitors": {
        "phrases": [
            r"\binhibitors?\b", r"\binhibition of\b", r"\bantagonists?\b",
            r"\ballosteric (modulators?|inhibitors?)\b", r"\bwarheads?\b",
        ],
        "acronyms": [r"\bIC50\b", r"\bIC₅₀\b"],
    },
    "Medicinal chemistry": {
        "phrases": [
            r"\bmedicinal chemistry\b", r"\bdrug (discovery|design|candidates?|development)\b",
            r"\bstructure[–—‐-]activity relationships?\b", r"\blead optimi[sz]ation\b",
            r"\bhit[- ]to[- ]lead\b", r"\bclinical candidates?\b", r"\bpharmacokinetic",
            r"\b(in vivo|oral) (efficacy|bioavailability|exposure)\b", r"\bxenograft\b",
            r"\bmetabolic stability\b", r"\b(anticancer|antitumor|antiviral|antibacterial|"
            r"antimicrobial|antifungal|antimalarial|anti-inflammatory) (agents?|activity|compounds?)\b",
            r"\bscaffold hopping\b", r"\bbioisoster",
        ],
        "acronyms": [r"\bSAR\b", r"\bADMET?\b", r"\bDMPK\b"],
    },
    "Chemical biology": {
        "phrases": [
            r"\bchemical biology\b", r"\bchemical probes?\b", r"\bbioconjugat",
            r"\bbioorthogonal\b", r"\bclick chemistry\b", r"\b(protein|peptide|RNA|DNA) labell?ing\b",
            r"\bantibody[- ]drug conjugates?\b", r"\bchemoproteomic", r"\bactivity[- ]based\b",
            r"\bpeptides?\b", r"\bmacrocyclic peptides?\b", r"\bfluorescent probes?\b",
            r"\b(DNA|RNA)[- ]encoded librar", r"\bphotoaffinity\b", r"\benzyme engineering\b",
            r"\bbiocatal",
        ],
        "acronyms": [r"\bADCs?\b", r"\bDEL\b"],
    },
    # ---------------- Synthesis and catalysis ----------------
    "Synthetic methods": {
        "phrases": [
            rf"\bcross{D}?couplings?\b", r"\b(Suzuki|Buchwald|Negishi|Stille|Sonogashira|Heck|"
            r"Chan[–—‐-]Lam|Ullmann|Wittig|Diels[–—‐-]Alder|Mitsunobu)\b",
            rf"C{D}H (bond )?(functionali[sz]ation|activation|arylation|alkylation|amination|"
            r"oxidation|borylation)", r"\bcycloadditions?\b", r"\bannulations?\b",
            r"\b(arylation|alkylation|allylation|alkenylation|amination|amidation|borylation|fluorination|"
            r"trifluoromethylation|cyclization|isomeri[sz]ation|"
            r"hydrofunctionali[sz]ation|difunctionali[sz]ation|carboxylation|olefination)\b",
            r"\bskeletal editing\b", r"\b(deaminative|decarboxylative|deoxygenative|dehydrogenative)\b", r"\blate[- ]stage functionali[sz]ation\b",
            r"\b(one[- ]pot|cascade|domino|multicomponent) (reaction|synthesis|process)",
            r"\bsynthetic (method|methodology|route|strategy)\b", r"\bsubstrate scope\b",
            r"\bfunctional[- ]group tolerance\b", r"\bheterocycles?\b",
        ],
        "acronyms": [],
    },
    "Catalysis": {
        "phrases": [
            r"\bcataly(sis|ses|st|sts|tic|tically|ze|zed|zes|zing|sed)\b",
            r"\benantioselective\b", r"\basymmetric\b", r"\bphotoredox\b", r"\bphotocataly",
            r"\belectrocataly", r"\belectrosynthe", r"\borganocataly", r"\bbiocataly",
            r"\b(palladium|nickel|copper|iron|cobalt|rhodium|iridium|ruthenium|gold|silver)"
            r"[- ]catalyz", r"\b(Pd|Ni|Cu|Fe|Co|Rh|Ir|Ru|Au|Ag)[- ]catalyz",
            r"\bligands? design\b", r"\bturnover (number|frequency)\b",
        ],
        "acronyms": [],
    },
    "Asymmetric synthesis and catalysis": {
        "phrases": [
            r"\benantioselective(ly)?\b", r"\benantiospecific\b", r"\benantioconvergent\b",
            r"\benantio(enriched|pure|merically)\b", r"\bdiastereoselective(ly)?\b",
            r"\basymmetric (catalysis|synthes[ie]s|hydrogenation|reduction|oxidation|addition|"
            r"alkylation|allylation|arylation|cycli[sz]ation|epoxidation|dihydroxylation|"
            r"aldol|Mannich|Michael|cross[- ]couplings?|C[–—‐-]H|transfer hydrogenation|"
            r"hydrofunctionali[sz]ation|organocatalysis|induction)\b",
            r"\bchiral (catalysts?|ligands?|phosphoric acids?|amines?|Lewis acids?|auxiliar(y|ies)|"
            r"building blocks?|centers?|centres?|sulfoxides?|phosphines?)\b",
            r"\b(axially|planar|inherently) chiral\b", r"\batroposelective\b",
            r"\bkinetic resolution\b", r"\bdynamic kinetic resolution\b", r"\bdesymmetri[sz]ation\b",
            r"\bstereodivergent\b", r"\bstereoselective synthes", r"\bstereocontrol",
            r"\benantiomeric (excess|ratio)\b", r"\b\d{2}(\.\d)?\s?% ee\b", r"\b\d{2}:\d{1,2} er\b",
            r"\bchirality transfer\b", r"\bcentral[- ]to[- ]axial\b",
        ],
        "acronyms": [],
    },
    "Total synthesis and natural products": {
        "phrases": [
            r"\btotal synthes[ie]s\b", r"\bformal synthes[ie]s\b", r"\bnatural products?\b",
            r"\b(alkaloids?|terpenoids?|terpenes?|diterpenoids?|sesquiterpenoids?|"
            r"meroterpenoids?|polyketides?|macrolides?|steroids?|glycosides?)\b",
            r"\bbiosynthe(sis|tic)\b", r"\bbiomimetic (total )?synthes", r"\bbioinspired synthesis\b",
            r"\bisolat(ed|ion) (from|of)\b", r"\bsecondary metabolites?\b",
        ],
        "acronyms": [],
    },
    # ---------------- Other areas ----------------
    "Materials and polymers": {
        "phrases": [
            r"\bpolymers?\b", r"\bpolymeri[sz]ation\b",
            r"\b(porous|functional|2D|two-dimensional|energy|electrode|cathode|anode|optical|soft) materials?\b",
            r"\b(metal|covalent)[- ]organic frameworks?\b", r"\bnanoparticles?\b",
            r"\bnanosheets?\b", r"\bnanoclusters?\b", r"\bperovskites?\b", r"\bsemiconductors?\b",
            r"\b(light[- ]emitting|organic electronics|OLEDs?)\b", r"\bbatter(y|ies)\b",
            r"\belectrolytes?\b", r"\bsolar cells?\b", r"\bphotovoltaic", r"\bthin films?\b",
            r"\bhydrogels?\b", r"\bself[- ]assembl", r"\bsupramolecular\b",
        ],
        "acronyms": [r"\b(MOF|COF)s?\b"],
    },
    "Computational chemistry and AI": {
        "phrases": [
            r"\bdensity functional theory\b", r"\bcomputational\b", r"\bmolecular dynamics\b",
            r"\bmachine learning\b", r"\bdeep learning\b", r"\bartificial intelligence\b",
            r"\bneural networks?\b", r"\blarge language models?\b", r"\bin silico\b",
            r"\bdocking\b", r"\bquantum chemi", r"\bsimulations?\b", r"\bfree energy\b",
            r"\bgenerative (model|design)", r"\bvirtual screening\b",
        ],
        "acronyms": [r"\bDFT\b", r"\bML\b", r"\bAI\b", r"\bLLMs?\b"],
        "threshold": 3,   # abstract-only: many experimental papers mention DFT or docking
    },
    "Analytical and physical chemistry": {
        "phrases": [
            r"\bspectroscop", r"\bmass spectrometr", r"\bNMR\b", r"\bcrystallograph",
            r"\bkinetics?\b", r"\bmechanis(m|tic) (study|studies|insight)", r"\bthermodynamic",
            r"\bphotophysic", r"\bexcited[- ]state\b", r"\bultrafast\b", r"\bsingle[- ]molecule\b",
            r"\bmicroscop", r"\bchromatograph", r"\belectrochemical (analysis|sensing|sensors?)\b",
            r"\bsensors?\b", r"\bimaging\b",
        ],
        "acronyms": [r"\b(LC[–—‐-]?MS|HPLC|EPR|XPS|XRD|SAXS|cryo[–—‐-]?EM)\b"],
        "threshold": 4,   # abstract-only: most papers mention NMR or crystallography
    },
}

# ---------------------------------------------------------------------------
_RULES = {
    t: [re.compile(p, re.IGNORECASE) for p in cfg["phrases"]] +
       [re.compile(p) for p in cfg.get("acronyms", [])]
    for t, cfg in TOPICS.items()
}
THRESHOLD = 2   # default abstract score needed; a topic can set its own "threshold"


def threshold_for(topic: str) -> int:
    return TOPICS[topic].get("threshold", THRESHOLD)


def explain(title: str, abstract: str = "") -> dict:
    """{topic: (score, [matched words])} for every topic that matched anything."""
    title, abstract = title or "", abstract or ""
    out = {}
    for topic, rules in _RULES.items():
        score, hits = 0, []
        for rule in rules:
            m = rule.search(title)
            if m:
                score += 2
                hits.append(f"T:{m.group(0)}")
                continue
            m = rule.search(abstract)
            if m:
                score += 1
                hits.append(f"A:{m.group(0)}")
        if score:
            out[topic] = (score, hits)
    return out


def qualifies(topic: str, score: int, hits: list) -> bool:
    """A title match always qualifies; otherwise the score must reach the threshold."""
    return any(h.startswith("T:") for h in hits) or score >= threshold_for(topic)


def tag_topics(title: str, abstract: str = "") -> list:
    """Topics this article belongs to."""
    return [t for t, (s, h) in explain(title, abstract).items() if qualifies(t, s, h)]
