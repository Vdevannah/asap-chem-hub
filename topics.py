"""
ASAP Chem Hub - research topic rules
====================================
Broad topics for browsing; specific terms (JAK2, Suzuki ...) are left to the
keyword search box. Eleven are shared with patents; five catalysis sub-topics
(Transition metal catalysis, Photoredox and photochemistry, Electrosynthesis,
C–H functionalization, Skeletal editing) are articles_only.

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
* Optional per topic (used by the catalysis sub-topics):
  - 'weak': rules that count only when the text also has synthesis context
    ('context', default ORGANIC_CONTEXT), e.g. "photocatalytic" or "visible light";
  - 'exclude': energy / materials / device terms. One in the title drops the topic;
    so do 3+ in the abstract, or 2 unless a main (not weak) rule matched the title;
  - 'articles_only': never given to patents (tag_topics(..., patents=True)).

To tune: edit the lists below, then run  python tune_topics.py
"""

import html
import re

D = r"[–—‐-]"  # any dash used by publishers
D2 = r"[–—‐‑−─-]"  # ... plus non-breaking hyphen, minus sign (C−H) and box-drawing dash (Angew: C─H)

# shared building blocks for the catalysis sub-topics
_METALS = r"Pd|Ni|Cu|Rh|Ir|Ru|Co|Fe|Au|Ag"
_METAL_NAMES = r"palladium|nickel|copper|rhodium|iridium|ruthenium|cobalt|iron|gold|silver"
_OX = r"(\((0|I|II|III|IV|V|I{1,3})\))?"                      # Pd(II), Ni(0)
_SP = r"(?:\(\s?sp\s?[23]?\s?\)|sp[23]?)"                         # (sp3), ( sp 3 ) in older titles, sp2
_CH = rf"C{_SP}?{D2}H"                                           # C–H, C-H, C−H, C─H, C(sp3)–H, Csp2–H
_METAL_WORD = rf"\b({_METALS}|{_METAL_NAMES}){_OX}"
# Organic-synthesis context: a 'weak' rule only counts when one of these is in the title or abstract
ORGANIC_CONTEXT = [
    r"\bsubstrate scope\b", r"\bfunctional[- ]group (tolerance|compatibility)\b", r"\bgram[- ]scale\b",
    r"\blate[- ]stage\b", r"\bbuilding blocks?\b", r"\bradicals?\b", r"\b(synthesis|construction|preparation) of\b",
    r"\bcross[- ]coupling", r"\b(cyclization|annulation|cycloaddition|dearomati[sz]ation)s?\b",
    r"\b(\w*functionali[sz]ation|alkylation|arylation|amination|amidation|carboxylation|fluorination|"
    r"trifluoromethylation|borylation|silylation|hydro\w+ation|oxidation of (alcohols|amines|alkenes))\b",
    r"\b(alkenes?|alkynes?|olefins?|arenes?|heteroarenes?|ketones?|aldehydes?|amines?|amides?|alcohols?|"
    r"carboxylic acids?|esters?|indoles?|pyridines?|quinolines?|sulfonamides?|sulfones?|nitriles?|imines?|"
    r"enones?|(aryl|alkyl|vinyl) halides?|boronic acids?|silanes?|phenols?|anilines?|thiols?|ethers?)\b",
    r"\b(good|high|excellent|moderate)( to (good|high|excellent))? yields?\b",
]
# Stricter: the text must describe making molecules (reaction words, not just substrate names)
SYNTH_CONTEXT = [
    r"\bsubstrate scope\b", r"\bfunctional[- ]group (tolerance|compatibility)\b", r"\bgram[- ]scale\b",
    r"\blate[- ]stage\b", r"\bbuilding blocks?\b", r"\b(synthesis|construction|preparation) of\b",
    r"\b(access to|synthesi[sz]ed?)\b", r"\bcross[- ]coupling",
    r"\b(cyclization|annulation|cycloaddition|dearomati[sz]ation|rearrangement)s?\b",
    r"\b(\w*functionali[sz]ation|alkylation|arylation|amination|amidation|carboxylation|fluorination|"
    r"trifluoromethylation|borylation|silylation|hydro\w+ation|sulfonylation|acylation|halogenation)\b",
    r"\b(good|high|excellent|moderate)( to (good|high|excellent))? yields?\b",
]
# Energy, materials and device work - not what the catalysis sub-topics are for
# Skeletal editing: ring expansion, atom insertion ... count only next to one of these
EDITING_CONTEXT = [r"\bskeletal\b", r"\bediting\b", rf"\bsingle{D2}?\s?atom\b", r"\bscaffold hopping\b",
                   r"\batom swaps?\b", r"\b(nitrogen|carbon|oxygen) atom insertion"]
_CO2 = r"CO\s?2"                                                # "CO2", or "CO 2" in older stored titles
ENERGY_MATERIALS = [
    r"(?-i:\b(HER|OER|ORR|NRR|CO2RR|NO3RR|UOR)\b)", rf"\b(hydrogen|oxygen|chlorine){D2}?\s?(evolution|reduction)\b",
    rf"\b(overall )?water{D2}?\s?(splitting|electrolysis|oxidation)\b", r"\bfuel cells?\b", r"\bbatter(y|ies)\b",
    rf"\b(lithium|sodium|potassium|zinc|magnesium|Li|Na|K|Zn|Mg){D2}?\s?(ion|metal|sulfur|air|oxygen)\b",
    r"\bsupercapacitors?\b", rf"\b{_CO2}\s(electrochemical\s|electro|photo)?(reduction|electroreduction)\b",
    rf"\b(electro|photo)?reduction of {_CO2}\b", rf"\b(convert(s|ing)?|conversion of) {_CO2}\b",
    rf"\b{_CO2}{D2}?\s?to{D2}?\s?(CO|fuels?|methanol|ethanol|ethylene|formate|C2\+?|multi{D2}?carbon)\b",
    rf"\b(nitrate|nitrite|nitrogen|N2){D2}?\s?(reduction|electroreduction|to{D2}ammonia)\b",
    r"\bammonia (synthesis|production|electrosynthesis)\b",
    r"\bH\s?2\s?O\s?2 (production|synthesis|generation|electrosynthesis)\b",
    rf"\bsingle{D2}?\s?atom (catalysts?|sites?|alloys?)\b", r"\bnanoparticles?\b", r"\bnanosheets?\b",
    r"\bnanoclusters?\b", r"\bheterojunctions?\b", r"\bheterostructures?\b", r"\belectrocatalysts?\b",
    rf"\bsolar{D2}?\s?(cells?|fuels?|driven|energy)\b", r"\bphotovoltaic", r"\bphotodetectors?\b",
    r"\bperovskites?\b", rf"\benergy (harvesting|storage)\b",
    r"\b(pollutants?|dyes?|antibiotics?|tetracycline|methylene blue|rhodamine B) (degradation|removal)\b",
    r"\bdegradation of (organic )?(pollutants?|dyes?|antibiotics?)\b",
    # framework / semiconductor materials
    rf"\b(covalent|metal){D2}organic frameworks?\b", r"(?-i:\b(COF|MOF)s?\b)", r"\bUiO{D2}?\d+",
    r"\bcarbon nitride\b", rf"\bg{D2}C3N4\b", r"\bTiO\s?2\b", r"\bsemiconductors?\b", r"\bcharge separation\b",
    rf"\bband{D2}?\s?gaps?\b", r"\bmethane\b", r"\bPrussian blue\b",
    rf"\b(layered double|metal{D2}|oxy)hydroxides?\b",
]
# heterogeneous (supported metal) catalysis and metal complexes as drugs: not homogeneous TM catalysis
HETEROGENEOUS_BIO = [
    rf"\b(oxide{D2})?supported\b", r"\bsupport effects?\b", rf"\bdeposition{D2}precipitation\b",
    r"\bsyngas\b", rf"\bwater{D2}?\s?gas shift\b", r"\bCO oxidation\b", r"\bzeolites?\b",
    r"\bover (\w+\s){0,3}catalysts?\b", r"\bcancer cells?\b", r"\bcytotoxic", r"\banti(cancer|tumou?r|proliferative)\b",
    r"\b(cuproptosis|ferroptosis|apoptosis)\b", r"\bmetallodrugs?\b", rf"\bmain{D2}?\s?group\b",
]
PHOTO_DEVICES = [rf"\blight{D2}?\s?emitting\b", r"(?-i:\bOLEDs?\b)", r"\bphotothermal\b", r"\bphotodynamic\b",
                 r"\bphototherap", r"\bphotoacoustic\b", r"\bscintillat", r"\bfluorescent probes?\b",
                 r"\b(bio)?imaging\b", r"\bmolecular (machines?|motors?|switch(es)?)\b", r"\bphotoswitch",
                 rf"\bsolid{D2}state NMR\b", r"\bmatrix isolation\b", r"\b(co)?polymeri[sz]ation\b",
                 r"\bcopolymers?\b"]
PHOTO_PHYSICS = [r"\bultrafast\b", r"\bphotoluminescen", r"\bphosphorescen", r"\btransient absorption\b",
                 r"\bfemtosecond\b", rf"\bpush{D2}pull\b", r"\bintramolecular charge transfer\b"]
ELECTRO_ANALYSIS = [r"\b(bio)?sensors?\b", r"\belectrochemical (detection|sensing|biosensing|determination|properties|behaviou?r)\b",
                    r"\bvoltammetric (detection|determination)\b", r"\bthin films?\b", r"\belectropolymeri",
                    r"\bPFAS\b", r"\bionic liquids?\b", r"\bPEDOT\b", r"\bcarbon materials?\b",
                    r"\bmetal oxides?\b", r"\bpolyoxo(metalate|vanadate|tungstate|molybdate)s?\b",
                    r"\bzeolites?\b", r"(?-i:\bQCM\b)"]

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
    # ---------------- Catalysis sub-areas (articles only) ----------------
    # Each also has 'weak' rules (count only next to organic-synthesis context) and 'exclude'
    # rules (energy / materials / device work). See explain() and qualifies() below.
    "Transition metal catalysis": {
        "phrases": [
            rf"\b({_METALS}|{_METAL_NAMES}){_OX}(\s|{D2})?(catalyz|catalys)(ed|es|ing)\b",   # Pd-catalyzed
            rf"\b({_METALS}|{_METAL_NAMES}){_OX}(\s|{D2})?(hydride\s)?catalysis\b",          # nickel catalysis
            rf"\btransition{D2}?\s?metal{D2}?\s?(catalyz|catalys|catalysts?\b)",
            rf"(?<!non{D2})(?<!non\s)\bmetal{D2}(catalyz|catalys)ed\b",
            rf"\bcross{D2}?\s?(electrophile\s)?couplings?\b",
            rf"\b(Suzuki|Buchwald|Negishi|Stille|Sonogashira|Mizoroki|Kumada|Hiyama|Catellani|Ullmann|"
            rf"Chan{D2}Lam|Tsuji{D2}Trost|Liebeskind)\b", r"\bHeck (reaction|coupling|arylation)",
            r"\bmetallaphotoredox\b", r"\borganometallic catalysis\b",
            rf"\bcatalyz(ed|es) by (an?\s|the\s)?(\w+{D2}?\s?){{0,2}}{_METAL_WORD}",          # catalyzed by an Ir complex
            rf"{_METAL_WORD}\s(complex|catalyst){D2}catalyz",                                  # Cu(II) Complex-Catalyzes
            rf"\bcatalysis (of|with|by) (\w+\s){{0,2}}{_METAL_WORD}",                           # Catalysis of Rh Complexes
        ],
        "acronyms": [r"\bPd\(OAc\)2", r"\bPd2\(dba\)3", r"\bNi\(cod\)2", r"\bCp\*(Rh|Ir|Co)\b"],
        "weak": [
            rf"{_METAL_WORD}(\s|{D2})?(pre)?catalysts?\b",                                      # nickel catalyst
            # mechanism words count only when a metal is named somewhere
            (r"\boxidative addition\b", [_METAL_WORD]), (r"\breductive elimination\b", [_METAL_WORD]),
            (r"\bmigratory insertion\b", [_METAL_WORD]), (r"\btransmetal+ation\b", [_METAL_WORD]),
            (rf"\bβ{D2}?(hydride|H|carbon) elimination\b", [_METAL_WORD]), (rf"\bchain{D2}walking\b", [_METAL_WORD]),
        ],
        "exclude": ENERGY_MATERIALS + HETEROGENEOUS_BIO,
        "threshold": 3,   # abstract-only: many papers mention "made by Suzuki coupling" in passing
        "articles_only": True,
    },
    "Photoredox and photochemistry": {
        "phrases": [
            r"\bphotoredox\b", r"\bmetallaphotoredox\b", r"\bphotoenzym", r"\bdecatungstate\b",
            rf"\benergy{D2}?\s?transfer (catalysis|photocatalysis|sensiti[sz]ation)\b",
            rf"\b(EDA|electron donor{D2}acceptor) complex", r"\bacridinium\b", r"\beosin Y\b",
            r"\bphotocycloaddition", rf"\bNorrish\b", rf"\bPatern[oò]{D2}B[uü]chi\b",
            r"\bphoto(chemical\s)?(deracemi[sz]ation|decarboxylation|cyclization|rearrangement)\b",
        ],
        "acronyms": [r"\bEnT\b", r"\b4CzIPN\b", r"\bIr\(ppy\)3", r"\bRu\(bpy\)3", r"\bTBADT\b"],
        "context": SYNTH_CONTEXT,
        "weak": [   # one rule per idea, so overlapping words don't add up to 2 points on their own
            r"\bphotocataly(sis|tic|tically|sts?)\b", r"\bphotochemi(cal|cally|stry)\b",
            rf"\bvisible{D2}?\s?light\b|\blight{D2}(driven|mediated|induced|promoted|enabled)\b",
            rf"\b(triplet\s)?energy{D2}?\s?transfer\b|\bexcited{D2}?\s?states?\b|\bphotoinduced\b|\bphotoexcit",
        ],
        "exclude": ENERGY_MATERIALS + PHOTO_DEVICES + PHOTO_PHYSICS,
        "articles_only": True,
    },
    "Electrosynthesis": {
        "phrases": [
            rf"\belectro{D2}?organic\b", r"\b(organic|preparative|synthetic) electro(chemistry|synthesis)\b",
            rf"\belectrochemical(ly)?{D2}?\s?(cross{D2}?coupling|coupling|functionali[sz]ation|C{D2}H|amination|"
            r"carboxylation|fluorination|halogenation|dehydrogenative|annulation|cyclization|deconstructive|"
            r"dearomati[sz]ation|difunctionali[sz]ation|alkylation|arylation|sulfonylation|selenylation|thiolation)\b",
            r"\bpaired electrolysis\b", rf"\belectro{D2}?carboxylation\b", r"\belectro(reductive|oxidative)\b",
            r"\belectrophotocataly", r"\bundivided cell\b", rf"\bconstant{D2}?\s?current electrolysis\b",
            rf"\banodic (oxidation|coupling|C{D2}H|dehydrogenat|fluorination|cyclization|amination|functionali)",
            r"\bcathodic (reduction|coupling|hydrogenation|dehalogenation|carboxylation|functionali)",
            r"\b(Shono|Kolbe) (oxidation|electrolysis|coupling|reaction)\b",
        ],
        "acronyms": [],
        "context": SYNTH_CONTEXT,
        "weak": [
            r"\belectrosynthe(sis|ses|tic)\b",
            rf"\belectrochemical(ly)?{D2}?\s?(enabled|driven|promoted|mediated|induced|synthesis|oxidation|"
            r"reduction|oxidative|reductive|hydrogenation|transformations?|strategy|method|approach|protocol)\b",
            r"\belectrolysis\b|\belectrocatalytic(ally)?\b|\belectrochemical(ly)?\b",   # one rule: same idea
        ],
        "exclude": ENERGY_MATERIALS + ELECTRO_ANALYSIS,
        "articles_only": True,
    },
    "C–H functionalization": {
        "phrases": [
            rf"\b{_CH}(\s*bonds?)?\s*((?!dissociation)\w*ations?|\w*i[sz]ations?|insertions?|cleavage|abstraction|"
            r"couplings?|annulations?)\b",
            rf"\bC{_SP}{D2}H\b",                                                     # C(sp3)–H, Csp2–H
            rf"\b{_CH}/[CNOS]{D2}H\b",                                                # C–H/N–H coupling
            rf"\blate{D2}?\s?stage (C{D2}H\s)?functionali[sz]ation\b",
            rf"\b(transient\s)?directing{D2}?\s?groups?\b", rf"\bcross{D2}?\s?dehydrogenative coupling\b",
            r"\bCatellani\b", rf"\bHofmann{D2}L[oö]ffler", rf"\bborylation of (\w+\s)?C{D2}H",
        ],
        "acronyms": [rf"\b1,\s?[56]{D2}HAT\b"],                                  # 1,5-HAT, "1, 5-HAT"
        # HAT counts only when the text also mentions a C–H bond (one rule: same idea)
        "weak": [(rf"\bhydrogen{D2}?\s?atom transfer\b|(?-i:\bHAT\b(?!\())", [rf"\b{_CH}"])],
        "exclude": [r"\bhistones?\b", r"\bacetyltransferases?\b", rf"\bC{D2}H\s*(···|\.\.\.|…|π)"],
        "articles_only": True,
    },
    "Skeletal editing": {
        "phrases": [
            r"\bskeletal editing\b",
            r"\b(molecular|single[- ]atom|ring|core|scaffold|skeleton|framework|aromatic|heteroaromatic|"
            r"heteroarene|arene|azine|pyridine) editing\b",
            rf"\bsingle{D2}?\s?atom (insertion|deletion|excision)s?\b", r"\batom (swap|transmutation)s?\b",
            rf"\b(nitrogen|carbon|oxygen|sulfur|[CNOS]){D2}?\s?(deletion|excision)\b",
            rf"\b(carbon|nitrogen|oxygen|sulfur|CH|[CNOSB]){D2}to{D2}(carbon|nitrogen|oxygen|sulfur|CH|[CNOSB])\b"
            r"( atom)? (swap|transmutation|exchange|replacement|switch|transposition)",
            rf"\bCiamician{D2}Dennstedt\b", r"\b(skeletal|scaffold) (remodel+ing|reshuffling)\b",
        ],
        "acronyms": [],
        "weak": [
            rf"\bskeletal (rearrangements?|reorgani[sz]ation)\b",
            # common reactions that are skeletal editing only in an editing context
            (rf"\bring{D2}?\s?(expansions?|enlargements?|homologation)\b", EDITING_CONTEXT),
            (rf"\bring{D2}?\s?contractions?\b", EDITING_CONTEXT),
            (r"\batom (deletion|excision)s?\b", EDITING_CONTEXT),
            (r"\batom insertions?\b", EDITING_CONTEXT),
            (r"\bscaffold hopping\b", [r"\bediting\b", r"\batom (insertion|deletion|swap)",
                                       rf"\bring{D2}?\s?(expansion|contraction)"]),
        ],
        "exclude": [rf"\bring{D2}?\s?(expansion|opening) (metathesis )?polymeri"] + ENERGY_MATERIALS,
        "articles_only": True,
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
def _compile(cfg):
    """rules: [(regex, context)] - context None = always counts, else a list of regexes of which
    one must be in the title or abstract (weak rules)."""
    rules = [(re.compile(p, re.IGNORECASE), None) for p in cfg["phrases"]]
    rules += [(re.compile(p), None) for p in cfg.get("acronyms", [])]
    default_ctx = [re.compile(p, re.IGNORECASE) for p in cfg.get("context", ORGANIC_CONTEXT)]  # for 'weak' rules
    for w in cfg.get("weak", []):
        pattern, ctx = (w, default_ctx) if isinstance(w, str) else (w[0], [re.compile(p, re.IGNORECASE) for p in w[1]])
        rules.append((re.compile(pattern, re.IGNORECASE), ctx))
    exclude = [re.compile(p, re.IGNORECASE) for p in cfg.get("exclude", [])]
    return rules, exclude


_RULES = {t: _compile(cfg) for t, cfg in TOPICS.items()}
_TITLE_TAG_RE = re.compile(r"</?(?:sub|sup|i)>")
THRESHOLD = 2   # default abstract score needed; a topic can set its own "threshold"


def threshold_for(topic: str) -> int:
    return TOPICS[topic].get("threshold", THRESHOLD)


def explain(title: str, abstract: str = "") -> dict:
    """{topic: (score, [matched words])} for every topic that matched anything."""
    # stored titles keep <sub>/<sup>/<i> (see poc_feeds.clean_title): match on the plain text
    title, abstract = html.unescape(_TITLE_TAG_RE.sub("", title or "")), abstract or ""
    text = f"{title} {abstract}"
    has_context = {}                                  # id(context list) -> bool, checked once per text

    def in_context(context):
        key = id(context)
        if key not in has_context:
            has_context[key] = any(c.search(text) for c in context)
        return has_context[key]

    out = {}
    for topic, (rules, exclude) in _RULES.items():
        score, hits = 0, []
        for rule, context in rules:
            if context is not None and not in_context(context):
                continue                              # weak rule without synthesis context
            tag = "W" if context is not None else ""
            m = rule.search(title)
            if m:
                score += 2
                hits.append(f"T{tag}:{m.group(0)}")
                continue
            m = rule.search(abstract)
            if m:
                score += 1
                hits.append(f"A{tag}:{m.group(0)}")
        if score:
            for rule in exclude:                      # recorded, not scored: see qualifies()
                m = rule.search(title)
                if m:
                    hits.append(f"XT:{m.group(0)}")
                elif rule.search(abstract):
                    hits.append(f"XA:{rule.search(abstract).group(0)}")
            out[topic] = (score, hits)
    return out


def qualifies(topic: str, score: int, hits: list) -> bool:
    """A title match always qualifies; otherwise the score must reach the threshold.
    Exclusions (energy, materials, devices...) drop the topic when an exclude term is in the
    title; when 3+ different exclude terms are in the abstract; or when 2 are, unless the title
    matched one of the topic's main (not 'weak') rules."""
    title_hit = any(h.startswith("T") for h in hits)
    strong_title_hit = any(h.startswith("T:") for h in hits)
    excluded = [h for h in hits if h.startswith("X")]
    if any(h.startswith("XT:") for h in excluded) or len(excluded) >= 3:
        return False
    if len(excluded) >= 2 and not strong_title_hit:
        return False
    return title_hit or score >= threshold_for(topic)


def tag_topics(title: str, abstract: str = "", patents: bool = False) -> list:
    """Topics this article (or, with patents=True, patent) belongs to.
    Article-only topics are never given to patents."""
    return [t for t, (s, h) in explain(title, abstract).items()
            if qualifies(t, s, h) and not (patents and TOPICS[t].get("articles_only"))]
