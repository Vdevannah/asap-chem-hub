// Topic families: each family has one colour, used on chips and card tags.
// Topics not listed fall into "Other" (graphite).
export const FAMILIES = [
  {
    id: "synthesis",
    name: "Synthesis and catalysis",
    topics: [
      "Synthetic methods",
      "Catalysis",
      "Asymmetric synthesis and catalysis",
      "Total synthesis and natural products",
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

const BY_NAME = {};
FAMILIES.forEach((f) => f.topics.forEach((t, i) => (BY_NAME[t] = { family: f.id, order: i })));

export function familyOf(topicName) {
  return BY_NAME[topicName]?.family || "computational";
}

// Group API topics ({topic_id, name}) by family, in the order above.
export function groupTopics(topics) {
  return FAMILIES.map((f) => ({
    ...f,
    items: topics
      .filter((t) => familyOf(t.name) === f.id)
      .sort((a, b) => (BY_NAME[a.name]?.order ?? 99) - (BY_NAME[b.name]?.order ?? 99)),
  })).filter((g) => g.items.length > 0);
}
