// Topic families: each family has one colour, used on chips and card tags.
// Topics not listed fall into "Other" (slate).
// `topics` is the flat order (used as is on the Patents tab, which has only the original topics).
// `subgroups` (optional) splits a family under small headings; the Articles tab sidebar and the
// About page show them. Every topic in `subgroups` must also be in `topics`.
export const FAMILIES = [
  {
    id: "synthesis",
    name: "Synthesis and catalysis",
    topics: [
      "Synthetic methods",
      "Skeletal editing",
      "Catalysis",
      "Transition metal catalysis",
      "Photoredox and photochemistry",
      "Electrosynthesis",
      "C–H functionalization",
      "Asymmetric synthesis and catalysis",
      "Total synthesis and natural products",
    ],
    subgroups: [
      { name: "Synthesis", topics: ["Synthetic methods", "Skeletal editing", "Total synthesis and natural products"] },
      {
        name: "Catalysis",
        topics: [
          "Catalysis",
          "Transition metal catalysis",
          "Photoredox and photochemistry",
          "Electrosynthesis",
          "C–H functionalization",
          "Asymmetric synthesis and catalysis",
        ],
      },
    ],
  },
  {
    id: "bio",
    name: "Medicinal and biological",
    topics: [
      "Medicinal chemistry",
      "Inhibitors",
      "Targeted protein degradation",
      "Chemical biology",
      "Antibody-drug conjugates",
      "Antibodies",
    ],
  },
  {
    id: "materials",
    name: "Materials and physical",
    topics: ["Materials and polymers", "OLED materials and devices", "Analytical and physical chemistry"],
  },
  { id: "computational", name: "Computational", topics: ["Computational chemistry and AI"] },
];

// Display labels inside sub-groups, where the stored name would read oddly. The stored name stays
// the same everywhere else (API, patents, card tags): "Catalysis" is the umbrella topic.
const SUBGROUP_LABELS = { Catalysis: "All catalysis" };

export function topicLabel(name, inSubgroup = false) {
  return (inSubgroup && SUBGROUP_LABELS[name]) || name;
}

const BY_NAME = {};
FAMILIES.forEach((f) => f.topics.forEach((t, i) => (BY_NAME[t] = { family: f.id, order: i })));

export function familyOf(topicName) {
  return BY_NAME[topicName]?.family || "computational";
}

const byOrder = (a, b) => (BY_NAME[a.name]?.order ?? 99) - (BY_NAME[b.name]?.order ?? 99);

// Group API topics ({topic_id, name}) by family, in the order above. With withSubgroups, a family
// that has sub-groups also gets `subgroups: [{name, items}]` (empty ones left out).
export function groupTopics(topics, withSubgroups = false) {
  return FAMILIES.map((f) => {
    const items = topics.filter((t) => familyOf(t.name) === f.id).sort(byOrder);
    const group = { ...f, items };
    if (withSubgroups && f.subgroups) {
      group.subgroups = f.subgroups
        .map((s) => ({ name: s.name, items: s.topics.map((n) => items.find((t) => t.name === n)).filter(Boolean) }))
        .filter((s) => s.items.length > 0);
    } else {
      delete group.subgroups;
    }
    return group;
  }).filter((g) => g.items.length > 0);
}
