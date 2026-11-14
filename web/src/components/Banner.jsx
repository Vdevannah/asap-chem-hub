// Split banner, shown on every visit: a pine panel on the left (name and tagline) and an
// AI-generated still life on the right (flasks and an open journal showing penicillin G).
const BASE = import.meta.env.BASE_URL;   // "/" locally; keeps image paths right if the site moves

export default function Banner() {
  return (
    <section className="banner" aria-labelledby="banner-title">
      <div className="banner-panel">
        <h1 id="banner-title" className="banner-title">ASAP Chem Hub</h1>
        <p className="banner-tagline">The newest chemistry papers and patents, by topic. Updated every day.</p>
      </div>
      {/* Decorative (alt=""): the heading already names the site. Phones load the ~1100px version. */}
      <picture className="banner-photo">
        <source media="(max-width: 700px)" srcSet={`${BASE}banner-small.jpg`} />
        <img src={`${BASE}banner.jpg`} alt="" decoding="async" fetchPriority="high" />
      </picture>
    </section>
  );
}
